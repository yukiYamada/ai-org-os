# ADR-0016: Mind 認証経路と「Container = コア、ホスト = Mind」境界

> 想定読者:
> - Mind がどの権限で Anthropic API を叩いているか把握したい人
> - Phase 5b-2 以降で Mind の orchestration (Conductor からの spawn) を設計する人
> - Realm の物理境界 (ADR-0014) を実装に落とし込むメンテナ
> - 「なぜ Realm Container 内に claude CLI を入れないのか」の根拠を探している人

## Status

**Accepted** — 2026-05-24

## Context（背景）

ADR-0014 で Realm の物理境界を 4 カテゴリ (A 内側 / B 穴あき / C 外部依存 / D 人間制御) に分けた。
このうち **Anthropic API は C (外部依存)**、**`claude` CLI binary も C** と分類済。
しかし Mind が **どの経路で Anthropic API を叩いているか** は明示されていなかった。

Phase 5b-1 (#71) の動作確認で、operator (人間) が「Mind は何の権限で動いてるの？login してないはず」と質問。
答えは「**ホスト上の `claude` CLI を呼んでいて、その認証はホストユーザーの Claude Code login セッション**」だが、ここが ADR で明示されていないと:

- Phase 5b-2 で Conductor から Mind を spawn する設計が **ホスト側 / Container 側どちらで起動するか** ブレる
- 「ai-org-os を別 machine で立てる」とき、claude login が必要なことが分からない
- API key 経路 (Judgment) と CLI login 経路 (Mind) が混在している事実が暗黙

### 認証経路が 2 系統あるという現状

| 主体 | 認証方法 | 起動方法 | 課金 |
|---|---|---|---|
| **Mind** | ホストユーザーの Claude Code login session (Pro / Max plan 等) | ホスト上で `cd runtime/minds/<name>; claude` | プラン内 quota（CLI 経由）|
| **Judgment Pillar** | `ANTHROPIC_API_KEY` 環境変数 | Container 内で Anthropic SDK 直叩き | API 従量課金 |

CLI 経由は plan 定額内に収まり、API key 直叩きは 1 トークンごとに課金されるため、コスト構造が大きく異なる。
**Mind は思考のために大量のトークンを消費するので、CLI login (定額 plan) で動かす方が現実的**。

## Decision（決定）

### 1. Container = Pillar 群（コア）、ホスト = Mind の境界を固定する

```
┌─ ホスト OS ────────────────────────────────────────────────┐
│                                                            │
│   人間（Realm 外監督者、ADR-0012）                          │
│   ホストユーザーの Claude Code login session               │
│                                                            │
│   ┌─ Mind プロセス群 (ホスト上で動く) ────────────────┐   │
│   │  - cd runtime/minds/<name>; claude                │   │
│   │  - ユーザー権限で動く = ユーザーの quota を消費    │   │
│   │  - .mcp.json で Conduit Pillar (Container 内) に  │   │
│   │    stdio で接続                                   │   │
│   └────────────────────────────────────────────────────┘   │
│                          │                                 │
│                          │ bind mount (穴あき層、ADR-0014 B)│
│                          ▼                                 │
│   ┌─ Realm Container ─────────────────────────────────┐   │
│   │                                                   │   │
│   │   Pillar 群 (Conductor / Observation / Inbox /    │   │
│   │   Lifecycle / Conduit / Judgment / Registry)      │   │
│   │                                                   │   │
│   │   Judgment は ANTHROPIC_API_KEY で SDK 直叩き      │   │
│   │   claude CLI は Container 内に **入れない**        │   │
│   │                                                   │   │
│   └────────────────────────────────────────────────────┘   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

- **Container 内**: Pillar 群が走る。`claude` CLI は **入れない**（依存最小、ADR-0009）
- **ホスト**: Mind プロセスが走る。`claude` CLI の login session を使う
- **接続**: bind mount でファイルを共有、Mind の `.mcp.json` 経由で Conduit Pillar に stdio 接続

### 2. Mind の認証経路は「ホストユーザーの Claude Code login」を採用

採用理由:
- **コスト**: Mind は大量のトークン消費が前提。CLI 経由なら Pro / Max plan の quota 内に収まる
- **既存資産**: ユーザーは既に Claude Code login 済が普通（ai-org-os は Claude Code 内で開発されている）
- **対話性**: 必要に応じて Mindspace に入って `claude` を対話的に叩いて debug できる
- **設定の単純化**: API key 管理を 1 種類（Judgment Pillar のみ）に絞れる

### 3. Judgment Pillar の認証経路は `ANTHROPIC_API_KEY` のまま

Mind との二重認証経路を受け入れる理由:
- **Judgment は対話なし**（ADR-0010 §5: 「Warden は SDK 直叩き、決定論的」）。CLI 経由のメリットは無い
- **Container 内で完結**: Conductor がプログラムから呼ぶので、login session よりも env var の方が扱いやすい
- **CI / 自動テスト**: 自動環境では login session を維持できないので、API key 方式の方が再現性が高い
- **少量・必要時のみ消費**: 判定 1 回あたり数百〜数千トークン程度。従量課金で受容できる規模

### 4. Phase 5b-2 以降の orchestration 設計の制約

**Conductor (Container 内) から Mind を spawn する場合、Mind 本体はホストで起動する必要がある**。

選択肢:
- (a) Conductor が「Mind を spawn してほしい」というシグナルをホスト側に出し、ホスト側 supervisor が `claude` を起動する
- (b) Conductor が docker host から `runtime/minds/` を bind mount 経由で書くまでにとどめ、Mind の `claude` 起動は人間が手で続ける（現状）
- (c) Mind も SDK 直叩きに統合する（**本 ADR §2 で不採用**）

Phase 5b-2 の設計はこの制約を前提に組む。

### 5. Realm の再現性は「Pillar 群」までを保証する

ADR-0014 §6 で「CI = Realm の再現性検証」と決めたが、**再現性の対象は Pillar 群 (Container 内)** に限定する。
Mind の挙動は **ユーザーの Claude Code login plan** に依存するため、CI で完全再現はしない（し、する必要もない）。

## Consequences（影響）

### 利点

1. **コスト構造が明示される**: Mind は plan 定額、Judgment は従量課金、と運用者に分かる
2. **Container の依存最小が維持される**: claude CLI を入れない → image build 時間 / 攻撃面積を最小化
3. **Phase 5b-2 の設計指針が確定**: Conductor は Mind を直接 spawn せず、ホスト側経路を介する必要がある
4. **operator の混乱を防ぐ**: 「なぜ Container 内で `claude` が無いのか」「なぜ login 必要なのか」が文書化される
5. **ADR-0014 が補完される**: カテゴリ B (穴あき層) の具体的な接続例として Mind プロセスが位置づけられる

### 不利益 / リスク

1. **「Container = Realm」が完全には成立しない**: Mind はホスト側で動くので、Realm を完全コンテナ化できない（意図された妥協）
2. **マルチユーザー運用の制約**: 1 ホストで複数の Claude login を切り替えるのは難しい（同一マシン = 同一ユーザーの quota を共有）
3. **CI で Mind 挙動を再現できない**: ユニットテストでカバーする範囲が限定される
4. **オーケストレーション複雑化**: Conductor → ホスト supervisor → Mind の経路が必要（Phase 5b-2 で設計）
5. **既存 ADR との差分明示が必要**: ADR-0006 「Realm 内同居方式」は Pillar 群限定であり、Mind は含まないことを明確化

### 派生する Issue / 後続作業

- **Phase 5b-2 (TBD)**: Conductor → ホスト supervisor → Mind spawn のオーケストレーション設計
- **ホスト supervisor の実装**: bind mount 越しの signal / file 経由で Conductor の要求を受け取り、`claude` を立ち上げる仕組み（別 Issue 候補）
- **ADR-0006 の補強**: 「Realm 内同居方式」は Pillar 群限定であることを追記注釈（本 ADR で代替可能）
- **`runtime/realm/README.md` の更新**: 起動前提として「ホストで `claude code login` 済」を明記

## 代替案（不採用）

### A. Container 内に claude CLI を install + login

Realm container 内で `claude` を動かし、Container 内で `claude code login` する案。

不採用理由：
- CLI plan の login token を Container に持たせると、ホストの login と権限スコープが分離して管理が複雑化
- Container の依存最小方針 (ADR-0009) と矛盾
- 既存 Claude login (ホスト) を再利用できない
- Container build 時に login を仕込めない（インタラクティブ login が必要）

### B. Mind も API key (Anthropic SDK) 方式に統一

Mind も Anthropic SDK 直叩きで動かし、認証経路を 1 つに統一する案。

不採用理由：
- **コスト**: Mind は大量トークン消費前提。従量課金では plan 定額より高額になる
- **対話 UX の喪失**: Mind が Mindspace に対話的に入って debug できる利点を失う
- **既存 Claude Code エコシステムから外れる**: `.mcp.json` / Persona (CLAUDE.md) / hooks 等の Claude Code 機能をフル活用できなくなる
- **Mind の能動性 (ADR-0010 §3)**: claude CLI の応答性を活かす設計と相性が良い

### C. Mind は Container 内、claude CLI も install、API key を渡す

Container 内で `claude` を入れて、`ANTHROPIC_API_KEY` で動かす案（CLI を SDK 的に使う）。

不採用理由：
- claude CLI は API key モードを公式サポートしていない（あっても plan 経由よりコスト高）
- Container 化のメリット (隔離) と Mind が触る範囲 (Mindspace) のトレードオフで、結局 bind mount が必要
- 案 A / B と類似の不利益を組み合わせた形になる

### D. 現状の暗黙運用を続ける（ADR 化しない）

明文化せず実装に任せる案。

不採用理由：
- Phase 5b-2 設計で必ずブレる（ホスト側 / Container 側どっちで spawn するか）
- 新しい operator が「なぜ login 必要」「なぜ Container に claude が無い」を毎回問う
- 「Realm = Container」という素朴な期待を明示的に裏切る必要がある

## 関連

- [ADR-0006](0006-phase-5-realm-warden-guildmaster.md) — Realm 内同居方式（**本 ADR で Pillar 群限定と明確化**）
- [ADR-0008](0008-nexus-identity-binding.md) — Conduit Pillar の identity binding（Mind と Pillar の境界）
- [ADR-0009](0009-relationship-with-bash-editor-and-claude-team.md) — 依存最小方針（claude CLI を Container に入れない根拠）
- [ADR-0010](0010-observation-philosophy-and-warden-as-collective.md) §5 — Warden は SDK 直叩き
- [ADR-0011](0011-warden-claude-naming-and-separation.md) — Pillar 境界（編集不可、本 ADR で再確認）
- [ADR-0012](0012-human-position-outside-realm.md) §3 — 人間と Realm のチャンネル（claude login も人間責務）
- [ADR-0013](0013-failure-handling-and-failsafe.md) §1 F4 — Realm 外部依存（Anthropic API / Claude CLI が落ちたとき）
- [ADR-0014](0014-realm-physical-boundary.md) §3 — 4 カテゴリ分類（本 ADR で Mind プロセスを B / C 跨ぎとして具体化）
- Issue #71 (Phase 5b-1) — 動作確認で本問題が顕在化
- Phase 5b-2 (TBD) — 本 ADR の制約下で Conductor → Mind orchestration を設計する
