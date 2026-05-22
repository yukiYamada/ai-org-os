# ADR-0004: Phase 3（Dispatch = 思考間通信）の設計案

> 想定読者:
> - Phase 3 を実装するメンテナ（`spawn-mind.sh` への inbox 配備、Dispatch 送受信スクリプトの追加、テスト拡張を担う）
> - Phase 3 への着手を判断する意思決定者（プロダクトオーナー）
>
> 目的: 朝起きたユーザーが「Phase 2（Docker 化）と Phase 3（Dispatch）のどちらに先に進むか / 並行するか / どちらかを棚上げするか」を、論点と材料を並べた状態で判断できるようにする。

## Status

**Proposed** — 2026-05-22

> 本 ADR は **設計のみ**。実装は本 ADR の承認後に着手する。
> Accepted に昇格させるには「採用案」セクションの選択肢を絞り込む必要がある。

## Context（背景）

### これまでの位置

- [ADR-0001](./0001-ai-org-os-as-invariant-framework.md): ai-org-os は「開発組織の不変項（Axiom）を定義するフレームワーク」。組織 = 思考のネットワーク。
- [ADR-0002](./0002-vocabulary-and-meta-meta-structure.md): 用語と階層構造を確定。**Realm / Warden / Nexus / Guild / Guildmaster / Mind / Mindspace / Persona / Axiom / Dispatch**。
- [ADR-0003](./0003-docker-and-phase-2-design.md): Phase 2（Docker 化 + Mindspace の named volume 化）の設計案。**Proposed**。
- Phase 1（実装済）: `runtime/spawn-mind.sh` で Mind を 1 個ホスト上に spawn できる。Mindspace = ホストの `runtime/minds/<name>/`。

Phase 1 を起点に「Mind が物理的に存在する」までは到達したが、ADR-0002 で定義した **Dispatch（明示プロセス経由の思考間通信）** はまだ存在しない。組織が「思考のネットワーク」である以上、Mind が 2 つ以上立ち、それらが通信できるところまで行かないと「組織」のコア体験には届かない。

### Phase 3 の達成目標

[runtime/README.md](../../runtime/README.md) の次フェーズ計画より:

> Phase 3: 2 Mind + Dispatch（ファイル経由通信）

これを ADR-0002 の Axiom と接続して具体化すると:

1. **2 つの Mind を spawn でき、それらが Dispatch（明示プロセス）で通信できる**
2. **メッセージは痕跡として残る**（=後で人間 / 他 Mind が読み返せる）
3. **どの Mind の Mindspace も他から侵されない**（不可侵原則維持）
4. **送信側と受信側は同期している必要がない**（=非同期、受信者が後で読めれば成立）
5. **Dispatch だけが正規ルート**であって、Mindspace から相手の Mindspace を直接いじる経路は存在しない

Phase 3 では **Nexus（MCP サーバー）／Warden ／Guildmaster はまだ作らない**。Mind ↔ Mind の通信を、最も素朴な手段（ファイル経由）で 1 本通すことに絞る。

### スコープ外（Phase 3 で扱わないこと）

- Nexus（MCP サーバー）（Phase 4）
- Warden（リソース管理、3 段階ライフサイクル）（Phase 5）
- Guildmaster / Guild の論理セグメント運営（Phase 5）
- 認証 / 認可（誰が誰に Dispatch を送れるかの権限制御）
- メッセージの暗号化
- 大量メッセージ時のバックプレッシャ / フロー制御
- Mind 間でのバイナリ送信（テキスト / Markdown のみを扱う）

### Phase 2 との関係（独立か、順序依存か）— **結論を先に置く**

**結論: Phase 2 と Phase 3 は独立。順序依存しない。先に Phase 3 に着手できる。**

理由:

1. Phase 1 の Mind（ホスト fs 上のディレクトリ）でも Dispatch（ファイル経由）は成立する。共通領域（例: `runtime/dispatches/`）を作って、各 Mind が読み書きすればよい。
2. Phase 2 で Mind がコンテナ化されても、Dispatch は依然「コンテナ間で共有される volume / ディレクトリ経由」で成立する。**Phase 3 で定義する Dispatch のインターフェース（書く場所・読む場所・フォーマット）が Phase 2 の有無に依存しない設計**にすればよい。
3. ただし、後述の通り「Phase 2 後の Dispatch」と「Phase 2 前の Dispatch」では **物理的な共有領域の実体が変わる**（ホスト fs か Docker volume か）。**論理インターフェース** を不変に保てば、実体は差し替え可能。

つまり Phase 3 のインターフェース設計は、**Phase 2 を前提にしてもしなくても同じ形に到達**する。ここが本 ADR の最大の主張。

---

## Decision（推奨案 + 候補比較）

