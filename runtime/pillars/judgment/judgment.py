#!/usr/bin/env python3
"""
Judgment Pillar — Warden 内 判断 Claude（Anthropic SDK 直叩き、Phase 5a-3、Issue #38）。

ADR-0010 / ADR-0011 / ADR-0013 で確定した「Warden は機能の集合体、その判断機能は
SDK 直叩き（対話不要・決定論的）」を最小実装する。

責務（Phase 5a-3 スコープ）:
- Observation v0.1 (#42) の snapshot JSON を入力に取る
- 各 Mind に対して「次にやるべき action」を判定する
- 結果を JSON で返す

スコープ外（後続フェーズ）:
- 複数 Judgment Claude の並走（最初は 1 種類）
- 判断結果のキャッシュ
- ループ常駐（Warden 機能から呼ばれて動く）

責任分離:
- 入力 fetch (snapshot を読む) は呼び出し側
- 出力 dispatch (action を実行する) は呼び出し側
- 本モジュールは「観測 → 判断」のみを担当（純粋関数に近い）

エラー耐性:
- API key 不在 → AnthropicNotConfigured で fallback 可能に
- API 失敗 (rate limit / network) → 例外を raise（呼び出し側が捕まえて rule-based に倒す）
- JSON パース失敗 → JudgmentParseError、こちらも rule-based fallback で対処可能

依存:
- anthropic >= 0.40.0 (requirements.txt 参照)
- 他 Pillar には import しない（純粋な判断機能、結合度を低く保つ）
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.0  # 決定論的、ADR-0010 §5 と整合
DEFAULT_TIMEOUT_S = 30.0

# Mind に対する判定の語彙。ADR-0013 §3 の対処グラデーションと整合する。
# 本 Phase ではまだ「実行」は呼び出し側に委ねており、判定のみ。
VALID_ACTIONS = frozenset({
    "ok",            # 問題なし、何もしない
    "monitor",       # 経過観察、次回 cycle で再判定
    "investigate",   # 何か変、詳細観測が必要（人間判断対象）
    "notify-human",  # 致命的、ADR-0012 責務 5 ルート
})


class AnthropicNotConfigured(RuntimeError):
    """ANTHROPIC_API_KEY が設定されておらず SDK を初期化できない。

    呼び出し側はこの例外を catch して rule-based fallback に倒すことを推奨。
    """


class JudgmentParseError(ValueError):
    """Claude の応答が期待する JSON 形式でない / VALID_ACTIONS 外の action を含む。"""


@dataclass(frozen=True)
class MindJudgment:
    """1 Mind に対する判定結果。"""

    mind_name: str
    action: str  # VALID_ACTIONS のいずれか
    reason: str


def _build_system_prompt() -> str:
    """Judgment Claude の役割と語彙を確定させる system prompt。

    語彙が VALID_ACTIONS と一致しないと parse error になるので、ここに固定する。
    """
    return """\
You are the Judgment Pillar of ai-org-os Warden. You receive an observation snapshot
of Minds (autonomous LLM agents) running inside a Realm and decide one action per Mind.

You MUST respond with a single JSON array, no prose, no markdown fences. Each element
must be an object with exactly these keys:
  - "mind_name": string, must match the input
  - "action": one of "ok", "monitor", "investigate", "notify-human"
  - "reason": short string, why you chose that action (max 200 chars)

Action vocabulary (ordered by escalation):
  - "ok": Mind looks healthy, no attention needed
  - "monitor": Looks fine but watch next cycle (mild stale, low unread count)
  - "investigate": Something is off — needs deeper observation (e.g., long stale + unread,
                   abnormal Dispatch pattern). A human or Warden should look.
  - "notify-human": Critical — failsafe path (ADR-0012 responsibility 5). Use sparingly.

