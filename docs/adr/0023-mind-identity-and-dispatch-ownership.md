# ADR-0023: Mind identity の単一性と dispatch 履歴の所有関係

> 想定読者:
> - `kill-mind` / `spawn-mind` の挙動を理解 / 拡張するメンテナ
> - 同名 Mind の再 spawn を運用する人 (= dogfooding を繰り返す)
> - 「kill した Mind の dispatch 履歴ってどうなるんだっけ?」と迷ったセッション
> - 将来 Mind の永続化 / 復元を提案する人

## Status

**Accepted** — 2026-05-28

## Context（背景）

2026-05-28 の Phase 5d-6 dogfooding (本物の GitHub repo を target にした end-to-end 検証) で、運用上の混乱が発覚した:

> 前回 dogfooding で worker-1 が gm-default に dispatch を 1 件送った後、worker-1 / gm-default を kill。新規 dogfooding で gm-default を再 spawn したところ、`conduit-storage/inbox/gm-default/` に **古い dispatch が残っていて**、`observe.py --realm` が「INBOX/ARCHIVE: 1/0」と表示 → 「何の未読 dispatch?」と混乱。

これは **Issue #104** として起票され、5 つの解決案が議論された:

| 案 | 内容 |
|---|---|
| A | 完全保持 (現状) |
| B | kill 時に削除 |
| C | archive に移動 |
| D | 名前空間 (session ID) で分離 |
| E | TTL 経過後 prune |

この混乱の根本は **「kill された Mind の dispatch 履歴は誰のもの?」** という Mind identity の問題:

- 現状の挙動 (A): 「dispatch 履歴は Realm の所有」と解釈される → kill → 再 spawn の Mind が引き継ぐ → 「同名再 spawn は前 Mind の continuation」と捉えられる
- 一方で ADR-0001 / ADR-0014 では「Mind = 思考個体、kill で破棄、Mindspace も消える」が大前提

つまり **Mind identity の semantics が一貫していない**。Mindspace は Mind と運命を共にするのに、dispatch 履歴は Realm に残る — 矛盾した二重所有。

これを設計レベルで決着する必要がある。本 ADR は **その判断を Mind 側に倒す**: dispatch 履歴は Mind と運命を共にする。同名再 spawn は別 Mind。

## Decision（決定）

### 1. Mind identity は spawn-kill 間で唯一

**「Mind」の identity は spawn から kill までの 1 つの期間に限定**される。同じ `<mind_name>` で再 spawn された Mind は、**前 Mind とは別の Mind** として扱う。

- 物理的観点:
  - Mindspace (`$AI_ORG_OS_HOME/minds/<name>/`) は spawn 時に新規作成、kill 時に削除 — 連続性なし
  - registry (`$AI_ORG_OS_HOME/registry/minds/<name>.md`) も同上 — kill で消えて再 spawn で新規
  - identity binding (ADR-0008) は session 単位、kill で完全に切れる
- 概念的観点:
  - Mind = 思考個体 (ADR-0001)
  - 思考が消えれば、その個体は消えた = identity は復元できない (ADR-0014 「破棄後の復元は仕組みとして提供しない」)

これを ADR-0023 の根本原則として確定する。再 spawn で「以前の続き」を実装することは v1 では **やらない** (将来必要なら別 ADR)。

### 2. dispatch 履歴は Mind と運命を共にする

`conduit-storage/inbox/<mind_name>/` と `conduit-storage/archive/<mind_name>/` は **その Mind の所有物**であり、kill 時に Mindspace と一緒に削除される。

