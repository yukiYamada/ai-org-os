# ADR-0028: 失敗扱いの operational mapping (ADR-0013 を A/B/C で再整理 + dogfooding 観察を組み込む)

> 想定読者:
> - Phase 5f Step 4 を担当する人
> - Mind の失敗時の「具体的に何を実装するか」を決める人
> - mind-loop.sh / conductor.py に timeout / quota 系の guard を追加する人
> - dogfooding で観察した既知の failure mode を knowledge として参照したい人
> - Phase 5g 以降の sandbox / quota 強化を担当する人

## Status

**Proposed** — 2026-06-04

## Context（背景）

ADR-0013 (2026-05-23) で **失敗の分類 (F1-F4) / 検出レイヤー (1-5) / 対処グラデーション (Hard block / Quarantine / Kill / Destroy) / 復旧方針** という概念フレームは確定した。
しかし **具体的に「Mind を何秒で kill するか」「API quota 0 で何が起きるか」「人間にどう通知するか」** の operational rule は ADR-0013 にはなく、Phase 5e-5f で **ad-hoc に積み上げ** られてきた:

- #136 (PR #142): dispatch 到着 sentinel — F1 系 (chain latency)
- #144 (PR #145/146/147): cycle body 短縮の case A/C
- #151 (PR #152): bob worktree 不使用 — F1 系 (Mind ジョブ判断ミス)
- #134: cycle outlier (gm 640s / carol 655s) — 未解決、F1 と F3 の境界
- run 6 API 529 Overloaded: F3 系 (外部 API 異常)、未明示対処
- run 7 carol review 間に合わず: chain timing、F1 か F3 か?

これらは個別 PR で対症療法されたが、「**どの category で**「**どの enforcement layer で (ADR-0021 A/B/C)**」**対応されたか**」が整理されていない。新規 dogfooding (Step 5+) で similar failure に遭遇したとき、既存 fix の知識を効率的に引けない。

加えて #124 Step 4 (Issue #47 由来) で明示されたゴール:
- **A: code 強制** (= API quota 0 で Mind 自動 kill)
- **B: 宣言的指示** (= 「無限ループは数えて break しろ」を Persona に)
- **C: 人間 escalation** (= notify-human action の rule 化)

これらを **ADR-0021 A/B/C framework と整合させて確定** する。本 ADR は ADR-0013 の **operational 補強** で、ADR-0013 を置き換えない。

### 関連する既決事項

- **ADR-0010 §3**: Mind に idle なし、Realm 停止で死を受容
- **ADR-0012 §2 責務 5**: 失敗時の手動介入は人間の責務
- **ADR-0013**: 失敗カテゴリ F1-F4、検出レイヤー 1-5、対処グラデーション
- **ADR-0021**: A (axiom 機械強制) / B (Persona 宣言) / C (manifest 後天的注入)
- **ADR-0027**: 信頼境界 axiom (Mind ⇔ 人間)
- **ADR-0024 / 0025**: Warden inbox feedback loop

## Decision（決定）

### 1. 失敗扱いを A/B/C で再整理（= ADR-0013 categories と直交する operational layer）

ADR-0013 の F1-F4 が「**何が起きたか**」の分類なら、本 ADR は「**どの enforcement layer で対処されるか**」の分類。両者は直交する 2 軸。

