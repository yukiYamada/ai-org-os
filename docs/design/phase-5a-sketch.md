# Phase 5a 最小実装スケッチ — Realm コンテナ + Warden の骨格

> 想定読者:
> - Phase 5a を実装するメンテナ（Dockerfile / docker-compose / Warden 常駐プロセス / Issue 投入経路を書く担当）
> - Phase 5a に着手するかどうかを判断する意思決定者
>
> 位置づけ: 本書は **設計議論用のスケッチ**。ADR ではない（決定文書ではない）。
> ADR-0006 が「Proposed」のまま固まっていない論点を Phase 5a に絞って具体化し、
> 着手前に詰めるべき細部・気づき・最大の懸念を可視化することを目的とする。
> 確定事項として進める前に、本書をベースに ADR-0006 を Accepted に昇格させる手順を踏むこと。

---

## 1. Phase 5a の達成目標（再掲）

ADR-0006「10. 段階分割の提案」より、Phase 5 は次の 3 段階に分かれる:

| 段階 | スコープ | 完了の証明 |
|---|---|---|
| **5a** | Realm コンテナ + Warden（Python 常駐）だけ動く。Guildmaster / Mind なし | `docker compose up -d realm` で Realm が起動し、Warden が `realm/inbox/issues/` を poll している |
| 5b | 5a + Guildmaster。3 段階のうち「要求 → 承認」までが回る | 既知の Issue を投入 → Guildmaster が承認 Dispatch を出す |
| 5c | 5b + Warden の `execute_spawn` 実装。3 段階プロセスが完全に一巡 | Mind A → request_spawn → Mind B が自動 spawn → Dispatch を交わす |

本書は **5a だけ** を扱う。5b / 5c は別書（または ADR-0006 の Accepted 化時にスコープを明示）。

### 5a で達成する 4 つの状態

1. **物理コンテナとして Realm が存在する** — `docker compose up` で 1 コンテナが立ち上がる
2. **Warden プロセスがその中で動いている** — Python 常駐プロセス + Claude CLI を judging mode で呼べる
3. **Warden が Mind Kind Registry を持っている** — 起動時に `runtime/kinds/*.md` を読み込み、内部状態にカタログを構築
4. **Warden が Issue inbox を poll している** — `realm/inbox/issues/*.md` を見て新着を検知できる（変換ロジックは 5b で完成）

### 5a で **やらない** こと（明示的にスコープ外）

- Guildmaster の起動（5b）
- Mind の動的 spawn（5c）
- 3 段階プロセスの「承認」「実行」（5b / 5c）
- `request_spawn` / `approve_spawn` / `execute_spawn` の MCP tool 実装（5b / 5c）
- リソース制限の enforce（Phase 6）
- 認可機構 / TTL / dead letter（別 Issue）

---

## 2. 物理構成

```
┌─────────────────────── Host (Windows / Linux) ───────────────────────┐
│                                                                       │
│  ┌─────────────────── Realm Container (Docker) ────────────────────┐  │
│  │                                                                  │  │
│  │  ┌──────────────────────────────────────────────────────────┐    │  │
│  │  │ Warden process (Python 常駐 + Claude CLI subprocess)     │    │  │
│  │  │  - Mind Kind Registry を保持                              │    │  │
│  │  │  - inbox/issues/ を poll                                  │    │  │
│  │  │  - 判断時に Claude CLI を起動                              │    │  │
│  │  └──────────────────────────────────────────────────────────┘    │  │
│  │                                                                  │  │
│  │  ┌──────────────────────────────────────────────────────────┐    │  │
│  │  │ Nexus process (既存 runtime/nexus/nexus.py、stdio MCP)    │    │  │
│  │  │  - Phase 5a では Warden の自己診断用途のみ                  │    │  │
│  │  │  - Mind がまだ居ないので Dispatch は流れない                │    │  │
│  │  └──────────────────────────────────────────────────────────┘    │  │
│  │                                                                  │  │
│  │  ┌──────────────────────────────────────────────────────────┐    │  │
│  │  │ Observatory (既存 runtime/observatory/observe.py)         │    │  │
│  │  │  - Warden が定期的に subprocess として呼ぶ                 │    │  │
│  │  │  - デーモン化はしない（呼び出し型）                          │    │  │
│  │  └──────────────────────────────────────────────────────────┘    │  │
│  │                                                                  │  │
│  │  Shared volume: /realm                                           │  │
│  │    ├─ /realm/inbox/issues/      ← Issue 投入経路                 │  │
│  │    ├─ /realm/audit/dispatches/  ← Phase 5b 以降の痕跡領域         │  │
│  │    ├─ /realm/audit/usage/       ← リソース集計の入り口（フックのみ）│
│  │    └─ /realm/runtime/           ← 既存 runtime/ を bind / volume   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  Docker daemon socket（5c で必要、5a では未マウント）                    │
└───────────────────────────────────────────────────────────────────────┘
```