> 本 ADR は Proposed のため、ここでは「単一の決定」ではなく **推奨案** と **候補比較** を並べる。
> Accepted に昇格するときに、ユーザーが下の選択肢から 1 案を選んで確定する想定。

### 推奨案（叩き台、Accepted 化のときに調整可）

| 軸 | 推奨 | 理由（要約） |
|---|---|---|
| 通信方式 | **(a) ファイル経由（共通の `runtime/dispatches/` ディレクトリ）** | 依存ゼロ、痕跡が自動で残る、Axiom と最も整合、Phase 4 で MCP に乗せ換えやすい |
| メッセージフォーマット | **Markdown + YAML frontmatter** | ai-org-os 文化（Markdown 中心、ADR も Markdown）と整合、人間も読める、痕跡として残る |
| 受信側ウェイク | **能動 poll（受信 Mind が自発的に inbox を覗きにいく）** | Axiom「思考の能動性」と整合、依存ゼロ、Phase 4 で push 化可能 |
| メッセージ寿命 | **読み取り後は archive へ移動、削除しない** | 痕跡保持、デバッグ・学習用途、容量問題は Phase 4 で再設計 |
| 保管場所 | **共通領域 `runtime/dispatches/` の下（Mindspace 内ではない）** | 不可侵原則維持（Mindspace は私有のまま、Dispatch は共有領域に置く） |
| spawn 時の inbox | **`runtime/dispatches/inbox/<mind-name>/` を `spawn-mind.sh` が作成** | spawn 時に通信路を確立、Mind は自分宛だけ読む |
| kill 時の処理 | **inbox の残メッセージは `archive/orphans/<mind-name>/<timestamp>/` へ退避** | 不可侵原則と整合（Mind 消滅と同時に消すのは Mindspace、Dispatch は共有領域なので扱いを分ける）。誰宛か分からなくなる事故を防ぐ |

### 論点ごとの候補比較

#### 1. 通信方式

| 候補 | 不可侵性 | 痕跡 | 同期性 | 実装コスト | 依存追加 | Axiom 整合 |
|---|---|---|---|---|---|---|
| **(a) ファイル経由（共通 `dispatches/` ディレクトリ）** | 高（Mindspace 外、共有領域として扱える） | **自動**（書き込み = 痕跡） | 非同期 | **最小** | なし | **最高** |
| (b) メッセージキュー（Redis / RabbitMQ / Postgres LISTEN/NOTIFY） | 高（外部プロセス経由） | 別途必要（broker のログ） | 即時 / 非同期両対応 | 中〜高 | **大**（broker サービス） | 中（broker が暗黙の Nexus 化する） |
| (c) MCP（Nexus 先取り） | 高（プロトコル経由） | MCP 経路に痕跡 | 即時 | **高**（Phase 4 の仕事を先食い） | **大**（MCP サーバー） | 中（Phase 4 と境界曖昧） |
| (d) stdin/stdout パイプ | 中（プロセス生存中のみ） | **弱**（明示的にログ取りが必要） | 同期寄り | 低 | なし | 低（永続化と痕跡が苦手） |

##### (a) ファイル経由の詳細

- 送信側 Mind は `runtime/dispatches/inbox/<receiver-mind-name>/<timestamp>-<sender>.md` に書く
- 受信側 Mind は自分の `inbox/<self>/` を定期的に覗き、未読を処理する
- 処理後は `archive/<receiver>/` へ移動（削除しない）
- 共通領域は Mindspace ではないので、不可侵原則は崩れない（誰の私有でもない共有領域）

##### (b) メッセージキュー の詳細

- broker（Redis / RabbitMQ）を 1 つ立て、Mind は pub/sub
- 即時配送が魅力だが、Phase 3 で本当に「即時」が要るかは疑問
- broker が事実上「初代 Nexus」になってしまい、Phase 4（MCP）と役割が衝突する
- 依存サービスが増える（テスト / CI / Windows ユーザーの負担）

##### (c) MCP（Nexus 先取り）の詳細

- Phase 4 の Nexus を Phase 3 で作ってしまう案
- 「ADR-0002 で MCP 採用を決めたなら、最初から MCP でいいのでは」という発想
- ただし、MCP の Resources / Tools / Prompts 設計まで Phase 3 で確定するコストが大きい
- Phase 3 = 「素朴に通信路を1本通す」/ Phase 4 = 「正規プロトコルに移行」 と分けたほうが、各 Phase の意思決定密度が下がる

##### (d) stdin/stdout パイプ の詳細

- Unix の伝統的なやり方。最も軽い
- ただし永続化（受信側がいない時にバッファされる場所）の設計が結局必要
- 痕跡（後で読み返せること）が明示的に弱い
- Phase 2 でコンテナ化されたら、コンテナ間 stdin/stdout は普通やらない（やるなら docker exec か socket）

