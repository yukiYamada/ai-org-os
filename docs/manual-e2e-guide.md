# 手動 End-to-End ガイド

> 想定読者: 初めて ai-org-os Realm を立ち上げて動かす運用者 / 評価者。
> Phase 5b-2 (#75) までの全配管が通っていることを実体験で確認するためのガイド。

このガイドは「**人間が Issue を投げ → Conductor が観測 → Mind が自分で claim → frontmatter に痕跡が残る**」までの一連を 1 セッションで確認するための手順。
所要時間 約 10 分（初回 Docker build 含む）。

## 全体像

```
[1] docker compose up        Conductor (Container) が回り始める
       │
[2] submit-issue              人間が Inbox に Issue 投入
       │
[3] observe.py --realm        Conductor が Inbox 堆積を検知したことを確認
       │
[4] spawn-mind.sh             ホストで Mind の Mindspace + .mcp.json を配置
       │
[5] cd <mindspace> && claude  ホストの claude (ユーザー login) を起動
       │                       claude が .mcp.json 経由で nexus.py を stdio 起動
       │
[6] Mind が MCP tool 呼び出し  read_pending_issues → claim_issue
       │
[7] archive を確認             frontmatter に claimed_by が記録されている
       │
[8] kill-mind / docker down   後片付け
```

## 前提

| 項目 | 確認方法 |
|---|---|
| Docker Desktop が動く | `docker --version` |
| ホストに Python 3.10+ | `python3 --version` |
| **ホストで claude code login 済** | `claude` 起動時に再 login を要求されない |
| (任意) ANTHROPIC_API_KEY | 未設定でも OK。設定すれば Conductor の Judgment が実 Claude (haiku) で動く |

依存の理由 (ADR-0016 と整合):
- mcp は **ホスト** に居る Mind が nexus.py を起動するために必要 → `runtime/host/setup.sh` で venv に install される
- anthropic SDK は **Container** に居る Judgment Pillar 専用 → Dockerfile で install 済

## 手順

### [0] ホスト setup を 1 回だけ叩く (Phase 5b-3 / 5b-4)

```bash
bash runtime/host/setup.sh
```

これで `$AI_ORG_OS_HOME` (default `~/.ai-org-os/`) に以下が生成:
- `venv/` — host Python venv (mcp 入り)
- `config.env` — OS ネイティブパス解決済
- `minds/`, `issues/{inbox,archive}/`, `snapshots/`, `conduit-storage/` — 状態置き場

**repo (`~/pgit/ai-org-os/`) には runtime state が一切作られない** (ADR-0018)。

別の場所を使いたいなら:
```bash
export AI_ORG_OS_HOME=/custom/path
bash runtime/host/setup.sh
```

再セットアップ (mcp の major upgrade 等):
```bash
bash runtime/host/setup.sh --recreate-venv
```

### [1] Realm を起動する

```bash
cd runtime/realm
docker compose up -d --build       # 初回は 1-2 分
docker compose ps                  # STATE が 'running'
docker logs -f ai-org-os-realm     # Conductor の cycle が見える
```

期待出力（cycle 1〜2）:
```
[conductor.sh] launching python3 /realm/runtime/pillars/conductor/conductor.py
[conductor] starting loop (period=30s, max_cycles=0)
[conductor][cycle 1] pending=0 snapshot=ok judgment=skipped|fallback-no-key actions={}
```

`Ctrl-C` で logs から抜ける（コンテナは生き続ける）。

### [2] Issue を投入する

```bash
cd <repo root>
bash runtime/pillars/inbox/submit-issue.sh "Realm E2E" "Mind に claim させる検証用"
```

出力:
```
20260524T053341Z-794544-85f19450
```

これが `issue_id`。フォーマットは `YYYYMMDDTHHMMSSZ-<microsecond>-<hex>` (ADR-0017 / Codex P2 PR #70 fix)。

### [3] Conductor が検知したか観測する

```bash
# 30 秒待ってから（次 cycle まで）
python3 runtime/pillars/observation/observe.py --realm
```

期待: 「`=== Inbox Queue (1 pending) ===`」と「`=== Conductor ===`」セクションで `pending: 1` が表示される。
Mind がまだ居ないので Realm Observatory は `No minds spawned.`。

### [4] Mind を spawn する

```bash
bash runtime/pillars/lifecycle/spawn-mind.sh generic designer alice
```

期待出力:
```
[spawn-mind] Creating Mindspace: <repo>/runtime/minds/alice
[spawn-mind] Installing Persona 'designer' as CLAUDE.md
[spawn-mind] Installing Nexus MCP config (.mcp.json) using 'python3', bound to 'alice'
[spawn-mind] Mind 'alice' is ready at <repo>/runtime/minds/alice
```

生成されたファイル:
- `runtime/minds/alice/CLAUDE.md` ← Persona (designer.md のコピー)
- `runtime/minds/alice/.mind-meta.md` ← kind / persona / spawned_at
- `runtime/minds/alice/.mcp.json` ← Nexus 接続設定 (AI_ORG_OS_MIND_NAME=alice で identity binding)

### [5] Mind 内で claude を起動する

```bash
cd runtime/minds/alice
claude
```

これで Mind の claude セッションが立ち上がる。**ホストユーザーの login session を使う** (ADR-0016)。

claude が起動したら:
- `CLAUDE.md` (designer Persona) を読み込む
- `.mcp.json` を読んで nexus サーバーを stdio で起動
- `mcp` package を **ホストの python3** で実行 (要 `pip install mcp`)

### [6] MCP tool を Mind に叩かせる

claude のプロンプトで例えば次を入力:

```
nexus MCP server の read_pending_issues を呼んで、Realm に届いている人間 Issue を一覧化してください。
```

claude が `read_pending_issues()` を呼び、[2] で投入した Issue が JSON で返ってくる。
続けて:

```
alice (自分) として claim_issue を呼んで上記 Issue を取り込んでください。
mind_name は "alice"、issue_id は <Issue の ID>。
```

成功すると `{ok: true, issue_id, title, claimed_by: "alice", body, archived_path}` が返る。

### [7] archive に痕跡が残ったことを確認

別ターミナルで:

```bash
cat runtime/issues/archive/<issue_id>.md
```

期待:
```yaml
---
issue_id: 20260524T053341Z-794544-85f19450
title: Realm E2E
submitted_at: 2026-05-24T05:33:41Z
submitter: human
priority: p2
claimed_by: alice
claimed_at: 2026-05-24T05:34:21Z
---

Mind に claim させる検証用
```

`claimed_by: alice` と `claimed_at` が追記されている = **Mind が層 B の責務として自分で取り込んだ痕跡** が残った (ADR-0017 §1)。

### [8] 後片付け

```bash
# claude セッションを exit (Mind の claude を抜ける)
exit                    # claude プロンプト内で

# Mind を破壊 (Mindspace ごと削除)
bash runtime/pillars/lifecycle/kill-mind.sh alice

# Realm container を停止
cd runtime/realm && docker compose down

# テスト Issue を削除 (任意)
rm runtime/issues/archive/<issue_id>.md

# snapshot を整理 (任意)
python3 runtime/pillars/observation/observe.py --prune --ttl-days 0
```

## 期待される観察

| シーン | 観察 | 意味 |
|---|---|---|
| Conductor が cycle ごとに log | `pending=N` が増減する | Inbox の堆積を観測している |
| `--realm` 出力 | Inbox Queue / Conductor 各セクション | 統合ビューが疎通 |
| Mind が claim 後 | archive ファイルに `claimed_by` | 層 B (Mind 自身が組織を動かす) が動いた |
| Conductor は claim **しない** | claim 痕跡は Mind 名で | ADR-0017 §4 (Conductor は層 A 限定) |

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `mcp` not found in Mind の claude | ホストで `pip install mcp` または `bash runtime/pillars/conduit/start.sh --setup-only` で venv 作成して `AI_ORG_OS_PYTHON` を venv の python に向ける |
| Conductor logs に `fallback-no-key` | ANTHROPIC_API_KEY 未設定。Realm は動くが Judgment が rule-based に。実 Claude を使うなら env をセット |
| `--realm` で Conductor が "not running yet" | container がまだ最初の cycle を完了してない。30 秒待つ |
| claim_issue で `forbidden` | mind_name が `.mcp.json` の AI_ORG_OS_MIND_NAME と不一致 (ADR-0008 identity binding が拒否) |

## 関連 ADR

- ADR-0006: Phase 5 設計
- ADR-0008: identity binding
- ADR-0011: Pillar 編集不可
- ADR-0012: 人間 = Realm 外
- ADR-0014: Realm 物理境界
- ADR-0016: Container = コア、ホスト = Mind
- ADR-0017: Warden 監視 vs ジョブ監視（本ガイドが体感的に確認するルール）

## このガイドが通る = 何が確認できたか

- Phase 5a (Pillar 群) + Phase 5b-1 (Conductor) + Phase 5b-2 (Mind 向け Inbox MCP) の **全配管が通る**
- ADR-0016 (Container / ホスト境界) が実装に正しく落ちている
- ADR-0017 (層 A / 層 B) が観察可能になっている (Mind が自分で claim する痕跡が残る)

ここから先（Mind が claim 後に何をするか / 完了通知 / 他 Mind 引継ぎ）は Persona / Dispatch の話なので **層 B = 組織として構築するフェーズ** に入る。
