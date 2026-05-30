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
# Phase 5e Step A までは観察寄り (passive) のみ。Step B で
# `dispatch-prompt` を追加: Judgment が判断した結果として Mind に
# 直接 prompt を投げる active action (= Warden が actuator として
# Mind に介入する最初の経路、ADR-0010 §5 の「無制約観測」を超えて
# 「観察→判断→動かす」のループを閉じる最初の一歩)。
VALID_ACTIONS = frozenset({
    "ok",            # 問題なし、何もしない
    "monitor",       # 経過観察、次回 cycle で再判定
    "investigate",   # 何か変、詳細観測が必要（人間判断対象）
    "dispatch-prompt",  # Step B: Mind に prompt を投げる (Warden actuator)
    "notify-human",  # 致命的、ADR-0012 責務 5 ルート
})

# dispatch-prompt の body 上限。LLM が暴走して大量 prompt を作らない安全弁。
MAX_DISPATCH_BODY_LEN = 1000
MAX_DISPATCH_TOPIC_LEN = 100

# dispatch-prompt 時の sender 識別子。固定 (= LLM が偽装できない)。
# storage._VALID_NAME_RE: [A-Za-z0-9._-]{1,64} に match。
WARDEN_SENDER_NAME = "warden"


class AnthropicNotConfigured(RuntimeError):
    """ANTHROPIC_API_KEY が設定されておらず SDK を初期化できない。

    呼び出し側はこの例外を catch して rule-based fallback に倒すことを推奨。
    """


class JudgmentParseError(ValueError):
    """Claude の応答が期待する JSON 形式でない / VALID_ACTIONS 外の action を含む。"""


@dataclass(frozen=True)
class MindJudgment:
    """1 Mind に対する判定結果。

    Phase 5e Step B (#109 続編): action="dispatch-prompt" のとき、optional
    `dispatch_topic` / `dispatch_body` を持つ。これらは Conductor が
    send_dispatch する内容で、Warden actuator の最初の経路。
    他 action では None (= 既存挙動と完全互換、副作用なし)。
    """

    mind_name: str
    action: str  # VALID_ACTIONS のいずれか
    reason: str
    dispatch_topic: str | None = None
    dispatch_body: str | None = None


def _build_system_prompt() -> str:
    """Judgment Claude の役割と語彙を確定させる system prompt。

    語彙が VALID_ACTIONS と一致しないと parse error になるので、ここに固定する。

    Phase 5e (#108 系 / Observation v1.0 統合): 入力に anomaly / flow / resource
    が含まれる場合、それらも判断材料に使うよう明示する。`schema_version: "1.0"`
    が `--for-warden` 互換、v0.1 snapshot は基本フィールドだけが含まれる。
    """
    return """\
You are the Judgment Pillar of ai-org-os Warden. You receive an observation report
of Minds (autonomous LLM agents) running inside a Realm and decide one action per Mind.

The report MAY include any of these sections (use what is present, ignore what is not):
  - "minds":         status snapshot per Mind (always present; primary signal)
  - "flow":          dispatch flow edges (from_mind -> to_mind, count, first_at, last_at)
                     use to spot communication patterns: silent Minds, broken pairs, loops
  - "resource":      per-Mind mindspace size + conduit-storage usage
                     use to spot bloat, runaway growth
  - "anomaly":       warning/info signals (W1-W3 / I1-I2)
                     if W2/W3 are present, treat as immediate concern (likely investigate)
                     if I1/I2 are present, treat as soft signal (monitor or investigate)
  - "warden_inbox":  replies FROM Minds TO Warden (you) for previous dispatch-prompts
                     each entry has from / topic / body / dispatched_at / msg_id
                     use to update your mental model:
                       - acknowledgement of completed work → ok / monitor
                       - request for clarification         → dispatch-prompt (clarify)
                       - report of a problem               → investigate / notify-human
                       - push-back on previous direction   → reconsider, possibly dispatch-prompt
                     do NOT include these replies' authors in the JSON output unless
                     they also appear under "minds" — judgments are per-Mind, not per-reply

You MUST respond with a single JSON array, no prose, no markdown fences. Each element
must be an object with these keys:
  - "mind_name": string, must match a mind from input "minds"
  - "action": one of "ok", "monitor", "investigate", "dispatch-prompt", "notify-human"
  - "reason": short string, why you chose that action (max 200 chars).
              Cite the signal you relied on (e.g., "W3 orphan kind", "no recent inbound")

If action is "dispatch-prompt", you MUST also include:
  - "dispatch_topic": short subject line (max 100 chars)
  - "dispatch_body":  the prompt message body (max 1000 chars)
For other actions, omit these fields (or leave them null).

Action vocabulary (ordered by escalation):
  - "ok": Mind looks healthy, no attention needed
  - "monitor": Looks fine but watch next cycle (mild stale, low unread, I1/I2 signals)
  - "investigate": Something is off — needs deeper observation
                   (e.g., W2/W3 anomalies, long stale + unread, no inbound dispatch,
                    abnormal resource growth). A human or Warden should look.
  - "dispatch-prompt": Send a short message FROM "warden" TO this Mind via
                       the Conduit Pillar's send_dispatch. Use when the Mind needs
                       a nudge or question that does NOT require human attention.
                       Examples: "long silence — what is your current focus?",
                       "you have N unread issues, please claim or skip them",
                       "I detected unusual file growth in your workspace, please clarify".
                       Do NOT use for critical issues (use "notify-human").
                       Do NOT use to issue commands to OTHER Minds (only this Mind).
  - "notify-human": Critical — failsafe path (ADR-0012 responsibility 5). Use sparingly.

Be decisive. Do not output explanations outside the JSON. If "minds" is empty, return [].
"""


