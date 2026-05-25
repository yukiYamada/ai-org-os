# Warden Observation Pillar ロードマップ（旧 `runtime/pillars/observation/`）

> 想定読者:
> - **Observation Pillar**（Warden の観測機能）を次に拡張する担当
> - Phase 5（Realm + Warden）の観測責務を設計する担当
> - 「観測の解像度をどこまで上げるか / どこから先は Mind には見せないか」をプロダクトオーナーと擦り合わせる立場
>
> 目的: 最小実装が動いた今、**次に何を作れば「Warden の自己認識が解像度高くなる / Mind への観測 API が運用判断に直結する」か** を明文化し、Phase 5a 以降の段階を SSOT として記録する。
> 本書は **設計のみ**。実装は本書の合意後に Issue / PR として切り出す。

---

## 0. 本書の位置づけ（重要）

### `observe.py` は Observation Pillar の暫定実装

[ADR-0010](../../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md) で **Observatory は Warden 機能の一部**、[ADR-0011](../../../docs/adr/0011-warden-claude-naming-and-separation.md) で **Warden 機能の構成要素は Pillar と呼ぶ** ことが確定。従って **`runtime/pillars/observation/observe.py` は「Observation Pillar の暫定実装」** である。本 ROADMAP は Pillar の進化計画として読む：

| 旧理解 | 新理解（ADR-0010 / ADR-0011） |
|---|---|
| Observatory = 単独の観測ツール | **Observation Pillar = Warden の自己認識機能** |
| ROADMAP = ツールの機能拡張 | **ROADMAP = Pillar が持つべき責務の段階的実装** |
| `runtime/pillars/observation/` 配下で完結 | Phase 5a-2 で **`runtime/pillars/observation/` に移動** |
| Phase 5 で Warden に「組み込む」 | Phase 5a で Warden の **構成要素として正式に位置づけ**（=吸収シナリオ） |

### 観測の 2 種類（ADR-0010 §4 の再掲）

| # | 観測主体 | 範囲 | 制約 | 用途 |
|---|---|---|---|---|
| 1 | **Warden**（世界そのもの） | **全部見える** | なし | 世界の自己認識（リソース管理、Axiom enforce、運用判断） |
| 2 | **Mind**（観測機能を利用する側） | 制限あり | **Axiom 制約下**（Mindspace 不可侵） | 組織の改善活動、自分の状況把握 |

**Observation Pillar の責務は (1) を完全に提供しつつ、(2) を Axiom 制約越しに切り出す**こと。
従って本書の観測軸（a〜m）は **「Warden の自己認識（無制約）」「Mind 制約付き観測（Axiom 下）」のどちらに属するか** で再分類する（§3 参照）。

### Phase 5a での Warden 吸収シナリオ

[ADR-0006](../../../docs/adr/0006-phase-5-realm-warden-guildmaster.md) Accepted、[ADR-0011](../../../docs/adr/0011-warden-claude-naming-and-separation.md) の Pillar 配置に基づき、以下のタイムラインで Observation Pillar を Warden に統合する：

| 段階 | やること | 関連 Issue |
|---|---|---|
| **現状（Phase 3 + α）** | `runtime/pillars/observation/observe.py` が暫定実装として独立して動く | — |
| **Phase 5a-1** | Realm コンテナ起動。Observation Pillar はまだ `runtime/pillars/observation/` に居る（参照のみ） | #35 |
| **Phase 5a-2** | `runtime/pillars/observation/` → `runtime/pillars/observation/` に **物理移動**、編集不可機構を適用 | #37 |
| **Phase 5a-3** | Judgment Pillar から Observation Pillar の API を Python import で呼ぶ経路を確立 | #38（仮） |
| **Phase 5b 以降** | Mind 向け観測 API（Axiom 制約付き）を Conduit Pillar（Nexus）の MCP tool として公開 | 未起票 |

**本 ROADMAP の v0.x は Phase 5a-2 までに完了し、v1.0 は Phase 5a-3 以降と並走する**。

---

## 1. 現状（できていること）の整理

PR #28 〜 #50 系列で `runtime/pillars/observation/` は以下を達成済み。本機能は **Warden 不在時の代替実装**（ADR-0010 §8）として位置づけられる。