### 各プロセスの責務 / 通信 / ライフサイクル

| プロセス | 責務 | 通信相手 | ライフサイクル |
|---|---|---|---|
| **Warden** | Axiom 保証 / Kind Registry / Issue poll / 判断 | Nexus（MCP client）、Claude CLI（subprocess）、Observatory（subprocess） | Realm コンテナと同寿命、`ENTRYPOINT` で起動 |
| **Nexus** | MCP server。Phase 5a では Warden の自己診断用 | Warden（stdio） | Warden の subprocess として起動 / Warden 終了で停止 |
| **Observatory** | Mind 観測。Phase 5a では Mind 0 なので空テーブル | Warden（subprocess、stdout） | 呼び出し型（常駐しない） |

> **重要**: Phase 5a では **Mind が存在しない**。よって Nexus は事実上 idle、Observatory も「No minds spawned.」を返す。これは「正しく動かない」のではなく「正しく空である」状態。5a の完成判定は「コンテナ + Warden + Registry + Issue poll が動いている」であり、Nexus / Observatory は配線確認のみで足りる。

---

## 3. Dockerfile / docker-compose.yml のスケッチ

### 3.1 ディレクトリレイアウト（ホスト側）

ADR-0006「Consequences > 副作用」で言及された議論をここで具体化する。**結論: `realm/` を新設し、`runtime/` は Phase 1〜3 の遺産として残す**（Realm はそれらを mount する形で利用）。

```
ai-org-os/
├── docs/
│   ├── adr/
│   │   └── 0006-phase-5-realm-warden-guildmaster.md
│   └── design/
│       └── phase-5a-sketch.md           ← 本書
├── runtime/                              ← Phase 1〜3 遺産（Realm が mount する）
│   ├── kinds/
│   ├── personas/
│   ├── nexus/
│   ├── observatory/
│   ├── spawn-mind.sh                    ← 5c で Warden が呼ぶ
│   ├── kill-mind.sh                     ← 5c で Warden が呼ぶ
│   └── list-minds.sh                    ← 5a で Warden が呼ぶ
└── realm/                                ← 新設、Phase 5 の本体
    ├── Dockerfile.realm
    ├── docker-compose.realm.yml
    ├── warden/
    │   ├── warden.py                    ← 常駐 Python プロセス
    │   ├── kind_registry.py             ← runtime/kinds/*.md ローダ
    │   ├── issue_poll.py                ← inbox/issues/ poll ループ
    │   ├── CLAUDE.md                    ← Warden Persona（Claude CLI が読む）
    │   └── requirements.txt             ← 最小依存（標準ライブラリ寄り）
    ├── inbox/
    │   └── issues/                      ← 人間が .md を投下する
    │       └── .gitkeep
    └── audit/
        ├── dispatches/                  ← 5b / 5c で書き込まれる
        │   └── .gitkeep
        └── usage/                       ← Warden が集計を書く
            └── .gitkeep
```

> Phase 5a の段階では `runtime/` と `realm/` が共存する。**今 `runtime/` を `realm/runtime/` に rename しない** ことを推奨する（破壊変更が大きい、5a の PR が肥大化する、ロールバックしにくい）。Phase 6 以降で構造が固まったら統合を別 PR で議論する。

### 3.2 Dockerfile.realm（スケッチ）