def _build_user_prompt(snapshot: dict) -> str:
    """observation report dict を Claude が読みやすい形に整形する。

    Phase 5a-3 では v0.1 snapshot (`{generated_at, snapshot_id, minds: [...]}`)。
    Phase 5e (Observation v1.0 統合) からは `--for-warden` の統合 JSON も受理:
    `{schema_version: "1.0", generated_at, minds, flow, resource, anomaly}`。

    判断 Claude には:
    - report 全体を JSON dump (= 全 signal を context として渡す)
    - "minds" の件数を末尾で伝える (= 期待出力件数を明示)

    余分な field (flow / resource / anomaly) は v0.1 snapshot だと欠落、
    Judgment Claude は system prompt の指示に従い「無いものは無視」する。
    """
    minds = snapshot.get("minds", [])
    schema = snapshot.get("schema_version", "0.1")
    has_flow = bool(snapshot.get("flow"))
    has_resource = bool(snapshot.get("resource"))
    has_anomaly = bool(snapshot.get("anomaly"))

    # ヘッダ: schema_version と含まれる section を明示 (Claude が「これは何」
    # を即座に判別できるよう)。
    sections_present = ["minds"]
    if has_flow:
        sections_present.append("flow")
    if has_resource:
        sections_present.append("resource")
    if has_anomaly:
        sections_present.append("anomaly")
    header = (
        f"Observation report (schema={schema}, "
        f"sections: {', '.join(sections_present)}):"
    )

    return (
        f"{header}\n\n"
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

        # Phase 5e Step B: dispatch-prompt action は body / topic が必須。
        # 他 action では None で固定 (= 存在しても無視、副作用なし)。
        action_str = str(entry["action"])
        dispatch_topic: str | None = None
        dispatch_body: str | None = None
        if action_str == "dispatch-prompt":
            topic_raw = entry.get("dispatch_topic")
            body_raw = entry.get("dispatch_body")
            if not topic_raw or not isinstance(topic_raw, str):
                raise JudgmentParseError(
                    f"entry {i} has action=dispatch-prompt but missing/empty "
                    f"dispatch_topic\nraw: {raw_snippet}"
                )
            if not body_raw or not isinstance(body_raw, str):
                raise JudgmentParseError(
                    f"entry {i} has action=dispatch-prompt but missing/empty "
                    f"dispatch_body\nraw: {raw_snippet}"
                )
            # 改行正規化 (Codex P1 of Phase 5e Step B self-review):
            # topic は Conduit Pillar 側で改行 reject される (frontmatter 破壊
            # = identity 偽装防止)。LLM 出力が改行を含むと storage 側で
            # ValueError になり dispatch が常に失敗する UX 劣化を避けるため、
            # 判定の手前で space に正規化しておく。strip で前後 whitespace も
            # 除去 (空文字になるなら _parse_response の必須チェックで救う)。
            topic_normalized = (
                topic_raw.replace("\n", " ").replace("\r", " ").strip()
            )
            if not topic_normalized:
                raise JudgmentParseError(
                    f"entry {i} dispatch_topic became empty after newline "
                    f"normalization\nraw: {raw_snippet}"
                )
            # 上限切り捨て (LLM が暴走しても安全側に倒す)
            dispatch_topic = topic_normalized[:MAX_DISPATCH_TOPIC_LEN]
            dispatch_body = body_raw[:MAX_DISPATCH_BODY_LEN]

        result.append(
            MindJudgment(
                mind_name=mind_name,
                action=action_str,
                reason=str(entry["reason"])[:200],
                dispatch_topic=dispatch_topic,
                dispatch_body=dispatch_body,
            )
        )
        seen.add(mind_name)

    # Codex P1 PR #65: 期待 Mind 名と出力 Mind 名は **完全一致** を要求する。
    # missing (expected - seen): 一部判定が抜けている → fallback 必要
    # unknown (seen - expected): Claude が hallucinated Mind を出した → fallback 必要
    # どちらも downstream で「存在しない Mind に action」を防ぐ防御。
    missing = expected_set - seen
    unknown = seen - expected_set
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"missing: {sorted(missing)}")
        if unknown:
            parts.append(f"unknown (hallucinated): {sorted(unknown)}")
        raise JudgmentParseError(
            f"mind_name set mismatch — {', '.join(parts)}\nraw: {raw_snippet}"
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
    """Observation report を Claude に渡して各 Mind の action を判定する。

    Phase 5e (Observation v1.0 統合): 引数 `snapshot` は v0.1 snapshot だけで
    なく、`mind_scope.build_realm_report()` 出力 (schema_version="1.0") も
    受理する (= "snapshot は report の subset" として上位互換)。Claude には
    flow / resource / anomaly セクションがあれば全部渡される。判断材料が
    増えても VALID_ACTIONS の語彙は変えない (= passive な観察 action のみ、
    active な spawn/kill 等は別 Phase で議論)。

    引数:
        snapshot: Observation report の dict。最低限 `minds: [...]` を持つ。
                  optionally `flow / resource / anomaly` を含む。
        client: Anthropic Client。None なら make_client() で初期化
        model / max_tokens / temperature: SDK 呼び出しパラメータ

    戻り値:
        各 Mind の MindJudgment のリスト。snapshot.minds の順序とは限らない
        ことに注意（mind_name で照合すること）。

    Mind が 0 件の input は空リストを返す（SDK 呼び出しせず短絡）。

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
