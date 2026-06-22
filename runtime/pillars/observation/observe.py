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
  python3 runtime/pillars/observation/observe.py --realm    # integrated view (#71)
  python3 runtime/pillars/observation/observe.py --flow     # dispatch flow summary (#66)
  python3 runtime/pillars/observation/observe.py --resource # per-mind + storage size (#66)
  python3 runtime/pillars/observation/observe.py --anomaly  # W1-W3 / I1-I2 signals (#67)
  python3 runtime/pillars/observation/observe.py --diff <prev> --against <curr>  # snapshot diff (#67)
  python3 runtime/pillars/observation/observe.py --for-warden  # integrated JSON (snapshot+flow+resource+anomaly, #68)
  python3 runtime/pillars/observation/observe.py --trace [--since 1h]  # JSONL event time-line (#122, ADR-0026)

See ADR-0009 for the design rationale (port pure logic only, no Web UI yet).
v0.1 snapshot details: runtime/pillars/observation/ROADMAP.md §「Observation Pillar v0.1」.
v0.2 flow/resource details: pillars/conduit/dispatch-format.md と pillars/observation/dispatch_flow.py / resource_usage.py.
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
    """Find latest mtime anywhere in the Mindspace. Returns 0.0 if empty.

    Symlinks are skipped to prevent dual-path inconsistency (same as
    resource_usage._scan_dir_size). See #195 for security rationale.
    """
    if not mind_dir.is_dir():
        return 0.0
    latest = 0.0
    # iterative DFS to avoid recursion depth limit
    stack: list[Path] = [mind_dir]
    while stack:
        cur = stack.pop()
        try:
            it = os.scandir(cur)
        except OSError:
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        # skip symlinks to prevent DoS / time-side-channel
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                        continue
                    if entry.is_file(follow_symlinks=False):
                        st = entry.stat(follow_symlinks=False)
                        latest = max(latest, st.st_mtime)
                        continue
                except OSError:
                    continue
    return latest


def _registry_dir() -> Path:
    """`$AI_ORG_OS_HOME/registry/minds/` (Phase 5c-2 P1 fix #91)。

    Mind の persona / guild / kind / spawned_at の **authoritative source**。
    Mindspace 内 `.mind-meta.md` は Mind 自身が書き換え可能なため authz の
    根拠にできない (caller-writable 排除)。registry は Pillar 管理領域。
    """
    home = os.environ.get("AI_ORG_OS_HOME")
    if home:
        return Path(home) / "registry" / "minds"
    h = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."
    return Path(h) / ".ai-org-os" / "registry" / "minds"