| 観測軸 | 実装 | 出典 | Warden 観点での意義 |
|---|---|---|---|
| **メタ情報**（kind / persona / spawned_at） | `runtime/minds/<name>/.mind-meta.md` をパース | `observe.py` `_read_meta` / `_epoch_from_iso` | Registry Pillar の前段 |
| **活動状態**（mtime ベースの 3 値 status） | Mindspace 配下の最新 `mtime` から `active` / `waiting` / `idle` を判定 | `mind_status.calc_status`、しきい値 5min / 1h | 「外形」観測（ADR-0010 §3：Mind の内面状態ではない） |
| **メッセージ件数**（inbox / archive） | `runtime/pillars/conduit/storage/{inbox,archive}/<name>/*.md` の件数集計 | `observe.py` `_count_messages` | Conduit Pillar のフロー観測の入り口 |
| **優先度カテゴリ**（5 値） | status × unread の組み合わせから `attention` / `running` / `unread` / `stale` / `read` を導出 | `mind_status.calc_category` | Warden / 人間運用者向けトリアージ材料 |
| **出力フォーマット** | 人間向け表 + 機械向け JSON（`--json`） | `observe.py` `_format_table` / `_format_json` | JSON は将来 Judgment Pillar が直接消費 |
| **依存** | Python 標準ライブラリのみ | ADR-0005 / ADR-0009 整合 | Pillar 共通方針 |
| **テスト** | unittest 14 ケース、`mind_status.py` を I/O なしで検証 | `test_mind_status.py` | Pillar 単体テストの先例 |

### 現状の穴（=Warden として未達の責務）

- **時系列が無い** — 「今この瞬間」のスナップショットのみ。Warden の自己認識として「変化」を扱えない
- **dispatch のフローが見えない** — inbox / archive の **件数** は見えるが、**誰から誰へ** が集計されない（Conduit Pillar 連携前段の欠落）
- **Mind 同士の関係が見えない** — トポロジ（who talks to whom）が無い
- **能動配信が無い** — pull 専用。Warden 自身が異常を検知して他 Pillar / 人間に通知できない
- **Realm / Guild / Pillar の概念が無い** — Phase 5a 階層に未対応
- **リソース消費が見えない** — Mindspace のディスク使用量、Nexus storage の蓄積量を測っていない（Warden のリソース管理機能の前段が欠落）
- **Axiom 違反検知が無い** — 観測情報はあるが「これは Axiom に反する動きでは？」を判定するロジックは無い（Judgment Pillar の入力欠落）

---

## 2. 次に欲しい観測軸（候補列挙、優先度付け）

実装コストは **S=半日 / M=2〜3 日 / L=1 週間以上**。Axiom 整合は ADR-0001 / ADR-0002 / ADR-0009 を基準とする。
**観測主体カラム**で「W=Warden 自己認識（無制約）」「M=Mind 制約付き観測（Axiom 下）」を区別する。

### (a) Dispatch のフロー可視化（誰が誰にいつ送ったか）

- **何が見える**: 過去 N 時間のメッセージを `from → to (count, last_at)` のテーブルで集計。inbox / archive の `*.md` から frontmatter を読む（中身は読まない、ヘッダのみ）
- **観測主体**: W / M 両方（M に見せる場合は frontmatter 経路のみで Axiom 整合）
- **Axiom**: Mindspace ではなく Nexus storage（共有領域）を読むので不可侵原則に違反しない
- **コスト**: S
- **優先度**: ★★★（解像度の伸び代が最大、Judgment Pillar の入力前段）

### (b) Persona と実際の行動の乖離検知

- **何が見える**: 「`persona=reviewer` なのに送信 0 / 受信 10、archive 0」のようなアンマッチを表に出す
- **観測主体**: W 主、M には「自分自身の乖離度」のみ公開
- **Axiom**: 観測情報の組み合わせだけ。Mindspace 中身に立ち入らない
- **コスト**: M（乖離のルールを定義する仕事が大半。判定そのものは S）
- **優先度**: ★★（運用洞察として強いが、ルール設計が属人化しやすい）

### (c) リソース使用量（Mindspace のディスク / Nexus storage 容量）

