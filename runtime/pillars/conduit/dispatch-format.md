# Conduit Dispatch ファイルフォーマット (frozen contract)

> 想定読者:
> - Observation Pillar など、Conduit storage を読み取る他 Pillar の実装者
> - Conduit Pillar 自体のメンテナ (このフォーマットを変える時は破壊的変更扱い)
> - 将来 dispatch を analytics / replay する人

本書は **Conduit Pillar が `$AI_ORG_OS_HOME/conduit-storage/{inbox,archive}/<to>/<msg_id>.md` に書き出すファイル形式** を契約として凍結する。Observation Pillar v0.2 (#66) でこのファイル群を frontmatter のみ走査するため、依存元として **形式が後方互換に変わる保証を明文化**しておく。

実装の単一参照点は `runtime/pillars/conduit/storage.py` の `Nexus.send_dispatch`。本書はその時点のフォーマットを文章として固定する。

## ファイルパス

```
$AI_ORG_OS_HOME/conduit-storage/inbox/<to_mind>/<msg_id>.md      # 未 ack
$AI_ORG_OS_HOME/conduit-storage/archive/<to_mind>/<msg_id>.md    # ack 済 (read_inbox から消える)
```

- `<to_mind>`: recipient Mind 名。`storage._validate_mind_name` で `[A-Za-z0-9._-]{1,64}` に制限
- `<msg_id>`: `storage._gen_msg_id(from_mind)` 生成。形式は `<YYYYMMDDTHHMMSSZ>-<6digits>-<8hex>` (例: `20260524T120000Z-123456-deadbeef`)。同名衝突は実質的に発生しない (時刻 + マイクロ秒 + 短ハッシュの三重)

inbox から archive への移動は `Nexus.ack_dispatch` が `os.replace` 相当で実施。アトミック (同一 fs 内 rename) で **inbox と archive に同 msg_id が同時に存在しない** ことが保証される。

## ファイル内容

UTF-8 / LF / BOM 無し。

```markdown
---
from: <sender mind_name>
to: <recipient mind_name>
topic: <subject line, single line>
dispatched_at: <YYYY-MM-DDTHH:MM:SSZ>
msg_id: <see above>
---

<body markdown, any length, may contain --- in body section>
```

### frontmatter フィールド契約

| key | type | 由来 | 保証 |
|---|---|---|---|
| `from` | string | `send_dispatch.from_mind` (identity binding 経由検証済) | `_VALID_NAME_RE` に合致、空ではない |
| `to` | string | `send_dispatch.to_mind` (regex 検証済) | 同上、ディレクトリ名と一致 |
| `topic` | string | `send_dispatch.topic` (現状 sanitize なし) | 単一行 (改行を含まない、`send_dispatch` の入力 schema 上の前提) |
| `dispatched_at` | ISO 8601 UTC | `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` | `Z` サフィックス付き秒精度 UTC |
| `msg_id` | string | `_gen_msg_id` | ファイル名 (拡張子除く) と一致 |

frontmatter は **必ず 2 個目の `---` 行で終わる**。本文側の `---` は frontmatter 終端と誤認しない (Observation Pillar 等のパーサは「冒頭の `---` から次の `---` まで」のみを frontmatter として扱う)。

## 後方互換のコミットメント

本書の表で **「保証」列に書かれた条件は変更しない**。フィールド追加は許容するが、以下を守る:

1. **既存フィールドを削除しない / 名前変更しない**: 上記 5 フィールド (from / to / topic / dispatched_at / msg_id) は今後も同じ key で存在する
2. **既存フィールドの型・形式を変えない**: 例えば `dispatched_at` を epoch 秒に変えるのは **破壊的変更** (やる場合は新フィールド `dispatched_at_epoch` を追加して dispatched_at は残す)
3. **frontmatter 終端ルール (2 個目の `---`) を変えない**: 本文側で `---` が出ても、frontmatter は **冒頭ブロックの最初の `---` 〜 次の `---`** で確定する。複数 frontmatter block を作らない
4. **新フィールドはすべて optional**: 古い読み手 (= 例えば v0.2 時点の Observation Pillar) は知らないフィールドを単に無視する。古い読み手が必須としているフィールドは新フィールドに置き換えない

実質的に **append-only 契約**。

## Observation Pillar v0.2 (#66) が依存する範囲

Observation v0.2 の `dispatch_flow.py` は以下のみを読む:

- `from` / `to` フィールド (集計キー)
- `dispatched_at` フィールド (時系列ソート / first_at / last_at)
- frontmatter 終端の `---` (それ以降の本文は **読まない**)

`topic` / `msg_id` / 本文は **観測の射程外**。これは Mindspace 不可侵原則 (ADR-0014) の精神を Conduit 側にも拡張する設計判断: 監視者 (Warden) であっても通信内容の中身は見ない、流量と方向のみ見る。

## Conduit Pillar 側の責務

- `send_dispatch` が本書のフォーマットを満たすファイルを書く
- フォーマット変更時は本書を更新する (PR の差分で contractual change が可視化される)
- 必要なら他 Pillar の利用箇所も同 PR でテスト含めて更新する

## 関連

- ADR-0005 — Phase 3 MCP 直結 / Nexus 設計
- ADR-0014 — 物理境界 (Mindspace 不可侵、Conduit storage は穴あき境界 = 共有領域)
- ADR-0017 — Warden vs Mind 監視層の分離 (本契約は層 A の入力)
- `storage.py` — フォーマットの単一実装
- `pillars/observation/dispatch_flow.py` (Phase 5d-1 / #66) — 本契約の最初の依存元