Be decisive. Do not output explanations outside the JSON. If input is empty, return [].
"""


def _build_user_prompt(snapshot: dict) -> str:
    """snapshot dict を Claude が読みやすい形に整形する。

    snapshot は Observation Pillar v0.1 の write_snapshot 出力フォーマット
    (`{generated_at, snapshot_id, minds: [...]}`)。
    """
    minds = snapshot.get("minds", [])
    return (
        "Snapshot to judge:\n\n"
        f"{json.dumps(snapshot, indent=2, ensure_ascii=False)}\n\n"
        f"Return one judgment per Mind ({len(minds)} total)."
    )


def _strip_markdown_fence(text: str) -> str:
    r"""先頭・末尾の ``` フェンスを行単位で剥がす。

    self-review fix (#65): 旧実装は `raw.strip("\`")` だったが、これは文字単位なので
    JSON 本文中の backtick (reason フィールド内の `\`grep\`` 等) も巻き込んで壊す。
    行単位なら本文を傷つけずに済む。
    """
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].rstrip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_response(text: str, expected_names: list[str]) -> list[MindJudgment]:
    """Claude の応答を MindJudgment のリストに変換する。

    フォーマット違反は JudgmentParseError で raise。debug のため raw 先頭 500 文字を
    例外メッセージに含める。
    """
    raw = _strip_markdown_fence(text.strip())
    # raw_snippet は debug 用に例外に乗せるための短縮版。
    raw_snippet = raw[:500] + ("..." if len(raw) > 500 else "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JudgmentParseError(
            f"response is not valid JSON: {exc}\nraw: {raw_snippet}"
        ) from exc

    if not isinstance(parsed, list):
        raise JudgmentParseError(
            f"expected JSON array at top level, got {type(parsed).__name__}\nraw: {raw_snippet}"
        )

    # self-review fix (#65): expected_names も dedup + truthy filter する。
    # Claude が duplicate / 空文字を返した場合の防御として set 比較を確実にする。
    expected_set = {n for n in expected_names if n}

    result: list[MindJudgment] = []
    seen: set[str] = set()
    for i, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            raise JudgmentParseError(f"entry {i} is not an object\nraw: {raw_snippet}")
        for key in ("mind_name", "action", "reason"):
            if key not in entry:
                raise JudgmentParseError(
                    f"entry {i} missing key '{key}'\nraw: {raw_snippet}"
                )
        mind_name = str(entry["mind_name"])
        if not mind_name:
            raise JudgmentParseError(f"entry {i} has empty mind_name\nraw: {raw_snippet}")
        if entry["action"] not in VALID_ACTIONS:
            raise JudgmentParseError(
                f"entry {i} has invalid action '{entry['action']}' "
                f"(allowed: {sorted(VALID_ACTIONS)})\nraw: {raw_snippet}"
            )
        if mind_name in seen:
            raise JudgmentParseError(
                f"entry {i} has duplicate mind_name '{mind_name}'\nraw: {raw_snippet}"
            )
        result.append(
            MindJudgment(
                mind_name=mind_name,
                action=str(entry["action"]),
                reason=str(entry["reason"])[:200],
            )
        )
        seen.add(mind_name)

    # 期待された Mind 名が出力に含まれていない場合は warning ではなく fail（呼び出し側で fallback）。
    missing = expected_set - seen
    if missing:
        raise JudgmentParseError(
            f"missing judgments for: {sorted(missing)}\nraw: {raw_snippet}"
        )

    return result


def make_client(api_key: str | None = None) -> Any:
    """Anthropic SDK Client を初期化。

    api_key=None なら ANTHROPIC_API_KEY 環境変数を読む。
    どちらも無ければ AnthropicNotConfigured を raise。

    SDK import を遅延させて、judgment.py の他関数（テスト可能な純粋関数）を
    anthropic 未インストール環境からも import できるようにする。
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise AnthropicNotConfigured(
            "ANTHROPIC_API_KEY is not set. Judgment Pillar requires an API key "
            "(human responsibility per ADR-0012 §2 responsibility 3)."
        )
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AnthropicNotConfigured(
            "anthropic SDK is not installed. Run "
            "`pip install -r runtime/pillars/judgment/requirements.txt`."
        ) from exc
    return anthropic.Anthropic(api_key=key, timeout=DEFAULT_TIMEOUT_S)


def judge_snapshot(
    snapshot: dict,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> list[MindJudgment]:
    """Observation snapshot を Claude に渡して各 Mind の action を判定する。

    引数:
        snapshot: Observation Pillar v0.1 形式の dict
        client: Anthropic Client。None なら make_client() で初期化
        model / max_tokens / temperature: SDK 呼び出しパラメータ

    戻り値:
        各 Mind の MindJudgment のリスト。snapshot.minds の順序とは限らない
        ことに注意（mind_name で照合すること）。

    Mind が 0 件の snapshot は空リストを返す（SDK 呼び出しせず短絡）。

    例外:
        AnthropicNotConfigured: API key / SDK 不足
        JudgmentParseError: 応答が期待する形式でない
        anthropic.APIError 等: API 呼び出し失敗（呼び出し側で fallback を）
    """
    minds = snapshot.get("minds", [])
    if not minds:
        return []

    # self-review fix (#65): 空文字 / None の mind_name を弾く。`m.get` は欠落で None を返す。
    expected_names = [str(m["mind_name"]) for m in minds if m.get("mind_name")]

    if client is None:
        client = make_client()

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=_build_system_prompt(),
        messages=[{"role": "user", "content": _build_user_prompt(snapshot)}],
    )

    # SDK の Message オブジェクトから text content を取り出す。
    # content は list[ContentBlock]、最初の text block を使う。
    text_parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text_parts.append(getattr(block, "text", ""))
    if not text_parts:
        raise JudgmentParseError("response contained no text content")

    return _parse_response("".join(text_parts), expected_names)


if __name__ == "__main__":
    # CLI: stdin から snapshot JSON を読んで stdout に judgments を出す。
    # 主に動作確認用。本番の呼び出し側は judge_snapshot を直接 import する。
    import sys

    snapshot = json.load(sys.stdin)
    judgments = judge_snapshot(snapshot)
    print(json.dumps(
        [{"mind_name": j.mind_name, "action": j.action, "reason": j.reason} for j in judgments],
        indent=2,
        ensure_ascii=False,
    ))
