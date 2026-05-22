# ADR-0003: Phase 2（Docker 化）の設計案

> 想定読者:
> - Phase 2 を実装するメンテナ（spawn-mind.sh の書き換え、Dockerfile / Compose の追加、テストの拡張を担う）
> - Phase 2 への着手を判断する意思決定者（プロダクトオーナー）
>
> 目的: 朝起きたユーザーが「Phase 2 をいま着手するか / 別 Phase に進むか / そもそも棚上げするか」を判断できる材料を残す。

## Status

**Proposed** — 2026-05-22

> 本 ADR は **設計のみ**。実装は本 ADR の承認後に着手する。
> Accepted に昇格させるには「採用案」セクションの選択肢を絞り込む必要がある。

## Context（背景）

### これまでの位置

- [ADR-0001](./0001-ai-org-os-as-invariant-framework.md): ai-org-os は「開発組織の不変項（Axiom）を定義するフレームワーク」。組織 = 思考のネットワーク。
- [ADR-0002](./0002-vocabulary-and-meta-meta-structure.md): 用語と階層構造を確定。**Realm / Warden / Nexus / Guild / Guildmaster / Mind / Mindspace / Persona / Axiom / Dispatch**。
- Phase 1（実装済）: `runtime/spawn-mind.sh` で Mind を 1 個ホスト上に spawn できる。Mindspace = ホストの `runtime/minds/<name>/` ディレクトリ。CLAUDE.md として Persona を配置するところまで。テスト（`runtime/tests/test-spawn-mind.sh`）も整備済。

Phase 1 は「Mind が物理的に存在しうる」を最小コストで確認した状態。ただし以下が未達:

- **Mindspace の不可侵性が物理的に担保されていない**: ホスト fs に裸で置いているので、他の Mind プロセスや人間が容易にアクセスできてしまう。ADR-0002 の「Mindspace は私有・不可侵」原則がポリシー止まりで、強制力がない。
- **Mind の実行環境が分離されていない**: Mind プロセスがホストの権限・依存・ファイルシステムをそのまま持つ。Mind 同士もホストプロセス空間で混在する。
- **持続性（24/365 稼働）の前提が無い**: ターミナルを閉じれば Mind は消える。

### Phase 2 の達成目標

[runtime/README.md](../../runtime/README.md) の次フェーズ計画より:

> Phase 2: Mindspace の永続化 + コンテナ化（Docker）

これを ADR-0002 の Axiom と接続して具体化すると:

1. **Mind = Docker コンテナで起動**（プロセス分離、依存分離、ライフサイクル分離）
2. **Mindspace = Docker volume として永続化**（コンテナを破棄しても残る、起動し直しても繋がる）
3. **不可侵性を物理的に担保**: ホストの fs を直接マウントしない。コンテナ間で読み書き不可（OS レベルの分離 + named volume のスコープ）
4. **`spawn-mind.sh` が Docker を呼ぶように書き換え**（または Compose ファイル生成に切り替え）

Phase 2 では **Realm / Warden / Nexus / Guildmaster / Dispatch はまだ作らない**。Mind 1 個をコンテナ化して永続化することに絞る。

### スコープ外（Phase 2 で扱わないこと）

- Realm コンテナ（Phase 5 以降）
- Warden（リソース管理、3 段階ライフサイクル）（Phase 5）
- Nexus（MCP サーバー）（Phase 4）
- Mind 同士の Dispatch（Phase 3）
- 同時 Mind 数の管理 / スケジューラ
- 認証フローのプロダクション化（API キー固定で十分）

---

## Decision（推奨案 + 候補比較）

> 本 ADR は Proposed のため、ここでは「単一の決定」ではなく **推奨案** と **候補比較** を並べる。
> Accepted に昇格するときに、ユーザーが下の選択肢から 1 案を選んで確定する想定。

### 推奨案（叩き台、Accepted 化のときに調整可）