**推奨**: **(a) ファイル経由**。**理由は Axiom 整合性が最も高く、依存ゼロ、痕跡が自動、Phase 4 で MCP に置き換える時もインターフェース変更だけで済む**。

#### 2. メッセージのフォーマット

| 候補 | 人間可読 | 機械処理 | ai-org-os 文化整合 | 痕跡品質 |
|---|---|---|---|---|
| **(a) Markdown + YAML frontmatter** | **高** | 中（frontmatter で構造化可） | **最高**（ADR / Persona / Kind 全部 Markdown） | 高（GitHub Web でも読める） |
| (b) JSON | 中 | 最高 | 低（ai-org-os に JSON は今ほぼない） | 中（読みづらい） |
| (c) YAML（全文 YAML） | 中 | 高 | 中 | 中 |
| (d) プレーンテキスト | 高 | 低（パース困難） | 中 | 中 |

**Markdown + frontmatter の最小例**:

```markdown
---
dispatch_id: 2026-05-22T11-30-00-abc123
from: mind-designer-01
to: mind-implementer-01
subject: "ADR-0004 のレビューお願い"
sent_at: 2026-05-22T11:30:00Z
in_reply_to: null
---

# 本文

ADR-0004 の Decision セクションを書いた。レビューをお願いしたい。
特に「Phase 2 と Phase 3 の関係」の結論部分を見てほしい。
```

**推奨**: **(a) Markdown + frontmatter**。
**理由**:
- ai-org-os の文化（Persona / ADR / Kind = すべて Markdown）と完全整合
- 人間が `cat` で読める = デバッグ・運用が容易
- frontmatter で `from` / `to` / `sent_at` が機械処理可能
- Phase 4 で MCP に乗せる時、frontmatter を MCP の構造化フィールドにマップしやすい

#### 3. メッセージの寿命

| 戦略 | 痕跡 | 容量 | 不可侵原則整合 | 実装コスト |
|---|---|---|---|---|
| (a) 受信したら消す | × | 軽い | 中 | 低 |
| (b) 永久に残す（archive へ移すだけ） | **最高** | 重い（将来） | 高 | 低 |
| (c) TTL（30 日後に削除） | 中 | 中 | 高 | 中（cron / 定期処理） |
| (d) 受信側が「読了マーク」を付ける（移動なし） | 高 | 重い | 中 | 中 |

**推奨**: **(b) 永久に残す（archive へ移すだけ）**。

**理由**:
- Phase 3 は「最小実装で 2 Mind が通信する」段階。容量問題が顕在化するスケールに到達するのはまだ先
- 痕跡は ai-org-os の核（Axiom「共有はプロセスを踏む」の証跡として残る）
- TTL の設計を今やると、判断材料（=どれくらいの期間で何件たまるか）が無いまま決めることになる
- Phase 5（Realm / Warden 導入）で「リソース制限は Realm が担保」の方針に従い、消去ルールはそこで再設計するほうが筋

**いつ archive へ動かすか**:
- 受信 Mind が「読んだ」と明示した時（受信側の責務）
- もしくは送信から N 日経過した時（運用判断、Phase 3 では実装しない）

#### 4. 保管場所（Mindspace 内 vs 共通領域）

| 候補 | 不可侵原則 | 実装簡便性 | Axiom 整合 |
|---|---|---|---|
| (a) 共通領域 `runtime/dispatches/`（Mindspace の外） | **完全に保たれる** | 中 | **最高** |
| (b) 各 Mind の Mindspace 内に `inbox/` を作って送信者が書きにいく | **崩れる**（送信者が受信者の Mindspace に書く） | 低 | **低**（Axiom 違反） |
| (c) 各 Mind の Mindspace 内に `outbox/` を作って受信者が読みにいく | **崩れる**（受信者が送信者の Mindspace を読む） | 低 | **低**（Axiom 違反） |

**推奨**: **(a) 共通領域**。**Mindspace は私有・不可侵を保ち、Dispatch は「誰の私有でもない共有領域」に置く**。これは現実の組織で「机の上（私物）」と「会議室のホワイトボード（共有）」を分けるのと同型。

#### 5. 受信側のウェイク方式

| 方式 | Axiom「能動性」整合 | 即時性 | 実装コスト | プラットフォーム依存 |
|---|---|---|---|---|
| (a) 能動 poll（受信 Mind が定期的に inbox を覗く） | **高** | 中（poll 間隔次第） | **最小** | なし |
| (b) 送信時にシグナル（OS signal / unix socket） | 中 | 高 | 中 | 中（Windows で詰むケースあり） |
| (c) ファイルシステムイベント（inotify / fswatch） | 中 | 高 | 中 | **高**（Linux / mac / Windows で API が違う） |
| (d) 送信者が受信者に直接呼びかける（CLI invoke） | 低（受動的になる） | 高 | 低 | 中 |