| layer (ADR-0021) | 性質 | 例 | 既存実装 | 未実装 |
|---|---|---|---|---|
| **A axiom (機械強制)** | code が拒否 / 自動実行 | per-cycle timeout、API quota 0 で kill、Conduit identity binding、worktree axiom | identity binding (ADR-0008)、kill-mind orphan kill (#141)、event_log rotation (#139) | **per-cycle timeout** (新規)、**API quota 0 auto-kill** (新規) |
| **B Persona (宣言)** | Persona に書かれた行動ガイド、機械強制なし | bursting 禁止、cycle budget、信頼境界、cd work/ | implementer/reviewer/designer/guildmaster Persona の各 section (#146, #147, #149, #152) | 「無限 dispatch 防止」明文化 (= ADR-0028 で encode 推奨) |
| **C config (manifest)** | 利用者が overlay で書き換え可、操作的に調整 | rotation 閾値、cycle period、max-cycles、notify-human channel | AI_ORG_OS_LOG_MAX_BYTES、AI_ORG_OS_LOOP_PERIOD、AI_ORG_OS_LOOP_MAX_CYCLES | **notify-human channel** (新規)、**timeout 閾値** (新規) |

### 2. 本 ADR で新規に確定する operational rule (= 未実装 → 後続 PR で実装)

#### 2.1 per-cycle timeout (A axiom)

**Issue #134** (gm-default cycle 2 が 640s) の本質: claude が長時間 hang した時に救う手段が無い。

**Decision**: mind-loop.sh が `claude -p` 呼び出しを **timeout でラップ** する:

- env: `AI_ORG_OS_MIND_LOOP_CYCLE_TIMEOUT` (default **`900` 秒** = 15 分、C category で上書き可。当初 300s だったが #160 / Step 4.6 で PR-mode の bob cycle 平均 300-700s + 最大 956s (run 7 で PR #154 作成) を catch しないよう拡張。真の hang = 20 分超 は依然 catch)
- 超過時: claude プロセスを SIGTERM → 10 秒猶予 → SIGKILL
- mind-loop は **cycle 失敗を記録**して次 cycle に進む (= F1 として記録、Realm 停止には繋げない、F3 fail-safe 整合)
- 連続失敗 N 回 (= `AI_ORG_OS_MIND_LOOP_TIMEOUT_STREAK`、default 3) で **Mind を自動 kill** (= ADR-0013 Kill 段階の自動化、Quarantine ではない理由は §5)

実装 hook: `runtime/pillars/lifecycle/mind-loop.sh` の `(cd "${MIND_DIR}"; "${CLAUDE_BIN}" -p ...)` を `timeout` GNU util でラップ。timeout コマンドが無い OS (macOS BSD) 用に `perl -e 'alarm; exec'` の portable shim を用意。

#### 2.2 API quota 0 / 外部 API 異常 (A axiom + C config)

**Run 6 cycle 4 で観察**した API 529 Overloaded は cycle exit=1 で記録されたが、Mind 視点では「失敗」と認識されないまま次 cycle に進んだ。

**Decision**:
- mind-loop が claude exit code を観察:
  - 0: 正常
  - 1: 通常 error (= claude が自分の error として認識した、本 ADR の対象外)
  - **2 以上 / 死亡 signal**: API 異常 / hang として記録 → cycle 失敗を JSONL event `mind_loop.error` で emit
- 連続失敗 M 回 (= `AI_ORG_OS_MIND_LOOP_ERROR_STREAK`、default 5) で **notify-human** (§2.3) を発火
- API quota 0 (= claude code login が無効化) の判定は **exit code + stderr "quota" 文字列** の組み合わせ (heuristic、最終的には Mind が動かないことで明白になる)
- Conductor 経路 (= Anthropic SDK 直接) の API quota は **すでに ADR-0013 F3 fallback** で対処済 (judgment status=fallback-no-key)。本 §は **mind-loop 側** の話

#### 2.3 notify-human channel (C config)

ADR-0013 §5 で「failsafe の起動条件」は明確化されたが、**通知メカニズム自体は未定義**。Phase 5b 待ちと書かれて Phase 5f 末まで未実装だった。

**Decision**: 多重出力 channel を確定:

- **L1 (必須)**: `$AI_ORG_OS_HOME/logs/notify.jsonl` に append (= structured log、observe.py で観察可)
- **L2 (推奨)**: stderr に 1 行 WARN (= operator が log を `tail -f` していたら気付く)
- **L3 (オプション、C config)**: 利用者が設定したコマンド (env `AI_ORG_OS_NOTIFY_CMD`) を fork (= Slack webhook / email / GitHub issue 起票 等、利用者次第)

L1 + L2 は機械強制 (A)、L3 は利用者選択 (C)。本 ADR では L1/L2 のみを Phase 5f Step 4 で実装、L3 は Phase 5g 候補。

#### 2.4 slow-cycle diagnostic telemetry (Phase 5g prep / #134)

§2.1 の per-cycle timeout は **真の hang** を catch するが、その手前 — 「timeout には到らないが明らかに遅い cycle (例: 300-800s)」— は素通りする。#134 で観察された "gm cycle 2 = 640s / carol cycle 3 = 655s" のような **outlier** は CYCLE_TIMEOUT=900s では timeout event を発火させず、観察者が `mind_loop.end` の `duration_s` を眼で grep するしかなかった。

**Decision**: `mind_loop.cycle_slow` event を追加し、cycle が正常終了 (RC=0) かつ duration >= threshold の時のみ emit する。

- env: `AI_ORG_OS_MIND_LOOP_SLOW_THRESHOLD_S` (default **300** 秒、C category で上書き可)
- 経路: `mind_loop.end` の直後、`RC == 0 && duration_s >= threshold` で 1 行 emit
- timeout / error 経路では emit しない (= 既に `mind_loop.timeout` / `mind_loop.error` で flag されているため二重 emit を避ける)
- auto-kill / notify-human は起こさない — **純粋に観察用 telemetry**

これは fix ではなく **Phase 5g の root cause 調査用 instrumentation**。次回 dogfooding で outlier が起きた時に `observe.py --trace --event mind_loop.cycle_slow` で時系列を抽出できる。

threshold default 300s の根拠: Step 2 通常 cycle 50-200s の 2-3 倍、CYCLE_TIMEOUT 900s の 1/3 (= まだ余裕がある領域)。Step 3 PR-mode (legit cycle 300-1000s) では env で 600 等に引き上げる想定。

### 3. dogfooding 観察した既知 failure と対処マッピング

「次回 dogfooding で似た失敗が起きた時、どこを見るか」の参照表:

| 観察 | ADR-0013 category | ADR-0021 layer | 対処 PR / 提案 | Status |
|---|---|---|---|---|
| #134: cycle 2 が 640s / 655s (gm / carol) | F1 (振る舞い系、観察量爆発) | A 追加 | per-cycle timeout (§2.1) + cycle_slow telemetry (§2.4) | ✅ §2.1 Merged (PR #156), ✅ §2.4 Merged (本 PR、Phase 5g 用 diagnostic)、root cause 調査は Phase 5g |
| #136: dispatch 到着 race | F1 (latency) | A 追加 | sentinel nudge (#142) | ✅ Merged |
| #144 case A: cycle body 短縮 | F1 (cycle 推論時間爆発) | A 追加 | inbox peek (#145) | ✅ Merged |
| #144 case C: bursting | F1 (過度な dispatch) | B encode | Persona cycle budget (#146) | ✅ Merged |
| #147: gm 初動 dispatch 遅延 | F1 (chain 起動遅延) | B encode | guildmaster 例外節 | ✅ Merged |
| #151: bob Mindspace 直下に code | F1 (worktree 不使用) | B encode | Persona "cd work/" 強化 (#152) | ✅ Merged |
| #137: --trace cp932 化け | F3 (host 観察出力異常) | A 追加 | stdout reconfigure (#140) | ✅ Merged |
| Run 6 API 529 Overloaded | F3 (外部 API 異常) | A 追加 | mind_loop.error event + streak (§2.2) | **未実装、本 ADR で枠を確定** |
| Run 7 carol review missed | F1 (chain timing) | C 調整 | max-cycles 増 or carol prioritize (= cycle budget の review-only モード) | **未実装、Step 5+ で検討** |
| Run 7 bob retire question | F1 (Mind role-check) | B encode | guildmaster の dispatch-prompt (= retire 判断) を encode | **未実装、ADR-0028 follow-up 候補** |

### 4. ADR-0013 との関係: 補強であって置き換えではない

ADR-0013 が「Phase 5a 設計時の概念フレーム」だったのに対し、本 ADR は「Phase 5f 末で Operational に降りてきた具体」。両者は **両方有効**:

- ADR-0013 §1-§6 は **概念分類の正規** として残す
- 本 ADR §1-§3 は **Phase 5f 以降の operational reference** として参照される
- ADR-0013 の category F1-F4 の名前 / 内容に変更は無い

### 5. ADR-0013 §3 「Quarantine」を採用しない理由 (= operational 判断)

ADR-0013 §3 の対処グラデーションには **Quarantine** (= Mindspace を read-only、Dispatch 遮断) があるが、Phase 5f 時点で **Mind を Quarantine する code path を実装しなかった**。理由:

1. Mind の Mindspace 不可侵 axiom は file system レベルで強制されていない (Mind 自身が自 Mindspace を編集する権利あり)。Quarantine = "read-only に flip" は OS chmod / 権限変更を伴うが、Realm の Container / Host 境界 (ADR-0014/0016) と相性が悪い (= Mind の python は file 書き込み権利を前提に動作する)
2. Dispatch 遮断は Nexus 側で実装可だが、「Quarantine された Mind は何のために生かしておくのか」が unclear (= 観察したいなら Mindspace を別場所にコピーして kill する方が forensic 用途に明快、= preserve-notes (#143) と同じ哲学)
3. Step 2-3 dogfooding 5 run で観察された全失敗 mode は **Kill (#141 で worktree 込み確実 kill) で対処可能** だった

**Quarantine を選択肢から除外する** (= Decision)。対処グラデーションは Hard block / Kill / Destroy の 3 段階に簡素化。

## Consequences（影響）

### 良い点

- Phase 5f で ad-hoc に積み上げた fix が **「どの layer に効いてる fix か」 一覧化**された (§3 table)
- 未実装の枠 (per-cycle timeout / API error streak / notify-human channel) が **本 ADR で明確** になり、後続 PR の scope が定義済
- ADR-0021 A/B/C 軸で再整理することで、「Persona に書くべきか / code で強制するか / config で調整可にするか」の判断指針が一貫
- Quarantine 不採用を明示することで、判断幅の収束

### 制約 / 代償

- per-cycle timeout (§2.1) を実装すると、claude が長考でも 5 分以上は強制 break する → 大物推論は許容できなくなる。閾値を運用で調整する余地 (C category) は残す
- API quota 0 検出 (§2.2) は heuristic (= exit code + stderr 文字列)。完全自動判定は claude code CLI の telemetry がない限り不可能
- notify-human L1 + L2 のみ実装 (L3 は Phase 5g 送り) なので「実際に通知が運用者の目に届く」までは operator が log を見にいく必要あり
- ADR-0013 と本 ADR の 2 つ並存で「次に何を読めばいいか」がやや増える → §4 で両者の関係を明示してナビゲーション

### 後続 PR の段取り (Step 4 chunk)

1. **Step 4.1**: 本 ADR 起草 ← 本 PR
2. **Step 4.2**: per-cycle timeout 実装 (§2.1 / A axiom) — mind-loop.sh + test
3. **Step 4.3**: mind_loop.error event + streak (§2.2 / A axiom) — mind-loop.sh + event_log
4. **Step 4.4**: notify-human L1+L2 (§2.3) — 新規 module、event 書き込み + stderr WARN
5. **Step 4.5** (オプション): Persona に「無限 dispatch 防止」明文化 — guildmaster / implementer Persona
6. **Step 4.6**: dogfooding 8th run で §2.1-2.3 の挙動検証

## Alternatives（検討した代替案）

### A1: 完全 sandboxing (= Linux namespace / cgroup で resource cap)

メリット: claude の hang / runaway を OS レベルで止められる、Phase 5g の sandbox hook (#71 / ADR-0027 L2 候補) の派生案

不採用 (Phase 5f では): 
- 本 ADR と直交する話 (= sandbox は層を増やす、本 ADR は既存層の operational mapping)
- Phase 5f のスコープを超える、Phase 5g で別 ADR

### A2: claude code SDK の telemetry / debug log を活用

メリット: API 呼び出し時間 / token 数を per-cycle で取れる → §2.1 timeout 判定が精密化

不採用 (本 ADR では):
- claude code CLI の public API として exposed か未確認
- 仮にあっても外部依存 (= Anthropic 側仕様変更で動かなくなる)
- §2.1 の wall-clock timeout は cruder だが robust

### A3: notify-human を最初から L3 (operator command fork) で実装

メリット: 実通知が即時 (Slack 等)

不採用 (本 ADR では):
- L3 は利用者ごとに channel が違う (Slack / email / Teams / ...) ので generic 実装が難しい
- L1 (jsonl log) は universal、まず L1+L2 で運用、operator が必要なら L3 を別途実装する pattern が現実的

## 関連 ADR / Issue

- 派生元: #124 Phase 5f Step 4、Issue #47 (Discussion F)
- 前提: ADR-0010, 0012, 0013, 0021, 0027
- 派生予定: Phase 5g で sandbox / cgroup 系の別 ADR (ADR-0029 候補)
- 観察源: dogfooding run 1-7 (2026-06-01 〜 2026-06-03)、preserve-notes snapshot 群

## メモ

- 本 ADR は **設計合意の入口**。後続 PR (Step 4.2-4.6) で実体化する。
- §3 の table は **生きた reference**。次回以降 dogfooding で新 failure mode が見つかったら更新するか、follow-up ADR で追記する。
- ADR-0028 番号は ADR-0027 の次。「失敗扱い」を別 ADR としたのは、信頼境界 (= 何が禁止か) と失敗扱い (= 失敗時にどう振舞うか) は **別概念** だから (= 前者は予防、後者は事後)。
