# runtime/observatory/ ロードマップ

> 想定読者:
> - `runtime/observatory/` を次に拡張する担当
> - Phase 5（Warden / Guildmaster）の観測責務を設計する担当
> - 「観測の解像度をどこまで上げるか」をプロダクトオーナーと擦り合わせる立場
>
> 目的: 最小実装が動いた今、**次に何を作れば「観測の解像度が上がる / 運用判断に直結する」か** を明文化し、Phase 5 接続までの段階を SSOT として記録する。
> 本書は **設計のみ**。実装は本書の合意後に Issue / PR として切り出す。
>
> **2026-05-23 注記（重要）**: [ADR-0010](../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md) で **Observatory は Warden 機能の一部** と位置づけ直された。
> 本書は当初「Observatory 単体ツールの進化」想定で書かれているが、v0.x のロードマップは「**Warden 機能の進化**」として読み替えること。次回更新時に該当箇所を明示的に書き直す。

---

## 1. 現状（できていること）の整理

PR #（現行 PR）時点で、`runtime/observatory/` は以下を達成済み。

| 観測軸 | 実装 | 出典 |
|---|---|---|
| **メタ情報**（kind / persona / spawned_at） | `runtime/minds/<name>/.mind-meta.md` をパース | `observe.py` `_read_meta` / `_epoch_from_iso` |
| **活動状態**（mtime ベースの 3 値 status） | Mindspace 配下の最新 `mtime` から `active` / `waiting` / `idle` を判定 | `mind_status.calc_status`、しきい値 5min / 1h |
| **メッセージ件数**（inbox / archive） | `runtime/nexus/storage/{inbox,archive}/<name>/*.md` の件数集計 | `observe.py` `_count_messages` |
| **優先度カテゴリ**（5 値） | status × unread の組み合わせから `attention` / `running` / `unread` / `stale` / `read` を導出 | `mind_status.calc_category` |
| **出力フォーマット** | 人間向け表 + 機械向け JSON（`--json`） | `observe.py` `_format_table` / `_format_json` |
| **依存** | Python 標準ライブラリのみ | ADR-0005 / ADR-0009 整合 |
| **テスト** | unittest 14 ケース、`mind_status.py` を I/O なしで検証 | `test_mind_status.py` |

### できていないこと（現状の穴）

- **時系列が無い** — 「今この瞬間」のスナップショットのみ。1 時間前との比較ができない
- **dispatch のフローが見えない** — inbox / archive の **件数** は見えるが、**誰から誰へ** は集計されない
- **Mind 同士の関係が見えない** — トポロジ（who talks to whom）が無い
- **能動配信が無い** — pull 専用。何か起きても誰にも通知されない
- **Realm / Guild / Warden の概念が無い** — Phase 5 で導入される階層に未対応
- **リソース消費が見えない** — Mindspace のディスク使用量、Nexus storage の蓄積量を測っていない
- **Axiom 違反検知が無い** — 観測情報はあるが「これは不可侵原則に反する動きでは？」を判定するロジックは無い

---

## 2. 次に欲しい観測軸（候補列挙、優先度付け）

実装コストは **S=半日 / M=2〜3 日 / L=1 週間以上**。Axiom 整合は ADR-0001 / ADR-0002 / ADR-0009 を基準とする。

### (a) Dispatch のフロー可視化（誰が誰にいつ送ったか）

- **何が見える**: 過去 N 時間のメッセージを `from → to (count, last_at)` のテーブルで集計。inbox / archive の `*.md` から frontmatter を読む（中身は読まない、ヘッダのみ）
- **Axiom**: Mindspace ではなく Nexus storage を読むので不可侵原則に違反しない。Dispatch は元々 Nexus 経由 = 共有領域
- **コスト**: S
- **優先度**: ★★★（解像度の伸び代が最大、Phase 5 audit の前段）

### (b) Persona と実際の行動の乖離検知

- **何が見える**: 「`persona=reviewer` なのに送信 0 / 受信 10、archive 0」のようなアンマッチを表に出す
- **Axiom**: 観測情報の組み合わせだけ。Mindspace 中身に立ち入らない
- **コスト**: M（乖離のルールを定義する仕事が大半。判定そのものは S）
- **優先度**: ★★（運用洞察として強いが、ルール設計が属人化しやすい）

