# ADR-0026: 構造化ログ（JSONL）の設計と配置

> 想定読者:
> - Conduit / Conductor / Judgment Pillar を拡張するメンテナ
> - observe.py に新しい表示モードを追加する人
> - 「dogfooding で何が起きたか後から追いたい」運用者
> - Phase 5f Step 1 (#122) を担当する人
> - ADR-0021 の A/B/C カテゴリで「ログ」をどこに置くか迷ったセッション

## Status

**Proposed** — 2026-06-01

## Context（背景）

2026-05-30 の Phase 5e Step D (PR #121) dogfooding で顕在化した観察手段の不足 (Issue #122):

- Codex code review が usage limit に達しがちで、Realm を自前で動作確認 → ログ追跡 → 判断する経路を強化したい
- 現状の観測手段は散発的で **時系列 join が手作業**:

| 既存源 | 性質 | 不足 |
|---|---|---|
| `$AI_ORG_OS_HOME/minds/<mind>/mind-loop.log` | Mind 別 stdout 系、行ベース | event 化されていない、Mind 横断の join 不能 |
| `conductor.sh` の stdout / journalctl | 起動時のみ | persistent な history が無い |
| `$AI_ORG_OS_HOME/realm/conductor-status.json` | **最新 cycle のみ** snapshot | 時系列が消える |
| `$AI_ORG_OS_HOME/conduit-storage/inbox/<mind>/*.md` | Dispatch 本体 (frontmatter+body) | ack されると archive へ移動、event としては parse 必要 |
| `$AI_ORG_OS_HOME/pillars/observation/snapshots/*.json` | Observation snapshot | 観測時点のみ、event 化されていない |

Phase 5e で実例として欲しかった view:

```
[01:42:13] warden→alice dispatch 'status check' (msg=...)
[01:57:10] alice mind-loop cycle 1 start
[01:58:03] alice→warden dispatch 're: status check' (msg=...)
[01:58:17] alice mind-loop cycle 1 end (exit=0)
[02:00:00] conductor cycle 5: warden_replies=1/1
```

これを後から再構築できる構造化ログ層が欲しい。Phase 5f「Mind に任せられる Realm」の **前提条件**: 任せる前に「何が起きたか追える状態」が必要 (#124 Step 1)。

### 関連する既決事項

- **ADR-0010 §5**: Warden は機能集合体、Judgment は呼び出し駆動。**新規 Pillar ではなく既存 Pillar の責務拡張**で済むか毎回問う
- **ADR-0013 §1 F3**: ログ書き込み失敗は cycle を止めない (= failsafe)
- **ADR-0014**: Realm 物理境界。host 側 observe.py は B カテゴリ（穴あき）として container の logs を読む
- **ADR-0017**: Warden 監視 (層 A) と Mind ジョブ監視 (層 B) の分離。ログも 2 層を混ぜない
- **ADR-0018**: `$AI_ORG_OS_HOME` = runtime state。logs もここ
- **ADR-0021**: A=axiom (機械強制) / B=Persona (宣言) / C=後天的依存注入 (manifest)。ログの各要素をこの軸で分類する

## Decision（決定）

### 1. 配置: `$AI_ORG_OS_HOME/logs/`（ADR-0018 準拠）

ログは runtime state。framework (repo) ではなく `$AI_ORG_OS_HOME/logs/` 配下に書く。git tracked にはしない。

```
$AI_ORG_OS_HOME/logs/
├── conductor.jsonl        cycle.* / judgment.* / warden_inbox.*
├── dispatch.jsonl         dispatch.sent / dispatch.acked (Conduit)
├── actuator.jsonl         actuator.kill / actuator.prompt / actuator.skipped
└── minds/
    └── <mind>/
        └── mind-loop.jsonl  mind-loop.sh の start/end/exit
```

### 2. ファイル分割の原則: Pillar 別

単一ファイル集約ではなく **書き手 Pillar 別** に分ける。理由:

| 軸 | 単一 file | Pillar 別 (採用) |
|---|---|---|
| 責務分離 | 全 Pillar が同じ file を append、責務が拡散 | Conduit は `dispatch.jsonl` だけ書く。書き手と内容が 1:1 |
| 書き込み競合 | 多 Pillar 多 Mind から同時 append、flush ロック必要 | 書き手単位で append のみ、ロック最小 |
| 時系列 join | 自然順 | 読み手 (observe.py) が merge sort |
| ローテーション単位 | 全体一律 | ファイル毎独立 |

複数ファイルの「時系列 join」は読み手が必ず必要になる作業なので、書き手側の単純化を優先する。

### 3. 共通 envelope schema

全 JSONL line は以下を必ず持つ:

```json
{
  "ts": "2026-06-01T01:42:13.123Z",   // UTC ISO-8601, millisecond precision
  "event": "dispatch.sent",            // 限定 enum、後述
  "actor": "warden",                   // 書き手 (Pillar 名 or Mind 名)
  ...                                  // event 別の追加 fields
}
```

- `ts` は UTC（Realm 内部時刻、host も UTC で読む）
- `event` は **enum**: 未知 event は読み手で skip。新規 event 追加時はこの ADR か後続 ADR で語彙拡張
- `actor` は「誰がこの行を書いたか」。Mind 名 / `warden` / Pillar 名 (`conduit`, `conductor`, `actuator`)
- `event` 別の追加 fields はその event の小節で定義

### 4. event 語彙（Phase 5f Step 1 着地点）

本 ADR で確定する初期語彙。実装は後続 PR で段階追加。

#### 4.1 dispatch.* (Conduit)

```json
{"ts":"...", "event":"dispatch.sent",  "actor":"conduit", "from":"warden", "to":"alice",  "topic":"status check", "msg_id":"..."}
{"ts":"...", "event":"dispatch.acked", "actor":"conduit", "by":"alice",  "msg_id":"..."}
```

書き手: `Nexus.send_dispatch` / `Nexus.ack_dispatch` の内部 hook。

#### 4.2 cycle.* / judgment.* (Conductor)

```json
{"ts":"...", "event":"cycle.start",      "actor":"conductor", "cycle":12}
{"ts":"...", "event":"judgment.invoked", "actor":"conductor", "cycle":12, "input_minds":3}
{"ts":"...", "event":"judgment.result",  "actor":"conductor", "cycle":12, "status":"ok", "dispatches_planned":1, "warden_replies_read":2}
{"ts":"...", "event":"cycle.end",        "actor":"conductor", "cycle":12, "duration_ms":2347, "judgment_status":"ok"}
```

`judgment.result.status` は `ok` / `fallback-no-key` / `fallback-parse-error` / `fallback-network` 等（既存の `conductor-status.json` の語彙を踏襲）。

#### 4.3 warden_inbox.* (Conductor, ADR-0025 経路)

```json
{"ts":"...", "event":"warden_inbox.read", "actor":"conductor", "cycle":12, "count":2, "msg_ids":["...","..."]}
{"ts":"...", "event":"warden_inbox.ack",  "actor":"conductor", "cycle":12, "msg_id":"..."}
```

#### 4.4 actuator.* (Actuator)

```json
{"ts":"...", "event":"actuator.prompt",  "actor":"actuator", "target":"alice", "topic":"...", "msg_id":"...", "result":"ok"}
{"ts":"...", "event":"actuator.kill",    "actor":"actuator", "target":"alice", "reason":"quota_exhausted"}
{"ts":"...", "event":"actuator.skipped", "actor":"actuator", "target":"alice", "reason":"not_in_registry"}
```

#### 4.5 mind_loop.* (mind-loop.sh)

```json
{"ts":"...", "event":"mind_loop.start", "actor":"alice", "cycle":1, "pid":12345}
{"ts":"...", "event":"mind_loop.end",   "actor":"alice", "cycle":1, "exit_code":0, "duration_s":42}
{"ts":"...", "event":"mind_loop.timeout", "actor":"alice", "cycle":N, "timeout_s":900, "signal":"SIGTERM", "streak":1}
{"ts":"...", "event":"mind_loop.error", "actor":"alice", "cycle":N, "exit_code":2, "streak":1}
{"ts":"...", "event":"mind_loop.cycle_slow", "actor":"alice", "cycle":N, "duration_s":420, "threshold_s":300}
{"ts":"...", "event":"mind_loop.cost", "mind":"alice", "cycle":N, "cost_usd":0.012, "duration_api_ms":2641, "num_turns":2, "tokens":{"input":100,"output":50,"cache_creation":1000,"cache_read":2000}, "models":{"claude-opus-4-7[1m]":0.011}, "session_id":"...", "is_error":false}
```

bash 側で append する（python に渡さなくていい単純 echo）。実装容易性のため。**例外**: `mind_loop.cost` のみ Python helper `_parse_cost.py` で emit する (= claude `--output-format json` の構造を bash で安全に parse できないため)。Helper は cost event を append し、`result` text を stdout 経由で mind-loop.sh 側に渡す。parse 失敗 (= JSON 不正 / timeout で truncate 等) は silent skip = cost event なし (= ADR-0013 §1 F3 準拠)。

### 5. 書き込み失敗は cycle を止めない（ADR-0013 F3 準拠）

ログ書き込み (`open(..., "a")` → write → close) が失敗した場合:

- stderr に WARN を出す（運用者が気付く経路）
- 例外を上位に上げない（cycle 続行）
- 該当行は失われる（at-most-once、対称的に observe.py 側でも欠落許容）

これはログを **観察補助情報** と定義する設計判断。ログが credentials store や billing record になる場合は別だが、ai-org-os のログは「後追い debugger」用なので失敗許容で良い。

### 6. ローテーション・TTL

**Phase 5f Step 1 初期**: ローテーションなし。append only。手動 prune (= 後続 PR で `observe.py --prune-logs`)。

**後続 PR / Phase 5f 後半**:
- size-based rotation: 10MB 超で `<name>.jsonl.1` に rename、5 file まで retain
- TTL: 30 日経過で `<name>.jsonl.N.gz` に圧縮、90 日で削除
- 閾値は manifest で上書き可（C カテゴリ、後述）

> **PR-F (Issue #135) 実装ノート**: 上記のうち **size-based rotation のみ** PR-F で実装済 (2026-06-01)。
> 閾値・retain は env var `AI_ORG_OS_LOG_MAX_BYTES` / `AI_ORG_OS_LOG_RETAIN` で
> C カテゴリ (manifest / config.env 等) から上書き可。
> **gz 圧縮 / TTL / `observe.py --prune-logs` は後続 PR** で別途実装。

### 7. observe.py への `--trace` mode

実装は後続 PR。要件のみ本 ADR で確定:

- 入力: `$AI_ORG_OS_HOME/logs/` 配下の全 JSONL
- `--since 1h` / `--since 2026-06-01T00:00` で時間範囲指定
- 全 file を merge sort（ts キー）して時系列表示
- 1 event = 1 行の人間可読フォーマット
- 壊れた JSONL 行は skip + stderr WARN
- 物理境界カテゴリは **B（穴あき）**: host から container の `$AI_ORG_OS_HOME/logs/` を読む

### 8. ADR-0021 観点（A/B/C 分類）

| 要素 | カテゴリ | 根拠 |
|---|---|---|
| 「ログを書く」という行為 | **A (axiom)** | Conduit / Conductor / Actuator が機械強制で書く。Persona に「ログを書け」とは書かない |
| event 名 (enum) | **A** | 限定された語彙、未知 event は読み手で skip |
| envelope schema (ts/event/actor) | **A** | 全 line がこの形を満たす、違反は読み手で skip |
| 配置 path (`$AI_ORG_OS_HOME/logs/`) | A (ADR-0018 で既決) | 個別 ADR で再宣言不要 |
| F3 準拠（失敗時 cycle 続行） | **A** | 機械側の振る舞い、設定不可 |
| TTL / rotation 閾値 | **C (manifest)** | 利用者が運用負荷で調整可、guild manifest または `config.env` で上書き |
| event 種別の enable/disable | **C** | 将来 `logs/<event-class>.enabled` 等、運用調整 |
| B (宣言的指示) | **無し** | Persona に「ログを書け」「この event を log しろ」とは書かない。機械側で完結 |

「B が無い」のは意図的。ログ書き込みは Mind の自由意思に委ねる対象ではない（= 信頼境界を Mind に置かない、機械で固める）。

## Consequences（影響）

### 良い点

- Phase 5f Step 2 以降の dogfooding で「後から流れを再構築」できる
- Codex review が止まっても自前で観察 → 判断 → 修正の loop が回る
- Pillar 責務が明確（書き手 1:1 file）
- F3 準拠で「ログのせいで Realm が止まる」が起きない

### 制約 / 代償

- Pillar 別ファイル分割により、読み手 (observe.py --trace) は merge sort が必須
- at-most-once 配送のため、診断時に「ログにない = 起きていない」と断言できない（書き込み失敗の可能性）
- TTL / 圧縮を後続 PR に回したため、長期 dogfooding で disk が肥大する可能性は残る（観察対象、size-based rotation は PR-F / Issue #135 で実装済、TTL は別 PR）

### 後続 PR の段取り（実装段階）

1. **PR-A**: `dispatch.jsonl` 実装（Conduit に hook）+ envelope util
2. **PR-B**: `conductor.jsonl` 実装（cycle.* / judgment.* / warden_inbox.*）
3. **PR-C**: `actuator.jsonl` 実装
4. **PR-D**: `mind-loop.sh` の JSONL 化
5. **PR-E**: `observe.py --trace` 実装
6. **PR-F**: rotation / TTL / `--prune-logs`（Phase 後半）
   - **実装済 (Issue #135, 2026-06-01)**: size-based rotation のみ。
     env var `AI_ORG_OS_LOG_MAX_BYTES` (default 10MB) / `AI_ORG_OS_LOG_RETAIN` (default 5) で C 上書き可。
     rotation 失敗時も F3 準拠で append は続行する。
   - **未実装 (後続 PR)**: gz 圧縮、TTL ベースの削除、`observe.py --prune-logs`。

各 PR は独立してマージ可能。PR-A が最小 vertical slice（書く側 1 つ + envelope util）。

## Alternatives（検討した代替案）

### A1: 単一 JSONL に全 event 集約

`$AI_ORG_OS_HOME/logs/realm.jsonl` 1 本で全 Pillar / 全 Mind が append。

- 利点: 時系列 join 不要
- 欠点: 書き込み競合（flush ロック）、Pillar 責務が拡散、rotation 単位が一律

→ Pillar 別の方が責務分離が明確で採用見送り。

### A2: 既存 `conductor-status.json` の JSONL 化

snapshot ファイルを append-only JSONL に変更し、cycle 毎に 1 行追加。

- 利点: 新規 file 不要
- 欠点: snapshot（最新状態のみ）と event log（時系列累積）は責務が違う。混ぜると最新参照側のコードが iter 必要になる

→ snapshot は snapshot として残す。event log は別。

### A3: 外部 logger（journalctl / rsyslog / OpenTelemetry）

host の syslog / OTel collector に流す。

- 利点: 既存運用ツール群と統合
- 欠点: ADR-0014 物理境界（container 内側）を破る依存。stdlib のみ縛り（ADR-0009 周辺の Pillar 実装方針）と整合しない。Phase 5f 段階では over-engineering

→ 採用見送り。将来 host 側 collector が欲しくなったら別 ADR で。

### A4: structlog / loguru 等の 3rd party

- 欠点: ADR-0009 / Pillar 実装方針で「stdlib のみ」を維持してきた。依存追加は最小限に
- 本 ADR の envelope schema は単純な dict + json.dumps で書けるので 3rd party 不要

→ 採用見送り。

## 関連 ADR / Issue

- 直接派生元: Issue #122 (Phase 5e fu)、Issue #124 (Phase 5f tracking) Step 1
- 前提: ADR-0010 / 0013 / 0014 / 0017 / 0018 / 0021 / 0024 / 0025
- 派生予定: ADR-0027（Phase 5f Step 4 失敗扱い）でログ event 分類が再登場する可能性

## メモ

- 本 ADR は **設計合意の入口**。実装は後続 PR で段階的に。
- 本 ADR を merge した直後、PR-A (dispatch.jsonl + envelope util) から着手する。
- 「event 語彙の追加」が後続 PR で頻発する見込み。enum 拡張は本 ADR §4 を更新する形で許容（軽い変更は新 ADR まで起こさない）。
