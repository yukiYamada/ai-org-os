# Phase 3 Dogfooding 検証

> 想定読者: Phase 3 (Nexus + Dispatch) が実際に動くことを手で確認したい人、新機能追加前に基盤を確かめたいメンテナ。

ai-org-os の Phase 3 では Nexus (MCP server) が Mind 間の Dispatch を仲介する。本ディレクトリには、その動作を **3 つの粒度**で検証する手段が揃っている。

## 方式 A: Python シミュレーション（1 分、依存ゼロ）

storage 層を直接呼んで 2 Mind 通信を再現する。最も軽量、本物の Claude 起動なし。**MCP wiring は通らない**が、storage ロジック + 冪等性が回ることは確認できる。

```bash
python3 runtime/verification/phase-3-dogfooding/simulate_two_minds.py
```

期待出力: 7 ステップ（送信 → 受信 → ack → 再 read → 冪等性 → archive → 他 Mind 不可侵）すべて通る。

このスクリプトは `tempfile.TemporaryDirectory` を使うので、`runtime/nexus/storage/` を汚さない。

## 方式 B: 2 ターミナル + 2 Claude（最も本物、5–10 分）

2 つのターミナルで Mind alice と Mind bob を起動し、MCP 経由で Dispatch を交わす **真の dogfooding**。

### 手順

1. 2 Mind を spawn:
   ```bash
   ./runtime/spawn-mind.sh generic designer alice
   ./runtime/spawn-mind.sh generic reviewer bob
   ```

2. **ターミナル 1** で alice 起動:
   ```bash
   cd runtime/minds/alice
   claude
   ```
   alice の Claude に指示する例:
   > Mind bob に「design-question」topic で「config の命名規則についてレビューしてほしい」と Dispatch を送って。`send_dispatch` tool を使う。

3. **ターミナル 2** で bob 起動:
   ```bash
   cd runtime/minds/bob
   claude
   ```
   bob の Claude に指示する例:
   > 自分の inbox を確認して。未読があれば内容を読んで、ack して、必要なら返信を送り返して。

4. **ターミナル 1** で alice が「inbox を確認、bob からの返信があるか」を確認:
   > 自分の inbox を read して、bob からの返信があれば内容を見せて。あったら ack して。

### 期待挙動

双方の Claude が `send_dispatch` / `read_inbox` / `ack_dispatch` を MCP 経由で呼ぶ。
ホスト上で `runtime/nexus/storage/inbox/{alice,bob}/` および `archive/{alice,bob}/` にファイルが出来ては移動していくのを観察できる。

### identity binding 確認（Issue #19 / PR #27 マージ後）

PR #27 マージ後は、各 Mind の `.mcp.json` の `env` に `AI_ORG_OS_MIND_NAME` が注入される。
alice の Claude が `from_mind="bob"` で `send_dispatch` を呼んだ場合、Nexus は `PermissionError` を返す。

検証:
- alice の Claude に「`send_dispatch(from_mind="bob", to_mind="carol", topic="x", body="y")` を呼んで」と指示
- 期待: `{ok: false, code: "forbidden"}` を含む応答

これが拒否されれば identity binding が機械的に効いていることが確認できる。

## 方式 C: 自動 E2E テスト（CI で常に実行、数秒）

```bash
./runtime/tests/run-tests.sh
```

`test-dispatch-e2e.sh` が storage 直接呼び出しで end-to-end を検証している。
CI でも GitHub Actions が `runtime/**` 変更時に毎回回す。

## 方式 E: bash-editor を外部観測ツールとして併用（方式 B の拡張）

> Status: **未検証**。手順書のみ提供。本方式は外部リポジトリ `local-multi-window-bash-editor` を使う。
> 統合方針は [ADR-0009](../../../docs/adr/0009-relationship-with-bash-editor-and-claude-team.md) を参照（**fork / submodule はしない、外部ツール併用に留める**）。

方式 B は 2 ターミナルを人間が交互に見る形だが、bash-editor を併用すれば **1 ブラウザタブで両方の Mind の出力を同時監視**できる。確認プロンプトの自動検知、グループ表示、優先度付きダッシュボードも得られる。

### 前提

- `C:\Users\kokoro068\git\local-multi-window-bash-editor` が手元にあり、Node.js 環境で `npm install` 済み
- bash-editor を起動できる: `node server.js` で Express + WebSocket がローカルポートを listen する想定

### 手順

1. **2 Mind を spawn**（方式 B と同じ）:
   ```bash
   ./runtime/spawn-mind.sh generic designer alice
   ./runtime/spawn-mind.sh generic reviewer bob
   ```

2. **bash-editor を起動**:
   ```bash
   cd ../local-multi-window-bash-editor
   node server.js
   # → localhost:<port> を開く（ポート番号は bash-editor 側の README 参照）
   ```

3. **bash-editor の UI で 2 session を作成**:
   - グループ名: `ai-org-os-phase3` （Guild 名と対応させる）
   - session 1: cwd = `<ai-org-os repo>/runtime/minds/alice`
   - session 2: cwd = `<ai-org-os repo>/runtime/minds/bob`