- **何が見える**: `du -sh` 相当（Python `os.scandir` で再帰サイズ）、Nexus storage 総容量、Mind ごとの占有率
- **観測主体**: W（リソース管理の根拠）、M には集計値のみ
- **Axiom**: サイズだけ、中身は読まない
- **コスト**: S
- **優先度**: ★★★（Warden のリソース管理機能の根拠データ、ADR-0006 §7 リソース管理フックに直結）

### (d) 履歴グラフ（時系列での状態遷移）

- **何が見える**: スナップショットを定期スナップに保存、過去 N 時刻分の status / category 推移を CSV / グラフ出力
- **観測主体**: W（時系列分析が Warden の中核責務、ADR-0010 §3 の「変化観測」）
- **Axiom**: 既存観測値の系列化のみ
- **コスト**: M（スナップ保存 + 表示）
- **優先度**: ★★★（時系列無しの限界が現状最大の制約、すべての応用観測の土台）

### (e) Mind 同士の相互作用ネットワーク図

- **何が見える**: dispatch フロー（候補 a）をグラフ化。誰がハブ / 誰が孤立 / クラスタ構造
- **観測主体**: W 主、M には自身を中心とした部分グラフのみ
- **Axiom**: (a) と同じ
- **コスト**: M（集計は (a) と共通、可視化を ASCII / graphviz / mermaid のいずれかで）
- **優先度**: ★★（Phase 5b 以降で複数 Guild が出てきたときに効く、Phase 5a 段階では装飾的）

### (f) ストレージ容量の見込み（成長率予測）

- **何が見える**: 履歴 (d) + サイズ (c) を組み合わせ、「現状の成長率では 30 日後に X GB」と推定
- **観測主体**: W（リソース管理の予測）
- **Axiom**: 既存観測値の派生
- **コスト**: S（(c) と (d) が揃ってから）
- **優先度**: ★★（Warden の enforce しきい値設定の材料）

### (g) Axiom 違反候補の検知

- **何が見える**: 例「Mind A の Mindspace の mtime が更新されたが、Mind A 自身は idle」「Nexus 経由でない経路で inbox にファイルが置かれた疑い」「Mindspace 配下に他 Mind 名のディレクトリ片」
- **観測主体**: W（Warden の中核責務、Mind には自分が触れた違反のみ通知）
- **Axiom**: メタ情報の比較だけで判定（中身は読まない）。**Warden は Axiom に縛られない**（ADR-0010 §5）ので無制約に判定できる
- **コスト**: M（違反パターンの定義が肝）
- **優先度**: ★★★（Judgment Pillar の中核入力、ADR-0001 / ADR-0002 の物理担保への第一歩）

### (h) Web UI（bash-editor 同等の 1 ブラウザタブ監視）

- **何が見える**: 現 CLI 出力を HTML で。`observe.py --json` を読んで再描画するだけの薄いページ
- **観測主体**: 人間（Realm の外）— Warden / Mind ではない
- **Axiom**: ADR-0009 §2 で「Web UI は当面作らない」と明示。**本ロードマップでは延期**
- **コスト**: L
- **優先度**: ★（明示的に後回し、Web UI を持つなら bash-editor を外部ツールとして併用する道を取る）

### (i) push 通知（waiting_confirmation 同等の能動配信）

- **何が見える**: `attention` カテゴリの Mind が出た瞬間に webhook / ファイル投入 / 終端ベル等で通知
- **観測主体**: W が判定、人間 / 他 Pillar に配信
- **Axiom**: 観測値の派生 + 外部 sink。Mindspace は触らない
- **コスト**: M（sink の抽象化が必要）
- **優先度**: ★★（CLI を polling する運用に対して即効性、Guildmaster の代替として簡易）

### (j) Guild / Pillar 階層対応（Phase 5a 以降）

- **何が見える**: `runtime/minds/<name>/.mind-meta.md` に Guild 識別子が入る前提で、Guild 単位のロールアップ表示。Pillar 自身の稼働状態も対象
- **観測主体**: W（自己認識として全 Pillar / Guild の状態を持つ）、M には自身が属する Guild のみ
- **Axiom**: Phase 5 設計に依存。ADR-0006 が Accepted（済）なので着手可
- **コスト**: M（メタの拡張に追従するだけ）
- **優先度**: ★★（Phase 5a 着手と同時に必要、それまで不要）