### (c) リソース使用量（Mindspace のディスク / Nexus storage 容量）

- **何が見える**: `du -sh` 相当（Python `os.scandir` で再帰サイズ）、Nexus storage 総容量、Mind ごとの占有率
- **Axiom**: サイズだけ、中身は読まない
- **コスト**: S
- **優先度**: ★★★（Phase 5 で Warden が enforce する前段、ADR-0006 §7 リソース管理フックに直結）

### (d) 履歴グラフ（時系列での状態遷移）

- **何が見える**: スナップショットを定期スナップに保存、過去 N 時刻分の status / category 推移を CSV / グラフ出力
- **Axiom**: 既存観測値の系列化のみ
- **コスト**: M（スナップ保存 + 表示）
- **優先度**: ★★★（時系列無しの限界が現状最大の制約。すべての応用観測の土台）

### (e) Mind 同士の相互作用ネットワーク図

- **何が見える**: dispatch フロー（候補 a）をグラフ化。誰がハブ / 誰が孤立 / クラスタ構造
- **Axiom**: (a) と同じ
- **コスト**: M（集計は (a) と共通、可視化を ASCII / graphviz / mermaid のいずれかで）
- **優先度**: ★★（Phase 5 で複数 Guild が出てきたときに効く、Phase 5 前は装飾的）

### (f) ストレージ容量の見込み（成長率予測）

- **何が見える**: 履歴 (d) + サイズ (c) を組み合わせ、「現状の成長率では 30 日後に X GB」と推定
- **Axiom**: 既存観測値の派生
- **コスト**: S（(c) と (d) が揃ってから）
- **優先度**: ★★（Phase 5 enforce のしきい値設定材料）

### (g) Axiom 違反候補の検知

- **何が見える**: 例「Mind A の Mindspace の mtime が更新されたが、Mind A 自身は idle」「Nexus 経由でない経路で inbox にファイルが置かれた疑い」「Mindspace 配下に他 Mind 名のディレクトリ片」
- **Axiom**: メタ情報の比較だけで判定（中身は読まない）
- **コスト**: M（違反パターンの定義が肝）
- **優先度**: ★★★（Phase 5 Warden の中核責務の前段、ADR-0001 / ADR-0002 の物理担保への第一歩）

### (h) Web UI（bash-editor 同等の 1 ブラウザタブ監視）

- **何が見える**: 現 CLI 出力を HTML で。`observe.py --json` を読んで再描画するだけの薄いページ
- **Axiom**: ADR-0009 §2 で「Web UI は当面作らない」と明示。**本ロードマップでは延期**
- **コスト**: L
- **優先度**: ★（明示的に後回し、Web UI を持つなら bash-editor を外部ツールとして併用する道を取る）

### (i) push 通知（waiting_confirmation 同等の能動配信）

- **何が見える**: `attention` カテゴリの Mind が出た瞬間に webhook / ファイル投入 / 終端ベル等で通知
- **Axiom**: 観測値の派生 + 外部 sink。Mindspace は触らない
- **コスト**: M（sink の抽象化が必要）
- **優先度**: ★★（CLI を polling する運用に対して即効性、Guildmaster の代替として簡易）

### (j) Guild 階層対応（Phase 5 で Guild が増える時）

- **何が見える**: `runtime/minds/<name>/.mind-meta.md` に Guild 識別子が入る前提で、Guild 単位のロールアップ表示
- **Axiom**: Phase 5 設計に依存。ADR-0006 が確定するまでは保留
- **コスト**: M（メタの拡張に追従するだけ）
- **優先度**: ★★（Phase 5 着手と同時に必要、それまで不要）

### (k) アラート機能（stale 検知時に通知）

- **何が見える**: `stale` カテゴリへ遷移した Mind をログに出す。(i) と sink を共有
- **Axiom**: (i) と同じ
- **コスト**: S（(i) が出来ていれば追加分は薄い）
- **優先度**: ★★（運用品質に直結、忘れられた Mind の回収）

### (l) ダッシュボードのプリセット（Guildmaster 用 / 人間用）

- **何が見える**: 表示する列・閾値・フィルタを preset 化（`--preset guildmaster` 等）
- **Axiom**: 表示制御だけ
- **コスト**: S
- **優先度**: ★（量が増えてから、現状 3〜5 Mind なら不要）

