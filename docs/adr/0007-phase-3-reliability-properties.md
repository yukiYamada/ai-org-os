# ADR-0007: Phase 3 Nexus の信頼性プロパティを「現状妥協」で確定する

> 想定読者: Phase 3 の Nexus を運用する人、信頼性が必要な機能を Phase 5+ で追加するメンテナ、Issue #21 の議論を追う人。

## Status

**Accepted** — 2026-05-23

## Context（背景）

[ADR-0005](./0005-phase-3-mcp-direct-with-nexus.md) で Phase 3 = MCP 直行（Nexus）を Accepted、PR #23 で実装した。
このとき以下を「Phase 3 非スコープ」と宣言したが、**個別の方針が確定していない**まま GitHub Issue #21 に残していた。

- **配送保証**: 送信したメッセージが必ず届く保証はあるか？
- **順序保証**: 1, 2, 3 と送った順で読めるか？
- **TTL（Time To Live）**: 古い archive を自動削除するか？
- **dead letter**: 不在の recipient 宛メッセージはどうするか？

これらは「ちゃんと作った企業向けメッセージング」（RabbitMQ, Kafka 等）が考える項目。
Nexus は MCP 経由の Mind 間通信を最小実装で動かす目的なので、ここを「**現状妥協で動かす**」と明文化し、Issue #21 を Close するのが本 ADR の目的。

## Decision（決定）

Phase 3 の Nexus は、4 項目すべてについて **「現状の素朴な挙動のまま」** で確定する。
強化は Phase 5+（Warden 導入）で必要性が顕在化した時に再設計する。

### 1. 配送保証: **at-most-once（妥協）**

| 状態 | Phase 3 の挙動 |
|---|---|
| 送信ファイルが書ける | OK、`send_dispatch` は `ok: true` を返す |
| 送信ファイルが書けない（ディスク満杯・権限・不正引数等） | `ok: false` で即座にエラー伝播。送信側は失敗を検知できる |
| 書いた後に第三者がファイルを消す | 検知不可、メッセージは消失する |
| 受信者が `read_inbox` しないまま放置 | メッセージは inbox に残り続ける（消えはしない） |

**強化候補（Phase 5+）**: Warden が「送信者 → 受信者 ack」を追跡し、未 ack が一定時間続いたら送信者に再試行を促す。

### 2. 順序保証: **なし**

- `inbox/` のファイル一覧順 = `sorted(glob('*.md'))` 順 = msg_id の文字列順
- msg_id 形式は `YYYYMMDDTHHMMSSZ-<sender>-<random>` なので、**事実上タイムスタンプ順**になる
- ただし秒未満の精度はないので、同一秒内の複数送信は順序が乱れる可能性
- 並行送信や複数送信者の場合も乱れる可能性

**強化候補（Phase 5+）**: Warden がシーケンス番号を発行する、または受信側が msg_id を見て並び替える。

### 3. TTL: **なし、archive は永久保存**

- ack 済みメッセージは `archive/<recipient>/<msg-id>.md` に移されて、削除されない
- ストレージ容量問題は、Phase 5 以降で運用実績が出てから設計する
- 痕跡を残すこと自体は Axiom 「共有はプロセスを踏む」の証拠として価値がある

**強化候補（Phase 5+）**: Warden が cron 的に「N 日経過した archive を削除」を実装、もしくは external storage への移送。

### 4. dead letter: **なし、不在 recipient 宛も保存**

- `send_dispatch(to_mind="存在しない-mind")` を呼ぶと、Nexus は `inbox/存在しない-mind/` を作って保存する
- 「存在しない Mind 」を Nexus は知らない（Mind 一覧は Warden の責務、ADR-0006 参照）ので、検証できない
- 結果: 誰も読まない孤児メッセージが溜まる可能性
- 受信者がいつか spawn された時にメッセージを発見できる、というメリットもある（仮にそういう運用なら）

**強化候補（Phase 5+）**: Warden に Mind 一覧を問い合わせ、不在なら `send_dispatch` を拒否、または `dead-letter/` に振り分ける。

## 検知能力の現状（参考、Issue #21 の壁打ちで整理）

| シナリオ | 現状の検知 |
|---|---|
| 送信時にファイル書けない | ✅ `send_dispatch` が `ok: false` |
| 送ったメッセージが第三者削除 | ❌ |
| 受信側が `read_inbox` しない | ❌（不可侵原則の必然） |
| 受信側 Mind が kill された後、未読 inbox の扱い | ❌（孤児化、警告なし） |
| archive 後に消える | ❌ |

「送信瞬間の失敗だけ即座に分かるが、その後は追跡できない」。
**消失検知は実装しない**判断（運用上、Warden / 管理者 Mind が責任を持つ領域）。

## Consequences（影響）

### ポジティブ
- Phase 3 の Nexus 実装が「最小で出荷可能」になる（信頼性プロパティが明文化された）
- Issue #21 を Close できる
- 強化が必要になった時の検討起点（Phase 5+ Warden 責務）が明確

### ネガティブ
- メッセージング基盤としては素朴で、本番運用には足りない
- 誤った Mind 名宛の dispatch が孤児化する（運用で気づきにくい）
- ストレージは時間と共に肥大化する（Phase 5+ の課題）

### リスク
- 「最小で動く」と「本番品質」のギャップが大きいので、利用者が誤解する可能性
  - 対応: `runtime/nexus/README.md` の「非スコープ」節で明示済み、本 ADR で詳細化

## 関連

- [ADR-0005](./0005-phase-3-mcp-direct-with-nexus.md) — Phase 3 = MCP 直行（実装根拠）
- [ADR-0006](./0006-phase-5-realm-warden-guildmaster.md) — Phase 5 = Realm + Warden（強化候補の担い手）
- Issue #21 — 本 ADR で Close
- Issue #19 — Nexus 認可機構（別 PR で実装）
- Issue #20 — MCP Resources / Prompts（Phase 5 / Warden 責務で実装、別途）
