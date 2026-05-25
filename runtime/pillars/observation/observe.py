#!/usr/bin/env python3
"""
Realm Observatory CLI.

Walks runtime/minds/ and runtime/pillars/conduit/storage/ to produce a current snapshot
of all spawned Minds with status / category. Standard library only.

Usage:
  python3 runtime/pillars/observation/observe.py
  python3 runtime/pillars/observation/observe.py --json     # machine-readable
  python3 runtime/pillars/observation/observe.py --snapshot # write JSON snapshot file
  python3 runtime/pillars/observation/observe.py --prune    # delete old snapshots (TTL days)

See ADR-0009 for the design rationale (port pure logic only, no Web UI yet).
v0.1 snapshot details: runtime/pillars/observation/ROADMAP.md §「Observation Pillar v0.1」.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import os
import time
from pathlib import Path

# Locate runtime (framework) root from this file's path.
RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent


def _runtime_home() -> Path:
    """$AI_ORG_OS_HOME or ~/.ai-org-os/ (Phase 5b-4 / ADR-0018)。

    関数化することで、テストが env を切り替えるだけで隔離が効くようにする
    (module-level の path 定数だと import 時に固定されてしまう)。
    """
    env = os.environ.get("AI_ORG_OS_HOME")
    if env:
        return Path(env)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(home) / ".ai-org-os"


def _minds_dir() -> Path:
    return _runtime_home() / "minds"


def _conduit_storage_dir() -> Path:
    return _runtime_home() / "conduit-storage"


def _inbox_dir(mind_name: str | None = None) -> Path:
    p = _conduit_storage_dir() / "inbox"
    return p / mind_name if mind_name else p


def _archive_dir(mind_name: str | None = None) -> Path:
    p = _conduit_storage_dir() / "archive"
    return p / mind_name if mind_name else p

# Make `import mind_status` work without needing a package setup.
sys.path.insert(0, str(Path(__file__).parent))

from mind_status import MindObservation, calc_category, calc_status  # noqa: E402


def _read_meta(meta_path: Path, key: str, default: str = "?") -> str:
    if not meta_path.is_file():
        return default
    try:
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}:"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return default


def _epoch_from_iso(iso_str: str) -> float:
    """Parse YYYY-MM-DDTHH:MM:SSZ into a UTC epoch. Returns 0.0 on failure."""
    try:
        parsed = dt.datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ")
        return parsed.replace(tzinfo=dt.timezone.utc).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _count_messages(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for _ in directory.glob("*.md"))


def _latest_mtime(mind_dir: Path) -> float:
    """Find latest mtime anywhere in the Mindspace. Returns 0.0 if empty."""
    if not mind_dir.is_dir():
        return 0.0
    latest = 0.0
    for entry in mind_dir.rglob("*"):
        if entry.is_file():
            try:
                latest = max(latest, entry.stat().st_mtime)
            except OSError:
                continue
    return latest


def gather_observations(now_epoch: float) -> list[tuple[MindObservation, str, str]]:
    """Walk $AI_ORG_OS_HOME/minds/ and return (observation, status, category) per Mind.

    Phase 5b-4 (#81 / ADR-0018): Mindspace 配置は $AI_ORG_OS_HOME 配下。
    Only directories with .mind-meta.md count as real spawned Minds (the
    convention from spawn-mind.sh). Bare dirs are ignored.

    Note (Phase 5c-1): MindObservation には guild フィールドが無いので
    table 表示で guild を出す場合は呼び出し側で再度 .mind-meta.md を読む
    (派生表示)。本関数は既存の出力契約を保つ。
    """
    result: list[tuple[MindObservation, str, str]] = []
    minds_dir = _minds_dir()
    if not minds_dir.is_dir():
        return result

    for mind_dir in sorted(minds_dir.iterdir()):
        if not mind_dir.is_dir():
            continue
        meta = mind_dir / ".mind-meta.md"
        if not meta.is_file():
            continue
        name = mind_dir.name
        observation = MindObservation(
            mind_name=name,
            kind=_read_meta(meta, "kind"),
            persona=_read_meta(meta, "persona"),
            spawned_at_epoch=_epoch_from_iso(_read_meta(meta, "spawned_at")),
            last_activity_epoch=_latest_mtime(mind_dir),
            unread_inbox_count=_count_messages(_inbox_dir(name)),
            archive_count=_count_messages(_archive_dir(name)),
        )
        result.append(
            (observation, calc_status(observation, now_epoch), calc_category(observation, now_epoch))
        )
    return result


def _format_table(observations: list[tuple[MindObservation, str, str]]) -> str:
    if not observations:
        return "No minds spawned."

    status_counts = {"active": 0, "waiting": 0, "idle": 0}
    category_counts = {"attention": 0, "running": 0, "unread": 0, "stale": 0, "read": 0}
    for _, status, category in observations:
        status_counts[status] += 1
        category_counts[category] += 1

    lines: list[str] = []
    lines.append("=== Realm Observatory ===")
    lines.append(f"  total: {len(observations)}")
    lines.append(
        "  status:   "
        f"active={status_counts['active']}  "
        f"waiting={status_counts['waiting']}  "
        f"idle={status_counts['idle']}"
    )
    lines.append(
        "  category: "
        f"attention={category_counts['attention']}  "
        f"running={category_counts['running']}  "
        f"unread={category_counts['unread']}  "
        f"stale={category_counts['stale']}  "
        f"read={category_counts['read']}"
    )
    lines.append("")
    lines.append(
        f"{'NAME':<20} {'KIND':<10} {'PERSONA':<14} {'STATUS':<8} {'CATEGORY':<10} {'INBOX/ARCHIVE'}"
    )
    for observation, status, category in observations:
        ia = f"{observation.unread_inbox_count}/{observation.archive_count}"
        lines.append(
            f"{observation.mind_name:<20} {observation.kind:<10} "
            f"{observation.persona:<14} {status:<8} {category:<10} {ia}"
        )
    return "\n".join(lines)


def _format_json(observations: list[tuple[MindObservation, str, str]]) -> str:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "minds": [
            {
                "mind_name": o.mind_name,
                "kind": o.kind,
                "persona": o.persona,
                "spawned_at_epoch": o.spawned_at_epoch,
                "last_activity_epoch": o.last_activity_epoch,
                "unread_inbox_count": o.unread_inbox_count,
                "archive_count": o.archive_count,
                "status": s,
                "category": c,
            }
            for o, s, c in observations
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _parse_int_option(argv: list[str], name: str, default: int) -> int:
    """Minimal `--name VALUE` parser. Raises SystemExit(2) on malformed input."""
    if name not in argv:
        return default
    idx = argv.index(name)
    if idx + 1 >= len(argv):
        print(f"[ERROR] {name} requires an integer argument", file=sys.stderr)
        raise SystemExit(2)
    raw = argv[idx + 1]
    try:
        return int(raw)
    except ValueError:
        print(f"[ERROR] {name} must be an integer (got '{raw}')", file=sys.stderr)
        raise SystemExit(2)


def _format_realm_view(observations: list[tuple[MindObservation, str, str]]) -> str:
    """Realm 統合ビュー (Phase 5b-1 / #71)。

    既存 snapshot 表 + Inbox queue + Guild summary + Conductor cycle status を
    1 画面に並べる。各セクションは独立に失敗しても残りを描画する。

    Mind 0 件でも "=== Realm Observatory ===" ヘッダは出す
    (E2E テスト / 統合ビュー識別性のため。Codex P2 CI fix)。
    """
    sections: list[str] = []
    if not observations:
        sections.append("=== Realm Observatory ===")
        sections.append("  No minds spawned.")
    else:
        sections.append(_format_table(observations))

    # --- Inbox queue
    # Codex P2 (#88): Inbox 読み込み失敗時は pending_list を None にする。
    # Guild section が「pending=0」を全 Guild に表示する不整合 (Inbox
    # unavailable なのに pending=0 が並ぶ) を避けるため、success/failure
    # を pending_list の型で区別する (list = 成功 / None = 失敗 = unknown)。
    pending_list: list | None = []
    try:
        sys.path.insert(0, str(RUNTIME_DIR / "pillars" / "inbox"))
        from inbox import list_pending_issues  # type: ignore[import-not-found]

        pending_list = list_pending_issues()
        sections.append("")
        sections.append(f"=== Inbox Queue ({len(pending_list)} pending) ===")
        if not pending_list:
            sections.append("  (no pending issues)")
        else:
            for rec in pending_list[:5]:
                # Phase 5c-1: guild も表示 (どの組織への依頼か即わかるように)
                sections.append(
                    f"  {rec.issue_id}  {rec.priority:<3}  "
                    f"{rec.submitter:<12}  [{rec.guild}]  {rec.title}"
                )
            if len(pending_list) > 5:
                sections.append(f"  ... and {len(pending_list) - 5} more")
    except Exception as exc:  # noqa: BLE001
        sections.append("")
        sections.append(f"=== Inbox Queue (unavailable: {exc}) ===")
        pending_list = None  # Codex P2 #88: 後続の Guild 集計に signal を渡す

    # --- Guild summary (Phase 5c-1 / ADR-0019 / ADR-0020)
    # default Guild は manifest 必須 (templates/guilds/default/ に同梱)。
    # 利用者が $AI_ORG_OS_HOME/guilds/<name>/ に追加した Guild は overlay
    # 経由で list_guilds() に含まれる。
    # members は .mind-meta.md 走査による派生、pending は Inbox queue から集計。
    try:
        sys.path.insert(0, str(RUNTIME_DIR / "pillars" / "registry"))
        from guild import (  # type: ignore[import-not-found]
            DEFAULT_GUILD,
            enumerate_members,
            list_guilds,
        )

        guild_names = list_guilds()
        sections.append("")
        if not guild_names:
            sections.append("=== Guilds (no manifest) ===")
            sections.append(
                "  (no manifest in templates/guilds/ or $AI_ORG_OS_HOME/guilds/)"
            )
        else:
            sections.append(f"=== Guilds ({len(guild_names)}) ===")
            # Codex P2 (#88): Inbox 読み込みが失敗していたら (pending_list が
            # None)、pending count は "?" として表示する。空 list と区別する
            # ことで「Inbox unavailable なのに pending=0」の誤情報を避ける。
            inbox_unknown = pending_list is None
            pending_by_guild: dict[str, int] = {}
            if not inbox_unknown:
                for rec in pending_list:  # type: ignore[union-attr]
                    g = rec.guild or DEFAULT_GUILD
                    pending_by_guild[g] = pending_by_guild.get(g, 0) + 1
            for gname in guild_names:
                members = enumerate_members(gname)
                member_str = ", ".join(members) if members else "(none)"
                pending_str = (
                    "?" if inbox_unknown
                    else str(pending_by_guild.get(gname, 0))
                )
                sections.append(
                    f"  {gname}: members={len(members)} [{member_str}], "
                    f"pending={pending_str}"
                )
            if inbox_unknown:
                # 「?」が並んでいる理由を 1 行で明示する
                sections.append(
                    "  (pending counts unknown: Inbox Queue read failed; "
                    "see Inbox section above)"
                )
            else:
                # manifest を持たないが Issue / Mind が参照している guild も併記
                referenced_unknown = (
                    set(pending_by_guild.keys()) - set(guild_names)
                )
                if referenced_unknown:
                    for g in sorted(referenced_unknown):
                        sections.append(
                            f"  {g}: [no manifest] pending={pending_by_guild[g]}"
                        )
    except Exception as exc:  # noqa: BLE001
        sections.append("")
        sections.append(f"=== Guilds (unavailable: {exc}) ===")

    # --- Conductor status
    # Phase 5b-4 (#81 / ADR-0018): conductor-status.json は $AI_ORG_OS_HOME 直下。
    status_path = _runtime_home() / "conductor-status.json"
    sections.append("")
    if not status_path.is_file():
        sections.append("=== Conductor (not running yet) ===")
        sections.append("  Start: docker compose up -d --build (under runtime/realm/)")
    else:
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            last = status.get("last_cycle", {})
            total = status.get("total_cycles", "?")
            sections.append(f"=== Conductor (total cycles: {total}) ===")
            sections.append(f"  last cycle:    #{last.get('cycle', '?')}")
            sections.append(f"  started_at:    {last.get('started_at', '?')}")
            sections.append(f"  ended_at:      {last.get('ended_at', '?')}")
            # pending_issues == -1 は Conductor 側で「取得失敗」マーカー (混乱回避のため "?" 表示)
            pending = last.get("pending_issues")
            pending_display = "?" if pending == -1 or pending is None else pending
            sections.append(f"  pending:       {pending_display}")
            sections.append(f"  judgment:      {last.get('judgment_status', '?')}")
            err = last.get("judgment_error")
            if err:
                sections.append(f"  judgment_err:  {err[:120]}")
            breakdown = last.get("judgments_action_breakdown", {})
            if breakdown:
                actions = "  ".join(f"{k}={v}" for k, v in sorted(breakdown.items()))
                sections.append(f"  last_actions:  {actions}")
        except Exception as exc:  # noqa: BLE001
            sections.append(f"=== Conductor (status JSON unreadable: {exc}) ===")

    return "\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    as_snapshot = "--snapshot" in argv
    as_prune = "--prune" in argv
    as_realm = "--realm" in argv

    now_epoch = time.time()

    if as_prune:
        # v0.1: TTL prune は --snapshot とは独立なサブコマンド扱い。
        # 自動削除はせず、利用者が明示的に呼ぶ（ROADMAP v0.1 の要件）。
        from snapshot import prune_snapshots, DEFAULT_TTL_DAYS

        ttl = _parse_int_option(argv, "--ttl-days", DEFAULT_TTL_DAYS)
        deleted = prune_snapshots(ttl_days=ttl)
        for p in deleted:
            print(f"deleted: {p}")
        print(f"[prune] removed {len(deleted)} snapshot(s) older than {ttl} day(s)", file=sys.stderr)
        return 0

    if as_snapshot:
        from snapshot import load_snapshot, write_snapshot

        # Codex P2 PR #62: 旧実装は write_snapshot 後に gather_observations を再度呼んで
        # stdout に出していたが、その間に Mind の状態が変わると saved file と stdout が
        # divergent になりうる（特に 5 分 / 1 時間の status しきい値跨ぎで）。
        # 修正: 書き込んだファイルを読み戻して同じ payload を stdout に流す。
        path = write_snapshot()
        print(f"[snapshot] wrote {path}", file=sys.stderr)
        # 利用者が pipe で次の処理に流せるよう、stdout には保存した JSON を出す。
        payload = load_snapshot(path)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    observations = gather_observations(now_epoch)
    if as_realm:
        # Phase 5b-1 統合ビュー: snapshot + Inbox + Conductor cycle status を 1 画面に
        print(_format_realm_view(observations))
    elif as_json:
        print(_format_json(observations))
    else:
        print(_format_table(observations))
    return 0


if __name__ == "__main__":
    sys.exit(main())