### (k) アラート機能（stale 検知時に通知）

- **何が見える**: `stale` カテゴリへ遷移した Mind をログに出す。(i) と sink を共有
- **観測主体**: W が判定、人間 / Guildmaster に配信
- **Axiom**: (i) と同じ
- **コスト**: S（(i) が出来ていれば追加分は薄い）
- **優先度**: ★★（運用品質に直結、忘れられた Mind の回収）

### (l) ダッシュボードのプリセット（Guildmaster 用 / 人間用 / Pillar 用）

- **何が見える**: 表示する列・閾値・フィルタを preset 化（`--preset guildmaster` / `--preset judgment-pillar` 等）
- **観測主体**: 利用者ごとに切り替え
- **Axiom**: 表示制御だけ
- **コスト**: S
- **優先度**: ★（量が増えてから、現状 3〜5 Mind なら不要）

### (m) Mind ライフサイクル統計（spawn / destroy の頻度・寿命）

- **何が見える**: `spawned_at` と destroy 時刻（Phase 5a で痕跡が増える）から、Mind の平均寿命・spawn rate
- **観測主体**: W（Lifecycle Pillar の運用評価）
- **Axiom**: 既存観測値の集計
- **コスト**: S（履歴 (d) が前提）
- **優先度**: ★★（Lifecycle Pillar との連動、destroyed Mind の痕跡保持方針と連動）

### 候補一覧サマリ

| ID | 候補 | 解像度の伸び | 観測主体 | Axiom | コスト | 優先度 |
|---|---|---|---|---|---|---|
| a | Dispatch フロー | 大 | W + M | 整合 | S | ★★★ |
| b | Persona 乖離 | 中 | W（M 部分） | 整合 | M | ★★ |
| c | リソース使用量 | 大 | W | 整合 | S | ★★★ |
| d | 履歴グラフ | 大（基盤） | W | 整合 | M | ★★★ |
| e | 相互作用ネットワーク | 中 | W（M 部分） | 整合 | M | ★★ |
| f | 容量見込み | 中 | W | 整合 | S | ★★ |
| g | Axiom 違反検知 | 大 | W（核心） | Warden は無制約 | M | ★★★ |
| h | Web UI | 大 | 人間 | ADR-0009 で延期 | L | ★ |
| i | push 通知 | 中 | W → 配信 | 整合 | M | ★★ |
| j | Guild / Pillar 階層 | 中 | W + M | Phase 5a 依存 | M | ★★ |
| k | stale アラート | 中 | W → 配信 | 整合 | S | ★★ |
| l | preset | 小 | 利用者別 | 整合 | S | ★ |
| m | ライフサイクル統計 | 中 | W | 整合 | S | ★★ |

---

## 3. 優先順位の判断軸

候補 13 個を以下の 3 軸で序列化した。

### 軸 1: 「Warden が自分の責務を果たすために必要な観測」を最優先

ADR-0006 / ADR-0010 / ADR-0011 で Warden は「リソース管理」「Registry」「3 段階プロセスの実行（Judgment Pillar）」「Axiom enforce」を担う。これらの入力観測：

- リソース管理（Warden 自己認識） → **(c) リソース使用量** + **(f) 容量見込み**
- Axiom enforce（Judgment Pillar 入力） → **(g) Axiom 違反検知**
- 3 段階プロセスの監査（Conduit Pillar 連携） → **(a) Dispatch フロー** + **(d) 履歴グラフ**

つまり Warden が「自分の判断材料に使える観測 API」は (a)(c)(d)(g)。本ロードマップはここを骨格に置く。これらは全て **観測主体 = W（無制約）** に属する。

### 軸 2: 「Mind 公開分を Axiom 制約に従って切り出せるか」

ADR-0010 §4 で「Mind の観測は Axiom 制約下」と確定。Pillar として実装する以上、**同じ観測関数を Warden 用 / Mind 用に二段で公開**できる設計を採る：

- 内部 API（Warden 自己認識、無制約）: Python import で Judgment Pillar 等が直接呼ぶ
- 外部 API（Mind 用、Axiom 制約付き）: Conduit Pillar の MCP tool として公開、自分自身 / 自 Guild のみ見える制約