**推奨**: **(a) 能動 poll**。

**理由**:
- ADR-0002 §7「**Mind は呼び出しを待つ受動的存在ではなく、能動的に動ける主体**」「ウェイク条件なし」と整合する
- poll は「思考が能動的に確認しに行く」=「メールを定期的に開く」と解釈でき、Axiom 違反にならない
- 依存ゼロで Windows / mac / Linux すべてで動く
- Phase 4 で MCP の subscription / notification に置き換える時、Mind 側の「inbox を見る」というメンタルモデルは変わらない（裏側だけ MCP push になる）

**poll の実装イメージ**:
- Persona の Claude が、自分の作業ループの中で `ls runtime/dispatches/inbox/<self>/` 相当を確認する
- 未読があれば読む、なければ作業継続
- 頻度は Persona / Kind に任せる（Axiom はこれを規定しない）

#### 6. ディレクトリ構造案

##### 案 X（推奨）: 共通領域 + Mind ごとの inbox サブディレクトリ

```
runtime/
├── dispatches/                          ← 共通の Dispatch 領域（Axiom 境界外、共有領域）
│   ├── inbox/
│   │   ├── <to-mind-name-A>/            ← Mind A 宛て
│   │   │   ├── 2026-05-22T11-30-00-abc.md
│   │   │   └── ...
│   │   └── <to-mind-name-B>/            ← Mind B 宛て
│   │       └── ...
│   └── archive/
│       ├── <mind-name-A>/               ← Mind A が読み終えた / orphan になった分
│       │   └── 2026-05-22T11-30-00-abc.md
│       └── orphans/
│           └── <killed-mind-name>/
│               └── <timestamp>/
│                   └── ...
├── minds/                               ← 各 Mind の Mindspace（不可侵）
│   ├── <mind-name-A>/
│   └── <mind-name-B>/
├── personas/
├── kinds/
└── ...
```

##### 案 Y: 各 Mindspace 内に inbox を持たせる

```
runtime/
├── minds/
│   ├── <mind-name-A>/
│   │   ├── CLAUDE.md
│   │   └── inbox/        ← Mind A 宛て（ただし送信者が書きにいく必要あり）
│   └── <mind-name-B>/
│       ├── CLAUDE.md
│       └── inbox/
```

**評価**: **案 X が圧勝**。案 Y は送信者が受信者の Mindspace に書き込む必要があるため、Axiom（Mindspace は私有・不可侵）に**正面から違反**する。

##### 案 Z: 共通領域 + 送信記録（outbox）も併設

```
runtime/
├── dispatches/
│   ├── inbox/<receiver>/...
│   ├── outbox/<sender>/...       ← 送信履歴（送信者が自分用に保持）
│   └── archive/...
```

**評価**: outbox は「送信者の私有」とみなすこともでき、Mindspace 内に置いてもよい（=送信者は自分の Mindspace に書く、Axiom 違反にならない）。Phase 3 では複雑性を避けて outbox を作らず、archive に統合してもよい。推奨案では outbox を作らない方向で寄せる。

**推奨**: **案 X**。outbox は当面作らない。必要なら Phase 3.1 で追加。

---

## Axiom（不変項）との整合性確認

| Axiom | Phase 3 での扱い | 整合性 |
|---|---|---|
| **思考⇔思考の境界**（ADR-0002 §2 / §9） | Dispatch だけが正規ルート。Mindspace から相手の Mindspace を直接いじる経路は存在しない | **強化される**（境界が物理的に1本に絞られる） |
| **Mindspace 不可侵**（ADR-0002 §2 / §9） | 共通 `dispatches/` 領域は誰の Mindspace でもない。送信者は共有領域に書く、受信者は共有領域から読む | **保たれる** |
| **共有はプロセスを踏む**（ADR-0002 §9） | Dispatch そのものが「プロセス」を踏む明示動作。frontmatter で from/to/sent_at を明示し、痕跡を残す | **保たれる**（むしろ核となる仕組み） |
| **思考の能動性 / ウェイク条件なし**（ADR-0002 §7） | poll は「能動的に確認しに行く」と解釈でき、受動的トリガではない。Mind 側からは「メールを定期的に開く」と同型 | **保たれる** |
| **記憶は思考と共に消える**（ADR-0002 §9） | Mind kill 時、Mindspace は消える。Dispatch は共有領域なので残す（送信者・受信者・第三者の痕跡）。orphan として archive する | 整合（Dispatch は記憶ではなく **公共の痕跡** という整理） |

**懸念点 / 整理**:

- 「Dispatch を archive に残す」は「思考と共に消える」と矛盾しないか？
  - 整理: archive されるのは **Dispatch というプロセスの結果**であって、Mind の **私的記憶（Mindspace）** ではない。会議の議事録が参加者の死後も残るのと同型。Axiom に違反しない。
- 受信 Mind が読まずに kill された場合、未読メッセージは誰のもの？
  - 整理: 共有領域に置かれていたので「誰のものでもなく、共有領域の orphan」。`archive/orphans/<killed-mind>/<timestamp>/` に退避する。新規に同名 Mind が spawn されても自動配達しない（明示の復元が必要）。これは Axiom と整合する（思考が変われば連続性はない）。

---

## ディレクトリ構造の最終提案

```
runtime/
├── dispatches/                          # 共通の Dispatch 領域
│   ├── inbox/                           # Mind 別 inbox（spawn 時に作成）
│   │   └── <mind-name>/
│   │       └── <timestamp>-<sender>.md
│   ├── archive/                         # 読了 / orphan を保管
│   │   ├── <mind-name>/
│   │   └── orphans/
│   │       └── <killed-mind-name>/
│   │           └── <timestamp>/
│   └── .gitkeep
├── minds/
├── personas/
├── kinds/
├── tests/
├── spawn-mind.sh        # 改修: spawn 時に inbox/<mind-name>/ を作る
├── kill-mind.sh         # 改修: kill 時に未読を archive/orphans/ へ移す
├── list-minds.sh
├── dispatch-send.sh     # 新規: 送信ヘルパー
├── dispatch-read.sh     # 新規: 受信ヘルパー（受信 Mind 内から呼ぶ）
└── ...
```

---

## spawn-mind.sh / kill-mind.sh への影響

### spawn-mind.sh 改修案（擬似コード）

```bash
# 既存の Phase 1 処理に加えて:
INBOX_DIR="${SCRIPT_DIR}/dispatches/inbox/${MIND_NAME}"
ARCHIVE_DIR="${SCRIPT_DIR}/dispatches/archive/${MIND_NAME}"

mkdir -p "${INBOX_DIR}"
mkdir -p "${ARCHIVE_DIR}"

echo "[spawn-mind] Dispatch inbox: ${INBOX_DIR}"
```

### kill-mind.sh 改修案（擬似コード）

```bash
# 既存の Phase 1 処理（Mindspace 消去）に加えて:
INBOX_DIR="${SCRIPT_DIR}/dispatches/inbox/${MIND_NAME}"
ORPHAN_DIR="${SCRIPT_DIR}/dispatches/archive/orphans/${MIND_NAME}/$(date -u +%Y%m%dT%H%M%SZ)"

if [ -d "${INBOX_DIR}" ] && [ -n "$(ls -A "${INBOX_DIR}" 2>/dev/null || true)" ]; then
  mkdir -p "${ORPHAN_DIR}"
  mv "${INBOX_DIR}"/* "${ORPHAN_DIR}/"
  echo "[kill-mind] Unread dispatches moved to ${ORPHAN_DIR}"
fi
rmdir "${INBOX_DIR}" 2>/dev/null || true

# archive/<mind-name>/ は **消さない**（痕跡保持）
```

### dispatch-send.sh（新規、擬似コード）

```bash
# Usage: dispatch-send.sh <from-mind> <to-mind> <subject> [body-file]
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
ID="${TS}-$(head -c 6 /dev/urandom | xxd -p)"
TARGET="${SCRIPT_DIR}/dispatches/inbox/${TO_MIND}/${ID}.md"

if [ ! -d "${SCRIPT_DIR}/dispatches/inbox/${TO_MIND}" ]; then
  echo "[ERROR] Receiver Mind '${TO_MIND}' has no inbox (not spawned?)" >&2
  exit 7  # 新規エラーコード: receiver not found
fi

cat > "${TARGET}" <<EOF
---
dispatch_id: ${ID}
from: ${FROM_MIND}
to: ${TO_MIND}
subject: ${SUBJECT}
sent_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
in_reply_to: null
---

$(cat "${BODY_FILE:-/dev/stdin}")
EOF

echo "[dispatch-send] Sent: ${TARGET}"
```

### dispatch-read.sh（新規、擬似コード）

```bash
# Usage: dispatch-read.sh <self-mind-name> [--archive]
# 自分宛 inbox を列挙、表示、archive へ移動する

INBOX="${SCRIPT_DIR}/dispatches/inbox/${SELF}"
ARCHIVE="${SCRIPT_DIR}/dispatches/archive/${SELF}"

for msg in "${INBOX}"/*.md; do
  [ -e "${msg}" ] || continue
  echo "----- $(basename "${msg}") -----"
  cat "${msg}"
  if [ "${ARCHIVE_AFTER_READ:-1}" = "1" ]; then
    mkdir -p "${ARCHIVE}"
    mv "${msg}" "${ARCHIVE}/"
  fi
done
```