| 軸 | 推奨 | 理由（要約） |
|---|---|---|
| ベースイメージ | **`node:20-slim` + Claude CLI を npm でインストールする独自イメージ** | Claude CLI の正攻法。サイズも実用域。 |
| Docker / Compose | **最初から Docker Compose** | Phase 3 以降で複数 Mind になるのが確定路線なので、最初から Compose で書いた方が後で書き直さない。 |
| API キー | **ホストの `.env` から `--env-file` 経由でコンテナへ注入** | Phase 2 では十分。Phase 5 で Warden が secret 管理に昇格させる。 |
| Mindspace | **named volume**（`mindspace-<mind-name>`） | 不可侵性が最も強い。Phase 2 の目的に直接合致。 |
| ネットワーク | **bridge network を Compose で 1 つ用意するが、Mind は接続だけしておく**（Phase 2 では使わない） | Phase 3 への布石。Phase 2 では不要だが、後付けの破壊的変更を避ける。 |
| spawn-mind.sh | **Compose ファイル（`runtime/minds/<name>/docker-compose.yml`）を生成して `docker compose up -d` を呼ぶ方式** | テンプレ生成 + 起動の二段。冪等性が出る。 |

### 論点ごとの候補比較

#### 1. ベースイメージ

| 候補 | サイズ感 | Claude CLI 動作 | 保守性 | リスク |
|---|---|---|---|---|
| `node:20`（フル） | 約 1.1GB | ◎（Node 公式、Claude CLI は Node 系） | 高 | サイズが大きい |
| `node:20-slim` | 約 240MB | ◎ | 高 | 不足パッケージは追加が必要 |
| `node:20-alpine` | 約 130MB | △（musl 起因の互換問題が時々ある） | 中 | Claude CLI の依存に glibc 依存があると詰む |
| `ubuntu:24.04` + Node を別途入れる | 約 80MB（ベース）+ Node 約 100MB | ◎ | 中 | レイヤ管理を自前で書く |
| `anthropic/claude-code:latest`（仮称） | 不明（公式があれば最小） | ◎ | 最高 | **2026-05 時点で公式の Claude Code Docker イメージが存在するかは未確認。事前検証が必要** |
| 完全独自イメージ（scratch から） | 最小 | × | 低 | やる価値なし |

**推奨**: `node:20-slim` を起点に、Claude CLI を `npm install -g` する独自イメージを 1 つ作って `ai-org-os/mind:phase2` 等としてタグ付け。
**もし公式の Claude Code イメージが提供されていれば、最優先で乗り換える**。

#### 2. Docker 単体 vs Docker Compose

| 観点 | Docker 単体（`docker run` を spawn-mind.sh が叩く） | Docker Compose（`docker-compose.yml` を生成して `docker compose up` を叩く） |
|---|---|---|
| 1 Mind しかない Phase 2 で十分か | 十分 | 過剰だが許容範囲 |
| 複数 Mind になった時の追加コスト | 中（複数 `docker run` を協調させる仕組みを書く） | 低（Compose は元々マルチサービス想定） |
| 設定の宣言性 | 低（シェルスクリプトで argv を組み立て続ける） | 高（YAML） |
| Phase 3 の Dispatch（ファイル経由通信）で必要になる共有 volume の追加 | スクリプト改修 | YAML 追記 |
| ローカル開発者の学習コスト | 低（誰でも知ってる） | 低〜中 |
| 起動オーバーヘッド | 低 | わずかに高い |

**推奨**: **最初から Compose**。Phase 3 で確実に Dispatch が来るので、書き直しコストを払うより最初から Compose の方が安い。

#### 3. API キー / 認証

| 方式 | 安全性 | 簡便性 | Phase 2 適合 | 備考 |
|---|---|---|---|---|
| 環境変数（`-e ANTHROPIC_API_KEY=...`） | 低（プロセスリスト・履歴に残る） | 高 | × | 採用しない |
| `.env` ファイル + `--env-file` | 中（ファイルに置く、git ignore 前提） | 高 | ◎ | **推奨** |
| Docker secret | 高 | 中（swarm モード前提が伝統的） | △ | Phase 2 では過剰、Phase 5 で Warden に持たせる |
| ホストの credential store + 起動時注入 | 高 | 中 | △ | Phase 2 では不要 |
| OAuth ベース（Claude CLI 標準の `claude login`） | 高 | **コンテナ内ではブラウザがないため著しく困難** | × | リスクセクション参照 |

**推奨**: **`.env` + `--env-file`**。`.env` はリポジトリ直下 or `runtime/.env` に置き、`.gitignore` で確実に除外。`spawn-mind.sh` は `.env` の存在を起動前に検証する。