### (m) Mind ライフサイクル統計（spawn / destroy の頻度・寿命）

- **何が見える**: `spawned_at` と destroy 時刻（Phase 5 で痕跡が増える）から、Mind の平均寿命・spawn rate
- **Axiom**: 既存観測値の集計
- **コスト**: S（履歴 (d) が前提）
- **優先度**: ★★（Phase 5 destroyed Mind の痕跡保持方針と連動）

### 候補一覧サマリ

| ID | 候補 | 解像度の伸び | Axiom | コスト | 優先度 |
|---|---|---|---|---|---|
| a | Dispatch フロー | 大 | 整合 | S | ★★★ |
| b | Persona 乖離 | 中 | 整合 | M | ★★ |
| c | リソース使用量 | 大 | 整合 | S | ★★★ |
| d | 履歴グラフ | 大（基盤） | 整合 | M | ★★★ |
| e | 相互作用ネットワーク | 中 | 整合 | M | ★★ |
| f | 容量見込み | 中 | 整合 | S | ★★ |
| g | Axiom 違反検知 | 大 | 整合（核心） | M | ★★★ |
| h | Web UI | 大 | ADR-0009 で延期 | L | ★ |
| i | push 通知 | 中 | 整合 | M | ★★ |
| j | Guild 階層 | 中 | Phase 5 依存 | M | ★★ |
| k | stale アラート | 中 | 整合 | S | ★★ |
| l | preset | 小 | 整合 | S | ★ |
| m | ライフサイクル統計 | 中 | 整合 | S | ★★ |

---

## 3. 優先順位の判断軸

候補 13 個を以下の 3 軸で序列化した。

### 軸 1: 「Phase 5 で Warden が必要とする観測」を最優先

ADR-0006 で Warden は「リソース管理」「Mind Kind Registry」「3 段階プロセスの実行」「Axiom enforce」を担う。これらが必要とする観測：

- リソース管理 → **(c) リソース使用量** + **(f) 容量見込み**
- Axiom enforce → **(g) Axiom 違反検知**
- 3 段階プロセスの監査 → **(a) Dispatch フロー** + **(d) 履歴グラフ**

つまり Warden が「自分の判断材料に使える観測 API」は (a)(c)(d)(g)。本ロードマップはここを骨格に置く。

### 軸 2: 「ai-org-os 単体で動く（外部依存なし）」を次に

ADR-0005 / ADR-0009 で「Python 標準ライブラリ + 既存 Nexus SDK のみ」と決まっている。新規依存を要求する候補は減点：

- (h) Web UI → HTTP server / フロント JS（標準ライブラリの `http.server` でも書けるが、運用が増える）→ 延期確定
- (e) ネットワーク図 → graphviz / matplotlib を引くなら減点、ASCII / mermaid 出力なら無依存

依存ゼロを守れる候補から優先する。

### 軸 3: 「UI 重視 / API 重視」のバランス

現状 `observe.py` は **CLI 表 + JSON** の二段構え。次に何を増やすかの選択：

- **API 重視**（JSON 拡張、機械可読を厚く）: Phase 5 で Warden が消費する想定なら API が筋
- **UI 重視**（表の見やすさ、preset、色付け）: 人間運用の即効性は高いが、Phase 5 に直接効かない

本ロードマップは **API 重視** を採る。理由：

1. Warden / Guildmaster という **機械消費者** が Phase 5 で来る
2. UI は CLI の表 + JSON で **当面足りる**（運用 Mind 数が一桁の間は）
3. UI の本格化は ADR-0009 で「Web UI 化は別 ADR」と保留済み

ただし「人間が眺める」体験は維持する（表の崩壊を起こさない）。

---

## 4. 推奨ロードマップ（4 段階）

各段階は **1 PR 1 段階** を原則とする。各 PR が独立して merge 可能で、merge 後も既存 CLI が動く（後方互換）こと。

### Observatory v0.1: 履歴記録（スナップショット定期保存）