---

## テストへの影響

### Phase 3 で追加すべきテスト（叩き台: `test-dispatch.sh`）

| ケース | 期待 |
|---|---|
| spawn 後に inbox が作られている | `runtime/dispatches/inbox/<name>/` が存在する |
| 存在しない Mind に送信 | exit 7、エラーメッセージで「未 spawn」を案内 |
| 正常送信 | inbox に `.md` ファイルが 1 個増える、frontmatter に from/to/subject/sent_at がある |
| 受信（read） | 内容が出力される、archive へ移動する |
| 同時送信（race） | 同じ timestamp でも `dispatch_id` が衝突しない（ランダム suffix で回避） |
| kill 時に未読あり | `archive/orphans/<killed>/<ts>/` に未読が移される、`inbox/<killed>/` は消える |
| kill 後の archive | `archive/<killed>/` の過去ログは消えずに残る |
| 2 Mind 双方向通信 | A → B 送信、B が読む、B → A 返信、A が読む、痕跡が両方向に残る |

### 既存テストとの統合

- 既存の `test-spawn-mind.sh` / `test-kill-mind.sh` は inbox 作成・退避の検査を追加する（破壊的変更ではなくチェック追加）
- `runtime/tests/run-tests.sh` に `test-dispatch.sh` を追記
- CI（`.github/workflows/runtime-tests.yml`）はそのまま動く

### Phase 2 と並行 / 後行した場合の差分

- **Phase 3 を Phase 2 より先に着手した場合**: テストはホスト fs だけで完結（依存ゼロを維持）。Phase 2 着手後、`dispatches/` を共有 Docker volume に置き換える改修が走る（**インターフェースは変えない**ので、テストの期待値は維持できる）
- **Phase 2 → Phase 3 の順**: `dispatches/` を最初から named volume として設計。テストはコンテナ前提になる

---

## リスク

| # | リスク | 重大度 | 緩和策 |
|---|---|---|---|
| R1 | **競合（同時書き込み）**: 同じ timestamp で 2 通同時送信すると衝突 | 中 | `dispatch_id` に timestamp + ランダム suffix を入れる（実装提案済）。ファイル名衝突を `set -o noclobber` 相当で検知 |
| R2 | **順序保証なし**: ファイル mtime 順 ≠ 論理順 | 低 | Phase 3 では「順序保証しない」と明示。frontmatter の `sent_at` を Mind が見て解釈する。完全な順序保証は Phase 4（MCP）まで延期 |
| R3 | **受信者がいない時のメッセージ（dead letter）**: 未 spawn の Mind に送信 | 低 | `dispatch-send.sh` が事前検査して exit 7。「送信先未 spawn」を明示エラー化 |
| R4 | **永続化容量**: archive が肥大化 | 低（Phase 3 段階） | Phase 5 で Warden に削減ロジックを持たせる。Phase 3 ではログ的に蓄積させて運用観察 |
| R5 | **能動 poll の負荷**: Mind が頻繁に inbox を覗くと token / IO を浪費 | 中 | Persona / Kind に「poll 頻度の目安」を書く。Phase 5 で Warden がリソース制限を担保 |
| R6 | **Axiom 違反の実装**: Mind が共通領域を経由せず相手 Mindspace に直接書く実装が混入 | 中 | Mindspace は他 Mind から読み書き不可（Phase 2 で named volume にすれば物理担保。Phase 3 単独だと policy 止まり）。テストでチェックする |
| R7 | **Phase 2 と Phase 3 の整合性が事後的に崩れる**: Phase 3 で `runtime/dispatches/` をホスト fs に置いたが、Phase 2 で Docker volume に移行する時にパスがズレる | 中 | 本 ADR で **論理パス（`runtime/dispatches/`）を固定**し、物理実体（fs / volume）は差し替え可能と明記。Phase 2 が後追いで来ても破壊的変更にならない |
| R8 | **同名 Mind が再 spawn された時に orphan が混ざる** | 低 | spawn 時に `archive/orphans/<name>/` の存在を警告するが、自動で配達はしない。明示の復元は人間 / 別 Mind の責務 |
| R9 | **Windows での挙動**: `mv` / ファイルロックの挙動が POSIX と微妙に違う | 中 | bash on Windows（Git Bash / WSL）で `mv` の atomic 性が落ちる場合がある。テストで `mv` の代わりに `rename` 系の atomic 操作を検討。Phase 2 でコンテナ化されれば問題は消える |

---

## Phase 3 を実装するかの判断軸

朝起きたユーザーが見て判断できるよう、**3 つの問い**で整理する。

### 問い 1: 「組織」感が今すぐ要るか？

