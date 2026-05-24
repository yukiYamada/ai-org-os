# runtime/host/ — ホスト側セットアップ (Phase 5b-3, Issue #78)

> 想定読者: ai-org-os Realm を初めて立ち上げる人 / 別マシンに移植する人。

ADR-0016 で「**Mind はホストの claude session で動く**」と決めた。
本ディレクトリは **ホスト固有のセットアップ** を集約する場所。

## 1 回だけ叩くもの

```bash
bash runtime/host/setup.sh
```

これで以下が揃う:

| 生成物 | 用途 |
|---|---|
| `runtime/host/.venv/` | ホスト用 Python venv (`mcp` パッケージ入り) |
| `runtime/host/config.env` | spawn-mind.sh が source する設定 (絶対パス etc.) |

config.env は `.gitignore` 対象（ホスト固有 = commit しない、ADR-0016 と整合）。

## なぜ setup を分けるのか (ADR-0017 と整合)

以前は `spawn-mind.sh` が venv 作成・パス解決・config 書き出しを **毎回** やっていた。これだと:
- ホスト固有事情 (パス形式 / venv 有無 / mcp 有無) が spawn 時に毎回判定される
- Windows 上で git-bash 形式パス `/c/...` を `.mcp.json` に書いてしまい、Claude Code が起動できない (Phase 5b-2 動作確認で顕在化)

責務を分離した:

| フェーズ | 担当 | 頻度 |
|---|---|---|
| **setup** (本書) | host/setup.sh | 1 回 (再セットアップは `--recreate-venv`) |
| **spawn** | pillars/lifecycle/spawn-mind.sh | Mind ごと、毎回 |

spawn-mind は **config.env を source するだけ** で、ホスト固有事情には立ち入らない。

## 前提

| 項目 | チェック |
|---|---|
| Python 3.10+ | `python3 --version` |
| claude code (login 済推奨) | `claude --version` ( login は `claude code login`) |
| pip | venv 経由で使うので別途不要 |

setup.sh は前提が揃ってない場合に明確にエラーを出す。

## 再セットアップ

mcp の major version を上げたいとき / venv が壊れたときは:

```bash
bash runtime/host/setup.sh --recreate-venv
```

`.venv/` を削除して作り直す。config.env は新しい値で上書きされる。

## OS 別の挙動

- **Windows (git-bash)**: venv の python は `.venv/Scripts/python.exe`、パスは `C:/...` 形式で config.env に書く (forward slash、Claude Code が受理可能な形式)
- **Linux / macOS**: venv の python は `.venv/bin/python`、通常の絶対パス

setup.sh は両対応。

## 後片付け

ホスト venv 自体を消したいとき:

```bash
rm -rf runtime/host/.venv runtime/host/config.env
```

## 関連

- ADR-0014 §3 (Realm 物理境界、ホスト = カテゴリ B 穴あき層)
- ADR-0016 (Container = コア / ホスト = Mind)
- ADR-0017 (Warden 監視 / ジョブ監視の責務分離) — 本 setup は「ホスト側の Mind 起動準備」=層 A の外側
- Issue #78 (本ディレクトリの起票元)
- spawn-mind.sh — 本 setup の出力 (config.env) を source する側
