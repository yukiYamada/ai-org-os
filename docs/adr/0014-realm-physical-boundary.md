# ADR-0014: Realm の物理境界（内 / 外 / 穴あき層の定義）

> 想定読者:
> - Phase 5a を設計する人
> - 「この機能は Realm 内？外？」を判断する立場
> - 外部ツール（GitHub Actions / bash-editor / Anthropic API 等）の取り扱いに迷う実装者

## Status

**Accepted** — 2026-05-24

## Context（背景）

ADR-0002 で Realm を「ai-org-os のルール適用範囲（メタ世界コンテナ）」と定義し、ADR-0006 で Realm 内同居方式（DinD 回避）を決め、Phase 5a-1（#35）で Docker container として実装した。
ADR-0012 で「**人間 = Realm の外側**」と確定した。

しかし「Realm の物理境界はどこか」は連続的な議論として残っていた：

- bash-editor は Realm の外？それとも併用時に内？
- GitHub Actions / GitHub Issue は 外？内？
- Anthropic API は外（依存先）—これは明らかだが、なぜ「外」と言い切れる？
- ホスト OS の filesystem は？bind mount で穴あいてるが…
- Realm container の内側は明確に「内」

この問いを決めないと、Phase 5a-3 以降で「Judgment Pillar はどこまで監視するか」「Inbox Pillar はどこから入力を受けるか」の設計判断がブレる。

### 整理済みの前提

- ADR-0002: Realm = ai-org-os のルール適用範囲（メタ世界コンテナ）
- ADR-0006: Realm 内同居方式（DinD 回避、Pillar はプロセスとして同居）
- ADR-0009: bash-editor / claude-team は fork しない、純粋ロジックだけ流用（外部ツール）
- ADR-0012: 人間は Realm の外側、5 つの境界チャンネル経由で作用

## Decision（決定）

### 1. 「Realm 内」の定義

**Realm 内 ＝ ai-org-os の Axiom enforce が機械的に効く範囲**。

これは物理的（コンテナ境界）と論理的（Axiom enforce 範囲）の **両方を同時に満たす場所**：

- 物理的: Docker container `ai-org-os-realm` のプロセス空間とファイルシステム
- 論理的: Conduit Pillar の identity binding（ADR-0008）、Judgment Pillar の判定（#38）、Pillar 編集不可（ADR-0011）が効く範囲

両方を同時に満たさない場所は「Realm 内」ではない。

### 2. 「Realm 外」の定義

**Realm 外 ＝ ai-org-os が制御できない世界 ＝ 人間が制御する世界**。

ADR-0012 の「人間 = Realm の外側」と整合する。Realm 外は人間の責務領域：

- 人間が直接操作する（責務 1〜3）
- 人間が外部サービスとして契約する（責務 4〜5）

「Realm 外で起きることは Axiom の管轄外」と明示しておくと、「外部ツールの挙動まで保証しようとして肥大化」を防げる。

### 3. カテゴリ別の所属判定

各構成要素を 4 カテゴリに分類する：

| カテゴリ | 説明 | 例 |
|---|---|---|
| **A. Realm 内（純粋内側）** | container 内のプロセスとファイル | Pillar 群、Mind プロセス、Mindspace |
| **B. 穴あき層（半透明境界）** | container 境界をまたぐが Axiom enforce 対象 | bind mount された `runtime/`、`.mcp.json` stdio、ホストの Python（spawn-mind 経由） |
| **C. Realm 外（外部依存）** | Realm が呼ぶ／受け取る外部サービス | Anthropic API、Claude CLI binary、Git remote、外部 MCP |
| **D. Realm 外（人間制御領域）** | 人間が Realm に作用する経路 | GitHub Issue/PR、GitHub Actions、bash-editor、ホスト OS そのもの |

#### カテゴリ別の主な要素