- **要る** → Phase 3（Dispatch）は最短経路。2 Mind が会話する=組織の最小単位
- **要らない（Mind 1 個で十分、ペアプロ的に Claude と対話できればよい）** → Phase 3 は急がない

### 問い 2: 同時 Mind 数の想定スケールは？

- **1 個（個人で 1 Mind）** → Phase 3 は意味がない（送る相手がいない）
- **2〜数個（複数役割を並走）** → Phase 3 は **必須**
- **多数（10+）** → Phase 3 単独では不十分。Phase 4（Nexus）まで一気に必要

### 問い 3: Phase 2 / Phase 3 / Phase 4 のどの順序がコスト最小か？

| 順序 | 評価 |
|---|---|
| **Phase 2 → Phase 3** | 王道。コンテナ化 → 通信。各 Phase の責務が明確 |
| **Phase 3 → Phase 2** | **可能**。Phase 3 のインターフェースを論理パスで固定すれば、Phase 2 の volume 化が後付けで効く。「組織感」を早く出したい時の最短ルート |
| **Phase 2 + Phase 3 を 1 PR で統合** | 設計トレードオフが増える、PR が肥大、レビュー困難。**非推奨** |
| **Phase 3 をスキップして Phase 4（MCP）から** | Phase 3 の素朴な実装で得られる「Mind が能動 poll する設計感覚」を得られないまま MCP に行くと、MCP の使い方を見誤る可能性。**推奨しない** |

**総合**: 「組織感を早く出したい」「同時 Mind 数 2 が現実的」なら **Phase 3 を Phase 2 より先に着手するのもアリ**。Phase 2 を先にやって不可侵性の物理担保を取りに行くのと、Phase 3 を先にやって Dispatch のインターフェースを確立するのは、**同価値**。

---

## 代替案

### 代替案 1: Phase 2 と Phase 3 を 1 PR で統合する

**内容**: Docker 化 + Dispatch を同一 PR で実装。コンテナ間で共有 volume を確保し、その volume を `dispatches/` として使う。

**長所**:
- 移行作業（Phase 3 のホスト fs パスを volume に差し替える）を後で発生させない
- 「Mind がコンテナで動き、コンテナ同士が会話する」=ADR-0002 の世界観に最短距離

**短所**:
- PR が肥大化し、レビュー困難
- 2 つの異なる設計判断（コンテナ化方式 / Dispatch 方式）を同時に決める必要があり、判断密度が上がる
- どちらかが詰まると両方止まる
- Phase 2 のリスク R1（Claude CLI が OAuth でしか動かない問題）が解決していない段階で Phase 3 まで一緒にやると、両方とも前進できなくなる

**評価**: 推奨しない。**独立な 2 PR に分けるべき**。

### 代替案 2: Phase 4（Nexus = MCP）まで一気に進める

**内容**: Phase 3 のファイル経由 Dispatch をスキップし、最初から MCP サーバーで通信する。

**長所**:
- ADR-0002 の本命プロトコル（MCP）に最短到達
- 認可 / 認証 / 痕跡などが MCP 標準で揃う

**短所**:
- MCP サーバー実装 + Mind 側 MCP クライアント実装の **両方** を一度に作る必要がある
- Phase 3 の素朴な実装で得られる「2 Mind の最小通信が成立する手応え」を経ずに Phase 4 に行くと、MCP の何を本当に必要としているか分からないまま設計することになる
- MCP 経由通信は Phase 5（Realm / Warden）の認可機構と密接で、Phase 4 単独で完結しにくい

**評価**: **非推奨**。段階を飛ばすコストが大きい。

### 代替案 3: Phase 3 を諦めて Mind 1 個運用に最適化する

**内容**: 「2 Mind の通信」を当面諦め、Mind 1 個（自分のペアプロ相手）を Phase 2 で安定させる方向に倒す。

**長所**:
- 個人用途で当面困らない
- Phase 2 までで Mindspace の不可侵性 + 24/365 稼働が達成できれば、組織感を出さなくても価値がある

**短所**:
- ai-org-os の本質（組織 = 思考のネットワーク）から離れる
- Phase 5 まで「組織」が成立しない

**評価**: 個人用途に閉じるなら合理。**組織フレームワークとしての本筋ではない**。

### 代替案 4: ファイル経由ではなくシンプルな TCP/Unix socket でやる

**内容**: ファイル経由を諦め、Mind 同士が直接 socket でつなぐ。

**長所**: 即時性、Unix 文化と整合
**短所**:
- 痕跡が自動で残らない（ログを別途取る必要）
- Mind が同時起動していないと通信不能（非同期性が崩れる）
- Phase 2（コンテナ化）後はコンテナネットワーキングの設計が要る

