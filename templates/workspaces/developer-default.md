---
workspace: developer-default
schema_version: "0.1"
purpose: 一般的な開発組織向け。GitHub on host repo + git/gh CLI + worktree per Mind
vcs: git
repo: $AI_ORG_OS_TARGET_REPO
mode: worktree
branch_prefix: mind
allowed_cli: [git, gh, bash, python3]
---

# Workspace: developer-default

ai-org-os が同梱する **主流ケース用テンプレート** (ADR-0022 §5)。「Mind は GitHub に host された git repo で開発する」想定の組織向け。

## 構成 (ADR-0022 §3)

| 項目 | 値 | 意味 |
|---|---|---|
| `vcs` | `git` | git で版管理する |
| `repo` | `$AI_ORG_OS_TARGET_REPO` | 利用者が env var で指定する target repo の絶対 path |
| `mode` | `worktree` | 各 Mind は別 worktree (= 別 branch) を持ち、隔離が物理保証される |
| `branch_prefix` | `mind` | spawn 時に `mind/<mind-name>` の branch が自動作成される |
| `allowed_cli` | `git, gh, bash, python3` | Persona に対するヒント (機械強制ではない、ADR-0022 §6) |

## 利用方法

### 1. target repo の path を env var で渡す

```bash
export AI_ORG_OS_TARGET_REPO=/home/me/my-project
bash runtime/pillars/lifecycle/spawn-mind.sh \
  --workspace developer-default generic designer worker-1
```

spawn-mind は `workspace.py` 経由で `repo: $AI_ORG_OS_TARGET_REPO` を展開し (ADR-0022 §2 / PR #100 Codex P2)、`/home/me/my-project` を target にする。

### 2. Mind は自分の Mindspace 内で 2 つの cwd を使い分ける

| 場所 | 用途 |
|---|---|
| `~/.ai-org-os/minds/worker-1/` | Persona (CLAUDE.md) / Nexus 接続 (.mcp.json) を読む |
| `~/.ai-org-os/minds/worker-1/work/` | **git worktree**。Mind はここで開発する (`git status` / `git diff` / `git add` / `git commit`) |

### 3. PR を出す

Mind が作業を完了したら:

```bash
cd ~/.ai-org-os/minds/worker-1/work
git push -u origin mind/worker-1
gh pr create --base main --head mind/worker-1
```

### 4. kill すると worktree も解除される

```bash
bash runtime/pillars/lifecycle/kill-mind.sh worker-1
```

kill-mind が `Mindspace/work/.git` (worktree marker) を検出し、`git worktree remove --force` で target repo の `.git/worktrees/worker-1` 登録も clean up する (Phase 5d-3、PR #101)。

## Guild manifest 経由での既定指定

利用者は Guild manifest に `workspace: developer-default` と書くことで、その Guild に spawn された Mind は **デフォルトで** 本テンプレを使うようになる (ADR-0022 §4、Phase 5d-4、PR #102):

```yaml
# $AI_ORG_OS_HOME/guilds/<my-team>/manifest.md
---
guild: my-team
schema_version: "0.1"
workspace: developer-default
kinds: [generic]
personas: [designer, implementer, reviewer]
---
```

## カスタマイズ

別組織が「branch prefix を `wt/` にしたい」「`bun`/`pnpm` も使いたい」場合、`$AI_ORG_OS_HOME/workspaces/developer-default.md` を overlay で書き換える (kinds / personas と同じ overlay パターン、ADR-0020)。

例: 利用者 overlay:

```yaml
---
workspace: developer-default
schema_version: "0.1"
purpose: my-team's custom dev environment
vcs: git
repo: $MY_REPO_PATH
mode: worktree
branch_prefix: wt
allowed_cli: [git, gh, bun, pnpm, python3]
---
```

## 関連

- ADR-0022 §3 物理レイアウト (Mindspace/work/ = worktree)
- ADR-0022 §4 解決順 (引数 > Guild manifest > default)
- ADR-0022 §5 同梱テンプレートの位置づけ
- `runtime/pillars/lifecycle/spawn-mind.sh --workspace`
- `runtime/pillars/lifecycle/kill-mind.sh` (worktree 連動)