この二段構造が成立する候補から優先する。(a)(c)(d)(g) は二段化が自然。(b)(e) は M 用 API では「自分が関わる部分のみ」に絞る追加設計が要る。

### 軸 3: 「依存ゼロ」「API 重視」を維持

- ADR-0005 / ADR-0009 で「Python 標準ライブラリ + 既存 Nexus SDK のみ」と決定。Pillar 移行後も維持。**(h) Web UI** / 重い可視化ライブラリは延期
- 現状 `observe.py` は **CLI 表 + JSON** の二段構え。次は **API 重視**（JSON 拡張）— Judgment Pillar が Phase 5a-3 で消費するため。UI は表 + JSON で当面足りる。Web UI は ADR-0009 で別 ADR 保留

---

## 4. 推奨ロードマップ（4 段階、Warden 機能としての進化）

各段階は **1 PR 1 段階** を原則とする。各 PR が独立して merge 可能で、merge 後も既存 CLI が動く（後方互換）こと。
**v0.1 〜 v0.3 は `runtime/pillars/observation/` のまま実装、v1.0 で `runtime/pillars/observation/` に移動**（Phase 5a-2 と連動）。

### Observation Pillar v0.1: 履歴記録（スナップショット定期保存）

**Warden 観点の責務**: 時系列観測の基盤（変化観測能力）を獲得する。

**スコープ**:
1. `runtime/pillars/observation/snapshot.py` 新設。`observe.py` の `gather_observations()` を呼んで JSON 1 ファイルに保存
2. 保存先: `runtime/pillars/observation/snapshots/<UTC timestamp>.json`（Phase 5a-2 で `runtime/pillars/observation/snapshots/` に移動予定）
3. `observe.py --snapshot` フラグで「出力 + 保存」を 1 アクションに
4. 古いスナップショットを保持する TTL（例: 7 日）を設定可能に（パージは別コマンド `prune`、自動削除はしない）
5. テスト: `test_snapshot.py` で保存 / 読み戻し / ID 重複 / TTL prune の安全性

**1 PR 見積もり**: +200 行 + +100 行（test）+ README 追記。S（半日〜1 日）

**Axiom 整合チェック**: Mindspace 中身に触れない / 依存ゼロ / 痕跡は **Pillar の領域** → OK

**依存関係**: 完全独立。Phase 3 / Phase 5 のどちらも前提にしない。

**判断ポイント**: snapshots/ を **git に入れるか出すか**。推奨 = `.gitignore` で除外、観測痕跡はホストローカルで持つ（再現性より運用性）。

### Observation Pillar v0.2: Dispatch フロー可視化 + リソース使用量

**Warden 観点の責務**: Conduit Pillar 連携（フロー観測）と、リソース管理機能の入力データを揃える。

**スコープ**:
1. `runtime/pillars/observation/dispatch_flow.py` 新設。`runtime/pillars/conduit/storage/{inbox,archive}/<to>/*.md` を全件走査、frontmatter の `from`/`to`/`sent_at` だけ読む（本文は読まない）
2. 集計を `from → to (count, last_at, first_at)` のテーブルとして表 / JSON 出力
3. `observe.py --flow` フラグで dispatch サマリを追加表示
4. `runtime/pillars/observation/resource_usage.py` 新設。Mindspace と Nexus storage の総バイト数を計測（`os.scandir` 再帰、symlink フォロー禁止）
5. `observe.py --resource` で容量カラム追加
6. テスト: frontmatter パーサの ill-formed 耐性、再帰中の OSError ハンドリング

**1 PR 見積もり**: +400 行（実装）+ +200 行（test）+ README 追記。M（2〜3 日）

**Axiom 整合チェック**:
- frontmatter = Nexus storage の **共有領域**、Mindspace には立ち入らない → OK
- 「Mindspace のサイズ」は `stat().st_size` だけ集計（ファイル名も中身も見ない）→ 不可侵を維持
- 本機能は **Warden 内部用は無制約、Mind 公開時は自分が from / to に登場するレコードのみ** という二段公開を設計時点で意識する（実装は v1.0）

**依存関係**: v0.1 と独立。並列開発可。

**判断ポイント**: frontmatter フィールドは `runtime/pillars/conduit/storage.py` の実装に追従する必要がある。**Conduit Pillar 側のフォーマット契約を本 PR で文書化**（`runtime/pillars/conduit/dispatch-format.md` 新設）して凍結する。