```dockerfile
# realm/Dockerfile.realm
#
# Realm container — ai-org-os Phase 5a 用の最小コンテナ。
# Warden（Python 常駐）+ Claude CLI + Nexus 依存（mcp）を内蔵する。
#
# Phase 5a:
#   - ENTRYPOINT で warden.py を起動
#   - Mind は spawn しない（5c で docker socket mount が必要になる）
#   - 観測は observe.py を warden が subprocess で呼ぶ
FROM python:3.12-slim

# システム依存最小化: curl は Claude CLI install と health-check で使う
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        bash \
        coreutils \
 && rm -rf /var/lib/apt/lists/*

# Claude CLI install（公式手順、固定 version 推奨）
# 5a-2 の最大未解決論点: 「コンテナ内 OAuth をどう通すか」（§10 R-1）
# 当面は API key 方式で起動可能なフラグを使う想定（後述）
ARG CLAUDE_CLI_VERSION=latest
RUN curl -fsSL https://claude.ai/install.sh | bash \
 && claude --version

# Nexus と Warden の Python 依存
WORKDIR /realm
COPY warden/requirements.txt /realm/warden/requirements.txt
COPY ../runtime/nexus/requirements.txt /realm/runtime/nexus/requirements.txt
RUN pip install --no-cache-dir \
        -r /realm/warden/requirements.txt \
        -r /realm/runtime/nexus/requirements.txt

# 残りは bind mount で持ち込む（5a では COPY しない、開発反復速度のため）
# Phase 6 で COPY ベースの immutable image に切り替える可能性あり

# Warden の Persona は image に焼く（中身が image の挙動を決める）
COPY warden/CLAUDE.md /realm/warden/CLAUDE.md
COPY warden/*.py /realm/warden/

# 非 root user で動かす（docker socket mount は 5c でしか起きない）
RUN useradd -ms /bin/bash warden
USER warden

WORKDIR /realm/warden
ENV PYTHONUNBUFFERED=1
ENV REALM_ROOT=/realm
ENV REALM_RUNTIME=/realm/runtime

ENTRYPOINT ["python", "/realm/warden/warden.py"]
```

#### 議論ポイント

- **Claude CLI を image に焼く vs runtime install**: 焼く方を推奨（再現性・起動速度）。バージョンは ARG で固定。
- **bind mount vs COPY**: Phase 5a は開発反復が多いので bind mount 寄り。5b 以降で固める。
- **multi-stage build**: 5a では不要（image サイズより読みやすさ優先）。
- **non-root user**: Phase 5a では強制（docker socket がまだマウントされないので問題なし）。5c で socket をマウントする際に再検討。

### 3.3 docker-compose.realm.yml（スケッチ）

```yaml
# realm/docker-compose.realm.yml
#
# Phase 5a: Realm 1 サービスのみ。Mind は別 docker run（5c 以降）。
#
# 起動: cd realm && docker compose -f docker-compose.realm.yml up -d
# 停止: docker compose -f docker-compose.realm.yml down
version: "3.9"

services:
  realm:
    build:
      context: ..
      dockerfile: realm/Dockerfile.realm
    image: ai-org-os/realm:phase5a
    container_name: ai-org-os-realm
    restart: unless-stopped

    environment:
      # 5a の最大論点: Claude セッションをどう確立するか（§10 R-1）
      # 推奨は「API key 方式」: Claude API を Python から直接叩く形に倒す
      # 副案として OAuth token を host で取得 → mount するパターンも検討
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}

      # Warden が自分を識別するための名前（Nexus identity binding 等で使う）
      AI_ORG_OS_WARDEN_NAME: warden-primary

      # ログレベル（Warden が standard logging で吐く）
      WARDEN_LOG_LEVEL: INFO

    volumes:
      # 既存 runtime/ を mount（Kind Registry / Persona / 既存スクリプト）
      - ../runtime:/realm/runtime:rw

      # Realm 固有領域（inbox / audit）。host 側で人間が触る前提なので bind
      - ./inbox:/realm/inbox:rw
      - ./audit:/realm/audit:rw

      # Phase 5c で docker socket をマウントする
      # - /var/run/docker.sock:/var/run/docker.sock:rw

    # 5a では外部ポート公開なし。Issue 投入はファイル経由のみ
    # ports:
    #   - "8080:8080"   # Phase 6 で Dashboard を載せる場合に予約

    # Warden プロセスが poll しているだけで応答するので、healthcheck も簡素
    healthcheck:
      test: ["CMD", "python", "-c", "import os, sys; sys.exit(0 if os.path.exists('/realm/audit/warden.heartbeat') else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

#### 議論ポイント

- **services 数**: 5a は 1 個。5b で Guildmaster service を追加、5c で別途 docker socket をマウント。
- **named volume vs bind mount**: 5a は人間が頻繁に inbox / audit を覗くので bind 推奨。Phase 6 で named volume に倒す可能性あり。
- **restart policy**: `unless-stopped` を推奨（手で down するまで生き続ける、=24/365 稼働）。
- **ANTHROPIC_API_KEY の渡し方**: `.env` ファイル経由（gitignore 済み）+ host の環境変数（明示的に export）の二段階を推奨。

---

## 4. Warden の初期実装案

### 4.1 Warden の Body 設計（ADR-0006 §4 推奨案 (a) の具体化）

```
Warden process
├─ main loop (Python, 常駐)
│   ├─ heartbeat 書き出し（/realm/audit/warden.heartbeat）
│   ├─ Mind Kind Registry のロード（起動時 1 回 + signal で reload）
│   ├─ Issue inbox poll（5 秒間隔、debounce あり）
│   └─ 判断トリガ検出 → Claude CLI を subprocess で起動
└─ Claude CLI (subprocess、判断時のみ)
    ├─ /realm/warden/CLAUDE.md を読み込む（Persona）
    ├─ 入力: 直近の Issue / Dispatch / Kind Registry 状態
    └─ 出力: 判断結果（JSON）を stdout へ
