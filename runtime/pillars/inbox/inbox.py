#!/usr/bin/env python3
"""
Inbox Pillar: 人間 → Realm への入力経路（Phase 5a-5 / Issue #40）。

ADR 整合:
- ADR-0006 §6: Phase 5a の達成判定は「Issue 投入が動くこと」。
- ADR-0010:    Warden は機能の集合体。観測は自由。
- ADR-0011:    Pillar は編集不可。`runtime/pillars/inbox/` 配下に置く。
- ADR-0012 §3: 人間 → Warden への入力経路は Inbox Pillar 経由（チャンネル表）。
- ADR-0013 §1 F4: Realm 外部からの入力なので「人間制御チャンネル」として扱う。
- ADR-0014 §3 D: 人間制御領域 → A 内側への入力経路として Inbox Pillar が境界に立つ。

責務:
- submit_issue(title, body, ...) -> Path
    新しい Issue を inbox/ に投入する。issue_id は内部生成のみ（path traversal 対策）。
    atomic write（tmp に書く → os.link で final path を予約 → tmp unlink）。
- list_pending_issues() -> list[IssueRecord]
    inbox/ の未処理 Issue を投入順（issue_id sort）で返す。
- claim_issue(issue_id) -> IssueRecord
    inbox/<id>.md を archive/<id>.md に rename して「処理開始」をマークする。
    rename は POSIX 上 atomic なので、並行 claim による二重取りを機械的に防ぐ。

ストレージ:
    runtime/issues/inbox/<id>.md       未処理（人間が投入、または submit_issue が書く）
    runtime/issues/archive/<id>.md     claim 後

依存:
- 標準ライブラリのみ（ADR-0005 / ADR-0009 の依存ゼロ方針）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# デフォルトの Issue 保管場所。テストでは tmp に差し替える。
# `runtime/pillars/inbox/` から見て `../../issues/` が runtime/issues/。
DEFAULT_ISSUES_DIR = (Path(__file__).parent / ".." / ".." / "issues").resolve()

# 入力検証。spawn-mind.sh / conduit/storage.py と同じ文字集合に揃える。
SUBMITTER_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
ALLOWED_PRIORITIES = ("p0", "p1", "p2", "p3")
TITLE_MAX_LEN = 200

# 内部生成 issue_id の形式: YYYYMMDDTHHMMSSZ-<8 hex chars>
# 外部から渡された文字列が「ファイル名として安全か」を検証する用途にも使う。
ISSUE_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


class IssueNotFoundError(LookupError):
    """claim 対象の Issue が inbox に存在しない場合に raise。"""


class IssueValidationError(ValueError):
    """submit_issue の入力検証エラー（title / submitter / priority など）。"""


@dataclass(frozen=True)
class IssueRecord:
    """Inbox / archive に置かれた Issue の正規表現。

    `path` は実体ファイルの絶対パス（inbox 側 or archive 側）。
    `body` は frontmatter を除いた Markdown 本文（末尾改行は維持されない）。
    """

    issue_id: str
    title: str
    submitted_at: str
    submitter: str
    priority: str
    path: Path
    body: str


# ---- 内部ヘルパ ---------------------------------------------------------------


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _gen_issue_id(now: dt.datetime | None = None) -> str:
    """内部生成のみ。外部入力にしないことで path traversal を機械的に防ぐ。

    形式: `YYYYMMDDTHHMMSSZ-<8 hex>`。Conduit Pillar の msg_id と同様にソート可能。
    """
    if now is None:
        now = _utcnow()
    ts = now.strftime("%Y%m%dT%H%M%SZ")
    rand = secrets.token_hex(4)  # 8 hex chars
    return f"{ts}-{rand}"


def _validate_title(title: str) -> None:
    if not isinstance(title, str):
        raise IssueValidationError("title must be a string")
    if len(title) == 0:
        raise IssueValidationError("title must not be empty")
    if len(title) > TITLE_MAX_LEN:
        raise IssueValidationError(
            f"title too long ({len(title)} > {TITLE_MAX_LEN} chars)"
        )
    if "\n" in title or "\r" in title:
        raise IssueValidationError("title must not contain newlines")


def _validate_submitter(submitter: str) -> None:
    if not isinstance(submitter, str) or not SUBMITTER_RE.match(submitter):
        raise IssueValidationError(
            f"invalid submitter: must match {SUBMITTER_RE.pattern}"
        )


def _validate_priority(priority: str) -> None:
    if priority not in ALLOWED_PRIORITIES:
        raise IssueValidationError(
            f"invalid priority '{priority}': must be one of {ALLOWED_PRIORITIES}"
        )


def _validate_issue_id(issue_id: str) -> None:
    """外部入力された issue_id がファイル名として安全か検証する。

    内部生成形式 (`YYYYMMDDTHHMMSSZ-<8 hex>`) にマッチしないものは全部 reject。
    これにより `../escape` / 絶対パス / ヌル文字などは一切受理しない。
    """
    if not isinstance(issue_id, str) or not ISSUE_ID_RE.match(issue_id):
        raise IssueValidationError(
            f"invalid issue_id: must match {ISSUE_ID_RE.pattern}"
        )


def _resolve_issues_dir(issues_dir: Path | None) -> Path:
    base = Path(issues_dir) if issues_dir is not None else DEFAULT_ISSUES_DIR
    return base.resolve()


def _ensure_dirs(issues_dir: Path) -> tuple[Path, Path]:
    inbox = issues_dir / "inbox"
    archive = issues_dir / "archive"
    inbox.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)
    return inbox, archive


def _build_payload(
    issue_id: str,
    title: str,
    submitted_at: str,
    submitter: str,
    priority: str,
    body: str,
) -> str:
    """frontmatter + 本文の Markdown を組み立てる。"""
    return (
        "---\n"
        f"issue_id: {issue_id}\n"
        f"title: {title}\n"
        f"submitted_at: {submitted_at}\n"
        f"submitter: {submitter}\n"
        f"priority: {priority}\n"
        "---\n\n"
        f"{body}\n"
    )


def _parse_issue_file(path: Path) -> IssueRecord | None:
    """Issue ファイルを読んで IssueRecord に組み立てる。

    frontmatter が無い / 必須フィールドが欠けている / issue_id 形式不正な場合は
    None を返す（list_pending_issues はこれを skip する）。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # frontmatter は最初の行が `---` で始まり、次の `---` で閉じる Markdown 標準形式。
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None

    meta: dict[str, str] = {}
    for line in lines[1:end_idx]:
        if not line.strip():
            continue
        if ":" not in line:
            return None
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()

    required = ("issue_id", "title", "submitted_at", "submitter", "priority")
    for k in required:
        if k not in meta:
            return None

    # 内部生成由来の Issue であることを担保。フォーマット違反はスキップ対象。
    if not ISSUE_ID_RE.match(meta["issue_id"]):
        return None
    # ファイル名と issue_id が一致することも検証（手書き偽装の防御層）。
    if path.stem != meta["issue_id"]:
        return None

    body_lines = lines[end_idx + 1:]
    # frontmatter 直後の空行 1 つは慣例なので食う。
    if body_lines and body_lines[0] == "":
        body_lines = body_lines[1:]
    body = "\n".join(body_lines)

    return IssueRecord(
        issue_id=meta["issue_id"],
        title=meta["title"],
        submitted_at=meta["submitted_at"],
        submitter=meta["submitter"],
        priority=meta["priority"],
        path=path,
        body=body,
    )