| 物理 path | 所有 | kill 時の挙動 |
|---|---|---|
| `$AI_ORG_OS_HOME/minds/<name>/` | Mind | rm (既存) |
| `$AI_ORG_OS_HOME/registry/minds/<name>.md` | Mind (Pillar 管理だが Mind 専属メタ) | rm (既存、Phase 5c-2 #91) |
| `$AI_ORG_OS_HOME/minds/<name>/work/` (worktree mode) | Mind | git worktree remove + 親 rm (既存、Phase 5d-3 #101) |
| **`$AI_ORG_OS_HOME/conduit-storage/inbox/<name>/`** | **Mind** | **rm (本 ADR で追加)** |
| **`$AI_ORG_OS_HOME/conduit-storage/archive/<name>/`** | **Mind** | **rm (本 ADR で追加)** |

target repo (`workspace.repo`) は **Mind の所有物ではない** (= 外部依存、ADR-0014 のカテゴリ C)。target repo に push された branch (例: `mind/<name>`) は kill 後も remote / target repo に残る。これは「Mind が世界に与えた痕跡」であり、Mind 自身ではないので保持される (= 組織の成果物)。

### 3. kill 時の削除順序

ADR-0023 確定後の kill-mind 削除順:

```
1. mind-loop.sh の停止 (PID 確認 + SIGTERM)        ← 既存
2. registry エントリ削除 (authoritative invalidation) ← 既存 (#91)
3. git worktree remove (worktree モード時)         ← 既存 (#101)
4. conduit-storage/inbox/<mind>/ の削除            ← 本 ADR で追加
5. conduit-storage/archive/<mind>/ の削除          ← 本 ADR で追加
6. Mindspace (`$AI_ORG_OS_HOME/minds/<name>/`) の rm ← 既存
```

**registry-first invariant** (Codex P2 #91) は維持: registry 削除を最初に行うことで、kill が中断されても axiom 上は「無いものとして扱う」が成立する。

conduit-storage の削除は **registry 削除の後** に行う (= 4-5 は 2 の後)。順序の意図:

- registry 削除前に dispatch を消すと、まだ axiom 上「生きている」Mind に「inbox 空」を観測させる過渡期が生じる
- registry 削除後なら axiom 上「死んでいる」ので、dispatch が残っていても消えていても「forbidden」で reject される → 観測上の差は無い

### 4. 観測 (Observation) への影響

Observation Pillar v0.2 (#66) の `dispatch_flow.py` は `conduit-storage/{inbox,archive}/*/*.md` を全件走査する。本 ADR で kill 時に dispatch ディレクトリが消えるので:

- 「kill された Mind の過去 dispatch 履歴」は **observation からも消える**
- これは「Mind の死とは観測上の完全な消失」(ADR-0014 系) と整合
- 反論: 「監査ログ的に dispatch 履歴は残したい」 → 別途 archive ログ機構を Observation Pillar で実装すべき (本 ADR スコープ外)

将来 Observation v1.0 / Judgment Pillar が「組織として何が起きたか」を残したい場合は、kill 前に snapshot を取る別経路を追加する (本 ADR は dispatch の **生きた状態**を Mind に紐付けるのみ)。

### 5. 既存 ADR との関係

- **ADR-0001 / ADR-0014**: Mind = 思考個体、kill = 破棄 = 復元不能。本 ADR はこの精神を dispatch 履歴にも拡張する
- **ADR-0008** (identity binding): Mind の identity は spawn 時に bind される。本 ADR は「bind は spawn-kill 間に限定」を明文化する補強
- **ADR-0010 §5** (Warden の無制約観測): Warden は dispatch を frontmatter ベースで観測する。kill で dispatch が消えれば観測対象も消える (= 自主規制と一致、観察対象の確定範囲)
- **ADR-0019** (Guild = 組織枠): Mind が同名再 spawn される場合、Guild が同じなら organizational continuity はあるが、Mind individual の continuity は無い。Guild が Mind を「再雇用」する形
- **ADR-0021** (axiom vs DI): 本決定は **axiom (機械強制)** に該当: 「kill = dispatch も消す」を kill-mind.sh で物理強制

## Consequences（影響）

### 利点

1. **Mind identity が一貫**: Mindspace と dispatch 履歴が同じ life cycle を持つ。「Mind が消えれば全部消える」を実装で物理保証
2. **dogfooding の混乱が消える**: 再 spawn 時に古い dispatch が紛れ込まない、観測が clean
3. **設計の単純化**: 「kill は何をどこまで消すか」が明確、エッジケースが減る
4. **組織の成果物は残る**: target repo の `mind/<name>` branch / PR / commit は外部依存 (= Mind の所有物ではない) なので保持される。「Mind 死、成果物は残る」 (= 開発組織として正しい)
5. **将来の Mind 永続化への余地**: 本 ADR は「v1 では再 spawn = 別 Mind」と明示。将来 「Mind の魂を引き継ぐ」機構が欲しくなったら別 ADR で追加 (例: `--resume <previous-snapshot>` のような import 経路)

### 不利益 / リスク

1. **過去 dispatch を後で確認できない**: kill 後は dispatch 履歴が消えるので「以前何があったか」を遡れない。対処: Observation Pillar の snapshot 機構 (v0.1) を kill 前に手動で取る、または将来「pre-kill audit log」を別途実装
2. **意図しない再 spawn で履歴が消える**: 利用者が同名で kill → re-spawn を繰り返すと履歴が累積しない。これは v1 では仕様 (= 別 Mind と扱う前提)。混乱しないようにドキュメントで明示
3. **dispatch 配送中の race**: kill 中に他 Mind が `send_dispatch` を呼ぶと、新規 dispatch が書かれた直後に kill-mind が削除する race window が存在。実害: 配送 lose。確率は低いが ADR-0007 (Phase 3 reliability) で「現状妥協」と確定済の範囲内
4. **「ログ全消し vs 一部残す」の議論再燃の可能性**: 将来「監査のため残したい」要求が来た時、本 ADR は B (削除) を選んだ。再 discussion が必要なら C (archive 移動) や E (TTL prune) を本 ADR を上書きする ADR-0024+ で実装する

### 派生する Issue / 後続作業

- **Phase 5d-? (本 PR)**: kill-mind.sh に conduit-storage 削除ロジック追加 + 回帰テスト
- **Issue #104**: 本 ADR で close。実装は本 PR に含む
- **将来検討**: 監査ログ機構 (kill 前 audit snapshot)。Judgment Pillar / Observation v1.0 の subset として
- **将来検討**: Mind の永続化 / 復元 (= 別 Mind ではなく「同 Mind の continuation」をサポートする `--resume` 経路)。本 ADR の v1 制約を緩める ADR が必要

## 代替案（不採用）

### A. 完全保持 (現状)

kill 時に何も消さない、dispatch 履歴は Realm の永続所有。

**不採用理由**:
- Mind identity の semantics が二重所有 (Mindspace は Mind 所有 vs dispatch は Realm 所有) → 矛盾
- 同名再 spawn で過去履歴を継承する挙動が dogfooding の混乱を生んだ (2026-05-28)
- ADR-0014 「破棄後の復元は仕組みとして提供しない」と矛盾 (実質的に dispatch 履歴で「復元」しているのと同じ)

### C. archive に移動

kill 時に `inbox/<mind>/` を `archive/<mind>/` に move、archive は残す。

**不採用理由**:
- inbox は clean になるが archive は累積、再 spawn 時に「異なる Mind だが同じ archive」を持つ状態が発生 → semantic がさらに複雑
- archive は本来 ack 済 message を入れる場所であり、kill 時の dispatch の保管庫として転用すると意味が薄まる
- 「監査ログ的に残したい」目的は別経路 (snapshot / audit log) で扱う方が責務分離が綺麗

### D. 名前空間 (session ID) で分離

`conduit-storage/inbox/<mind>/<spawn_session_uuid>/...` のような階層を導入し、同名再 spawn でも完全に隔離。

**不採用理由**:
- レイアウト変更が repo 全体に波及 (Conduit storage / Observation / dispatch_flow / read_inbox 全部)
- v1 の問題に対する過剰実装
- 「Mind = spawn-kill 期間 = 1 identity」というシンプルな原則のほうが運用も理解しやすい

将来「Mind の永続化 / 復元」が必要になれば D を採用する余地はある (= 本 ADR の v1 制約を緩める時)。

### E. TTL 経過後 prune

dispatch ファイルに TTL を持たせて、定期的に古いものを削除。

**不採用理由**:
- TTL の決め方が運用依存 (= 5 日? 30 日? 7 日?)、利用者の運用条件で大きく変わる値を framework が決めるべきではない (ADR-0021 C カテゴリの議論と類似)
- TTL prune は別の retention policy 機構として後で追加できる (本 ADR を否定しない、補完する形)
- 本問題 (= 再 spawn 時の混乱) は TTL では解決しない (= TTL 未到達期間で再 spawn したら混乱が再発)

### F. ADR 起こさず実装だけ

issue #104 のコメントで合意して kill-mind.sh だけ修正、ADR 化しない。

**不採用理由**:
- 「Mind identity = spawn-kill 期間に限定」は **本旨レベル**の決定 (ADR-0001 系の精緻化)
- 将来「再 spawn を continuation にしたい」「過去履歴を残したい」要望が来た時、コミット履歴の grep では決定根拠が辿れない
- ADR で残せば「本決定を撤回するには新規 ADR が要る」という重みが生まれる (ADR-0021 / 0022 と同じ運用)

## 関連

- [ADR-0001](0001-ai-org-os-as-invariant-framework.md) — 本旨「Mind = 思考個体」
- [ADR-0014](0014-realm-physical-boundary.md) — 物理境界、破棄後の復元なし
- [ADR-0008](0008-nexus-identity-binding.md) — identity binding (本 ADR で「期間」を明確化)
- [ADR-0007](0007-phase-3-reliability-properties.md) — dispatch 配送保証の「現状妥協」(kill 中 race の許容根拠)
- [Issue #104](https://github.com/yukiYamada/ai-org-os/issues/104) — 本 ADR の発議元、5 案議論
- 2026-05-28 Phase 5d-6 dogfooding — 本問題の実機検出
- `runtime/pillars/lifecycle/kill-mind.sh` — 本 ADR の実装対象
- `runtime/pillars/conduit/storage.py` / `dispatch-format.md` — dispatch ファイルの正規フォーマット