def gather_observations(now_epoch: float) -> list[tuple[MindObservation, str, str]]:
    """Walk $AI_ORG_OS_HOME/minds/ and return (observation, status, category) per Mind.

    Phase 5b-4 (#81 / ADR-0018): Mindspace 配置は $AI_ORG_OS_HOME 配下。
    Only directories with .mind-meta.md count as real spawned Minds (the
    convention from spawn-mind.sh). Bare dirs are ignored.

    Phase 5c-2 P1 fix (#91 Codex): kind / persona / spawned_at の参照は
    Mind registry (`$AI_ORG_OS_HOME/registry/minds/<name>.md`) を優先する。
    Mindspace 内 `.mind-meta.md` は Mind が書き換え可能なため、改ざんが
    あった場合に観察結果が「真実 (registry)」と乖離する。registry が無い
    過渡期 Mind は `.mind-meta.md` にフォールバック (= 既存テスト fixture
    互換)。inbox/archive/mtime は引き続き Mindspace 内の動的状態を見る。
    """
    result: list[tuple[MindObservation, str, str]] = []
    minds_dir = _minds_dir()
    if not minds_dir.is_dir():
        return result

    registry_dir = _registry_dir()
    for mind_dir in sorted(minds_dir.iterdir()):
        if not mind_dir.is_dir():
            continue
        meta = mind_dir / ".mind-meta.md"
        if not meta.is_file():
            continue
        name = mind_dir.name
        # Authoritative メタ source は registry。無ければ Mindspace 内
        # `.mind-meta.md` にフォールバック (= 過渡期 / 旧 Mind 互換)。
        reg_entry = registry_dir / f"{name}.md"
        meta_source = reg_entry if reg_entry.is_file() else meta
        observation = MindObservation(
            mind_name=name,
            kind=_read_meta(meta_source, "kind"),
            persona=_read_meta(meta_source, "persona"),
            spawned_at_epoch=_epoch_from_iso(_read_meta(meta_source, "spawned_at")),
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


def _format_table_with_resource(
    observations: list[tuple[MindObservation, str, str]],
) -> str:
    """`_format_table` の拡張。BYTES / FILES カラムを追加し、末尾に
    Conduit storage バケットを 1 行併記する (Phase 5d-1 / #66, --resource)。

    Mind 名は既に観察済の dir 名なので、各 Mind の Mindspace サイズは
    `resource_usage._scan_dir_size` で再計算する。ストレージ全体は
    `resource_usage.conduit_storage_usage` を使う。
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from resource_usage import (  # noqa: PLC0415
        _scan_dir_size,
        conduit_storage_usage,
        _human_bytes,
    )

    if not observations:
        # Mind 0 の場合でも storage 行は意味がある (例: e2e fixture)。
        cs = conduit_storage_usage()
        return (
            "No minds spawned.\n"
            f"\n"
            f"=== Resource Usage ===\n"
            f"  conduit-storage  files={cs.file_count}  "
            f"bytes={cs.byte_count}  size={_human_bytes(cs.byte_count)}"
        )

    status_counts = {"active": 0, "waiting": 0, "idle": 0}
    category_counts = {
        "attention": 0,
        "running": 0,
        "unread": 0,
        "stale": 0,
        "read": 0,
    }
    for _, status, category in observations:
        status_counts[status] += 1
        category_counts[category] += 1

    lines: list[str] = []
    lines.append("=== Realm Observatory (with resource usage) ===")
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
        f"{'NAME':<20} {'KIND':<10} {'PERSONA':<14} {'STATUS':<8} "
        f"{'CATEGORY':<10} {'INBOX/ARCHIVE':<14} {'FILES':<6} {'BYTES':<10} SIZE"
    )
    total_bytes = 0
    total_files = 0
    for observation, status, category in observations:
        ia = f"{observation.unread_inbox_count}/{observation.archive_count}"
        # Mindspace dir 名 = Mind 名。`resource_usage._scan_dir_size` は
        # symlink を辿らないので、信頼できるサイズが取れる。
        mind_dir = _minds_dir() / observation.mind_name
        files, byte_count = _scan_dir_size(mind_dir)
        total_files += files
        total_bytes += byte_count
        lines.append(
            f"{observation.mind_name:<20} {observation.kind:<10} "
            f"{observation.persona:<14} {status:<8} {category:<10} "
            f"{ia:<14} {files:<6} {byte_count:<10} {_human_bytes(byte_count)}"
        )
    lines.append("")
    lines.append("=== Resource Usage ===")
    lines.append(
        f"  mindspace total  files={total_files}  bytes={total_bytes}  "
        f"size={_human_bytes(total_bytes)}"
    )
    cs = conduit_storage_usage()
    lines.append(
        f"  conduit-storage  files={cs.file_count}  bytes={cs.byte_count}  "
        f"size={_human_bytes(cs.byte_count)}"
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
            enumerate_guildmasters,
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
                # Phase 5c-2 (ADR-0021): Guildmaster 在/不在を可視化。
                # Guildmaster axiom (guildmaster-only-spawn 等) が機能するかは
                # 「persona=guildmaster の Mind が居るか」で決まる (= 依存注入)。
                gms = enumerate_guildmasters(gname)
                gm_str = ", ".join(gms) if gms else "(none)"
                pending_str = (
                    "?" if inbox_unknown
                    else str(pending_by_guild.get(gname, 0))
                )
                sections.append(
                    f"  {gname}: members={len(members)} [{member_str}], "
                    f"guildmaster=[{gm_str}], pending={pending_str}"
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


def _parse_path_option(argv: list[str], name: str) -> Path | None:
    """`--name PATH` 解析 (`--snapshot` などと同じ流儀)。未指定は None。"""
    if name not in argv:
        return None
    idx = argv.index(name)
    if idx + 1 >= len(argv):
        print(f"[ERROR] {name} requires a path argument", file=sys.stderr)
        raise SystemExit(2)
    return Path(argv[idx + 1])


def _parse_str_option(argv: list[str], name: str) -> str | None:
    """`--name VALUE` の文字列引数を取り出す。無ければ None。

    Phase 5f Step 1 / ADR-0026: --since 等の string 引数用。既存の
    _parse_int_option / _parse_path_option と対称な薄い helper。
    """
    if name not in argv:
        return None
    idx = argv.index(name)
    if idx + 1 >= len(argv):
        print(f"[ERROR] {name} requires a value", file=sys.stderr)
        raise SystemExit(2)
    return argv[idx + 1]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    as_snapshot = "--snapshot" in argv
    as_prune = "--prune" in argv
    as_realm = "--realm" in argv
    as_flow = "--flow" in argv
    as_resource = "--resource" in argv
    as_anomaly = "--anomaly" in argv
    as_for_warden = "--for-warden" in argv
    as_trace = "--trace" in argv
    as_cost = "--cost" in argv
    as_status = "--status" in argv
    as_chain = "--chain" in argv
    as_mermaid = "--mermaid" in argv
    diff_a = _parse_path_option(argv, "--diff")
    diff_b = _parse_path_option(argv, "--against")

    # Phase 5f Step 1 / ADR-0026: --trace は他フラグ無視で時系列ビューのみ。
    # 全 JSONL を merge sort して人間可読 1 行に整形する。他の --realm 等とは
    # 独立 (--json と組み合わせない、人間可読限定)。
    if as_trace:
        sys.path.insert(0, str(Path(__file__).parent))
        from trace import cmd_trace  # noqa: PLC0415

        since = _parse_str_option(argv, "--since")
        return cmd_trace(since=since)

    # Phase 5g.B #172 chunk 2: --cost は mind_loop.cost event の per-Mind /
    # per-day / per-model 集計。--mind / --since / --json と組み合わせ可。
    if as_cost:
        sys.path.insert(0, str(Path(__file__).parent))
        from cost import cmd_cost  # noqa: PLC0415

        mind = _parse_str_option(argv, "--mind")
        since = _parse_str_option(argv, "--since")
        return cmd_cost(mind=mind, since=since, as_json=as_json)

    # Phase 5g.B #174: --status は「いまの Realm」を 1 view に集約。後追い
    # (--trace / --cost) と違い現時点の生死 / 進行 / 累計を返す。--json と
    # 組み合わせ可。`observe.py --status` だけで Realm の health overview が出る。
    if as_status:
        sys.path.insert(0, str(Path(__file__).parent))
        from status import cmd_status  # noqa: PLC0415

        return cmd_status(as_json=as_json)

    # Phase 5g.B #175: --chain は dispatch.sent / dispatch.acked event から
    # chain timeline を text or mermaid で表示。--from / --since と組み合わせ可。
    # --mermaid フラグで markdown 用の sequence diagram を出力。
    if as_chain:
        sys.path.insert(0, str(Path(__file__).parent))
        from chain import cmd_chain  # noqa: PLC0415

        from_mind = _parse_str_option(argv, "--from")
        since = _parse_str_option(argv, "--since")
        return cmd_chain(
            from_mind=from_mind, since=since, as_mermaid=as_mermaid,
        )

    now_epoch = time.time()

    # Phase 5d-3 (#68): --for-warden は履歴 / dispatch / resource / anomaly を
    # schema_version 付きの 1 つの JSON にまとめる。Mind 向けではなく Warden
    # 内部 / 人間運用者向けの **無制約観察** payload。
    if as_for_warden:
        sys.path.insert(0, str(Path(__file__).parent))
        from mind_scope import build_realm_report  # noqa: PLC0415

        threshold = None
        if "--inbox-threshold" in argv:
            threshold = _parse_int_option(argv, "--inbox-threshold", 10)
        w1_window = None
        if "--w1-window" in argv:
            w1_window = _parse_int_option(argv, "--w1-window", 3600)
        payload = build_realm_report(
            inbox_threshold=threshold,
            w1_window_seconds=w1_window,
            now_epoch=now_epoch,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    # Phase 5d-2 (#67): anomaly / snapshot diff。--anomaly と --diff は
    # 各々独立した小さなビュー。--anomaly は --prev-snapshot/--curr-snapshot
    # を併用すると I1 (stale 遷移) も含めて出す。
    if as_anomaly:
        sys.path.insert(0, str(Path(__file__).parent))
        from anomaly import (  # noqa: PLC0415
            DEFAULT_INBOX_BUILDUP_THRESHOLD,
            DEFAULT_W1_WINDOW_SECONDS,
            detect_all,
            format_signals_table,
            signals_to_json,
        )

        prev_path = _parse_path_option(argv, "--prev-snapshot")
        curr_path = _parse_path_option(argv, "--curr-snapshot")
        prev_payload = None
        curr_payload = None
        if prev_path and curr_path:
            from snapshot import load_snapshot  # noqa: PLC0415

            prev_payload = load_snapshot(prev_path)
            curr_payload = load_snapshot(curr_path)
        threshold = _parse_int_option(
            argv, "--inbox-threshold", DEFAULT_INBOX_BUILDUP_THRESHOLD
        )
        w1_window = _parse_int_option(
            argv, "--w1-window", DEFAULT_W1_WINDOW_SECONDS
        )
        signals = detect_all(
            prev_snapshot=prev_payload,
            curr_snapshot=curr_payload,
            inbox_threshold=threshold,
            w1_window_seconds=w1_window,
            now_epoch=now_epoch,
        )
        if as_json:
            print(
                json.dumps(
                    signals_to_json(signals), ensure_ascii=False, indent=2
                )
            )
        else:
            print(format_signals_table(signals))
        return 0

    if diff_a and diff_b:
        # --diff <prev> --against <curr> で snapshot 差分を出す。
        # 一般的な diff (added/removed/changed) を返す観察用 view。
        sys.path.insert(0, str(Path(__file__).parent))
        from anomaly import diff_snapshots  # noqa: PLC0415
        from snapshot import load_snapshot  # noqa: PLC0415

        prev_payload = load_snapshot(diff_a)
        curr_payload = load_snapshot(diff_b)
        result = diff_snapshots(prev_payload, curr_payload)
        if as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("=== Snapshot Diff ===")
            if result["added"]:
                print(f"  added ({len(result['added'])}):")
                for m in result["added"]:
                    print(
                        f"    + {m['mind_name']}  "
                        f"category={m.get('category')}  status={m.get('status')}"
                    )
            if result["removed"]:
                print(f"  removed ({len(result['removed'])}):")
                for m in result["removed"]:
                    print(
                        f"    - {m['mind_name']}  "
                        f"category={m.get('category')}  status={m.get('status')}"
                    )
            if result["changed"]:
                print(f"  changed ({len(result['changed'])}):")
                for m in result["changed"]:
                    print(f"    ~ {m['mind_name']}")
                    for k, (before, after) in m["fields"].items():
                        print(f"        {k}: {before} -> {after}")
            if not (result["added"] or result["removed"] or result["changed"]):
                print("  (no changes)")
        return 0

    if diff_a and not diff_b:
        print(
            "[ERROR] --diff requires --against <curr-snapshot>",
            file=sys.stderr,
        )
        return 2

    # Codex P2 (#94): 逆方向 (--against のみ) も明示的に reject する。
    # 旧実装は --diff 無しの --against を黙って通して default observation
    # view を出していたため、自動化スクリプトの引数ミスを検出できない不整合
    # があった。両方無 → default view、両方有 → diff、片方のみ → error の
    # 対称な三値判定にする。
    if diff_b and not diff_a:
        print(
            "[ERROR] --against requires --diff <prev-snapshot>",
            file=sys.stderr,
        )
        return 2

    # Phase 5d-1 (#66): dispatch フロー / リソース使用量。各々独立して
    # 動作する小さなビューなので、--realm より前に分岐する。
    # --flow は他フラグ無視で flow ビューのみ。--json と組み合わせ可。
    if as_flow:
        sys.path.insert(0, str(Path(__file__).parent))
        from dispatch_flow import (  # noqa: PLC0415
            aggregate_flow,
            flow_to_json,
            format_flow_table,
        )

        edges = aggregate_flow()
        if as_json:
            print(json.dumps(flow_to_json(edges), ensure_ascii=False, indent=2))
        else:
            print("=== Dispatch Flow ===")
            print(format_flow_table(edges))
        return 0

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
    elif as_resource:
        # Phase 5d-1 (#66): 既存 mind table を拡張し、BYTES / FILES 列 + 末尾に
        # Conduit storage バケットを併記。--json と組み合わせた場合は
        # 同じ「spawned mind 集合」(.mind-meta.md 持ち) を JSON で出す。
        # Codex P2 (#93): 旧実装は all_usage() を呼んでいたため `minds/`
        # 配下の dir 名規則を満たす全ディレクトリを集計に含めてしまい、
        # table 側の gather_observations() ベース (= .mind-meta.md 必須) と
        # Mind 集合が乖離する不整合があった。observations を共通の駆動軸に
        # することで「`--resource` と `--resource --json` が同じ Mind を
        # 報告する」性質を実装上で保証する。
        if as_json:
            sys.path.insert(0, str(Path(__file__).parent))
            from resource_usage import (  # noqa: PLC0415
                UsageBucket,
                _scan_dir_size,
                conduit_storage_usage,
                usage_to_json,
            )

            buckets: list[UsageBucket] = []
            for obs, _, _ in observations:
                mind_dir = _minds_dir() / obs.mind_name
                files, byte_count = _scan_dir_size(mind_dir)
                buckets.append(
                    UsageBucket(
                        name=obs.mind_name,
                        category="mindspace",
                        file_count=files,
                        byte_count=byte_count,
                    )
                )
            buckets.append(conduit_storage_usage())
            print(
                json.dumps(
                    usage_to_json(buckets), ensure_ascii=False, indent=2
                )
            )
        else:
            print(_format_table_with_resource(observations))
    elif as_json:
        print(_format_json(observations))
    else:
        print(_format_table(observations))
    return 0


if __name__ == "__main__":
    sys.exit(main())