# ---- public API ---------------------------------------------------------------


def submit_issue(
    title: str,
    body: str,
    *,
    priority: str = "p2",
    submitter: str = "human",
    issues_dir: Path | None = None,
    now: dt.datetime | None = None,
) -> Path:
    """新しい Issue を inbox に投入する。

    引数:
        title:     1〜200 文字、改行不可。
        body:      Markdown 本文（複数行可、検証なし）。
        priority:  p0 / p1 / p2 / p3 のいずれか。デフォルト p2。
        submitter: `[A-Za-z0-9._-]{1,64}` にマッチする識別子。デフォルト `human`。
        issues_dir: 保管ルート。None なら DEFAULT_ISSUES_DIR。テストで差し替え可。
        now:       タイムスタンプ生成用の現在時刻（UTC aware）。テストで固定可。

    戻り値:
        書き込んだ Issue ファイルの絶対パス（inbox 側）。

    例外:
        IssueValidationError: title / submitter / priority / body が不正な場合。

    並行性:
        - issue_id は内部生成（外部入力にしない）。path traversal は構造的に不可。
        - 並行 submit による衝突は os.link で atomic に予約 → 衝突したら新しい
          issue_id を再生成してリトライ。tmp 残骸は finally で unlink。
    """
    _validate_title(title)
    _validate_submitter(submitter)
    _validate_priority(priority)
    if not isinstance(body, str):
        raise IssueValidationError("body must be a string")

    base = _resolve_issues_dir(issues_dir)
    inbox, _archive = _ensure_dirs(base)

    if now is None:
        now = _utcnow()
    submitted_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # tmp に書く → os.link で final を予約 → tmp unlink、の atomic パターン。
    # snapshot.py を踏襲。並行プロセス間でも衝突しない。
    attempts = 0
    while True:
        attempts += 1
        if attempts > 1000:
            raise RuntimeError(
                f"could not allocate issue_id after 1000 attempts at {inbox}"
            )
        issue_id = _gen_issue_id(now)
        final_path = inbox / f"{issue_id}.md"
        # PID と microsecond で他プロセスとぶつからない tmp 名にする。
        tmp_name = (
            f"{issue_id}.md.tmp."
            f"{os.getpid()}."
            f"{dt.datetime.now().strftime('%f')}."
            f"{secrets.token_hex(2)}"
        )
        tmp_path = inbox / tmp_name
        serialized = _build_payload(
            issue_id=issue_id,
            title=title,
            submitted_at=submitted_at,
            submitter=submitter,
            priority=priority,
            body=body,
        )
        tmp_path.write_text(serialized, encoding="utf-8")
        try:
            # os.link は既存ファイルがあれば FileExistsError。POSIX 上 atomic。
            os.link(str(tmp_path), str(final_path))
        except FileExistsError:
            # 8 hex chars 同士の衝突。retry。tmp は finally で消す。
            try:
                tmp_path.unlink()
            except OSError:
                pass
            continue
        finally:
            # link 成功時も tmp 本体は不要（hardlink で final が本体を共有）。
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return final_path


