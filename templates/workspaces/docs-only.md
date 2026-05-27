---
workspace: docs-only
schema_version: "0.1"
purpose: 文書チーム向け。git 連携無し、Mindspace 内で markdown 編集のみ
vcs: none
allowed_cli: [bash]
---

# Workspace: docs-only

ai-org-os が同梱する **見本テンプレート** (ADR-0022 §5)。「**git を使わない開発組織**」が成立することを示すために存在する。

## 構成 (ADR-0022 §3)

| 項目 | 値 | 意味 |
|---|---|---|
| `vcs` | `none` | git / SVN / その他いずれも使わない |
| `mode` | (省略) | vcs=none では mode は意味を持たない |
| `repo` | (省略) | 同上 |
| `allowed_cli` | `bash` | ファイル編集に必要な最小限のみ |

## 想定する組織

- ドキュメントチーム (= 文書を書くだけ、コードを変更しない)
- 仮設実験 (ai-org-os の core 動作確認、git 連携をスキップしたい)
- 教育用デモ (= 開発環境の構成は意識せず、Mind の Dispatch だけ試したい)

## Mind の挙動

`spawn-mind.sh --workspace docs-only generic designer doc-writer-1` を叩くと:

1. Mindspace `~/.ai-org-os/minds/doc-writer-1/` が作成される (既存挙動)
2. **worktree は作られない** (vcs=none のため、`work/` subdir 無し)
3. Mind は Mindspace 内で markdown を編集 / 自身の Mindspace に note を残す
4. 他 Mind との連携は Dispatch (= Conduit Pillar) でのみ行う

これは **ADR-0022 確定前の挙動と等価** (= `default` テンプレと同じ no-op)。違いは `purpose` と `allowed_cli` がより明示的に「文書のみ」を示している点だけ。

## なぜ「見本」か

Workspace = C 依存注入の意味は「組織が**自由に**作業環境を選べる」こと。本テンプレは「**git を強制しない**」フレームワークの保証を体現するためのデモ:

- `developer-default` (git + worktree) — 主流
- `docs-only` (git 無し) — **別の可能性の例**
- `readonly-analysis` (git + shared) — もう 1 つの例

「自分の組織は git 使わないが ai-org-os を使えるのか?」という問いに「Yes、`docs-only` テンプレがある」と答えるための存在。

## 関連

- ADR-0022 §5 同梱テンプレートとカスタマイズ
- ADR-0019 「組織を git clone で配れる」(Workspace = C で実装される側面)
- `templates/workspaces/default.md` (no-op、後方互換用)
