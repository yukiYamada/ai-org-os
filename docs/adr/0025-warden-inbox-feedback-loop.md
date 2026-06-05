# ADR-0025: Mind から warden への返信を Conductor が判断入力に取り込む

> 想定読者:
> - Conductor / Judgment Pillar を拡張するメンテナ
> - 「warden inbox に届いた reply を誰が読むの?」と疑問を持ったセッション
> - Phase 5e の outer loop が「観察 → 判断 → 動かす」だけで完結しないことに気付いた人
> - 将来 Realm sender が増えた時の inbox 管理方針を考える人

## Status

**Accepted** — 2026-05-30
**Refined** — 2026-06-05 (#123: `fallback-no-key` も ack 側に倒す。詳細は §2)

## Context（背景）

2026-05-30 の dogfooding (PR #111 / Step B 後) で発見した設計漏れ (Issue #117)。

ADR-0024 で **warden を Mind 以外の永続 Realm sender** として導入した。Step B (#111) で Warden → Mind 経路 (actuator) が動き、Step C (#114) で Mind 側の受信宣言 (Persona) が揃った。実機で alice (designer Persona) を 1 cycle 走らせたところ:

1. alice は warden dispatch を ack
2. alice は **warden 宛に reply (2 案 + 推奨 + メタ質問)** を send_dispatch した
3. → `conduit-storage/inbox/warden/<id>.md` に reply が **永続**

ここで設計の問題が浮上:

| 観測 | 問題 |
|---|---|
| warden は Mind ではない (ADR-0024) | spawn-kill 機構が無い → inbox 自動管理が無い |
| ADR-0023 kill 順は Mind 用 | warden には適用不可能 (永続のため) |
| Conductor が warden inbox を読まない | reply が蓄積、誰も活かさない |

dogfooding で alice が出した reply は **本来 Judgment が次 cycle で読むべき情報**:

- 「指示の意図を確認したい」
- 「指示を遂行した、結果はこれ」
- 「自分は今この設計を進めている」

これらが Judgment に渡らないと、Warden の outer loop は **片肺** で完結する: 観察 → 判断 → 働きかけ → (Mind の応答が消える) → 同じ観察 → 同じ判断 → ...

ADR-0010 §5「Warden は機能集合体」「観察→判断→動かす」のループから **「Mind の声を取り込む」エッジが欠けていた**。これを埋める。

## Decision（決定）

### 1. Conductor が cycle 毎に warden inbox を読む

Conductor の `run_one_cycle` 内、snapshot 取得後 / Judgment 呼び出し前に:

```python
warden_inbox = _read_warden_inbox()  # Nexus(identity=None).read_inbox("warden")
judgment_input["warden_inbox"] = [
    {
        "msg_id": m["msg_id"],
        "from": parsed.from_mind,
        "topic": parsed.topic,
        "body": parsed.body,
        "dispatched_at": parsed.dispatched_at,
    }
    for m in warden_inbox["messages"]
]
```

Judgment は通常の minds / flow / anomaly に加え、`warden_inbox` も判断材料として受け取る。

### 2. Judgment 呼び出し **後** に ack

Judgment が消費した、もしくは「消費できない」ことが確定した場合に、読んだメッセージ全件を `ack_dispatch` する:

```python
# refined by #123 (Phase 5e Step D follow-up)
if judgment_status in ("ok", "fallback-no-key"):
    for msg in warden_inbox["messages"]:
        _ack_warden_inbox(msg["msg_id"])
```

ack 判断の 3 ケース:

| status | 状況 | ack | 理由 |
|---|---|---|---|
| `ok` | Judgment 正常稼動 | ✅ | 消費した → archive へ |
| `fallback-no-key` | API key 不在で Judgment Pillar 機能なし | ✅ (#123) | retry しても回復しない (operator が `ANTHROPIC_API_KEY` 投入するまで永続) → at-least-once を維持すると inbox 無限蓄積 |
| `fallback-error` | 一時的失敗 (network / rate limit / parse error) | ❌ | retry に意味あり → 次 cycle で reprocess |

ack タイミングを「読んだ直後」ではなく「Judgment 後」にする理由: Judgment 呼び出しが**一時的に**失敗した場合に、次 cycle で同じ reply を再度読んで judgment 入力にできる (= at-least-once 配送)。Judgment は冪等な観察関数なので、同じ入力で重複呼び出し可。

`fallback-no-key` を ack 側に倒すのは at-least-once 原則の **意図的な部分的緩和** (#123)。「Judgment が読まない宣言」と等価扱いで archive 移送する。archive は永続なので、key 投入後の人間 review で取りこぼし検出は可能。

### 3. Judgment system prompt の拡張

`_build_system_prompt` に warden_inbox section を追加:

```
The report MAY include "warden_inbox":
  - Replies from Minds to Warden's previous dispatches
  - Use to update mental model: did the Mind acknowledge? did they push back?
                                did they answer your question?
                                did they report progress?
  - If a reply explicitly asks for clarification, consider dispatch-prompt
    with the clarification
  - If a reply reports a problem, consider investigate / notify-human
  - If a reply is acknowledgement of completed work, consider ok / monitor
```

### 4. warden inbox の prune ポリシー

毎 cycle 全件読み + 全件 ack なので **「読んだ瞬間 inbox 空 → archive へ」** の流れになる。archive は永続 (= Realm 監査ログ)。

警戒すべき failure mode: **massive reply burst** で 1 cycle に大量の reply が来た場合、Judgment 入力が token 上限を超える。

本 ADR では「読める分だけ読む、それ以上は次 cycle」とせず、シンプルに **全件読み + truncate** (= 上限件数 default 20、超過分は今 cycle で ack しないので次 cycle で読まれる)。

ADR-0021 A/B/C 分類:

- **現状 = B (宣言的 default)**: `MAX_WARDEN_REPLIES_PER_CYCLE = 20` は Conductor の literal 定数で、code 側で truncate を機械強制 (= rep 数で reject ではなく上位 N 件採用)。利用者が値を変えるには code 編集が要る。
- **将来 = C (利用者構成)**: `$AI_ORG_OS_HOME/config.env` 等で利用者調整可にする (= 別 issue。ロード負荷 / token cost と相談しながら運用調整できるようにする)。

PR 段階で「B 寄り宣言、将来 C 化」と明示しておく。

### 5. Mind→Mind dispatch との非対称性

| 経路 | 受信側 | ack 機構 |
|---|---|---|
| Mind → Mind | 受信 Mind | Mind が `ack_dispatch` (Persona docs に書かれた既存挙動) |
| Mind → warden | Warden Pillar (Realm) | **Conductor が cycle 毎に自動 ack (本 ADR)** |
| warden → Mind | 受信 Mind | Mind が `ack_dispatch` (ADR-0024 §2 + Persona) |

これは Realm sender (= 永続) と Mind sender (= 一時的) で受信機構が異なるための非対称性。Conduit Pillar の `Nexus` API は両方で同じ (read_inbox / ack_dispatch)、運用側の責務が違うだけ。

### 6. Conductor が Conduit を呼ぶ Pillar 間結合

Phase 5e Step B (PR #111) で既に `_send_dispatch_via_conduit` で同じ結合が存在。本 ADR ではそれを `_read_warden_inbox` / `_ack_warden_inbox` に拡張するのみ。Conductor → Conduit の方向は ADR-0010 §6 「Pillar 間は薄く」の前提範囲内 (= Conductor は他 Pillar を呼ぶ常駐エンジン)。

## Consequences（影響）

### 良いこと

- Warden の outer loop が **観察 → 判断 → 働きかけ → 反応取り込み → 観察 → ...** で閉じる (双方向)
- Mind の声 (質問、報告、確認要求) が Judgment context に乗る → より文脈に沿った判断
- warden inbox が永続的に膨張しない (毎 cycle prune)
- ADR-0024 §4「Warden から見た送信ログ」と対称な「Warden から見た受信ログ」が archive として残る → 監査可能

### 悪いこと / 残る曖昧さ

- Judgment 入力が膨らむ → token cost / latency 増 (Phase 5e Step A での flow/resource 統合と同じ tradeoff)
- 大量 reply burst で `fallback-error` (一時的失敗) が続くと inbox が貯まる (ack しないため)。これは Judgment 復旧時に一気に解消するので一時的問題
- `fallback-no-key` (key 不在) では至急 ack するが、archive 移送された声は人間 review がない限り消費されないまま堆積する。dev / 検証環境で起きる想定で、Realm 本運用前提では key 投入が前提 (#123)
- Judgment LLM が warden_inbox を「読まなければならない」を機械強制できない (B レベル)。system prompt の質に依存

### follow-up

- 大量 reply 時の truncate ポリシーを C 構成化 (= 利用者が `max_warden_replies_per_cycle` 設定)
- archive の TTL / 容量 prune (= Realm の長期運用課題、別 ADR)
- 将来 Realm sender が増えた時、各々の inbox 管理ポリシーをどう拡張するか

## Alternatives considered（採用しなかった案）

### A. Mind は warden に返信不可 (axiom A 強制)

`Nexus.send_dispatch` で `to_mind == "warden"` を ValueError。

- メリット: 設計超シンプル、本 ADR 不要
- デメリット: dogfooding で見えた Mind の表現力 (designer の質問、状態報告、push-back) を捨てる。Warden が一方向の指示者になり、Mind の意図を取り込まないと判断品質が低下
- 却下 (= Mind を「指示を聞くだけの装置」にする本旨と相反)

### B. warden inbox を Conductor は読まず、archive プロセスのみ

read_inbox → ack_dispatch を Conductor cycle 内で機械的に回し、Judgment には渡さない。

- メリット: 中間。inbox は溢れない、Judgment 入力も増えない
- デメリット: Mind の声が消える。Realm に archive は残るが活用されない。本 ADR の本旨を達成できない
- 却下 (= 案 C と本質的に同じだが Judgment への帰還が無い分劣化)

### C. Realm sender ごとに inbox 自動 prune (TTL / 最大件数)

warden inbox は N cycle / M 件で自動削除、Judgment には渡さない。

- メリット: 実装最小
- デメリット: B と同じ問題 (Mind の声を活かせない)
- 却下

### D. Mind の reply を Judgment ではなく専用 Pillar が処理

新規 Pillar `ReplyProcessor` を作って Judgment と別経路で reply を捌く。

- メリット: 責務分離
- デメリット: Pillar 数の膨張、ADR-0010 §6「Pillar 間は薄く」と緊張。reply 解釈は本質的に Judgment と同種の作業
- 却下

### E. Judgment 呼び出しの **前** に ack

ack を read 直後にする (Judgment 呼び出し前)。

- メリット: 一瞬で inbox 空く、reply の二重処理が起きない
- デメリット: Judgment 呼び出しが network error 等で失敗すると **reply が消える** (at-most-once 配送になる)。Mind の声を取りこぼす
- 却下 (= 「Judgment 後 ack」= at-least-once 配送を採用)

## 関連

- ADR-0010 — Pillar / Warden (本 ADR は §5 のループに「反応取り込み」エッジを追加)
- ADR-0013 §1 F3 — Pillar 異常は cycle 止めない (warden_inbox 読み失敗時も cycle 完走)
- ADR-0017 — Warden vs Mind 監視責務 (本 ADR の判断主体は Warden)
- ADR-0021 — A/B/C 分類 (§1=A 機械、§3=B 宣言、§4=C 設定)
- ADR-0023 — Mind identity の単一性 (warden は対象外、本 ADR の前提)
- ADR-0024 — warden = Realm sender (本 ADR は §4 を逆方向に拡張)
- Issue #117 — 本 ADR の trigger となった設計漏れ発見
- PR #111 — Phase 5e Step B (Warden→Mind 経路)
- PR #114 — Phase 5e Step C (Mind 受信側宣言)