def list_pending_issues(
    issues_dir: Path | None = None,
) -> list[IssueRecord]:
    """inbox/ の未処理 Issue を投入順（issue_id sort）で返す。

    frontmatter が壊れているファイルは skip する（壊れたファイルで全体停止しない）。
    issue_id はソート可能な形式なので、ファイル名昇順 = 投入時刻昇順。
    """
    base = _resolve_issues_dir(issues_dir)
    inbox = base / "inbox"
    if not inbox.is_dir():
        return []
    records: list[IssueRecord] = []
    # `.gitkeep` 等の付随ファイルは glob('*.md') で自動的に除外される。
    for path in sorted(inbox.glob("*.md")):
        rec = _parse_issue_file(path)
        if rec is None:
            continue
        records.append(rec)
    return records


def claim_issue(
    issue_id: str,
    issues_dir: Path | None = None,
) -> IssueRecord:
    """Issue を archive に移動して「処理開始」をマークする。

    引数:
        issue_id: 内部生成形式 (YYYYMMDDTHHMMSSZ-<8 hex>) のみ受理。
                  形式違反は IssueValidationError、inbox に無いものは IssueNotFoundError。

    戻り値:
        archive 側に置かれた IssueRecord（path は archive のもの）。

    例外:
        IssueValidationError: issue_id 形式違反。
        IssueNotFoundError:   inbox に該当ファイルが無い（未投入 or 既に claim 済み）。

    並行性:
        - `Path.rename` は POSIX 上 atomic（src と dst が同一 device の inbox/archive）。
        - 2 つの並行 claim が同じ Issue を取りに来た場合、先着が rename に成功し、
          後着は FileNotFoundError → IssueNotFoundError として再生される。
        - archive に既存ファイルがあれば（ありえないが防御層として）reject する。
    """
    _validate_issue_id(issue_id)
    base = _resolve_issues_dir(issues_dir)
    inbox, archive = _ensure_dirs(base)

    src = inbox / f"{issue_id}.md"
    dst = archive / f"{issue_id}.md"

    # claim の atomic 化は os.link + os.unlink の 2 段で行う。
    # `os.rename` は POSIX 上 atomic だが、Windows では `os.rename(src, dst)` で
    # dst が既存だと失敗する一方、並行する 2 つの rename を機械的に区別できない
    # ケースがあり、`dst.exists()` 事前チェックでは race window が残る。
    # 対して `os.link` は POSIX/Windows どちらでも「dst が既存なら FileExistsError」
    # で atomic に失敗する（POSIX は `link(2)`、Windows は CreateHardLinkW）。
    # これで「先着が link 成功 → unlink で src を消す」を保証できる。
    try:
        os.link(str(src), str(dst))
    except FileExistsError as exc:
        # dst が既に存在 = 既に誰かが archive に移動した（二重 claim）。
        raise IssueNotFoundError(
            f"issue '{issue_id}' is already archived (double claim?)"
        ) from exc
    except FileNotFoundError as exc:
        # src が存在しない = 未投入 or 先行 claim が完了済み。
        raise IssueNotFoundError(f"issue '{issue_id}' not in inbox") from exc

    # ここまで来たら dst は確実に存在する。src を unlink して claim を完了。
    try:
        src.unlink()
    except FileNotFoundError:
        # 先行 claim が src を消した（極めて稀。link 成功後に競合）。
        # archive 側に自分が link した本体は残るので claim は有効。
        pass

    rec = _parse_issue_file(dst)
    if rec is None:
        # archive に移動はできたが parse できない（frontmatter 破損）。
        # 「claim は成功した」ことを最低限呼び出し側に伝えるため、最小限の record を返す。
        return IssueRecord(
            issue_id=issue_id,
            title="",
            submitted_at="",
            submitter="",
            priority="",
            path=dst,
            body=dst.read_text(encoding="utf-8") if dst.exists() else "",
        )
    return rec