4. **各 session で `claude` を起動**:
   - bash-editor の write_terminal API（または UI 入力）で各 session に `claude\n` を送る
   - `.mcp.json` と `CLAUDE.md` が自動読み込みされ Nexus 接続 + Persona 装着

5. **方式 B と同じく Dispatch を交わす指示を投入**:
   - alice の Claude に「bob に Dispatch を送って」
   - bob の Claude に「inbox を確認して」
   - bash-editor の UI で**両 session の出力を 1 画面で観測**

### bash-editor で得られる追加情報（ai-org-os 単体では見えない）

| 観測対象 | bash-editor の機能 |
|---|---|
| 各 Mind の活動状態 | session のステータスドット（active / waiting / idle） |
| 確認プロンプト待ち | `waiting_confirmation` 自動検知（CONFIRM_PATTERNS） |
| 出力の差分 | 最新出力をブラウザでリアルタイム表示 |
| 介入 | `write_terminal` / UI 入力で Mind に直接指示を送れる |

### 注意（ADR-0009 と整合）

- bash-editor の **PTY 内で動く Claude** が `.mcp.json` を読んで Nexus に接続する
- Nexus と bash-editor は **独立プロセス** で動き、通信は MCP stdio 経由（Mind 内部）
- bash-editor は「**外側から Mind を見る目**」、Nexus は「**Mind 同士をつなぐ経路**」、役割分担は崩れない

### ai-org-os 単体ツールとの比較

| 観測手段 | スコープ | 即時性 | 介入 |
|---|---|---|---|
| `runtime/observatory/observe.py` | Mind のメタ情報（mtime / 件数） | ポーリング | 不可（観測のみ） |
| bash-editor 併用（方式 E） | Mind 内部の出力（リアルタイム） | リアルタイム | 可（write_terminal） |
| `runtime/list-minds.sh` | spawn 中の Mind 一覧 | 1 shot | 不可 |

**使い分け**: 普段は `observe.py`、本物検証 / トラブルシュート時は方式 E。

## 方式の使い分け

| 方式 | 何を検証 | 時間 | 本物度 | 自動化 | 外部依存 |
|---|---|---|---|---|---|
| A | storage ロジック + 冪等性 + 不可侵 | 1 分 | 中 | 半自動（手で実行） | なし |
| B | MCP wiring + Claude 統合 + 実 Persona の振る舞い | 5–10 分 | 高 | 手動 | Claude CLI |
| C | 回帰テスト（CI） | 数秒 | 中 | 完全自動 | なし |
| E | 方式 B + 1 ブラウザタブで複数 Mind 同時観測 | 10–20 分 | 最高 | 手動 + ブラウザ | Claude CLI + bash-editor |

通常運用は **A + C** で十分。**B / E は新機能追加時 / Phase 5 着手前 / 詰まった時**に手で確認する。

## 既知の制限（Phase 3 時点）

- 本物の「24/365 持続稼働 Mind」は未実装（Phase 5 で Realm + Warden 導入予定、[ADR-0006](../../../docs/adr/0006-phase-5-realm-warden-guildmaster.md)）
- 方式 B では各 Claude セッションは対話型なので人間が指示を投入する必要あり
- Claude Code の **subagent から Nexus への接続**が動くかは Claude Code 仕様依存（未確認、別途試す価値あり）
- Phase 3 では認可は **stdio 1 セッション = 1 Mind** の前提でのみ効く（HTTP transport 化したら作り直し、[ADR-0008](../../../docs/adr/0008-nexus-identity-binding.md)）

## サブエージェント検証への伸ばし方（補足、未検証）

Claude Code の Agent ツールでサブエージェントを 2 つ spawn し、それぞれが `runtime/minds/alice` / `bob` のディレクトリで動くよう指示することで、**親 1 Claude セッション内で擬似的に 2 Mind を動かす** ことが理論上は可能。

ただし以下が未確認:

1. サブエージェントが `.mcp.json` を読んで独自に Nexus を spawn するか
2. サブエージェントが親の MCP server 接続を継承するか
3. サブエージェントが対話なしで自走できるか（呼ばれて 1 回動いて終わる性質との整合）

これらが clear になったら方式 A と方式 B の中間として「**方式 D: subagent 自動 dogfooding**」を追加できる。本ディレクトリに `subagent_dogfooding.py` 等として追加する想定（現時点では未実装）。

## 関連

- [ADR-0005](../../../docs/adr/0005-phase-3-mcp-direct-with-nexus.md) — Phase 3 = MCP 直行
- [ADR-0007](../../../docs/adr/0007-phase-3-reliability-properties.md) — 信頼性プロパティ（消失検知は運用責任）
- [ADR-0008](../../../docs/adr/0008-nexus-identity-binding.md) — identity binding（PR #27）
- [ADR-0009](../../../docs/adr/0009-relationship-with-bash-editor-and-claude-team.md) — bash-editor / claude-team との関係（方式 E の根拠）
- [`runtime/nexus/README.md`](../../nexus/README.md) — Nexus の使い方
- [`runtime/observatory/README.md`](../../observatory/README.md) — Realm 観測ツール（最小・独自実装）