**スコープ**:
1. `runtime/observatory/snapshot.py` 新設。`observe.py` の `gather_observations()` をそのまま呼んで JSON 1 ファイルに保存
2. 保存先: `runtime/observatory/snapshots/<UTC timestamp>.json`
3. `observe.py --snapshot` フラグで「出力 + 保存」を 1 アクションに
4. 古いスナップショットを保持する TTL（例: 7 日）を設定可能にする（パージは別コマンド `prune` を用意するに留め、自動削除はしない）
5. テスト: `test_snapshot.py` で「保存できる」「読み戻せる」「ID が重複しない」「TTL prune が他ファイルを壊さない」を unittest

**1 PR 見積もり**: +200 行（実装）+ +100 行（test）+ README 追記。S（半日〜1 日）

**Axiom 整合チェック**:
- Mindspace 中身に触れない → OK
- 依存ゼロ → OK
- 痕跡が `runtime/observatory/snapshots/` に残るのは **観測者の領域**、Mindspace でも Nexus storage でもない → OK

**依存関係**: 完全独立。Phase 3 / Phase 5 のどちらも前提にしない。

**判断ポイント**: snapshots/ を **git に入れるか出すか**。推奨 = `.gitignore` で除外、観測痕跡はホストローカルで持つ（再現性より運用性）。

### Observatory v0.2: Dispatch フロー可視化 + リソース使用量

**スコープ**:
1. `runtime/observatory/dispatch_flow.py` 新設。`runtime/nexus/storage/{inbox,archive}/<to>/*.md` を全件走査、frontmatter の `from`/`to`/`sent_at` だけ読む（本文は読まない）
2. 集計を `from → to (count, last_at, first_at)` のテーブルとして表 / JSON 出力
3. `observe.py --flow` フラグで dispatch サマリを追加表示
4. `runtime/observatory/resource_usage.py` 新設。Mindspace と Nexus storage の総バイト数を計測（`os.scandir` 再帰、symlink フォロー禁止）
5. `observe.py --resource` で容量カラム追加
6. テスト: frontmatter パーサの ill-formed 耐性、再帰中の OSError ハンドリング

**1 PR 見積もり**: +400 行（実装）+ +200 行（test）+ README 追記。M（2〜3 日）

**Axiom 整合チェック**:
- frontmatter 読み取り = Nexus storage の **共有領域**を読む、Mindspace には立ち入らない → OK
- ただし「Mindspace のサイズ」を測るのは中身を読まないファイル列挙 = 灰色。`du` 相当はファイル名すら見ずに `stat().st_size` だけ集計 → 不可侵に踏みとどまる
- frontmatter 以外のメッセージ本文は **明示的に読まない**（コード規約として README に書く）

**依存関係**: v0.1 と独立。v0.1 が無くても動く。並列開発可。

**判断ポイント**: frontmatter にどのフィールドが必須かは `runtime/nexus/storage.py` の実装に追従する必要がある。**Nexus 側のフォーマット契約を本 PR で文書化**（`runtime/nexus/dispatch-format.md` 新設）して凍結する。

### Observatory v0.3: Axiom 違反検知 + 履歴比較

**スコープ**:
1. `runtime/observatory/anomaly.py` 新設。以下のシグナルを検知し、`warning` / `info` レベルで列挙する：
   - **W1**: Mindspace の mtime が更新されたが、その Mind の Nexus tool 呼び出し履歴（v0.2 の dispatch flow）と整合しない（Nexus を介さない外部書き込みの疑い）
   - **W2**: Mindspace 配下に他 Mind 名のディレクトリ片がある（不可侵原則違反の物理的痕跡）
   - **W3**: `.mind-meta.md` の `kind` が `runtime/kinds/` に存在しない（孤児 Mind）
   - **I1**: `stale` カテゴリへの遷移を v0.1 履歴と比較して新規発生分だけ通知
   - **I2**: inbox の蓄積（unread が一定閾値超）
2. `observe.py --anomaly` で warning / info を別セクションに出力
3. v0.1 の snapshot を 2 つ指定して diff を出す `observe.py --diff <a> <b>`
4. テスト: 各シグナルの true / false ケース、snapshot diff のキー整合

**1 PR 見積もり**: +500 行（実装）+ +300 行（test）+ ADR 追記検討（違反検知ロジックを ADR-0009 の流用方針に紐付ける）。M（3〜4 日）

**Axiom 整合チェック**:
- W1〜W3 はファイル名・mtime・メタのみで判定 → OK
- W1 の判定は v0.2 の集計が前提（dispatch 履歴と mtime の照合）→ v0.2 依存

