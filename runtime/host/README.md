# runtime/host/ — ホスト側セットアップ (Phase 5b-3 / 5b-4)

> 想定読者: ai-org-os Realm を初めて立ち上げる人 / 別マシンに移植する人。

ADR-0016 で「**Mind はホストの claude session で動く**」と決め、ADR-0018 で
「**framework (repo) と runtime state (`$AI_ORG_OS_HOME`) を物理分離**」と確定した。
本ディレクトリは **ホスト側のセットアップスクリプト** を集約する場所。

## 1 回だけ叩くもの

```bash
bash runtime/host/setup.sh
```

これで以下が **`$AI_ORG_OS_HOME` (default `~/.ai-org-os/`)** に揃う:

```
$AI_ORG_OS_HOME/
├── venv/                    host Python venv (mcp パッケージ入り)
├── config.env               setup.sh の出力 (絶対パス etc.)
├── minds/                   spawn された Mindspaces
├── issues/{inbox,archive}/  人間 → Realm 入力
├── snapshots/               Observation 履歴
├── conduit-storage/         Mind 間 Dispatch
│   ├── inbox/
│   └── archive/
└── conductor-status.json    Warden cycle 状態
```

**repo (`pgit/ai-org-os/`) には runtime state は一切作られない** (ADR-0018)。
`git pull` での更新と、Mind / Issue の運用データが物理的に独立する。

## `$AI_ORG_OS_HOME` を変更したい場合

```bash
export AI_ORG_OS_HOME=/path/to/your/realm-home
bash runtime/host/setup.sh
```

env で渡せばそこに作る。後続の `spawn-mind.sh` / `docker compose up` 等もこの env を見る。
別 user / 別 Realm を同じ machine で並走させたいときに使う。

## なぜ setup を分けるのか

過去の試行錯誤（ADR-0017 / 0018）の結果として:

| フェーズ | 担当 | 頻度 |
|---|---|---|
| **setup** (本書) | host/setup.sh | 1 回 (再セットアップは `--recreate-venv`) |
| **spawn** | pillars/lifecycle/spawn-mind.sh | Mind ごと、毎回 |

spawn-mind は **config.env を source するだけ** で、ホスト固有事情には立ち入らない。
`config.env` 自体も `$AI_ORG_OS_HOME` 配下にある (= repo から物理的に独立)。

## 前提

| 項目 | チェック |
|---|---|
| Python 3.10+ | `python3 --version` |
| claude code (login 済推奨) | `claude --version` ( login は `claude code login`) |
| pip | venv 経由で使うので別途不要 |

## 再セットアップ

mcp の major version を上げたいとき / venv が壊れたときは:

```bash
bash runtime/host/setup.sh --recreate-venv
```

`$AI_ORG_OS_HOME/venv/` を削除して作り直す。config.env は新しい値で上書きされる。
**Mind / Issue / Snapshot 等の運用データは影響を受けない** (別ディレクトリにあるため)。

## OS 別の挙動

- **Windows (git-bash)**: venv の python は `$AI_ORG_OS_HOME/venv/Scripts/python.exe`、パスは `C:/...` 形式で config.env に書く (forward slash、Claude Code が受理可能な形式)
- **Linux / macOS**: venv の python は `$AI_ORG_OS_HOME/venv/bin/python`、通常の絶対パス

setup.sh は両対応。

## 完全リセット

```bash
rm -rf "${AI_ORG_OS_HOME:-$HOME/.ai-org-os}"
bash runtime/host/setup.sh
```

これで Mind / Issue / Snapshot を含めた **全 runtime state** が消える。
repo (フレームワーク本体) はもちろん無傷。

## 関連

- ADR-0014 §3 (Realm 物理境界、ホスト = カテゴリ B 穴あき層)
- ADR-0016 (Container = コア / ホスト = Mind)
- ADR-0017 (Warden 監視 / ジョブ監視の責務分離)
- ADR-0018 (framework / runtime state 物理分離、本書の根拠)
- spawn-mind.sh — config.env を source、`$AI_ORG_OS_HOME/minds/<name>/` を作る
- docker-compose.yml — `$AI_ORG_OS_HOME` を `/realm/home` に bind mount