> **重要なリスク**: Claude CLI が現在 OAuth フローをデフォルトとしている場合、コンテナ内では `claude login` が成立しない。
> → Phase 2 着手前に「Claude CLI が API キー直接指定で動くか」「動くなら環境変数名は何か」を確認する必要がある。
> → 動かない場合、Phase 2 の前提が崩れるので別案（ホスト側で `claude` を起動して Mindspace だけ volume 化する hybrid）を検討する。

#### 4. Mindspace の永続化方式

| 方式 | 不可侵性 | デバッグ容易性 | 移植性 | バックアップ容易性 |
|---|---|---|---|---|
| (a) named volume（`docker volume create mindspace-<mind>`） | **高**（コンテナ間で隔離、ホストから直接見えにくい） | 中（`docker run --rm -v` で覗く必要あり） | 高 | 中（`docker run --rm tar` 等で取り出す） |
| (b) bind mount（`runtime/minds/<mind>:/mindspace`） | **低**（ホスト fs に裸で見える、他プロセスから読める） | 高（ホストからそのまま見える） | 中（パス差異が出る） | 高（普通にコピー） |
| (c) ハイブリッド（メイン部分は named volume、ログだけ bind） | 中 | 中 | 中 | 中 |

**推奨**: **(a) named volume**。
**理由**: Phase 2 の中核目的は「不可侵性を物理的に担保」。bind mount だと Phase 1 と同じく policy 止まりになる。
**トレードオフ受容**: デバッグ時は `docker run --rm -v mindspace-<name>:/m -it alpine sh` のような救済コマンドを README に書いておけば実用上問題ない。

#### 5. ネットワーク

| 案 | Phase 2 での妥当性 | Phase 3 への布石 |
|---|---|---|
| ネットワーク指定なし（default bridge） | 動く | Mind 間通信のときに作り直し |
| Compose で `ai-org-os-net` という bridge を 1 つ作って Mind を所属させる | わずかに過剰 | Phase 3 で Mind を追加するだけで Dispatch 経路が確保される |
| host network | 動くが分離が崩れる | 採用しない |

**推奨**: **Compose で `ai-org-os-net` という bridge を 1 つ作って Mind を所属させる**。Phase 2 では使わないが、Phase 3 で追加コストゼロ。

### Phase 2 完了の Definition of Done（叩き台）

- [ ] Dockerfile が 1 個存在し、`docker build -t ai-org-os/mind:phase2 .` でビルドが通る
- [ ] `runtime/spawn-mind.sh <kind> <persona> <name>` が以下を実行する:
  - Compose ファイル（`runtime/minds/<name>/docker-compose.yml`）を生成
  - named volume `mindspace-<name>` を作成
  - CLAUDE.md（Persona）を volume に投入する初期化ステップ（init container か one-shot コンテナ）
  - `docker compose up -d` でコンテナ起動
- [ ] `docker ps` で Mind コンテナが Running になっている
- [ ] `docker volume ls` に `mindspace-<name>` が見える
- [ ] コンテナを `docker compose down` → `up -d` しても Mindspace の内容が残る
- [ ] ホスト側からは `runtime/minds/<name>/` に **CLAUDE.md が直接見えない**（不可侵性確認）
- [ ] テスト `test-spawn-mind-docker.sh` が追加されている（後述）

---

## 不変項（Axiom）との整合性確認

| Axiom | Phase 2 での扱い | 整合性 |
|---|---|---|
| Mindspace の不可侵性（ADR-0002 §2 / §9） | named volume で物理的に隔離 | **強化される**（Phase 1 は policy 止まりだったのが Phase 2 で物理担保） |
| 思考と共に消える記憶 | コンテナ削除 + volume 削除を 1 操作にまとめる（`docker compose down -v`） | 整合 |
| 思考の能動性 / ウェイク条件なし（ADR-0002 §7） | ENTRYPOINT で Claude CLI を直接起動。条件待ちは作らない | 整合 |
| 共有プロセス（Dispatch） | Phase 2 ではまだ作らない | スコープ外 |
| 3 段階ライフサイクル（要求→承認→実行）（ADR-0002 §6） | Phase 2 では Warden がいないので、`spawn-mind.sh` 直接実行 = 要求と実行のみ。承認は人間（ユーザー）が CLI 実行することで暗黙に与える | 整合（Phase 5 で Warden に昇格） |
| リソース制限は Realm レイヤーで担保（ADR-0002 §7） | Phase 2 では Docker の `--memory` `--cpus` で予備実装可能だが、Phase 5 の Warden 統合まで本格運用しない | 整合 |