**依存関係**: v0.1（snapshot）+ v0.2（dispatch flow）に依存。**v0.2 → v0.3 の順を守る**。

**判断ポイント**: W1 は誤検知が出やすい（Mindspace 内で Mind 自身が書いた変更も mtime を更新する）。**最初は warning ではなく info に降格して様子見**、運用ログを v0.1 で蓄積してから昇格させる。

### Observatory v1.0: Phase 5 統合（Warden の入力に）

**スコープ**:
1. ADR-0006 で Warden が `realm/audit/dispatches/` を読む経路が確定したら、`observe.py` がそれも観測対象に加える
2. Guild 識別子が `.mind-meta.md` に追加されたら（候補 j）、Guild 単位のロールアップを実装
3. `observe.py --for-warden` フラグで Warden が消費しやすい JSON 形式（schema versioned）を出力
4. **Warden は本 Observatory の関数を Python import して使ってよい**（同じプロセス内）—— ADR-0006 §3「Warden は Realm コンテナ内の常駐 Python プロセス」と整合
5. 履歴・dispatch・容量・anomaly を一つの「Realm Status Report」JSON に統合
6. **bash-editor を外部ツールとして併用する手順**（ADR-0009 §3 で予告した方式 E）を `runtime/verification/phase-3-dogfooding/README.md` に追記。Observatory の JSON を bash-editor のセッション情報と照合する例を入れる

**1 PR 見積もり**: +800 行（実装、Phase 5 設計確定後）+ +400 行（test）+ ADR-0009 改稿。L（1〜2 週間、Phase 5 並走）

**Axiom 整合チェック**:
- Warden が同プロセス内で import するので **境界は Realm = ai-org-os の責務**、観測ツールがその責務を持って良い
- `realm/audit/dispatches/` は ADR-0006 で痕跡領域として定義済 → 観測対象として正当

**依存関係**: **ADR-0006 が Accepted になっていること**。それまでは v0.3 で止める。

**判断ポイント**: v1.0 では「Observatory を Warden のサブモジュールにする」か「独立モジュールのまま Warden が import する」かの選択がある。**独立モジュール推奨**——Observatory は Phase 5 以前から動く実績があり、Warden 以外（人間 CLI、CI nightly）からも使う。

---

### 段階間の依存関係まとめ

```
v0.1 (snapshot)        ──┬─→ v0.3 (anomaly + diff) ──→ v1.0 (Phase 5)
v0.2 (flow + resource) ──┘                              ↑
                                                        |
                                            ADR-0006 Accepted が前提
```

v0.1 / v0.2 は並列開発可能。v0.3 は両者を前提とする。v1.0 は Phase 5 と並走する。

---

## 5. 既知の制限

### 5.1 Mindspace 不可侵原則による情報の制限

ADR-0001 / ADR-0002 で Mindspace は不可侵と確定している。Observatory は **中身を読まない**：

- ファイルの **存在 / mtime / サイズ** は観測してよい
- ファイルの **内容（テキスト）** は読まない
- 例外的に **メタファイル**（`.mind-meta.md`）と **共有領域**（Nexus storage の frontmatter）は読む

この制約により、以下は **構造的に観測不能**：

- Mind が何を考えているか
- Mind が今どんなコードを書いているか
- Mind が外部 API を叩いたか（Nexus 経由でないアクセス）

これは制約であり、同時に **Axiom の保証**でもある。Observatory はこの境界を越えない。

### 5.2 ファイルベースの即時性限界

mtime / ディレクトリ列挙ベースのため：

- **秒未満の解像度は無理**（OS により mtime 粒度が異なる）
- **inotify / fsevent を使わない**ので、polling 前提（典型 = 数十秒〜分単位）
- 大量の Mind（>100）が動くと再帰列挙が重い → v0.2 のリソース計測で頭打ちが見える

これは Mind が秒単位で動かない設計（Dispatch は非同期 / 確認ベース）と整合する。即時性が要れば push 通知（候補 i）か bash-editor 併用に倒す。

### 5.3 Mind が死んだ時の履歴保持方針（未決）

ADR-0006 で `destroy_mind` が実装されると、Mindspace は削除される。このとき：