### Observation Pillar v0.3: Axiom 違反検知 + 履歴比較

**Warden 観点の責務**: Judgment Pillar が消費する違反候補シグナルを生成する。Warden は Axiom に縛られない（ADR-0010 §5）ので無制約に判定できる。

**スコープ**:
1. `runtime/pillars/observation/anomaly.py` 新設。以下のシグナルを `warning` / `info` で列挙：
   - **W1**: Mindspace の mtime 更新と Conduit Pillar 呼び出し履歴（v0.2）が不整合（Nexus を介さない外部書き込みの疑い）
   - **W2**: Mindspace 配下に他 Mind 名のディレクトリ片（不可侵原則違反の物理的痕跡）
   - **W3**: `.mind-meta.md` の `kind` が Registry overlay (`$AI_ORG_OS_HOME/kinds/` + `templates/kinds/`、ADR-0020) のどちらにも存在しない（孤児 Mind）
   - **I1**: `stale` カテゴリへの遷移を v0.1 履歴と比較、新規発生分のみ通知
   - **I2**: inbox の蓄積（unread が一定閾値超）
2. `observe.py --anomaly` で warning / info を別セクションに出力
3. v0.1 の snapshot を 2 つ指定して diff を出す `observe.py --diff <a> <b>`
4. テスト: 各シグナルの true / false ケース、snapshot diff のキー整合
5. **Mind には公開しない**（Warden 内部 / 人間運用者向け）。Mind 通知は Judgment Pillar が個別判断で配信（v1.0 以降）

**1 PR 見積もり**: +500 行（実装）+ +300 行（test）。M（3〜4 日）

**Axiom 整合チェック**: W1〜W3 はファイル名・mtime・メタのみ → OK。Warden 無制約立場（ADR-0010 §5）で違反候補を洗い出し。

**依存関係**: v0.1（snapshot）+ v0.2（dispatch flow）に依存。**v0.2 → v0.3 の順を守る**。

**判断ポイント**: W1 は誤検知が出やすい（Mindspace 内で Mind 自身が書いた変更も mtime を更新）。**最初は warning ではなく info に降格して様子見**、運用ログを v0.1 で蓄積してから昇格。

### Observation Pillar v1.0: Pillar 統合（Warden 機能の正式構成要素へ）

**Warden 観点の責務**: 暫定実装から正式 Pillar への昇格。他 Pillar からの内部 API 呼び出しと、Mind 用 MCP tool（Axiom 制約付き）を両立する。

**スコープ**:
1. **物理移動**: `runtime/pillars/observation/` → `runtime/pillars/observation/`（ADR-0011 §3、Phase 5a-2 = Issue #37 と同期）
2. **編集不可機構の適用**: CODEOWNERS / pre-commit / CI チェック（ADR-0011 §4）
3. **Warden 内部 API**: 他 Pillar が `from runtime.pillars.observation import ...` で直接呼ぶ。同プロセス内 import を許可（ADR-0010 §6「Warden は機能集合体」と整合）
4. **Mind 向け MCP tool**: Conduit Pillar に Axiom 制約付き API を追加：
   - `observe_self()`: 呼び出し元 Mind 自身の status / unread / size のみ
   - `observe_my_guild()`: 自 Guild のロールアップ（Phase 5b で Guild 概念が入ってから）
   - `observe_my_dispatches(window)`: 自分が from / to に登場する dispatch のみ
5. **Realm Status Report**: 履歴・dispatch・容量・anomaly を一つの JSON に統合（`observe.py --for-warden`、schema versioned）
6. **Guild 識別子対応**（候補 j）: `.mind-meta.md` に Guild が追加されたら Guild 単位ロールアップを実装
7. **bash-editor 併用手順**（ADR-0009 §3 方式 E）を `runtime/verification/phase-3-dogfooding/README.md` に追記

**1 PR 見積もり**: +800 行 + +400 行（test）+ ADR-0009 改稿。L（1〜2 週間、Phase 5a-2 / 5a-3 並走）

**Axiom 整合チェック**:
- Warden 内部 API は無制約（ADR-0010 §5）
- Mind 向け MCP tool は Axiom 制約付き（呼び出し元 identity を見て返却データを絞る、ADR-0008 identity binding と連携）
- `realm/audit/dispatches/` は ADR-0006 で痕跡領域として定義済 → 観測対象として正当