# ---- CLI ----------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> int:
    issues_dir = Path(args.issues_dir) if args.issues_dir else None
    records = list_pending_issues(issues_dir=issues_dir)
    if not records:
        print("(no pending issues)")
        return 0
    for rec in records:
        print(f"{rec.issue_id}\t{rec.priority}\t{rec.submitter}\t{rec.title}")
    return 0


def _cmd_submit(args: argparse.Namespace) -> int:
    issues_dir = Path(args.issues_dir) if args.issues_dir else None
    try:
        path = submit_issue(
            title=args.title,
            body=args.body,
            priority=args.priority,
            submitter=args.submitter,
            issues_dir=issues_dir,
        )
    except IssueValidationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    print(path.stem)
    return 0


def _cmd_claim(args: argparse.Namespace) -> int:
    issues_dir = Path(args.issues_dir) if args.issues_dir else None
    try:
        rec = claim_issue(args.issue_id, issues_dir=issues_dir)
    except IssueValidationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except IssueNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 3
    print(f"claimed: {rec.issue_id} -> {rec.path}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="inbox.py",
        description="Inbox Pillar: 人間 → Realm 入力経路 (Phase 5a-5 / Issue #40)",
    )
    parser.add_argument(
        "--issues-dir",
        default=None,
        help="保管ルート（デフォルト: runtime/issues/）。テスト用に上書き可。",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="未処理 Issue を一覧")
    p_list.set_defaults(func=_cmd_list)

    p_submit = sub.add_parser("submit", help="Issue を投入")
    p_submit.add_argument("title", help="短いタイトル（1-200 文字、改行不可）")
    p_submit.add_argument(
        "--body",
        default="",
        help="本文（Markdown 可、未指定なら空）",
    )
    p_submit.add_argument(
        "--priority",
        default="p2",
        choices=list(ALLOWED_PRIORITIES),
        help="優先度 (default: p2)",
    )
    p_submit.add_argument(
        "--submitter",
        default="human",
        help="投入者識別子（[A-Za-z0-9._-]{1,64}）",
    )
    p_submit.set_defaults(func=_cmd_submit)

    p_claim = sub.add_parser("claim", help="Issue を archive に移して処理開始")
    p_claim.add_argument("issue_id", help="claim 対象の issue_id")
    p_claim.set_defaults(func=_cmd_claim)

    ns = parser.parse_args(list(argv) if argv is not None else None)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