**懸念点**:

- Phase 2 で「Mindspace は他 Mind から読めない」が達成されるが、**ホストの root ユーザー**は Docker volume の中身を見られる。これは Axiom と完全一致しない。
  - 整理: Axiom は「他 **Mind** から不可侵」を要求。Realm 外（ホスト管理者）は別レイヤー。許容する。
  - Phase 5 以降で Realm をホスト全体を覆うコンテナに昇格させたとき、この境界が再整理される。

---

## spawn-mind.sh の変更案（擬似コードレベル）

### 案 A: docker run 直叩き（Compose を使わない案）

```bash
# Phase 2 案 A — Compose を使わない最小案
docker volume create "mindspace-${MIND_NAME}" >/dev/null

# Persona を volume に投入（one-shot コンテナ）
docker run --rm \
  -v "mindspace-${MIND_NAME}:/mindspace" \
  -v "${SCRIPT_DIR}/personas/${PERSONA}.md:/tmp/persona.md:ro" \
  alpine sh -c "cp /tmp/persona.md /mindspace/CLAUDE.md"

# Mind 本体を起動
docker run -d \
  --name "mind-${MIND_NAME}" \
  -v "mindspace-${MIND_NAME}:/mindspace" \
  --env-file "${RUNTIME_DIR}/.env" \
  --label "ai-org-os.kind=${KIND}" \
  --label "ai-org-os.persona=${PERSONA}" \
  --label "ai-org-os.phase=2" \
  --workdir /mindspace \
  "ai-org-os/mind:phase2" \
  claude
```

**長所**: 既存 spawn-mind.sh の構造を維持しやすい。学習コスト低。
**短所**: Phase 3 で複数サービス協調が来た時に書き直し。

### 案 B: Compose ファイル生成 + `docker compose up`（推奨）

```bash
# Phase 2 案 B — Compose ファイルを生成して起動
MIND_DIR="${RUNTIME_DIR}/minds/${MIND_NAME}"
mkdir -p "${MIND_DIR}"

# Persona を volume に投入する初期化スクリプトを書き出す（init service として）
cat > "${MIND_DIR}/docker-compose.yml" <<EOF
version: "3.9"

networks:
  ai-org-os-net:
    name: ai-org-os-net
    external: false

volumes:
  mindspace-${MIND_NAME}:
    name: mindspace-${MIND_NAME}

services:
  init-${MIND_NAME}:
    image: alpine
    command: sh -c "cp /tmp/persona.md /mindspace/CLAUDE.md && echo done"
    volumes:
      - mindspace-${MIND_NAME}:/mindspace
      - ${SCRIPT_DIR}/personas/${PERSONA}.md:/tmp/persona.md:ro
    restart: "no"

  mind-${MIND_NAME}:
    image: ai-org-os/mind:phase2
    container_name: mind-${MIND_NAME}
    depends_on:
      init-${MIND_NAME}:
        condition: service_completed_successfully
    env_file:
      - ${RUNTIME_DIR}/.env
    volumes:
      - mindspace-${MIND_NAME}:/mindspace
    working_dir: /mindspace
    networks:
      - ai-org-os-net
    labels:
      ai-org-os.kind: "${KIND}"
      ai-org-os.persona: "${PERSONA}"
      ai-org-os.phase: "2"
    command: ["claude"]
    restart: unless-stopped
EOF

docker compose -f "${MIND_DIR}/docker-compose.yml" up -d
```

**長所**: 宣言的、Phase 3 で `services:` を追加するだけ、bridge network もすでに用意済。
**短所**: 生成される YAML を git に含めるか否か（推奨: 含めない、`.gitignore` で除外し、`spawn-mind.sh` が毎回生成）。

### 案 C: 静的 Compose テンプレ + env で差し込み