**依存関係**: **ADR-0006 / ADR-0011 Accepted（済）+ Phase 5a-2 着手**。それまでは v0.3 で止める。

**判断ポイント**: Observation Pillar は **独立 Python パッケージ + 他 Pillar が import** とする。サブモジュール化（Judgment Pillar 内に含める）は不採用——Observation Pillar は Warden 以外（人間 CLI、CI nightly）からも使うため。

---

### 段階間の依存関係まとめ

```
v0.1 (snapshot)        ──┬─→ v0.3 (anomaly + diff) ──→ v1.0 (Pillar 統合)
v0.2 (flow + resource) ──┘                              ↑
                                                        |
                                Phase 5a-2 (Issue #37) と並走
                                ADR-0011 配置に従い runtime/pillars/observation/ へ
```

v0.1 / v0.2 は並列開発可能。v0.3 は両者を前提とする。v1.0 は Phase 5a-2 と並走する。

---

## 5. 既知の制限

### 5.1 Mind 公開時の Axiom 制約による情報の制限

ADR-0001 / ADR-0002 で Mindspace は不可侵と確定。Warden（および Observation Pillar の内部関数）は **無制約に観測してよい**（ADR-0010 §5）が、**Mind に公開する MCP tool では Axiom 制約を適用**する：

- **Warden 内部 API**: ファイルの **存在 / mtime / サイズ** 全てを観測してよい。Mindspace 中身は依然読まない（観測の本質的制約、Pillar の設計規約）
- **Mind 公開 API（v1.0 以降）**: 呼び出し元自身に関連する情報のみ返す。他 Mind の status は見せない

この二段制約により、以下は **構造的に観測不能**（Warden 含めて）：

- Mind が何を考えているか
- Mind が今どんなコードを書いているか
- Mind が外部 API を叩いたか（Nexus 経由でないアクセス）

これは制約であり、同時に **Axiom の保証**でもある。Observation Pillar はこの境界を越えない。

### 5.2 ファイルベースの即時性限界

mtime / ディレクトリ列挙ベースのため：

- **秒未満の解像度は無理**（OS により mtime 粒度が異なる）
- **inotify / fsevent を使わない**ので、polling 前提（典型 = 数十秒〜分単位）
- 大量の Mind（>100）が動くと再帰列挙が重い → v0.2 のリソース計測で頭打ちが見える

これは Mind が秒単位で動かない設計（Dispatch は非同期 / 確認ベース、ADR-0010 §1 の event-aware self-driven loop）と整合する。即時性が要れば push 通知（候補 i）か bash-editor 併用に倒す。

### 5.3 Mind が死んだ時の履歴保持方針（未決）

ADR-0006 で `destroy_mind`（Lifecycle Pillar の責務）が実装されると、Mindspace は削除される。このとき：

- **観測履歴（snapshot）はどうする**？
- **Nexus storage の archive はどうする**？

**選択肢**:

| 案 | 内容 | 評価 |
|---|---|---|
| (X1) Mindspace と同時消去 | 痕跡をすべて消す、プライバシ重視 | Axiom「共有はプロセスを踏む」(=痕跡が残る) と矛盾 |
| (X2) 観測履歴は残す、Mindspace 本体だけ消す | 「Mind は消えたが、世界が観測したログは残る」 | ADR-0002 §6「痕跡が残る」と整合、推奨 |
| (X3) すべて残す（Mindspace tarball として保存） | 完全再現可能 | Mindspace 不可侵と矛盾（消えた後でも他が読める） |

**仮の方針**: **(X2)**。Observation Pillar の snapshot は Mind の生死と独立に保持される。Mindspace は Lifecycle Pillar の destroy 経路で消えるが、観測痕跡は残る。ただしこの判断は **本ロードマップでは仮置き**、Lifecycle Pillar の destroy 仕様確定時に正式判断する。

### 5.4 観測者の観測者問題

Observation Pillar 自身が Mindspace / Nexus storage を走査することで mtime を更新する可能性。**読み取りなので mtime は更新されない**が、`os.stat` だけで済ます規約を README に書く。Pillar 自身の動作は別 Pillar（Judgment Pillar）が観測する想定（Phase 5a-3 以降）。