| 要素 | カテゴリ | 根拠 |
|---|---|---|
| `runtime/pillars/` 配下のコード | A | Pillar = Warden 構成要素（ADR-0011） |
| `runtime/minds/<name>/` の Mindspace | A | Mind 所有領域（ADR-0002） |
| Mind プロセス（claude CLI 実行中） | A | Realm 内で起動、Axiom 制約下 |
| Conduit Pillar の MCP stdio 接続 | A → A | container 内通信 |
| ホストの `runtime/` ディレクトリ（bind mount） | **B** | container 内とホスト両方から見える。Axiom enforce は container 側で効く |
| ホストの Python（spawn 経由で実行） | **B** | spawn-mind.sh が呼び出す。Realm 内挙動の前提だが、ホスト側依存 |
| Anthropic API（Claude 本体の通信先） | C | 外部 SaaS、Realm から HTTP で呼ぶ |
| `claude` CLI バイナリ | C | 外部ツール、Realm に同梱しない（API key 含めて Phase 5a-3 で導入） |
| Git remote（GitHub repository） | C | Realm の永続化先だが Realm 内ではない |
| GitHub Issue / PR | **D** | 人間が ai-org-os に介入するチャンネル（ADR-0012 §3） |
| GitHub Actions CI | **D** | Realm 内挙動の検証手段、Realm そのものではない |
| bash-editor | **D** | ADR-0009 で「fork しない、外部併用」確定 |
| ホスト OS / docker daemon | **D** | Realm を起動する側（責務 3） |

### 4. 穴あき層（カテゴリ B）の扱い

bind mount は **「物理的に穴があいているが、Axiom enforce は片側で効く」** という半透明境界である。これを正確に扱う：

| 方向 | 物理 | Axiom enforce | 扱い |
|---|---|---|---|
| Realm 内 → bind mount → ホスト fs | 書き込める | container 側の Conduit / Judgment Pillar が検知可能 | **Realm 内挙動として扱う**（Axiom 適用） |
| ホスト fs → bind mount → Realm 内 | 書き込める | container 側からは「ある日突然変わった」としか見えない | **Realm 外からの介入として扱う**（ADR-0012 人間の責務） |

つまり **同じ物理パスでも「どちら側から書いたか」で意味が違う**。ホスト側から書き換えたら、それは人間（責務 1〜3）の作用であり、Axiom 違反検知の対象ではない（むしろ Axiom 自体を改定している可能性がある）。

この非対称性は **意図された設計**。「人間が壁の外側から書き換える権利」と「Realm 内 Mind が Axiom に縛られる」を両立させる。

### 5. Anthropic API は外（穴あきだが Realm 外）

Anthropic API は Realm 内 Mind が思考のために HTTP 呼び出しする外部サービス。これは **カテゴリ C（外部依存）として固定**：

- Realm が落ちても Anthropic API は影響を受けない
- Anthropic API が落ちたら Mind は思考できない（Realm の機能停止に近い、ADR-0013 F4）
- API key 管理は人間の責務（Phase 5a-3 で導入、責務 3 / 5 と関連）

「Anthropic API を Realm 内に取り込む」（自前 LLM ホスト）案は本 ADR では不採用（§代替案 A）。

### 6. CI / GitHub Actions は「Realm の再現性検証」であって Realm そのものではない

GitHub Actions が `runtime/tests/` を実行することは、**Realm が再現可能であることの検証** であり、**Realm そのものではない**。

- CI で Pillar テストが PASS する = ai-org-os コードが Realm を立てられる、という保証
- CI 環境 = 揮発する Realm の使い捨てクローン、本物の Realm ではない
- CI が落ちても本番 Realm は止まらない（独立）

これは Phase 5a-3 で「CI で何を担保するか」を決めるときの前提になる。

### 7. bash-editor は外（併用時も外）

ADR-0009 で「fork しない、submodule しない、純粋ロジック移植のみ」と確定済。本 ADR で **bash-editor は併用時も Realm 外** と明示する：

- bash-editor は人間が外側から Realm を観察するための補助ツール
- bash-editor が見るのは bind mount 経由のホスト側ファイル（カテゴリ B の host 側）
- bash-editor の挙動は ai-org-os の Axiom enforce 対象外

「bash-editor を Realm 内に同梱する」案は不採用（§代替案 B）。

## Consequences（影響）

### 利点