`runtime/templates/mind.docker-compose.yml.tpl` を 1 個用意し、`spawn-mind.sh` は `envsubst` 等で展開するだけ。

**長所**: テンプレが版管理しやすい。
**短所**: Bash 依存外のツール（envsubst）が必要。Windows 開発者には負担。

**推奨**: **案 B**（生成、ただし生成器ロジックは bash のヒアドキュメントで完結させる）。

---

## テストへの影響

Phase 1 のテスト（[test-spawn-mind.sh](../../runtime/tests/test-spawn-mind.sh)）は「ファイルが配置されている」をホスト fs で検証している。Phase 2 では検証対象が変わる:

### Phase 2 で追加すべきテスト（叩き台: `test-spawn-mind-docker.sh`）

| ケース | 期待 |
|---|---|
| Docker daemon がない | exit 5（新規エラーコード）、明確なエラーメッセージ |
| `.env` がない | exit 6、`.env` の場所を案内 |
| イメージがない | 自動 `docker build` するか、`docker pull` を試みるか、明示エラーで止めるか（要判断） |
| 正常 spawn | exit 0 / `docker ps --filter name=mind-<name>` で Running / `docker volume inspect mindspace-<name>` が成功 |
| Mindspace の不可侵性 | ホスト側で `cat runtime/minds/<name>/CLAUDE.md` が **存在しないこと** を確認 |
| 同名 Mind の重複起動 | exit 4（既存挙動と整合） |
| 破棄 | `spawn-mind.sh destroy <name>` 等を新設 → volume と container が両方消える |

### CI（GitHub Actions）への影響

- GitHub Actions の `ubuntu-latest` runner は Docker が動く。Phase 2 のテストは CI でも実行可能。
- ただし `docker build` を毎回やると CI 時間が伸びる。layer cache を効かせる設定が必要。
- macOS / Windows の self-hosted で動かす場合は Docker Desktop 要件が出る。

### 開発者体験への影響

- Phase 1 は `bash` だけあれば動いた。Phase 2 は **Docker daemon 必須**。
- Windows ユーザーは Docker Desktop（または WSL2 + Docker Engine）が必要。**ユーザーの環境では既に Docker Desktop が動いている前提**（要確認）。
- 起動時間が「ディレクトリ作成（1 秒）」から「コンテナ起動（5〜15 秒）」に伸びる。

---

## リスク

| # | リスク | 重大度 | 緩和策 |
|---|---|---|---|
| R1 | **Claude CLI が API キー直接指定で動かない**（OAuth が必須） | **高**（Phase 2 の前提が崩れる） | 着手前に最小 PoC で確認する。動かない場合、Phase 2 は「ホスト側で claude 起動 + Mindspace だけ volume 化」の hybrid に降格する。 |
| R2 | イメージサイズが想定より大きい（>1GB） | 中 | `node:20-slim` ベース、multi-stage build、npm cache の削除 |
| R3 | 起動オーバーヘッドが体験を悪化させる（>30 秒） | 中 | ベースイメージを事前 build / pull させる README 整備 |
| R4 | Windows / macOS / Linux でのパス差異（特に bind mount を使う場合） | 中→低（named volume に倒したので緩和） | named volume を採用しているので最大の問題は回避。残りは `.env` のパス等の細部 |
| R5 | API キーが `.env` から git に commit される事故 | 高 | `.gitignore` 設定、`spawn-mind.sh` が起動時に `.env` を `git check-ignore` で確認 |
| R6 | Mind が暴走してホストの Docker daemon を圧迫 | 中 | `--memory` `--cpus` を Compose に明記。Phase 5 で Warden に昇格 |
| R7 | 公式の Claude Code Docker イメージが将来出てきて、独自イメージが陳腐化する | 低 | 陳腐化したら乗り換える。独自イメージは Phase 5 までの暫定 |
| R8 | named volume のバックアップ手順がドキュメント化されていないと運用事故になる | 中 | Phase 2 完了時に README に救済コマンドを記載 |

---

## Phase 2 を実装するかの判断軸

朝起きたユーザーが見て判断できるよう、**3 つの問い**で整理する。

### 問い 1: 24/365 稼働は今すぐ要るか？

