# runtime/pillars/observation/

> 想定読者: Realm 内に複数の Mind が居る状態を一目で把握したい人。Guildmaster や Warden を実装する前段としての観測ベースライン。

ai-org-os 用の **Realm 観測ツール最小実装**。Python 標準ライブラリのみ、依存ゼロ。

設計の根拠は [ADR-0009](../../../docs/adr/0009-relationship-with-bash-editor-and-claude-team.md) を参照。
`local-multi-window-bash-editor` の `lib/pure.js`（calcStatus / calcCategory）の発想だけを Python に移植し、Web UI や PTY 監視は持ち込まない。

## 構成

```
runtime/pillars/observation/
├── mind_status.py        ← 状態判定の純粋関数（依存ゼロ、テスト可能）
├── observe.py            ← CLI、ホストの runtime/minds と runtime/pillars/conduit/storage を歩いてレポート
├── test_mind_status.py   ← unittest（標準ライブラリ）
└── README.md
```

## 使い方

### 人間向け（表）

```bash
python3 runtime/pillars/observation/observe.py
```

出力例（spawn 中の Mind が無いとき）:

```
No minds spawned.
```

Mind が居るときは：

```
=== Realm Observatory ===
  total: 3
  status:   active=1  waiting=1  idle=1
  category: attention=1  running=0  unread=0  stale=0  read=2

NAME                 KIND       PERSONA        STATUS   CATEGORY   INBOX/ARCHIVE
alice                generic    designer       active   attention  2/5
bob                  generic    reviewer       waiting  read       0/3
carol                generic    implementer    idle     read       0/1
```

### 機械向け（JSON）

```bash
python3 runtime/pillars/observation/observe.py --json
```

`{generated_at, minds: [...]}` で構造化された出力。後で Guildmaster / Warden が消費する想定。

## ステータスとカテゴリの意味

### Status（活動の鮮度、`mind_status.calc_status`）

| Status | 条件 | 意味 |
|---|---|---|
| `active` | 最終 mtime から < 5 分 | 直近で何かが書かれた |
| `waiting` | 5 分 ≤ 経過 < 1 時間 | 直近の動きはないが死んでない |
| `idle` | 1 時間 ≤ 経過 | しばらく動いていない |

### Category（運用上の優先度、`mind_status.calc_category`）

| Category | 条件 | 意味 |
|---|---|---|
| `attention` | active + 未読あり | 誰か（Guildmaster / 人間）が見るべき |
| `unread` | non-active + 未読あり | 次回の poll で拾われる |
| `running` | active + 未読なし | 自走中、放置で OK |
| `stale` | 6 時間以上動かず + 未読なし | 忘れられかけ |
| `read` | それ以外 | 直近 idle、未読なし、追いついている |

しきい値は `mind_status.py` 冒頭の定数で調整可能。

## なぜ最小なのか

ADR-0009 で「**fork / submodule はしない、純粋ロジックだけ流用する**」と決めたため。
将来 Realm Dashboard を Web UI 化する判断が出たら、`bash-editor` を **外部ツールとして併用** する手順を [`runtime/verification/phase-3-dogfooding/README.md`](../../verification/phase-3-dogfooding/README.md) に追加する想定（方式 E 候補）。

## Warden との関係（重要、2026-05-23 追記）

[ADR-0010](../../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md) で確定：

- **本ツール（observe.py）は Warden の機能の一部**として位置づけられる
- 現状は **Warden 不在時の暫定実装**
- Phase 5 で Warden が登場 → Observatory は Warden に吸収（独立ツールではなくなる）

Mind は「観測されている」を意識する必要はない（application log と同じ性質）。観測情報を必要な Mind には Warden 経由で提供される（MCP tool / Persona 注入 / 人間向け UI）。

## 不可侵原則との関係

- Mindspace の**中身は読まない**（Axiom: Mindspace 不可侵）
- 観測するのは：
  - `runtime/minds/<name>/.mind-meta.md` の `kind` / `persona` / `spawned_at`
  - Mindspace 配下のファイル `mtime`（中身ではなく外形）
  - `runtime/pillars/conduit/storage/{inbox,archive}/<name>/` のメッセージ件数

これは「壁の外から灯りがついてるかを観察する」レベルで、Mindspace の所有権は侵さない。

## スナップショット履歴（v0.1, ROADMAP）

時系列観測の基盤として、現状の `observe.py --json` 相当の JSON を
`runtime/pillars/observation/snapshots/<UTC timestamp>.json` に保存できる：

```bash
# 1 件保存 + stdout に JSON も出す（pipe で次の処理に流せる）
python3 runtime/pillars/observation/observe.py --snapshot

# 7 日より古いスナップショットを削除（デフォルト TTL=7、自動削除はしない）
python3 runtime/pillars/observation/observe.py --prune

# TTL を変える（例: 30 日）
python3 runtime/pillars/observation/observe.py --prune --ttl-days 30
```

ファイル名は `YYYYMMDDTHHMMSSZ-<microsecond>.json`（ソート可能、衝突回避）。

### 定期実行の例

#### cron（Linux / macOS）

```cron
# 10 分ごとにスナップショット、毎日 03:30 に古いものを削除
*/10 * * * * cd /path/to/ai-org-os && python3 runtime/pillars/observation/observe.py --snapshot >/dev/null
30 3 * * *   cd /path/to/ai-org-os && python3 runtime/pillars/observation/observe.py --prune >/dev/null
```

#### 外側スクリプト（コンテナ常駐 / どこでも動く）

```bash
# 30 秒ごとに snapshot を取り続ける小さなループ
while true; do
  python3 runtime/pillars/observation/observe.py --snapshot >/dev/null
  sleep 30
done
```

### 設計判断

- **snapshots/ は `.gitignore`**（ROADMAP v0.1 §判断ポイント）。観測痕跡はホストローカル、再現性より運用性
- **TTL prune は自動化しない**。利用者が明示的に `--prune` を呼ぶ。古い記録を消す判断は外側に置く
- **書き込みは tmp + `os.link` で atomic 予約** — 並行プロセスから同時に呼んでも最終ファイル名が衝突しない（衝突時は counter で別名）
- **microsecond 衝突は -2/-3 suffix で回避**。`write_snapshot` を高速連打しても重複なし
- **`--snapshot` と `--prune` は同時指定不可（実質排他）** — 両方渡すと `--prune` が優先され `--snapshot` は実行されない。別々に呼ぶこと
- **`.tmp` 残骸は次回 `--prune` が掃除**（5 秒経過後）。write_snapshot が途中でクラッシュした場合の保険

詳細仕様: [`ROADMAP.md`](./ROADMAP.md) §「Observation Pillar v0.1」

## テスト

```bash
# 観測ロジックのユニットテスト
python3 -m unittest discover runtime/pillars/observation -p 'test_*.py'

# または既存テストランナーで全部
./runtime/tests/run-tests.sh
```

## 関連

- [ADR-0009](../../../docs/adr/0009-relationship-with-bash-editor-and-claude-team.md) — bash-editor / claude-team との関係性
- [ADR-0006](../../../docs/adr/0006-phase-5-realm-warden-guildmaster.md) — Phase 5（Warden が観測責務を本格的に負う）
- `runtime/pillars/lifecycle/list-minds.sh` — シェルベースの軽量一覧
- `runtime/pillars/conduit/storage.py` — メッセージ件数のデータ源