**評価**: **非推奨**。Phase 3 の目的（非同期 + 痕跡）に合わない。

---

## Consequences（影響、Accepted 時に何が起きるか）

### ポジティブ

- ai-org-os が初めて「複数 Mind が会話する組織」になる
- Axiom（思考⇔思考の境界 / Mindspace 不可侵 / 共有はプロセス）が実装で具現化される
- Dispatch のインターフェース（書く場所・読む場所・フォーマット）が確立し、Phase 4（MCP）への移行が **インターフェース変更なし** で可能
- 痕跡が自動で残るので、後の「組織記憶」の派生形成（ADR-0002 §2 注）の元データとして利用可能
- Phase 2 と独立に進められるので、開発の並列度が上がる

### ネガティブ

- `runtime/dispatches/` という新規ディレクトリが increases the surface area
- `spawn-mind.sh` / `kill-mind.sh` の責務が増える
- テストが増える
- 永続化容量が（緩やかに）増えていく

### 副作用

- Phase 1 のテストは inbox 作成・退避のチェック追加で済むが、**Phase 2 を後追いで着手したときに `runtime/dispatches/` の物理実体が volume に変わる**。論理パスは固定なので、テスト・運用の期待値は維持できるが、**Phase 2 を Phase 3 より後にやる場合、Phase 2 設計時に Dispatch volume の扱いを盛り込む必要がある**（ADR-0003 への追補が要る）

---

## 議論ログ（Discussion log）

本 ADR は壁打ちセッションを経ずに設計担当（私）が初稿を書き起こした。承認プロセスの中で議論を追記する。

### Step 1（初稿、設計担当）

- ADR-0001 / ADR-0002 / ADR-0003 と Phase 1 実装を踏まえ、Phase 3 の達成目標と論点を網羅
- 推奨案を「ファイル経由 + Markdown + 能動 poll + 共通領域 + 永久 archive」に倒した
- **Phase 2 と Phase 3 は独立であると明示**し、順序は判断の余地ありとした
- 代替案として「Phase 2 と統合」「Phase 4 まで飛ばす」「Phase 3 をスキップ」「socket 通信」を提示

### Step 2（朝のユーザー判断、想定）

- 推奨案の各論点に対して採用/不採用を決める
- 着手判断（Phase 2 を先 / Phase 3 を先 / 並行 / どちらか後回し）を確定
- Accepted に昇格させるか、Proposed のまま改稿するかを決める

---

## 次にやること（Accepted 時の Issue 化候補）

1. **`runtime/dispatches/` の初期構造作成**（空ディレクトリ + `.gitkeep`）
2. **`spawn-mind.sh` 改修**: spawn 時に inbox を作る
3. **`kill-mind.sh` 改修**: kill 時に未読を orphan へ退避
4. **`dispatch-send.sh` 新設**: 送信ヘルパー
5. **`dispatch-read.sh` 新設**: 受信ヘルパー
6. **`test-dispatch.sh` 新設**: 双方向通信 / orphan 化 / archive をテスト
7. **既存テストへのチェック追加**: inbox 作成、kill 時の orphan 化
8. **`runtime/README.md` 更新**: Phase 3 用の Quick Start
9. **Persona への追記**（任意）: 「Dispatch を能動的に確認する」運用ガイドの追記
10. **Phase 2 着手済みの場合の追補**: `dispatches/` を named volume として扱う ADR-0003 への追記

これらは Accepted 後に個別 Issue として切り出す。

---

## 関連

- [ADR-0001: ai-org-os を「開発組織の不変項」を定義するフレームワークとして再定義する](./0001-ai-org-os-as-invariant-framework.md)
- [ADR-0002: 用語と「メタのメタ」構造の確定](./0002-vocabulary-and-meta-meta-structure.md)
- [ADR-0003: Phase 2（Docker 化）の設計案](./0003-docker-and-phase-2-design.md)
- [`runtime/spawn-mind.sh`](../../runtime/spawn-mind.sh) — Phase 1 実装、Phase 3 で改修対象
- [`runtime/kill-mind.sh`](../../runtime/kill-mind.sh) — Phase 1 実装、Phase 3 で改修対象
- [`runtime/tests/`](../../runtime/tests/) — テスト群、Phase 3 で `test-dispatch.sh` 追加
- [`runtime/README.md`](../../runtime/README.md) — runtime の現状と Phase 計画

---

> **改めて**: 本 ADR は **Proposed**。実装は本 ADR の承認後に着手する。
> Accepted に昇格させるには、上記「推奨案」の各論点をユーザーが確認し、代替案との比較で最終案を確定する必要がある。
> 特に **「Phase 2 と Phase 3 のどちらを先に着手するか」** は本 ADR で「独立」と結論したが、実務的にどちらに開発リソースを振るかはユーザー判断。
