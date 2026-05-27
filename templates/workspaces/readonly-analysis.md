---
workspace: readonly-analysis
schema_version: "0.1"
purpose: 分析 Mind 向け。target repo を shared で読むだけ、commit/push しない想定
vcs: git
repo: $AI_ORG_OS_TARGET_REPO
mode: shared
branch_prefix: analysis
allowed_cli: [git, bash, python3]
---

# Workspace: readonly-analysis

ai-org-os が同梱する **見本テンプレート** (ADR-0022 §5)。「**既存 repo を読むだけの Mind**」のための workspace。

## 構成 (ADR-0022 §3)

| 項目 | 値 | 意味 |
|---|---|---|
| `vcs` | `git` | git で repo を参照する |
| `repo` | `$AI_ORG_OS_TARGET_REPO` | 利用者が env var で指定する target repo |
| `mode` | `shared` | **worktree を作らず**、target repo を直接共有 (read-only 推奨) |
| `branch_prefix` | `analysis` | shared モードでは branch は作らないが、概念上の prefix |
| `allowed_cli` | `git, bash, python3` | `gh` は無し (PR / commit を出さない想定) |

## `mode: shared` の意味と注意

ADR-0022 §3 で定義した `mode: shared` は **「1 つの repo を複数 Mind が同時に触る」モード** を指す。`mode: worktree` (隔離) との対比:

| | worktree | shared |
|---|---|---|
| 各 Mind に branch | あり (隔離) | 無し (常に target repo の HEAD) |
| Mind 同士の干渉 | 物理的に不可 | あり得る (= 同時 commit で index lock 等) |
| 用途 | 開発 | 読み取り中心の分析 |

**実装上の注意 (Phase 5d-2)**: spawn-mind の現状は `mode: worktree` のみ実装。`mode: shared` を渡すと spawn-mind は (現時点では) **何もしない** = vcs=none と等価。Phase 5d / 6 以降で「shared mode は Mindspace 内に target repo の symlink を作る」等の実装を追加する余地を残している。

本テンプレは **Workspace template の柔軟性を示すための見本** で、actual な動作は今後の拡張で完成する。

## 想定する Mind

- コードレビュー Persona (read のみ、コメントを Dispatch で残す)
- 統計分析 Persona (repo の commit 履歴を集計)
- アーキテクチャ俯瞰 Persona (依存グラフを描く)

これらの Mind は **commit / push しない**。書き込みが必要になったら、Dispatch 経由で開発 Persona (developer-default workspace の Mind) に依頼する形。

## 利用方法

```bash
export AI_ORG_OS_TARGET_REPO=/home/me/some-codebase
bash runtime/pillars/lifecycle/spawn-mind.sh \
  --workspace readonly-analysis generic reviewer analyst-1
```

Mind は Mindspace 内で:
- Persona / Nexus 接続: `~/.ai-org-os/minds/analyst-1/`
- target repo を参照: `cd $AI_ORG_OS_TARGET_REPO; git log; git diff main~5..main`

## なぜ「見本」か

`developer-default` (= worktree) / `docs-only` (= vcs 無し) / **`readonly-analysis` (= shared)** の 3 つは「Workspace = C 依存注入」の 3 つの軸を示すデモ:

| 軸 | テンプレ |
|---|---|
| 書き込みあり、隔離 | developer-default |
| vcs 無し | docs-only |
| 読み取り中心、共有 | readonly-analysis |

利用者はこの 3 つを参考に自組織の workspace template を作る。

## 関連

- ADR-0022 §3 mode=worktree / shared の対比
- ADR-0022 §5 同梱テンプレートの位置づけ
- Phase 5d-2 (PR #100): worktree モード実装。shared モードは未実装