```

#### 「Warden は何の Claude セッションか」

**結論: 非対話・呼び出し型 Claude セッション**。
- 常駐は Python プロセス。Claude は判断のたびに起動して終了する短命セッション。
- Persona（`warden/CLAUDE.md`）と入力 prompt は毎回読み込み直す（コンテキストの引き継ぎは Python 側で構築）。
- 理由: ADR-0006 §4 R-2「Claude CLI の長時間運用が未知」を回避する最も保守的な実装。

> 代替案として「永続 Claude CLI を tmux 内に保持し、Python が `send-keys` で会話する」案もある（claude-team / bash-editor の Supervisor / Worker パターン）。ADR-0009 で「使えるものは使う」と決めた以上、5b / 5c でこちらに振り直す余地は残す。

### 4.2 Warden Persona（CLAUDE.md）の中身

`realm/warden/CLAUDE.md` の骨子:

```markdown
# あなたは Warden です

あなたは ai-org-os の Realm の守護者です。
Realm が起動している限り、あなたも存在しつづけます（24/365）。

## あなたの責務

1. **Axiom の保証**: ADR-0002 §2 の 4 不変項を破る挙動を検出したら拒否する
2. **Mind Kind Registry の管理**: runtime/kinds/*.md を全 Mind 共有のカタログとして保持する
3. **ルール解釈**: ADR-0001 / ADR-0002 / global rules に照らして判断する
4. **リソース管理**: Mind ごとの token 集計を /realm/audit/usage/ に書く（Phase 5a ではフックのみ）

## あなたが触れていいもの

- /realm/inbox/issues/*.md（読み取り、処理後に /realm/audit/issues/processed/ へ移動）
- /realm/audit/**（書き込み）
- /realm/runtime/kinds/**（読み取りのみ、Registry 構築のため）
- /realm/runtime/observatory/observe.py（subprocess 実行）
- /realm/runtime/list-minds.sh（subprocess 実行）

## あなたが触れてはいけないもの

- /realm/runtime/minds/<any>/**（Axiom: Mindspace 不可侵）
- Mind の Dispatch ストレージ /realm/runtime/nexus/storage/**
  （Nexus 経由でのみアクセスする、5b 以降）

## 判断の流れ（Phase 5a 範囲）

Python ループから「Issue 1 件を判断せよ」と呼ばれたら:

1. Issue の本文を読み取る
2. Kind Registry に該当する Kind があるか確認
3. Axiom 整合性を確認（Mindspace 不可侵 / 3 段階プロセスの要請）
4. 判断結果を JSON で返す:
   {
     "verdict": "accepted" | "rejected" | "needs_clarification",
     "reason": "...",
     "next_action": "wait_for_guildmaster" | "noop"
   }
5. Phase 5a では next_action は常に "wait_for_guildmaster"（Guildmaster がまだ居ないので実質保留）

## 参照すべき文書

- /realm/runtime/../docs/adr/0001-ai-org-os-as-invariant-framework.md
- /realm/runtime/../docs/adr/0002-vocabulary-and-meta-meta-structure.md
- /realm/runtime/../docs/adr/0006-phase-5-realm-warden-guildmaster.md
- /realm/runtime/kinds/*.md（Kind Registry の根拠）
```

### 4.3 Warden が呼ぶもの

| 呼び出し先 | 呼び方 | 用途 |
|---|---|---|
| `runtime/observatory/observe.py --json` | subprocess.run | Mind 一覧の状態スナップショット |
| `runtime/list-minds.sh` | subprocess.run | Mind 一覧の軽量取得（observe.py の障害時 fallback） |
| `runtime/spawn-mind.sh` | subprocess.run | **Phase 5c でのみ呼ぶ**（5a では呼ばない） |
| `runtime/kill-mind.sh` | subprocess.run | **Phase 5c でのみ呼ぶ**（5a では呼ばない） |
| Claude CLI | subprocess.Popen + stdin pipe | 判断時、Persona + 入力を渡して JSON 出力を受ける |

> 「Warden の常駐プロセス が運用スクリプトを subprocess で呼ぶ」設計は、ADR-0006 §10「次にやること」項目 4（warden.py 常駐ループ実装）と整合する。spawn-mind.sh などはあくまで 5c のための既存資産であり、5a の Warden は「呼ばないこと」を選ぶ。

### 4.4 Warden の起動シーケンス（ENTRYPOINT が実行する処理）

```
1. heartbeat ファイルを 1 回書く（healthcheck pass のため）
2. Kind Registry をロード（/realm/runtime/kinds/*.md）
   - 失敗時: exit 10、コンテナごと再起動（restart policy 任せ）
3. Persona（/realm/warden/CLAUDE.md）の存在確認
   - 無ければ exit 11
4. Nexus 依存（mcp module）の import 試行
   - 失敗時: warning ログのみ、5a では fatal にしない
5. main loop 開始
   while True:
     - heartbeat 更新
     - inbox poll → 新着検出 → Claude 判断 → 結果を audit/ に記録
     - sleep(POLL_INTERVAL=5s)
6. SIGTERM / SIGINT で graceful shutdown
   - 進行中の Claude subprocess を待ってから exit
```

---

## 5. Mind Kind Registry の初期実装

ADR-0006 §6 推奨案「**(a) 静的ロード**」を Phase 5a で具体化する。

### 5.1 ストレージ形態

**結論: Warden プロセス内のメモリ（in-process dict）+ 起動時ファイルロード**。
- 永続化は不要（Realm 再起動 = 再ロード）
- DB は過剰（Phase 6 で動的登録時に再検討）
- ファイルキャッシュも 5a では不要（`runtime/kinds/` 自体が SSOT）

### 5.2 ロード対象

```
/realm/runtime/kinds/*.md
```

各 `.md` ファイルの frontmatter（`kind:` / `version:` / `status:`）を読み、本文を `description` として保持。

### 5.3 Registry のスキーマ（メモリ内）

```python
# realm/warden/kind_registry.py の API（実装スケッチ）
@dataclass
class KindEntry:
    name: str               # ex. "generic"
    version: str            # ex. "0.1"
    status: str             # ex. "experimental"
    description: str        # Markdown 本文
    source_path: pathlib.Path

class KindRegistry:
    def __init__(self, kinds_dir: pathlib.Path): ...
    def reload(self) -> None: ...
    def get(self, name: str) -> KindEntry | None: ...
    def list(self) -> list[KindEntry]: ...
```

### 5.4 reload トリガ（5a）

- **起動時 1 回のみ**（推奨）
- SIGHUP で再ロード（任意、運用便利機能）
- ファイル watch（inotify 等）は Phase 6 以降

### 5.5 Phase 5a 完了の証明

```bash
docker compose exec realm python -c "
from warden.kind_registry import KindRegistry
import pathlib
r = KindRegistry(pathlib.Path('/realm/runtime/kinds'))
print([k.name for k in r.list()])
"
# 期待出力: ['generic']
```

---

## 6. Realm の Issue 投入インターフェース

ADR-0006 §8 推奨案「**(a) ファイル投入**」を採用。

### 6.1 経路

```
人間 → ホスト上 realm/inbox/issues/<timestamp>-<slug>.md を作成
     → Realm コンテナ内 /realm/inbox/issues/... として見える（bind mount）
     → Warden が poll → 判断（Phase 5a では受領記録のみ）
     → /realm/audit/issues/processed/<timestamp>-<slug>.md に移動
```

### 6.2 Issue ファイルのフォーマット

```markdown
---
issue_id: 2026-05-23T10-00-00Z-add-reviewer-mind
submitted_by: human
submitted_at: 2026-05-23T10:00:00Z
---

# タイトル

新しい Reviewer Mind を 1 個立ち上げてほしい。Persona は既存の reviewer.md でよい。

## 背景

...
```

### 6.3 Warden の poll 挙動（5a 範囲）

- 5 秒間隔で `/realm/inbox/issues/` を `os.listdir`
- 新規ファイル（`processed/` に移動されていないもの）を検出
- 各 Issue を順に Claude 判断にかける
- Phase 5a では **判断結果を `/realm/audit/issues/<issue_id>.verdict.json` に書く** のみ（Guildmaster への Dispatch は 5b）
- 処理済みファイルは `/realm/audit/issues/processed/` へ move（同じ名前で再投入を防ぐ）

### 6.4 候補 (b) (c) を採らなかった理由（簡潔再掲）

- (b) GitHub Issue webhook: 公開 endpoint + webhook secret 管理が 5a 範囲外。Phase 6 に延期。
- (c) MCP tool `submit_issue`: 5a では Mind / Guildmaster が居ないので呼び出し主体がない。人間が直接 MCP を叩くインフラは過剰。

---

## 7. 既存資産との接続

### 7.1 `spawn-mind.sh` / `kill-mind.sh` / `list-minds.sh`

| スクリプト | Phase 5a での扱い |
|---|---|
| `spawn-mind.sh` | **呼ばない**。5c で Warden が呼ぶ形になる。引数仕様は維持されるので、5c で Python の `subprocess.run` で呼び出せる |
| `kill-mind.sh` | 同上 |
| `list-minds.sh` | Warden が起動時 / poll ループで `subprocess.run` してもよい（observe.py の fallback） |

> spawn-mind.sh は既に `.mcp.json` 配置・identity binding を含む完成品なので、5c で Warden 内部から呼ぶ際に大幅な手直しは不要。Warden 側は「引数を組み立てて呼ぶ」だけで済む。

### 7.2 Nexus（`runtime/nexus/nexus.py`）

**結論: 5a では Warden 内部で Nexus を起動しない**。

理由:
- Mind がまだ居ないので Dispatch が流れない
- Nexus は stdio MCP server なので、起動するには「誰かが MCP client として接続する」必要があり、Warden 自体は今のところそのクライアントになる必然性がない
- 依存（mcp パッケージ）の install だけ image に焼いておけば 5b / 5c で即起動できる

5b で Guildmaster が登場した時点で、Guildmaster の `.mcp.json` 経由で Nexus が stdio として起動する設計に乗る（既存 `spawn-mind.sh` と同じパターン）。Warden 自身は Nexus に **接続しない**（Warden は judgment ロールであり、Mind ではないため Nexus tools を呼ぶ責務がない）。

> ただし「Warden が Nexus 経由で全 Dispatch を観測する」という案は Phase 6 で検討の余地あり（audit ログを Nexus 一箇所に集める設計）。5a ではスコープ外。

### 7.3 Observatory（`runtime/observatory/observe.py`）

**結論: Warden が定期的に subprocess で呼ぶ**。

```python
# warden.py 内のスケッチ
def snapshot_minds() -> dict:
    result = subprocess.run(
        ["python3", "/realm/runtime/observatory/observe.py", "--json"],
        capture_output=True, text=True, timeout=10,
    )
    return json.loads(result.stdout)
```

- 呼び出し間隔: 60 秒（Phase 5a では Mind 0 なので形式的）
- 失敗時: warning ログ、次の周期で再試行
- 用途: `audit/snapshots/<timestamp>.json` に書き出し、後で診断できる状態を作る

Observatory 側は既に `--json` 出力に対応しており、改修不要。

---

## 8. テスト方針

| カテゴリ | 内容 | 実行方法 | CI 適合 |
|---|---|---|---|
| **コンテナビルド** | `docker compose build` が成功する | GitHub Actions ubuntu-latest | OK |
| **コンテナ起動** | `docker compose up -d` で healthcheck pass | GitHub Actions ubuntu-latest | OK |
| **Warden 起動** | ログに「Warden ready」相当が出る、heartbeat が 1 分以内に更新される | docker exec から確認 | OK |
| **Kind Registry** | `runtime/kinds/generic.md` がロードされ、`KindRegistry.list()` で取得できる | 上記 §5.5 のコマンド | OK |
| **Issue poll** | `inbox/issues/foo.md` を投入 → 10 秒以内に `audit/issues/foo.verdict.json` が生成 | テストスクリプト | OK |
| **Observatory 呼び出し** | Warden が observe.py を呼んで JSON を `audit/snapshots/` に書く | log / 出力ファイル確認 | OK |
| **Claude CLI 起動**（オプション） | 実 API key を使った 1 回の judgment が成功する | nightly only、API key 必須 | nightly |
| **graceful shutdown** | `docker compose stop` で SIGTERM → 進行中の subprocess を待って exit | テストスクリプト | OK |

### CI 構成（提案）

- `.github/workflows/realm-build.yml`: build + up + 基本 healthcheck。各 PR で実行。
- `.github/workflows/realm-judgment-nightly.yml`: Claude API を使う judgment テスト。nightly + 手動 trigger。`ANTHROPIC_API_KEY` を Secret から注入。

---

## 9. 着手順序（5a の中での更なる細分化）

各サブ段階は **1 PR 程度** を目安とする。

### 5a-1: Realm コンテナだけ立つ（空中身）

- `realm/Dockerfile.realm` の最小版（Python + curl のみ、ENTRYPOINT は `sleep infinity`）
- `realm/docker-compose.realm.yml` の最小版（1 service、bind mount なし）
- README に「docker compose up -d で立つ」確認手順
- **完了判定**: `docker compose up -d` で起動、`docker compose ps` で healthy（heartbeat ではなく `sleep` の有無）

### 5a-2: Warden が中で動く（最小 CLAUDE.md）

- `realm/warden/warden.py`（heartbeat 書くだけのループ）
- `realm/warden/CLAUDE.md`（Persona の骨子のみ、§4.2）
- Dockerfile に Claude CLI install を追加
- ENTRYPOINT を `warden.py` に切り替え
- healthcheck を heartbeat ファイル基準に変更
- **完了判定**: `docker compose up -d` 後、`/realm/audit/warden.heartbeat` が継続的に更新される
- **5a-2 で立ち止まる選択肢**: Claude CLI の OAuth / API key 問題（§10 R-1）が解けない場合、ここで足踏みする

### 5a-3: Warden が `observe.py` / `list-minds.sh` を呼べる

- bind mount で `runtime/` を `/realm/runtime/` にマウント
- `warden.py` に `snapshot_minds()` 関数を追加（§7.3）
- 60 秒に 1 回 snapshot を `audit/snapshots/` に書き出す
- **完了判定**: snapshot ファイルが定期生成される、Mind 0 でも `{"minds": []}` が正しく出る

### 5a-4: Warden が Mind Kind Registry を構築できる

- `realm/warden/kind_registry.py`（§5.3 の API）
- `warden.py` 起動時に Registry をロード、ログに `loaded kinds: [generic]` を出す
- SIGHUP で reload する optional 機能
- 単体テスト `realm/warden/test_kind_registry.py`（標準 unittest）
- **完了判定**: §5.5 のコマンドで `['generic']` が取れる

### 5a-5: Warden が Issue 投入を受け取れる

- `realm/warden/issue_poll.py`（§6.3 のロジック）
- `realm/inbox/issues/` の bind mount 追加
- `realm/audit/issues/` のディレクトリ自動作成
- Claude CLI を呼んで judgment JSON を生成する `_invoke_judgment()`
  - **API key 方式の場合**: `claude` コマンドに stdin で Persona + Issue を渡し、stdout から JSON を取る
  - **OAuth 方式の場合**: 当面 dry-run（Persona だけ load、Claude を呼ばずに `{verdict: "accepted (dry-run)"}` を返す）
- E2E テスト: Issue 投入 → 10 秒待機 → verdict.json が生成
- **完了判定**: §8 の「Issue poll」テストが green

### 各段階で 5a を打ち切る選択肢

- **5a-1 で打ち切り**: Realm コンテナが立つだけでも ADR-0002 §3「Realm = 実コンテナ」の最低要件は満たせる
- **5a-2 で打ち切り**: Warden が「居る」ことは確認できる
- **5a-4 で打ち切り**: Kind Registry を Warden が握る = ADR-0002 §5 の責務分離が物理的に始まる
- **5a-5 まで完走**: ADR-0006 §10 の「5a 完了の証明」（Issue poll が動く）に到達

---

## 10. 既知のリスク / 検討事項

| # | リスク / 論点 | 重大度 | 5a での対応方針 |
|---|---|---|---|
| **R-1** | **Claude CLI を Docker 内で OAuth する方法**（コンテナ内ブラウザなし） | **最大** | 推奨: **API key 方式に倒す**（`ANTHROPIC_API_KEY` を env で渡し、`claude` CLI ではなく `anthropic` Python SDK を直接呼ぶ実装に切り替える選択肢を残す）。OAuth はホスト側で取った token をマウントする副案もあるが運用が複雑 |
| **R-2** | **ANTHROPIC_API_KEY をどう渡すか** | 高 | `.env` ファイル + host export の二重管理。`.env` は gitignore 済み確認。Phase 6 で secrets manager 検討 |
| **R-3** | **Warden の「常駐」設計の現実性** | 高 | Python は問題なく常駐できる。Claude CLI は **判断時のみ短命 subprocess** にして「常駐 Claude セッション」を避ける。これで R-2（ADR-0006 §R2）の長時間運用懸念を回避 |
| **R-4** | **リソース制限の実装**（cgroup？プロセス監視？） | 中 | Phase 5a では「集計フックだけ」（ADR-0006 §7 推奨）。Mind 0 なので実質ノーオペ。docker の `mem_limit` / `cpus` で物理担保する余地は compose に追記可 |
| R-5 | bind mount のホスト OS 差異（Windows / Linux） | 中 | docker-compose で path を相対指定、Windows でも WSL2 経由なら動く想定。CI は ubuntu-latest のみ |
| R-6 | `runtime/kinds/` の path 解決（コンテナ内 vs ホスト） | 中 | 環境変数 `REALM_RUNTIME=/realm/runtime` を Dockerfile / compose 両方で固定。Warden コード内は path 直書き禁止 |
| R-7 | Observatory が Mind 0 で何も出さない問題 | 低 | 仕様通り。`{"minds": []}` を返すことを §8 のテストで確認 |
| R-8 | Warden が判断を間違えた / Persona が緩すぎる | 中 | 5a の judgment は Issue を「受領記録するだけ」。実害が出ないようスコープを 5a で絞る |
| R-9 | `realm/audit/` の肥大化 | 低 | 5a では log rotation 不要（Mind 0 で書き込み量小）。Phase 6 で rotation 設計 |
| R-10 | Docker daemon が動いていない開発環境 | 中 | README に明示。Phase 5a 着手は「Docker が手元で動く」前提を確認してから |

### 最大の懸念（1 つに絞ると）

> **R-1: Claude CLI のコンテナ内認証経路**。

これが解けないと 5a-2 以降が dry-run 止まりになる。5a 着手の最初の 1 日で、次のいずれかを確定すべき:

- (A) API key 方式 + `anthropic` SDK 直接呼び出しに倒す（Claude CLI を image から外す）
- (B) `claude` CLI の API key login モード（環境変数 only）が現行版で動くことを確認
- (C) ホスト OAuth → token 共有ボリュームで mount

最も保守的なのは **(A)**。Phase 5a の範囲では judgment が 1 回成功すれば十分なので、`anthropic.messages.create(...)` を直接叩く Python コードに倒す方が制御しやすい。Claude CLI を Warden の subprocess として呼ぶ案は、Phase 5b / 5c で Mind が登場した際に Mind 側で `spawn-mind.sh` の文脈で利用すれば足りる（Mind は対話的な使い方も含めて Claude CLI を活用できる）。

---

## 11. 関連

### ADR

- [ADR-0001](../adr/0001-ai-org-os-as-invariant-framework.md): ai-org-os = 不変項フレームワーク
- [ADR-0002](../adr/0002-vocabulary-and-meta-meta-structure.md): 用語 / 階層構造（Realm / Warden / Mind Kind Registry の責務）
- [ADR-0003](../adr/0003-docker-and-phase-2-design.md): Phase 2 Docker 化（Proposed）
- [ADR-0005](../adr/0005-phase-3-mcp-direct-with-nexus.md): Phase 3 Nexus 直行（Accepted、実装済）
- [ADR-0006](../adr/0006-phase-5-realm-warden-guildmaster.md): Phase 5 設計（Proposed、本書のベース）
- [ADR-0009](../adr/0009-relationship-with-bash-editor-and-claude-team.md): bash-editor / claude-team との関係（流用方針）

### `runtime/` 配下

- [`runtime/README.md`](../../runtime/README.md): Phase 1 + 3 の使い方
- [`runtime/spawn-mind.sh`](../../runtime/spawn-mind.sh): Mind 起動スクリプト（5c で Warden が呼ぶ）
- [`runtime/kill-mind.sh`](../../runtime/kill-mind.sh): Mind 破棄スクリプト（5c で Warden が呼ぶ）
- [`runtime/list-minds.sh`](../../runtime/list-minds.sh): Mind 一覧（5a で Warden が呼ぶ）
- [`runtime/kinds/generic.md`](../../runtime/kinds/generic.md): Mind Kind 唯一の定義
- [`runtime/personas/`](../../runtime/personas/): designer / implementer / reviewer
- [`runtime/nexus/`](../../runtime/nexus/): MCP server（5a では未使用、5b 以降で本格稼働）
- [`runtime/observatory/observe.py`](../../runtime/observatory/observe.py): Mind 観測（5a で Warden が定期呼び出し）

### 新規作成予定（Phase 5a の PR で）

- `realm/Dockerfile.realm`
- `realm/docker-compose.realm.yml`
- `realm/warden/warden.py`
- `realm/warden/CLAUDE.md`
- `realm/warden/kind_registry.py`
- `realm/warden/issue_poll.py`
- `realm/warden/requirements.txt`
- `realm/inbox/issues/.gitkeep`
- `realm/audit/dispatches/.gitkeep`
- `realm/audit/usage/.gitkeep`
- `realm/README.md`（5a-1 の PR で作成）

---

> 改めて: 本書は **設計議論用のスケッチ**。最終決定は ADR-0006 の Accepted 化と本書の論点を反映した実装 PR で行う。
> 特に **R-1（Claude CLI のコンテナ内認証）** は 5a 着手前に方針確定が必須。
> 5a-1〜5a-5 の段階分割は各 PR 単位で打ち切り可能で、どこで止めても「動く ai-org-os の一段」が手元に残る設計とする。
