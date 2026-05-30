# ADR-0024: Warden を「Mind ではない sender」として dispatch protocol に組み込む

> 想定読者:
> - Warden actuator (Conductor) の挙動を拡張するメンテナ
> - Persona docs を書く / 更新する人
> - `from: warden` という dispatch を見て「これ何?」と混乱したセッション
> - 将来 Warden 以外の「Mind ではない sender」 (Conductor sub-component, external orchestrator) を増やそうとする人

## Status

**Accepted** — 2026-05-29

## Context（背景）

Phase 5e Step B (#111, merged 2026-05-29) で、Warden Pillar (Judgment + Conductor) から Mind の inbox に dispatch を投入する最初の actuator が動いた。dispatch の frontmatter は `from: warden` で固定 (`WARDEN_SENDER_NAME`)。

これは ADR-0023 が暗黙に前提していた「**dispatch sender はすべて Mind**」という invariant を破る:

- ADR-0023 §1: 「Mind identity = spawn-kill period only」
- ADR-0023 §2: 「dispatch 履歴は Mind と運命を共にする」
- → これらは「sender も Mind」を前提に書かれていたが、`warden` は Mind ではない。spawn されないし kill されない (= Realm 起動中ずっと存在)

加えて受信側 (Mind) も `from: warden` を見て何をすべきか定義されていない:

- Persona 4 つ (designer / implementer / reviewer / guildmaster) は `read_inbox` + Dispatch 受信処理を書いているが、`from` の値による分岐は未定義
- 「他 Mind 由来の Dispatch」と「warden 由来の Dispatch」を同列に扱うと、Warden の観測ベースの軌道修正 (judgment.action="dispatch-prompt") が業務 Dispatch のキューに埋もれてレスポンスが遅れる
- そもそも `warden` が `from_mind` として有効な名前なのかが axiom レベルで未確定 (= spawn-mind が `warden` を Mind 名として reject していない、follow-up #112 で議論中)

ADR-0023 の単純な拡張では足りず、「**Mind ではない sender が存在する**」ことを protocol に明示する必要がある。

## Decision（決定）

### 1. `warden` は「Realm 永続 sender」として予約

dispatch frontmatter の `from:` フィールドが取り得る値を 2 種類に分ける:

| 種別 | 値 | identity の寿命 | spawn / kill | dispatch 履歴所有 |
|---|---|---|---|---|
| **Mind sender** | `[A-Za-z0-9._-]{1,64}` (但し予約語除く) | spawn-kill 間で唯一 (ADR-0023 §1) | あり (spawn-mind / kill-mind) | Mind と運命を共にする (ADR-0023 §2) |
| **Realm sender** | `warden` (予約) | Realm 起動中ずっと | なし (Pillar として常在) | Realm storage に残る (Mind 同名再 spawn の影響を受けない) |

「Realm sender」は Mind 集合と直交する概念。今後 `conductor`, `observer` 等を増やす場合は Realm sender に追加する (ADR 改訂で明示)。

### 2. Realm sender からの dispatch は受信側で「最優先」扱い

これは **ADR-0021 B (宣言的指示)** レベルの規約。機械強制ではない (= Mind が無視しても storage 層は通る) が、Persona docs に共通宣言として書き、Mind が学習しているとして扱う。

具体宣言 (各 Persona docs の Dispatch 受信 section に追加):

> **`from: warden` の Dispatch は最優先で扱う**。warden は Mind ではなく Warden Pillar (世界そのもの) からの直接の声であり、観測に基づく judgment の結果 (silent 警告 / 軌道修正 / inbox の溜まり通知 等) が届く。他 Mind 由来 Dispatch より先に内容を読み、要求された行動 (状況報告 / 再開 / 優先度変更) を **1 cycle 内で開始** する。

Realm sender からの指示を **無視する自由は Mind にある** (B レベル = 機械強制ではない)。ただし無視すると次 cycle の Judgment が同じ silent シグナルを観測してエスカレーション (notify-human 等) する可能性が高い、という自然な収束機構を仕組む。

### 3. Mind は `warden` を名乗れない (axiom A 強制、follow-up)

「Mind ではない sender」を Mind が偽装できると、Realm sender vs Mind sender の区別が壊れる。これを axiom レベル (機械強制) で防ぐ:

- `spawn-mind.sh` / `registry.register` で `warden` を Mind 名として **reject**
- `Nexus.send_dispatch` の `from_mind` validation で `warden` を `identity=None` (= Warden 経路) 以外から渡された場合に reject

本 ADR では「方針として確定」とする。実装は **#112 (follow-up Issue)** で扱う。Phase 5e Step B 時点では `Nexus._authorize` の identity binding で運用上は安全 (= Mind プロセスは MCP 経由でしか dispatch できず、その MCP は identity-bound)。

### 4. ADR-0023 との関係

ADR-0023 は「dispatch 履歴は Mind と運命を共にする」と決めた。本 ADR は **「Mind に紐付かない dispatch 履歴 (= Warden 発信分) は Realm に残る」** ことを補足する:

- `conduit-storage/inbox/<mind>/` に warden から届いた dispatch も、Mind が kill されると Mindspace ごと消える (ADR-0023 §3 kill 順)
- ただし archive (= 受信側 Mind が ack 済みのもの) は通常通り Mind 単位なので、Mind 削除で archive も消える
- 「Warden から見た送信ログ」 (= 「いつ何を warden から送ったか」の Realm 視点履歴) は **本 ADR スコープ外**。必要なら別途 Observation Pillar の flow snapshot で扱う (ADR-0010 §7 統合 report の \"flow\" section に warden→mind edge が出る)

### 5. なぜ A axiom 化を即時にしないか

Phase 5e Step B の merge を急がず axiom A 化まで含めると、scope が膨れる:

- `spawn-mind.sh` (bash) の予約語 check
- `registry.py` の予約語 check
- 既存テストの「warden を Mind 名として使う」regression が無いかの全件 scan
- ADR-0019 (Guild) との整合 (Guild 名 "warden" もブロックするか?)

これらを 1 PR にまとめると Codex review が長引く可能性が高く、Phase 5e の outer loop (judgment → actuator → 受信) を閉じる優先度が下がる。本 ADR で **方針を確定して docs に書く**、実装は次の small PR (#112) に分ける。

## Consequences（影響）

### 良いこと

- `from: warden` が「Mind ではないものから来た」という意味であることが docs に書かれ、Persona は迷わずに最優先で扱える
- 将来 `from: conductor` / `from: observer` のような Realm sender が増えても、本 ADR の「Realm sender」カテゴリに追加するだけで protocol を維持できる
- ADR-0023 (Mind identity) と矛盾しない (Mind ではない sender を直交カテゴリとして導入)

### 悪いこと / 残る曖昧さ

- B レベル (宣言) なので「Mind が warden dispatch を無視する」を機械的に検出する手段は無い。次 cycle の Judgment が「同じ silent」を見て対処するという間接的検出のみ
- axiom A 化 (Mind が `warden` を名乗れない) が #112 に分離されているため、本 PR merge 後 #112 merge までの間は「悪意ある (or 事故的な) `spawn-mind --name warden`」が運用上の脅威。今は MCP の identity binding で実害なしだが、テストが書きづらい

### follow-up

- **#112**: `warden` を予約 Mind 名として spawn-mind / registry が reject する強制 (本 ADR §3 の axiom 実装)
- 将来: 他 Realm sender (`conductor`, `observer` 等) を追加する際に本 ADR を改訂

## Alternatives considered（採用しなかった案）

### A. `warden` も Mind として扱う (永続 Mind 化)

`spawn-mind --name warden` を初期化時に 1 度だけ呼んで、Realm 起動中ずっと kill しない Mind として扱う案。

- メリット: ADR-0023 の「sender = Mind」前提を維持できる
- デメリット: Warden = Pillar 群 ≠ Mind (ADR-0001 / ADR-0010 §5) という根本概念と矛盾。Mind は「思考個体」、Warden は「世界そのもの」。混ぜると意味論が壊れる
- 却下

### B. `from:` フィールドを Mind name と type の 2 つに分割

`from_mind: alice` + `from_type: mind|warden` のように分ける。

- メリット: protocol 上の区別が明示的
- デメリット: 既存の dispatch frontmatter schema を非互換に変える必要があり、PR scope が膨れる。`warden` という予約名 1 つで区別する方が小さく済む
- 却下 (将来 Realm sender が 5+ 増えたら再検討余地あり)

### C. ADR-0023 を改訂して「Realm sender」を §1 に追加

新規 ADR ではなく ADR-0023 を改訂する案。

- メリット: 関連知識を 1 箇所にまとめられる
- デメリット: ADR は判断記録 (immutable). 後付けで挙動を加えるのは適切でない。本 ADR が ADR-0023 を "extends" する形が正しい
- 却下

### D. Persona docs に直接書く (ADR 不要)

「ADR を起こさず Persona 4 つに直接書けばよい」案。

- メリット: 軽量
- デメリット: 「warden が dispatch sender になれる」「Mind は `warden` を名乗れない」は **Conduit Pillar の protocol 拡張** であり Persona 文書では責任が取れない。判断の主体は不明瞭になる
- 却下 (Persona は ADR の宣言 (§2) を反映する受信側の実装に留める)

## 関連

- ADR-0010 — Pillar (Warden) と Mind の境界
- ADR-0017 — Warden vs Mind 監視責務 (本 ADR の「Realm sender = Warden が発信」がここに乗る)
- ADR-0021 — A / B / C 分類 (本 ADR は §2 が B, §3 が A 予定)
- ADR-0023 — Mind identity の単一性 (本 ADR が直交カテゴリとして補強)
- Issue #112 — `warden` を予約 Mind 名として axiom 強制 (本 ADR §3 の実装 follow-up)
- PR #111 — Phase 5e Step B (本 ADR の trigger となった warden actuator 実装)
