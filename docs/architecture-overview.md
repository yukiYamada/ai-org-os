# ai-org-os アーキテクチャ俯瞰図

> 想定読者:
> - 初めて ai-org-os を読み始める人
> - 全体の物理境界・責務分担・永続化境界を 1 枚で把握したい人
>
> 本書は **現状のスナップショット**。判断の根拠は ADR を、運用手順は `manual-e2e-guide.md` を参照。
> ADR と矛盾しそうになったら **ADR が正**（本書を更新する）。

## 一枚図（Phase 5b-4 時点）

```
  外部 (Realm 外)                                    人間 = ADR-0012 監督者
  ─────────────────────────────────────────────────────────────────────────
        │ submit-issue          observe.py --realm        spawn-mind
        │ (層A 入口へ投入)        (層A 観測ビュー読む)      (層A: Mindspace 作る)
        ▼                              ▲                       │
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ホスト OS                                                            ▼
                                                          ┌──────────────────┐
                                                          │ Mindspace        │
                                                          │ (層B = Mind の家) │
                                                          │  CLAUDE.md       │
                                                          │  .mcp.json       │
                                                          │  ホスト claude    │
                                                          │  ▲ login session │
                                                          └─────┬────────────┘
                                                                │ stdio (MCP)
   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─
   Realm Container                                              ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │  Conduit (MCP) ◀─── read_pending_issues / claim_issue を受ける       │
   │      │                                                              │
   │      ▼                                                              │
   │  Inbox ◀─── submit-issue (人間 → 棚)                                 │
   │  Archive ◀── claim 後 frontmatter に claimed_by が刻まれる            │
   │                                                                     │
   │  Conductor (心拍 30s) ─┬─ Observation : pending 数 / snapshot         │
   │   ↑ ココが層A           ├─ Judgment    : SDK 直叩き (haiku / fallback) │
   │                        ├─ Registry    : Kind カタログ                │
   │                        └─ Lifecycle   : spawn-mind 等 (実体はホスト) │
   │                                                                     │
   │  ※ claude CLI は Container 内には居ない (ADR-0009/0016)              │
   └─────────────────────────────────────────────────────────────────────┘

  ─────────────────────────────────────────────────────────────────────────
  永続化 (ADR-0018):
    framework (immutable) : ~/pgit/ai-org-os/   (repo, git tracked)
    runtime state (mutable): ~/.ai-org-os/      ($AI_ORG_OS_HOME)
        ├ venv/   minds/   issues/{inbox,archive}/
        └ snapshots/  conduit-storage/

  責務 (ADR-0017):
    層 A = Warden  : 環境を維持・観測する (Pillar 群)
    層 B = Mind    : 組織として仕事を取り合う (pull model、自発 claim)
    人間            : Realm 外から submit / observe / spawn / kill のみ

  欠けている (next):
    ・Mind が claim 後に「何をやる」 (Persona の肉付け)
    ・Mind 同士の Dispatch ベース連携 (Phase 5c)
    ・guildmaster Persona (進捗管理を Mind 圏内で完結させる)
```

## 3 軸の読み方

世界はこの 3 軸の重ね合わせ。図を読むときも、ADR を読むときも、この 3 軸を意識すると迷子にならない。

| 軸 | カテゴリ | 根拠 ADR |
|---|---|---|
| **物理軸** | ホスト / Container / 外部 | ADR-0014, ADR-0016 |
| **責務軸** | 人間 (Realm 外) / Warden = Pillar 群 / Mind | ADR-0012, ADR-0017 |
| **時間軸** | framework (静的・git tracked) / runtime state (動的・`$AI_ORG_OS_HOME`) | ADR-0018 |

## 現状の「導線」整理

### 人間 → 組織への依頼導線

- ✅ **入口はある**: `submit-issue.sh` → Inbox Pillar (Warden の棚)
- ❌ **能動 dispatch は無い**: Warden は「誰にやらせるか」を決めない。これは ADR-0017 の意図的決定
- 🔄 **pull model**: Mind が `read_pending_issues` → `claim_issue` で自発的に取りに来る

つまり Warden は「投入を受け取って棚に並べる」までが責務。**「誰がやるか」を決めるのは組織 (Mind 集合) 自身** であって、それを Warden に持たせると本旨 (組織は Mind の集合で構築する) が崩れる。

### 観測導線

- ✅ `observe.py --realm` で「Inbox / Conductor / Mind」を統合ビューで見れる (層 A 観測)
- ⚠️ Dispatch フロー可視化 / リソース使用量 / Axiom 違反検知 / 履歴比較はまだ無い → Observation v0.2〜v1.0 (#66 / #67 / #68)

### Mind ライフサイクル導線

- ✅ `spawn-mind.sh` で Mindspace + Persona + .mcp.json を配置
- ✅ ホストの `claude` (login session) で起動 → ADR-0016「Container = コア / ホスト = Mind」
- ✅ identity binding で別 Mind 名なりすましは拒否 (ADR-0008)
- ✅ `kill-mind.sh` で破壊

## 関連 ADR (詳細はこちら)

| ADR | テーマ |
|---|---|
| ADR-0001 | ai-org-os は開発組織の不変項を定義するフレームワーク |
| ADR-0010 | Warden は機能の集合体、観測は 2 種類 |
| ADR-0011 | Pillar 命名 / 編集不可 / Mind との境界 |
| ADR-0012 | 人間 = Realm 外監督者 |
| ADR-0014 | Realm 物理境界 (A/B/C/D カテゴリ) |
| ADR-0016 | Mind 認証経路 / Container = コア・ホスト = Mind |
| ADR-0017 | Warden 監視 (層 A) と ジョブ監視 (層 B) の分離 |
| ADR-0018 | framework (repo) と runtime state (`$AI_ORG_OS_HOME`) の物理分離 |

## 関連ドキュメント

- `docs/manual-e2e-guide.md` — 10 分で全配管を体験する手順書
- `runtime/README.md` — ディレクトリ階層
- `runtime/pillars/README.md` — Pillar 一覧と編集不可宣言
- `CLAUDE.md` (repo root) — セッションで踏み外しがちなパターン