### 5.5 Pillar 編集不可機構との整合

ADR-0011 §4 で `runtime/pillars/` 配下は機械的に編集不可（CODEOWNERS / pre-commit / CI）。v1.0 移動後は **バグ修正・機能追加は許可ラベル付き PR でのみ**（ADR-0011 §5）。観測軸の追加（a〜m 以外）は本 ROADMAP に追記してから PR を起こす運用。

---

## 6. 関連

### 上位設計

- [ADR-0001: ai-org-os を「開発組織の不変項」を定義するフレームワークとして再定義する](../../../docs/adr/0001-ai-org-os-as-invariant-framework.md) — Axiom の出典
- [ADR-0002: 用語と「メタのメタ」構造の確定](../../../docs/adr/0002-vocabulary-and-meta-meta-structure.md) — Mindspace 不可侵 / 3 段階プロセス / 痕跡
- [ADR-0005: Phase 3 = Nexus（MCP サーバー）直行](../../../docs/adr/0005-phase-3-mcp-direct-with-nexus.md) — 依存ゼロ方針
- [ADR-0006: Phase 5（Realm + Warden + Guildmaster）の設計案](../../../docs/adr/0006-phase-5-realm-warden-guildmaster.md) — v1.0 統合先、Accepted（2026-05-23）
- [ADR-0009: bash-editor / claude-team との関係性と流用方針](../../../docs/adr/0009-relationship-with-bash-editor-and-claude-team.md) — fork しない / 流用方針
- [ADR-0010: 観測の哲学 / Warden は機能の集合体 / Mind の能動性](../../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md) — **本書の起点**、Warden = 機能集合体 / 観測の 2 種類
- [ADR-0011: Warden 内 Claude の命名と分離（Pillar 採用）](../../../docs/adr/0011-warden-claude-naming-and-separation.md) — Pillar 命名と配置、編集不可機構（PR #53）

### 同 Observation Pillar 内

- [`runtime/pillars/observation/README.md`](./README.md) — 設計根拠と現状の使い方
- [`runtime/pillars/observation/mind_status.py`](./mind_status.py) — 純粋関数群
- [`runtime/pillars/observation/observe.py`](./observe.py) — CLI 本体（暫定実装）
- [`runtime/pillars/observation/test_mind_status.py`](./test_mind_status.py) — unittest

### 観測データ源

- [`runtime/pillars/conduit/storage.py`](../conduit/storage.py) — Dispatch storage、v0.2 で frontmatter を読む対象。Phase 5a-2 で Conduit Pillar に統合
- `$AI_ORG_OS_HOME/minds/<name>/.mind-meta.md` — Mind メタ、v0.3 で kind 整合を取る (ADR-0018)
- `templates/kinds/*.md` + `$AI_ORG_OS_HOME/kinds/*.md` — Kind カタログ overlay (ADR-0020)、v0.3 W3 で照合

### 参考（流用しないが発想元）

- `local-multi-window-bash-editor` の `lib/pure.js` — `calcStatus` / `calcCategory` の出典（Python 移植済）
- `local-multi-window-bash-editor` の Web UI / WebSocket / xterm.js — **流用しない**。Observation Pillar が UI を必要とする段階に至ったら、bash-editor を **外部ツールとして併用**（ADR-0009 §3 方式 E）

---

## 7. 本ロードマップの位置づけ

> 本書は **設計のみ**。各バージョン（v0.1 / v0.2 / v0.3 / v1.0）の着手は、それぞれ **個別 Issue として切り出し、本書をリンクして詳細化する**。
>
> 本書の更新タイミング:
> - 各 v リリース後に「現状」セクションを更新
> - Phase 5a-2（Issue #37）の進捗に応じて v1.0 の移動詳細を確定
> - 候補（a〜m）に新しい観測軸が増えたら本書に追記
> - ADR-0010 / ADR-0011 の改訂が入ったら整合性を再確認
>
> 本書を **Accepted** に昇格させる条件:
> - v0.1 のスコープが詳細化されて 1 PR として merge 可能になったとき
> - またはプロダクトオーナーが「Pillar として進化させる順序と判断軸に同意」と明示したとき