1. **Phase 5a-3 (#38 Judgment Pillar) の監視範囲が確定**: §3 のカテゴリ A と B の Realm 内挙動のみ監視、C/D は人間責務として除外
2. **Phase 5a-5 (#40 Inbox Pillar) の入力経路が明確**: D から A への入力チャンネルとして位置づけられる
3. **「外部依存をどこまで取り込むか」の判断軸ができた**: §5 (Anthropic API)、§7 (bash-editor) で外部のままにする方針が明確化
4. **bind mount の二重性が明文化**: §4。ホスト側書換と container 側書換が同じパスでも意味が違う
5. **CI と本番 Realm の混同を防ぐ**: §6。「CI green = 本番 Realm が動く」ではなく「再現性が保たれている」

### 不利益 / リスク

1. **bind mount の二重性が運用で混乱を生む可能性**: §4 の非対称性は読み間違いやすい。Pillar 監視ログで「誰が書いたか」を区別する必要があるが、ファイルシステムだけでは判定困難。Phase 5a-3 で対処
2. **CI 環境と本番 Realm の差分管理**: §6 で「別物」と明示したが、差分が大きすぎると CI の意味がなくなる。Dockerfile を共有して差分を最小化する運用が必要
3. **Anthropic API 依存の単一点故障**: §5 で「外部依存」と整理したが、それは ai-org-os 全体が Anthropic SaaS に依存していることを意味する。これは本旨（思考 = LLM）から不可避

### 派生する Issue / 後続作業

- **#38 (Judgment Pillar)**: §3 カテゴリ A/B を監視範囲として実装
- **#40 (Inbox Pillar)**: §3 カテゴリ D → A の入力経路として実装
- **Phase 5a-3 ログ機構**: §4 bind mount の二重性を区別できるログ（書き手の主体識別）
- **README / 用語集の更新**: §3 のカテゴリ表を `runtime/README.md` に転載候補

## 代替案（不採用）

### A. Anthropic API を Realm 内に取り込む（self-hosted LLM）

ローカルで Llama 等を動かして、Realm 内で完結させる案。

不採用理由：
- ai-org-os の本旨は「思考の集合体としての組織」であり、思考実装は問わない（ADR-0001）。特定 LLM への依存を消すために実装複雑性を爆発させるのは本末転倒
- Realm 内に LLM ホスティングを入れると、Realm のリソース管理 / GPU 制約 / OS チューニングが必要になり、Phase 5 の本質（思考の集合体としての組織）から外れる
- 「外部依存があること」は人間の責務 5（failsafe）でカバーされる

### B. bash-editor を Realm 内に同梱

bash-editor を Realm container に同梱して、ai-org-os の一部として配布する案。

不採用理由：
- ADR-0009 で確定済（fork / submodule しない、純粋ロジック移植のみ）
- bash-editor は人間（=Realm 外監督者）の観察補助ツール。これを内側に置くと「人間 = Realm 内」の混乱を招く（ADR-0012 と矛盾）
- bash-editor のメンテナがアクセス境界に縛られる（ai-org-os の Axiom）と、bash-editor 単独の進化が阻害される

### C. 物理境界と論理境界を分離（"Realm" を 2 概念に）

「Realm 物理（container）」と「Realm 論理（Axiom enforce 範囲）」を別の用語で分ける案。

不採用理由：
- 用語増加でメタファーが崩れる（ADR-0002 / 0006 / 0010 / 0012 の整合性が壊れる）
- 物理と論理が一致しないケース（bind mount のホスト側を内側扱いするか）は §4 の「穴あき層（カテゴリ B）」で十分に扱える
- カテゴリ B が二重性を吸収するので、Realm 概念は 1 つで足りる

### D. CI を Realm 内扱いにする

GitHub Actions の CI 実行を「Realm の使い捨てインスタンス」として Realm 内扱いする案。

不採用理由：
- CI は人間の責務領域（責務 2: Pillar コードのレビュー支援）。Realm 内扱いすると「人間 = Realm 外」（ADR-0012）と矛盾
- CI の挙動を Axiom enforce 下にすると、CI の柔軟性（並列実行 / 一時的 mock 等）が失われる
- 「CI = Realm の再現性検証」（§6）の位置づけで十分機能する

## 関連

- [ADR-0002](0002-vocabulary-and-meta-meta-structure.md) — Realm の定義
- [ADR-0006](0006-phase-5-realm-warden-guildmaster.md) — Realm 内同居方式
- [ADR-0008](0008-nexus-identity-binding.md) — Conduit Pillar の identity binding（§1 論理境界の実装）
- [ADR-0009](0009-relationship-with-bash-editor-and-claude-team.md) — bash-editor 取り扱い（§7 の根拠）
- [ADR-0011](0011-warden-claude-naming-and-separation.md) — Pillar 編集不可（§1 論理境界の実装）
- [ADR-0012](0012-human-position-outside-realm.md) — 人間 = Realm 外（§2 / §4 の根拠）
- [ADR-0013](0013-failure-handling-and-failsafe.md) — F4（Realm 系異常）は本 ADR の §3 カテゴリ A 全体の故障
- Issue #38 (Judgment Pillar) — 本 ADR §3 カテゴリ A/B の監視を実装
- Issue #40 (Inbox Pillar) — 本 ADR §3 カテゴリ D → A の入力経路
- Issue #44（Discussion B）— 本 ADR の起票元
