---
workspace: default
schema_version: "0.1"
purpose: 後方互換用の no-op テンプレート。git 連携なし、Mindspace のみ作成
vcs: none
---

# Workspace: default

ai-org-os が同梱する **後方互換用 no-op テンプレート** (ADR-0022 §5)。

## 役割

`spawn-mind.sh` に `--workspace` 引数を渡さなかった場合、かつ Guild manifest に
`workspace:` フィールドが無い場合に解決されるフォールバック先 (ADR-0022 §4)。

- **`vcs: none`** = git 連携を行わない
- worktree も作らない
- 結果として **既存の spawn-mind 挙動 (Mindspace のみ作成、git 触らず) を維持**

## いつ別の workspace を使うか

- Mind に **git/GitHub で開発させたい** → `--workspace developer-default` を渡す
  か、Guild manifest に `workspace: developer-default` を書く
  (PR #5 で同梱予定)
- **組織全体の既定** を変えたい → 利用者が overlay で
  `$AI_ORG_OS_HOME/workspaces/default.md` を作って書き換える
  (例: `vcs: git, mode: worktree, repo: ...` にして全 Mind を worktree モードに)

## 関連

- ADR-0022 §4-5: Workspace 解決順とデフォルトテンプレート方針
- `runtime/pillars/registry/workspace.py`: 本テンプレを parse する Pillar
- `runtime/pillars/lifecycle/spawn-mind.sh`: 本テンプレを利用する spawn 経路
