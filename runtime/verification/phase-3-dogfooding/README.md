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

## 方式の使い分け

| 方式 | 何を検証 | 時間 | 本物度 | 自動化 |
|---|---|---|---|---|
| A | storage ロジック + 冪等性 + 不可侵 | 1 分 | 中 | 半自動（手で実行） |
| B | MCP wiring + Claude 統合 + 実 Persona の振る舞い | 5–10 分 | 高 | 手動 |
| C | 回帰テスト（CI） | 数秒 | 中 | 完全自動 |

通常運用は **A + C** で十分。**B は新機能追加時 / Phase 5 着手前**に手で確認する。

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
- [`runtime/nexus/README.md`](../../nexus/README.md) — Nexus の使い方
