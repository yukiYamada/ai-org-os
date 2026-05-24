# ADR-0018: フレームワーク（repo）と実行環境（AI_ORG_OS_HOME）の物理分離

> 想定読者:
> - ai-org-os を別マシン / 別 user で運用したい人
> - `git pull` で更新する際に Mind データを壊さないことを保証したい人
> - Container と Host の bind mount を設計するメンテナ
> - Phase 5b-4 (Runtime Home 実装) を担当する人

## Status

**Accepted** — 2026-05-24

## Context（背景）

Phase 5b-3 (#78) で Host setup フェーズを分離したが、生成物 (`runtime/host/.venv/`, `runtime/host/config.env`) を **repo ディレクトリ配下** に置く設計のままだった。同様に Phase 5a 以降ずっと、運用データも repo 内に置いてきた:

| 種別 | 現状の置き場所 | 性質 |
|---|---|---|
| Host venv | `runtime/host/.venv/` | mutable (mcp version, etc.) |
| Host config | `runtime/host/config.env` | mutable (絶対パス、ホスト固有) |
| Mindspaces | `runtime/minds/<name>/` | mutable (Mind 個体のデータ) |
| Inbox / archive | `runtime/issues/{inbox,archive}/` | mutable (Issue データ) |
| Snapshots | `runtime/pillars/observation/snapshots/` | mutable (観測履歴) |
| Conduit storage | `runtime/pillars/conduit/storage/{inbox,archive}/` | mutable (Mind 間 Dispatch) |
| Conductor status | `runtime/realm/conductor-status.json` | mutable (cycle 状態) |

全部 `.gitignore` 済なので git tracking 自体はクリア。**だが物理的に repo 内に居る**ことが問題:

1. **`git clean -dfx` の事故リスク**: untracked を全消しすると Mind / Inbox / Snapshot まで吹き飛ぶ
2. **複数 checkout 間の競合**: 同じ repo を別 branch で 2 つ checkout すると環境を共有 / 干渉
3. **更新と運用の混線**: `git pull` で更新 → 環境ファイルが場所変わったら手動移行 (Phase 5b-3 で venv 場所が変わったとき実際に起きた)
4. **判別困難**: 利用者が「どれが repo の一部、どれが私のデータ?」を見分けにくい
5. **配布性の欠如**: 「ai-org-os を /opt に置いて複数 user で使う」が成立しない (各 user の venv をどう分ける?)

### operator からの指摘 (顕在化)

Phase 5b-3 マージ後の E2E 再挑戦時、operator が**「環境とgitでおかしくならない？だからcloneはしてくるけど、環境作成する場所は別ディレクトリ。だとおもうけど？」** と指摘。

筆者 (実装担当) はこの設計の浅さに気付いていなかった。本 ADR で **修正方針を確定** する。

## Decision（決定）

### 1. 物理的に 2 つの root に分離する

| 役割 | 場所 | 性質 |
|---|---|---|
| **Framework**（コード） | repo dir (例: `~/pgit/ai-org-os/`) | immutable (git で管理、`git pull` で更新) |
| **Runtime Home**（状態） | `$AI_ORG_OS_HOME` (default `~/.ai-org-os/`) | mutable (ホスト固有、git 管理外) |

repo は code+ADR+test だけ。生きてる状態は何 1 つ repo に入らない。

### 2. `AI_ORG_OS_HOME` の構造（Phase 5b-4 時点）

```
$AI_ORG_OS_HOME/                  (default: ~/.ai-org-os/)
├── venv/                         host Python venv (mcp 入り)
├── config.env                    setup.sh の出力 (絶対パス解決済)
├── minds/                        Mindspaces
│   └── <name>/                   CLAUDE.md, .mcp.json, .mind-meta.md, ...
├── issues/                       人間 → Realm 入力
│   ├── inbox/<id>.md             未処理
│   └── archive/<id>.md           claim 済
├── snapshots/                    Observation 履歴
│   └── <timestamp>.json
├── conduit-storage/              Mind 間 Dispatch
│   ├── inbox/<to>/<msg>.md
│   └── archive/<to>/<msg>.md
├── conductor-status.json         Warden cycle 最新サマリ
└── realm/                        (将来) container 起動時の補助 (ログ等)
```

### 3. `AI_ORG_OS_HOME` の解決ルール

| 環境 | 優先順位 |
|---|---|
| **どこでも** | `$AI_ORG_OS_HOME` env が設定されてればそれ |
| **Host (set 未済)** | `$HOME/.ai-org-os/` |
| **Container 内** | `/realm/home/` (docker-compose で env パススルー) |

### 4. Container の bind mount 構成変更

旧:
```yaml
volumes:
  - ../../:/realm/repo:ro
  - ../../runtime:/realm/runtime         # ← code + state 混在
```

新:
```yaml
volumes:
  - ../../:/realm/repo:ro                # コードは read-only
  - ${AI_ORG_OS_HOME:-~/.ai-org-os}:/realm/home   # 状態は別パス
environment:
  AI_ORG_OS_HOME: /realm/home
```

Container 内の Conductor 等の Pillar は **`$AI_ORG_OS_HOME` (= /realm/home) を read** する。コード自体は `/realm/repo/runtime/pillars/...` を読み書きしない。

### 5. ホスト側スクリプトの責務

| スクリプト | 旧 | 新 |
|---|---|---|
| `runtime/host/setup.sh` | `runtime/host/.venv/` 作成 | `$AI_ORG_OS_HOME/venv/` 作成、`$AI_ORG_OS_HOME` ディレクトリ構造を初期化 |
| `spawn-mind.sh` | `runtime/minds/<name>/` 作成 | `$AI_ORG_OS_HOME/minds/<name>/` 作成 |
| `submit-issue.sh` / `inbox.py` | `runtime/issues/inbox/` | `$AI_ORG_OS_HOME/issues/inbox/` |
| `observe.py` / `snapshot.py` | `runtime/pillars/observation/snapshots/`, `runtime/pillars/conduit/storage/` | `$AI_ORG_OS_HOME/snapshots/`, `$AI_ORG_OS_HOME/conduit-storage/` |
| `conductor.py` | `runtime/realm/conductor-status.json` | `$AI_ORG_OS_HOME/conductor-status.json` |

`runtime/kinds/`, `runtime/personas/` は **コード扱い** (git tracked) のまま (ユーザーが Persona を編集するとき git に commit する想定、ADR-0011 と整合)。

### 6. 既存 `.gitignore` の整理

これまで `.gitignore` で除外していた以下のパターンは **不要** になる (そもそも repo に居ない):

```
runtime/minds/*
runtime/issues/inbox/*
runtime/issues/archive/*
runtime/pillars/observation/snapshots/*
runtime/pillars/conduit/storage/inbox/*
runtime/pillars/conduit/storage/archive/*
runtime/host/.venv/
runtime/host/config.env
runtime/realm/conductor-status.json
```

`.gitkeep` 達も不要。`runtime/minds/`, `runtime/issues/` 等のディレクトリ自体を repo から削除する。

### 7. 移行 (1 回限り、ADR の Consequences §後段で詳述)

既存利用者の `runtime/` 配下に状態がある場合、`$AI_ORG_OS_HOME` に手動 (or 自動移行ヘルパで) 移す。Phase 5b-4 PR の README に手順を明記する。

## Consequences（影響）

### 利点

1. **`git clean -dfx` が安全**: untracked 全消ししても Mind / Issue / Snapshot は失われない
2. **複数 checkout 共存**: 同 repo を別 branch で 2 つ checkout しても environment は 1 つを共有 / 別 `AI_ORG_OS_HOME` で完全分離も選択可
3. **`git pull` が完全に non-destructive**: コード更新と運用データが物理的に独立
4. **マルチ user / マルチ Realm**: 1 つの repo (e.g., `/opt/ai-org-os`) を複数 user が各々の `$HOME/.ai-org-os/` で動かせる
5. **配布性**: 「コード」と「データ」が明示的に分離されるので、ai-org-os を別マシンにポートする / package 化する道が見える
6. **テスト分離が強制される**: tests は必ず tmp の `AI_ORG_OS_HOME` で動く ← もう repo 内に書き出す経路がない

### 不利益 / リスク

1. **既存利用者の移行コスト**: `runtime/{minds,issues,...}` に状態がある人は手動 / ヘルパで `$AI_ORG_OS_HOME` に移す必要あり (Phase 5b-4 で移行手順を提供)
2. **デバッグ時の path 追跡**: 「Mind の data はどこ?」が 2 段階 (env → 解決) で見えるので、慣れるまで戸惑う
3. **Container 内の bind mount が 2 つになる**: docker-compose の volumes が複雑化 (とはいえ可読性は高い)
4. **大型リファクタ PR**: 全 Pillar / スクリプト / テスト / docs を一気に修正する必要があり、コンフリクトリスク
5. **Symlink / Junction の扱い**: Windows で `$AI_ORG_OS_HOME` が `~/.ai-org-os/` (Unix-style HOME 解決) が動くか確認要 (`%USERPROFILE%` ベースになる可能性)

### 派生する Issue / 後続作業

- **Phase 5b-4 (本 ADR の実装)**: 全 Pillar / スクリプト / docker-compose / tests / docs を `AI_ORG_OS_HOME` ベースに統一
- **移行ヘルパ** (任意): `runtime/host/migrate-to-home.sh` で旧 `runtime/{minds,issues,...}` を `$AI_ORG_OS_HOME` に移すスクリプト
- **README / manual-e2e-guide 更新**: 新しい mental model (repo + home) を明示
- **multi-tenant 検討** (Phase 6+): 1 repo / 複数 `AI_ORG_OS_HOME` の運用パターン

## 代替案（不採用）

### A. 現状維持 (環境とコードを同居させる)

何もしない案。

不採用理由:
- 上記「不利益」のすべての逆効果が現在進行中で起きている
- `git clean -dfx` 事故、複数 checkout 競合、`git pull` 後の不整合は現実的なリスク
- マルチ user / マルチ Realm 配布の道が永久に閉ざされる
- operator の指摘 (再掲): 「環境と git でおかしくならない？」

### B. `runtime/state/` のように repo 内サブディレクトリに集約

repo 内に居続けるが、`runtime/` 直下を「コード」、`runtime/state/` を「データ」と分離する案。

不採用理由:
- 物理的には依然 repo 内 → `git clean -dfx` リスクが残る
- 複数 checkout で `runtime/state/` を **どう共有するか** の問題が解消されない
- `git pull` 後に `runtime/state/` 構造が変わったらやはり手動移行
- 「半分だけ分離」は将来の混乱の元 (この階層は git 管理? と毎回問われる)

### C. CWD ベース (起動した場所 = home)

`pwd` を基準にすればいい案。

不採用理由:
- どこで起動するかで挙動が変わる = 再現性が低い
- Container 起動と host 起動で挙動が分岐 → 設計が複雑化
- env var override 不可

### D. ハードコード `/var/lib/ai-org-os/`

Linux 標準的な場所に固定する案。

不採用理由:
- Windows / macOS で動かない
- マルチ user (各 user が自分の home に持つ) で破綻
- root 権限が必要になる

### E. XDG_DATA_HOME / XDG_CONFIG_HOME を厳密に使い分ける

Linux Desktop の慣習に従い、設定と data を別ディレクトリに分ける案。

不採用理由:
- 過剰 (ai-org-os の利用者にとって 2 箇所を意識する負荷は不要)
- Windows での XDG サポートが弱い
- 単一 root (`$AI_ORG_OS_HOME`) の方がメンタルモデルが単純

## 関連

- [ADR-0011](0011-warden-claude-naming-and-separation.md) — Pillar = ai-org-os コア (本 ADR の「framework」に該当)
- [ADR-0012](0012-human-position-outside-realm.md) — 人間 = Realm 外、本 ADR の `$AI_ORG_OS_HOME` 管理者
- [ADR-0014](0014-realm-physical-boundary.md) §3 — 物理境界カテゴリ、本 ADR で「ホスト側」を更に 2 層に分割
- [ADR-0016](0016-mind-auth-and-host-container-boundary.md) — Container = コア / ホスト = Mind、本 ADR でホスト側の **コード vs データ** が明確化
- [ADR-0017](0017-warden-monitoring-vs-job-monitoring.md) — 層 A / 層 B 分離、本 ADR は層 A 内部のさらなる分離 (framework vs runtime state)
- Issue #78 (Phase 5b-3) — Host setup の分離、本 ADR の前提
- Phase 5b-4 (TBD) — 本 ADR の実装