- **要る** → Phase 2（コンテナ化）は必須。`docker compose up -d` で常駐させるのが最も低コスト。
- **要らない（試作中、対話的にしか動かさない）** → Phase 2 は急がない。Phase 3（Dispatch）に先に進むのも合理的。

### 問い 2: 同時 Mind 数の想定スケールは？

- **1 個（しばらくは個人で 1 Mind）** → Phase 2 はオーバーキル気味だが、不可侵性の物理担保を取りに行く価値は別途ある。
- **2〜数個（複数役割の Mind を並走させたい）** → Phase 2 は必須。プロセス分離なしで複数 Mind を同居させるとデバッグ不能になる。
- **多数（10+）** → Phase 2 だけでは不十分。Phase 4（Nexus）と Phase 5（Realm / Warden）まで一気に行く計画が必要。

### 問い 3: Phase 3 以降への布石として価値があるか？

- **ある**: Phase 3 の Dispatch（ファイル経由通信）は **複数の Mindspace volume を共有領域経由でやり取り** する形が自然。Phase 2 で volume 化されていれば自然に乗る。
- Phase 2 を飛ばすと、Phase 3 で「ホスト fs 経由の通信」を作ってしまい、Phase 4 の Nexus（MCP）に移る時に二度手間になる。

**総合**: 「24/365 を急がない」かつ「同時 Mind 数が当面 1」なら Phase 2 は **後回し可能**。
それ以外（特に同時 Mind 数が 2 以上になる）なら **Phase 2 は今着手すべき**。

---

## 代替案

### 代替案 1: Phase 2 をスキップして Phase 3（Dispatch、ファイル経由通信）に進む

**内容**: Mind は引き続きホスト上で動かす。代わりに 2 個目の Mind を立て、ホスト fs 上の決まったディレクトリで JSON / Markdown をやり取りさせる Dispatch を先に作る。

**長所**:
- 「組織」感が早く出る（複数 Mind が会話する）
- Docker の認証問題（R1）を回避
- 開発者体験の劣化なし

**短所**:
- Mindspace の不可侵性が policy 止まり継続
- Phase 4（Nexus = MCP）に移るとき、ファイル経由通信から MCP に移行する手間
- 「壊れたら困る」という心理的バリアが薄いので Mind 同士で勝手にファイルを覗き合う実装になりがち

**評価**: 「対話的な使い方が中心で 24/365 稼働は急がない」場合は強い代替案。

### 代替案 2: Docker ではなく軽量 isolate（systemd-nspawn / Firecracker / chroot）

**内容**: Mind を Docker ではなく OS レベルの軽量分離で動かす。

**長所**: 起動が速い。イメージ管理不要。
**短所**:
- systemd-nspawn は Linux 限定。ユーザーは Windows。
- Firecracker は VM 寄りで重い（起動は速いが構築が重い）。
- chroot は分離が弱く、Axiom の物理担保にならない。

**評価**: Windows ユーザー前提では現実的でない。**却下**。

### 代替案 3: Docker は使うが Phase 2 を「実験ブランチ」として併存

**内容**: `main` には Phase 1 を残し、`phase-2-docker` ブランチで実装。本流では Phase 1 で開発を続け、Phase 2 が安定したら切り替え。

**長所**: 開発を止めない。Phase 2 が詰まっても Phase 1 で前進できる。
**短所**: ブランチ管理コスト。仕様分岐リスク。

**評価**: 着手するならこれ。**推奨実装戦略**。

### 代替案 4: Phase 2 を「Mindspace の永続化だけ」に縮小し、コンテナ化は Phase 5 まで延期

**内容**: Mindspace は named volume にするが、Mind プロセス自体はホスト上で `docker run --rm -v mindspace-<name>:/mindspace -v $(pwd):/host alpine` 経由で fs だけ借りる、等の hybrid。

**長所**: Claude CLI の OAuth 問題（R1）を完全回避。物理不可侵性は獲得。
**短所**: 設計が中途半端で、Phase 5 でほぼ作り直し。

**評価**: R1 が解決できなかった場合のフォールバック案。

---

## Consequences（影響、Accepted 時に何が起きるか）

### ポジティブ

