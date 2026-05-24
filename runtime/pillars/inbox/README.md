# Inbox Pillar

> 想定読者: Realm に Issue を投入したい人間、Warden が Issue を消費するフローを実装する人、Phase 5a-5 を読む人。

**Inbox Pillar は ai-org-os における人間 → Realm の入力経路**。
人間が依頼を書き込み、Warden（および Warden 配下の Mind）がそれを消費する境界。

詳細な決定背景:
- [ADR-0006](../../../docs/adr/0006-phase-5-realm-warden-guildmaster.md) §6 (Phase 5a 達成判定)
- [ADR-0012](../../../docs/adr/0012-human-position-outside-realm.md) §3 (人間 → Warden 入力経路)
- [ADR-0013](../../../docs/adr/0013-failure-handling-and-failsafe.md) §1 F4 (人間制御チャンネル)
- [ADR-0014](../../../docs/adr/0014-realm-physical-boundary.md) §3 D (穴あき層 / 人間制御領域)

## なぜ「ホスト fs に投入」を選んだか

ADR-0006 §6 が示す 3 案のうち、本 Pillar は **(a) ホスト fs に投入** を採用する。

| 案 | 投入経路 | 採否 |
|---|---|---|
| (a) ホスト fs に `runtime/issues/inbox/` | bind mount で Realm 内から自然に見える。HTTP/webhook 不要 | **採用** |
| (b) GitHub Issue webhook | 外部依存（GitHub）が要る、認証・公開エンドポイントが要る | 見送り（将来オプション） |
| (c) 別 MCP server を Warden が listen | Warden が常駐 listener を持つ必要がある | 見送り（複雑） |

採用理由:
- ADR-0014 §4 の「穴あき層」と整合（ホスト fs は bind mount で Realm から見える）。
- HTTP server / webhook が要らないので攻撃面が増えない。
- ファイルベースなので Conduit Pillar のメッセージング設計と一貫した（frontmatter + Markdown）。

## 提供する API

| 関数 | 役割 |
|---|---|
| `submit_issue(title, body, *, priority, submitter)` | inbox に Issue を 1 件投入する（atomic write）|
| `list_pending_issues()` | inbox の未処理 Issue を投入順で返す |
| `claim_issue(issue_id)` | inbox → archive に rename して「処理開始」をマーク |

シェル経由（人間向け）:
```bash
./runtime/pillars/inbox/submit-issue.sh "短いタイトル" "本文" [priority] [submitter]
```

Python CLI（動作確認用）:
```bash
python3 runtime/pillars/inbox/inbox.py list
python3 runtime/pillars/inbox/inbox.py submit "title" --body "body" --priority p1
python3 runtime/pillars/inbox/inbox.py claim 20260524T120000Z-abcdef01
```

## ストレージ（裏側）

```
runtime/issues/
├── inbox/<issue_id>.md       未処理（人間が投入、または submit_issue が書く）
├── archive/<issue_id>.md     claim 後（Warden が処理を引き取った）
└── .gitkeep                  ディレクトリだけ tracked（中身は .gitignore で除外）
```

`<issue_id>` は内部生成（`YYYYMMDDTHHMMSSZ-<8 hex>`）。
**外部から issue_id を渡す API は存在しない**（path traversal 防御）。

Issue ファイルの形式（Conduit Pillar の Dispatch と同じく frontmatter + Markdown）:

```markdown
---
issue_id: 20260524T120000Z-abcdef01
title: 短いタイトル
submitted_at: 2026-05-24T12:00:00Z
submitter: human
priority: p1
---

# Body

詳細な依頼内容。Warden / 判断 Claude / Mind に渡される。
```

## 入力検証

| フィールド | 制約 |
|---|---|
| `title` | 1〜200 文字、改行（`\n` / `\r`）不可 |
| `body` | 文字列（Markdown 可、長さ制限なし、改行 OK）|
| `priority` | `p0` / `p1` / `p2` / `p3` のいずれか |
| `submitter` | `[A-Za-z0-9._-]{1,64}` （spawn-mind.sh と conduit/storage.py に揃える）|

issue_id はファイル名そのものになるため、形式違反を `claim_issue` でも厳格に弾く。

## セキュリティ視点

- **path traversal 防御**: issue_id は内部生成のみ。`submit_issue` には `issue_id` 引数が存在しないので、外部から `../escape` を渡す経路がそもそも無い。
- **二重 claim 防御**: `claim_issue` は `Path.rename` を使う。POSIX 上 atomic なので、2 並行 claim でも先着 1 つだけ成功し、もう一方は `IssueNotFoundError`。
- **atomic write**: `submit_issue` は tmp に書く → `os.link` で final path を予約 → tmp unlink、のパターン（Conduit / Observation Pillar と同じ）。書き込み中断による壊れたファイルは inbox に残らない。
- **frontmatter 偽装の防御**: `list_pending_issues` はファイル名と frontmatter の `issue_id` が一致しないファイルを skip する。手書きで偽装したファイルを置いてもパースされない。
- **書き込み権限**: Inbox は「人間制御チャンネル」（ADR-0013 §1 F4）。Mind は Inbox に書き込んではいけない。書き込み権限分離は v0.1 では文書化のみで強制しないが、Mind の Persona と `.mcp.json` には Inbox 系ツールを露出させないことで運用的に分離する。

## Warden との接続（v0.1）

本 Pillar は「投入された Issue が読み出せること」までを担保する。
受信検知から実際に判断 Claude / Mind に渡す orchestration は Phase 5b（別 Issue）で扱う。
v0.1 では `list_pending_issues()` を Warden 側のループが叩く形（pull モデル）で十分。

将来 Phase 5b で：
- Warden が一定間隔で `list_pending_issues()` を pull
- 未処理 Issue があれば `claim_issue()` → 判断 Claude（Judgment Pillar）に渡して assignment 決定
- 決定された Mind に Conduit Pillar 経由で Dispatch

を組む想定。

## 動作確認

```bash
# 単体テスト
cd runtime/pillars/inbox
python3 -m unittest discover -p 'test_*.py' -v

# 一括テスト
./runtime/tests/run-tests.sh    # test-inbox-unit.sh が含まれる

# スモーク
./runtime/pillars/inbox/submit-issue.sh "テスト" "本文"
python3 runtime/pillars/inbox/inbox.py list
python3 runtime/pillars/inbox/inbox.py claim <id>
```

## Phase 5a-5 のスコープと非スコープ

- スコープ:
  - `submit_issue` / `list_pending_issues` / `claim_issue` の 3 関数
  - `submit-issue.sh`（人間向けシェル）
  - 入力検証 / atomic write / 二重 claim 防御
- 非スコープ（Phase 5b 以降）:
  - Warden の常駐ループによる Issue 自動引き取り
  - 判断 Claude への自動委譲
  - 優先度ベースの再ソート / SLA
  - リトライ / dead letter
  - GitHub Issue / webhook ブリッジ