- **観測履歴（snapshot）はどうする**？
- **Nexus storage の archive はどうする**？

**選択肢**:

| 案 | 内容 | 評価 |
|---|---|---|
| (X1) Mindspace と同時消去 | 痕跡をすべて消す、プライバシ重視 | Axiom「共有はプロセスを踏む」(=痕跡が残る) と矛盾 |
| (X2) 観測履歴は残す、Mindspace 本体だけ消す | 「Mind は消えたが、世界が観測したログは残る」 | ADR-0002 §6「痕跡が残る」と整合、推奨 |
| (X3) すべて残す（Mindspace tarball として保存） | 完全再現可能 | Mindspace 不可侵と矛盾（消えた後でも他が読める） |

**仮の方針**: **(X2)**。Observatory の snapshot は Mind の生死と独立に保持される。Mindspace は ADR-0006 §3 destroy 経路で消えるが、観測痕跡は残る。ただしこの判断は **本ロードマップでは仮置き**、ADR-0006 の destroy 仕様確定時に正式判断する。

### 5.4 観測者の観測者問題

Observatory 自身が Mindspace / Nexus storage を走査することで、それらの mtime を更新する可能性。**読み取りなので mtime は更新されない**が、`open(O_RDONLY)` を使う / `os.stat` だけで済ます規約を README に書く。

---

## 6. 関連

### 上位設計

- [ADR-0001: ai-org-os を「開発組織の不変項」を定義するフレームワークとして再定義する](../../docs/adr/0001-ai-org-os-as-invariant-framework.md) — Axiom の出典
- [ADR-0002: 用語と「メタのメタ」構造の確定](../../docs/adr/0002-vocabulary-and-meta-meta-structure.md) — Mindspace 不可侵 / 3 段階プロセス / 痕跡
- [ADR-0005: Phase 3 = Nexus（MCP サーバー）直行](../../docs/adr/0005-phase-3-mcp-direct-with-nexus.md) — 依存ゼロ方針
- [ADR-0006: Phase 5（Realm + Warden + Guildmaster）の設計案](../../docs/adr/0006-phase-5-realm-warden-guildmaster.md) — v1.0 統合先、リソース管理 / Axiom enforce
- [ADR-0009: bash-editor / claude-team との関係性と流用方針](../../docs/adr/0009-relationship-with-bash-editor-and-claude-team.md) — fork しない / 流用方針

### 同 Observatory 内

- [`runtime/observatory/README.md`](./README.md) — 設計根拠と現状の使い方
- [`runtime/observatory/mind_status.py`](./mind_status.py) — 純粋関数群
- [`runtime/observatory/observe.py`](./observe.py) — CLI 本体
- [`runtime/observatory/test_mind_status.py`](./test_mind_status.py) — unittest

### 観測データ源

- [`runtime/nexus/storage.py`](../nexus/storage.py) — Dispatch storage、v0.2 で frontmatter を読む対象
- `runtime/minds/<name>/.mind-meta.md` — Mind メタ、v0.3 で kind 整合を取る
- `runtime/kinds/*.md` — Kind カタログ、v0.3 W3 で照合

### 参考（流用しないが発想元）

- `local-multi-window-bash-editor` の `lib/pure.js` — `calcStatus` / `calcCategory` の出典（Python 移植済）
- `local-multi-window-bash-editor` の Web UI / WebSocket / xterm.js — **流用しない**。Observatory が UI を必要とする段階に至ったら、bash-editor を **外部ツールとして併用**（ADR-0009 §3 方式 E）

---

## 7. 本ロードマップの位置づけ

> 本書は **設計のみ**。各バージョン（v0.1 / v0.2 / v0.3 / v1.0）の着手は、それぞれ **個別 Issue として切り出し、本書をリンクして詳細化する**。
>
> 本書の更新タイミング:
> - 各 v リリース後に「現状」セクションを更新
> - ADR-0006 が Accepted になった時点で v1.0 の依存関係を確定
> - 候補（a〜m）に新しい観測軸が増えたら本書に追記
>
> 本書を **Accepted** に昇格させる条件:
> - v0.1 のスコープが詳細化されて 1 PR として merge 可能になったとき
> - またはプロダクトオーナーが「順序と判断軸に同意」と明示したとき