- Mindspace の不可侵性が **policy → 物理保証** に格上げ
- Mind プロセスがホスト依存から切り離され、移植性が上がる
- 24/365 稼働が可能になる（`restart: unless-stopped`）
- Phase 3 / 4 / 5 への布石が確立する
- Phase 1 のテストは残しつつ Phase 2 用テストを追加する形で進化的に拡張できる

### ネガティブ

- ユーザーの環境に Docker daemon が必須化する
- `spawn-mind.sh` の責務が増える（生成 + 起動 + 破棄）
- イメージビルドの保守が新たな作業として発生する
- CI 時間がわずかに伸びる
- 起動時間が体感で 5〜15 秒に伸びる（Phase 1 は 1 秒未満）

### 副作用

- `runtime/minds/<name>/` の中身が変わる:
  - Phase 1: CLAUDE.md と .mind-meta.md が直接置かれる
  - Phase 2: `docker-compose.yml` だけが置かれ、CLAUDE.md は volume の中
  - → 既存テスト `test-spawn-mind.sh` は **Phase 2 では失敗する**。新テスト `test-spawn-mind-docker.sh` に置き換えるか、Phase 1 動作を別エントリポイント（例: `spawn-mind-bare.sh`）として残すか、要判断。

---

## 議論ログ（Discussion log）

本 ADR は壁打ちセッションを経ずに設計担当（私）が初稿を書き起こした。承認プロセスの中で議論を追記する。

### Step 1（初稿、設計担当）

- ADR-0001 / ADR-0002 / Phase 1 実装を踏まえ、Phase 2 の達成目標と論点を網羅
- 推奨案を「Compose + named volume + 独自 node:20-slim ベースイメージ + .env」に倒した
- 最大リスクとして「Claude CLI が OAuth でしか動かない場合 Phase 2 の前提が崩れる」を明示
- 代替案として「Phase 2 を飛ばして Phase 3 に進む」「コンテナ化を縮小して volume だけ取りに行く」を提示

### Step 2（朝のユーザー判断、想定）

- 推奨案の各論点に対して採用/不採用を決める
- 着手判断（今行く / 後回し / 別 Phase 優先）を確定
- Accepted に昇格させるか、Proposed のまま改稿するかを決める

---

## 次にやること（Accepted 時の Issue 化候補）

1. **PoC**: Claude CLI が `node:20-slim` コンテナ内で `ANTHROPIC_API_KEY` 環境変数だけで動くかを最小確認（R1 の検証）
2. **Dockerfile 作成**: `runtime/docker/Dockerfile`（または `runtime/images/mind/Dockerfile`）
3. **`spawn-mind.sh` リファクタ**: Phase 1 動作を `spawn-mind-bare.sh` 等に退避 or 引数で切替
4. **Compose 生成ロジック**: 案 B の実装
5. **`destroy-mind.sh` の新設**: `docker compose down -v` で volume 含め破棄
6. **テスト追加**: `test-spawn-mind-docker.sh`
7. **CI 設定**: GitHub Actions で Docker layer cache 設定
8. **README 更新**: `runtime/README.md` と `README.md` の Quick Start を Phase 2 用に
9. **`.env.example` 整備 + `.gitignore` 強化**

これらは Accepted 後に個別 Issue として切り出す。

---

## 関連

- [ADR-0001: ai-org-os を「開発組織の不変項」を定義するフレームワークとして再定義する](./0001-ai-org-os-as-invariant-framework.md)
- [ADR-0002: 用語と「メタのメタ」構造の確定](./0002-vocabulary-and-meta-meta-structure.md)
- [`runtime/spawn-mind.sh`](../../runtime/spawn-mind.sh) — Phase 1 実装
- [`runtime/tests/test-spawn-mind.sh`](../../runtime/tests/test-spawn-mind.sh) — Phase 1 テスト
- [`runtime/README.md`](../../runtime/README.md) — runtime の現状と Phase 計画
- [`runtime/personas/`](../../runtime/personas/) — Persona 定義（Phase 2 でも volume に投入する対象）
- [`runtime/kinds/`](../../runtime/kinds/) — Kind 定義

---

> **改めて**: 本 ADR は **Proposed**。実装は本 ADR の承認後に着手する。
> Accepted に昇格させるには、上記「推奨案」の各論点をユーザーが確認し、代替案との比較で最終案を確定する必要がある。
