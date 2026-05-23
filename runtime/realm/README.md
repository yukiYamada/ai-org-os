# runtime/realm/

> 想定読者: Phase 5a で Realm を立ち上げる人、Phase 5 全体の物理境界を理解したい人。

**Phase 5a-1 の実体**：ai-org-os の Realm を Docker コンテナとして起動する最小定義。

Pillar 群（Observation / Lifecycle / Conduit / Judgment / Registry / Inbox、[ADR-0011](../../docs/adr/0011-warden-claude-naming-and-separation.md)）はまだ常駐していない。本 Phase は **「Realm という容器がそこにある」状態の確立** に絞る。

## 構成

```
runtime/realm/
├── Dockerfile           ← Python 3.11-slim + 最小ユーティリティ
├── docker-compose.yml   ← 1 service (realm)、bind mount 中心
└── README.md            ← 本書
```

## 前提

- Docker Desktop 等で `docker` / `docker compose` が動くこと
- ai-org-os repo を git で clone 済み

## 起動

```bash
cd runtime/realm
docker compose up -d --build
```

これで Realm コンテナ（`ai-org-os-realm`）が立ち上がります。

## 動作確認

### 1. コンテナが Running であること

```bash
docker compose ps
# STATE が 'running' なら OK
```

### 2. コンテナ内で既存ツールが動くこと

```bash
# Mind 一覧（runtime/list-minds.sh を呼ぶ、bash 経由で実行ビット不要に）
docker exec ai-org-os-realm bash /realm/runtime/list-minds.sh

# Observatory レポート（runtime/observatory/observe.py を呼ぶ）
docker exec ai-org-os-realm python3 /realm/runtime/observatory/observe.py
```

> 注: shell スクリプト群（`list-minds.sh` / `spawn-mind.sh` / `kill-mind.sh`）は
> git 上で実行ビット無し（100644）として tracked されているため、bind mount 経由でも
> 実行ビットが無く、コンテナ内では `bash <script>` 形式で起動する必要があります。

ホスト側で spawn した Mind が見えれば成功（bind mount で同期されている証拠）。

### 3. コンテナ内に入る（デバッグ）

```bash
docker exec -it ai-org-os-realm bash
# /realm/runtime に居る状態でシェルが開く
ls -la
exit
```

## 停止 / 削除

```bash
docker compose down
# image も消したい場合
docker compose down --rmi all
```

## Phase 5a-1 のスコープ（重要）

**含まれる**:
- Realm コンテナの起動定義
- 既存 runtime/ ツール（list-minds / spawn-mind / kill-mind / observatory / nexus）が bind mount 経由で動くこと
- bind mount による書き込み伝播（コンテナ内で spawn した Mind がホストにも見える）

**含まれない**（Phase 5a-2 以降で追加）：

| Phase | 内容 | 対応 issue |
|---|---|---|
| 5a-2 | 既存ツールを `runtime/pillars/` 配下に統合（Observation / Lifecycle / Conduit Pillar） | #37 |
| 5a-3 | Judgment Pillar（Anthropic SDK 直叩き）と Claude CLI / API key 導入 | #38 |
| 5a-4 | Mind Kind Registry を Warden に統合（Registry Pillar） | #39 |
| 5a-5 | Issue 投入インターフェース（Inbox Pillar） | #40 |

5a-1 段階では **「Realm が立つこと」だけを確認**し、Pillar 常駐は次フェーズで追加していく。

## 設計判断（ADR との対応）

- [ADR-0002](../../docs/adr/0002-vocabulary-and-meta-meta-structure.md): Realm = 実コンテナ → Docker コンテナで実装
- [ADR-0006](../../docs/adr/0006-phase-5-realm-warden-guildmaster.md): Realm 内同居方式（DinD 回避） → Pillar はプロセスとして同居（Phase 5a-2 以降）
- [ADR-0010](../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md): Warden = 機能の集合体 → Pillar 群が集合体を成す（Phase 5a-2 以降で実体化）
- [ADR-0011](../../docs/adr/0011-warden-claude-naming-and-separation.md): Pillar 命名と配置（runtime/pillars/） → Phase 5a-2 で実装

## テスト

```bash
./runtime/tests/run-tests.sh
# test-realm.sh が docker の有無で自動 skip / run する
```

非 Docker 環境では skip、Docker ありなら `docker compose up` まで実行して確認。

## 既知の制限

- **Windows / macOS の bind mount は遅い**: 大量ファイルアクセス時に遅延あり（Phase 5a-3 で named volume への移行を検討）
- **Claude CLI / Anthropic SDK 未導入**: Phase 5a-1 では判断機能なし（5a-3 で追加）
- **常駐 Pillar なし**: コンテナは sleep infinity で生きてるだけ（5a-2 以降で意味のある常駐に）

## 関連

- ADR-0002 / ADR-0006 / ADR-0010 / ADR-0011
- Issue #35 — 本ディレクトリの起票元
- Issue #37〜#40 — Phase 5a-2〜5a-5
