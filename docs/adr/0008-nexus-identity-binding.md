# ADR-0008: Nexus セッションを Mind の identity に bind する

> 想定読者: Nexus の認可機構を理解する人、Phase 5+ で HTTP transport / 認可強化に進むメンテナ、Issue #19 を追う人。

## Status

**Accepted** — 2026-05-23

## Context（背景）

[ADR-0005](./0005-phase-3-mcp-direct-with-nexus.md) で Nexus を Accepted、PR #23 で実装した時点で、以下の **なりすまし可能性** が残っていた：

- `send_dispatch(from_mind=...)` の引数で **任意の Mind 名** を名乗れる
- `read_inbox(mind_name=...)` で **他 Mind の inbox** を読める
- `ack_dispatch(mind_name=...)` で **他 Mind 宛のメッセージ** を ack できる

つまり、ある Mind が **他の Mind になりすまして** Dispatch を送る／受信する／既読化することができる状態。これは「Mindspace 不可侵」「思考⇔思考の境界」という Axiom と矛盾する。

Issue #19 でこの問題を別途追跡し、本 ADR で方針を確定する。

### 制約

- MCP の stdio transport では **1 セッション = 1 プロセスペア**（クライアント1 ↔ サーバー1）
- `spawn-mind.sh` は Mind ごとに `.mcp.json` を配置し、Mind 内の Claude Code が起動時に Nexus を sub-process として spawn する
- つまり「ある Mind の中の Claude が呼び出す Nexus セッション」は **常にその Mind 1 体に対応**している
- ただし Nexus 側はその対応関係を**知らない**ので、認可ができない

## Decision（決定）

**Nexus セッションを起動元 Mind の identity に bind する。**

具体的には：

1. `spawn-mind.sh` が `.mcp.json` を生成するとき、`mcpServers.nexus.env` に `AI_ORG_OS_MIND_NAME=<mind-name>` を追加する
2. `nexus.py` 起動時に `os.environ.get("AI_ORG_OS_MIND_NAME")` を読んで `Nexus(identity=...)` に渡す
3. `Nexus.send_dispatch / read_inbox / ack_dispatch` は、`identity` がセットされていれば操作対象の `from_mind` / `mind_name` がそれと一致する必要があり、一致しない場合は `PermissionError` を raise する
4. `identity=None`（環境変数未設定）の場合は、既存挙動を維持する（全 Mind 名を許可）。これはユニットテスト / 将来の HTTP multi-tenant 用途のため

### コード上の振る舞い（要約）

```python
nx = Nexus(identity="alice")

nx.send_dispatch(from_mind="alice", to_mind="bob", ...)   # OK
nx.send_dispatch(from_mind="bob",   to_mind="carol", ...) # PermissionError

nx.read_inbox(mind_name="alice")   # OK
nx.read_inbox(mind_name="bob")     # PermissionError

nx.ack_dispatch(mind_name="alice", msg_id=...)   # OK
nx.ack_dispatch(mind_name="bob",   msg_id=...)   # PermissionError
```

### MCP wiring 側

`PermissionError` は `nexus.py` の `call_tool` で捕捉され、`{"ok": false, "error": "...", "code": "forbidden"}` を返す。MCP クライアント（Mind 内 Claude）には JSON として届く。

### Identity の検証

`Nexus.__init__` で `identity` が指定された場合、`_validate_mind_name` で形式チェック（`[A-Za-z0-9._-]{1,64}`）。不正な identity（path traversal 等）で起動した場合は `ValueError` で即時失敗する。

## Consequences（影響）

### ポジティブ

- **なりすまし不可**: Mind A から Mind B として Dispatch を送ったり、Mind B の inbox を読むことができなくなる
- **不可侵原則の機械的担保**: Axiom が運用ではなくコードで守られる
- **痕跡が信頼できる**: Dispatch の `from:` 欄が「本当にその Mind が送った」ことを保証する
- **後方互換**: `identity=None` で従来通りも動く（テスト容易性 / 将来拡張用）

### ネガティブ

- `spawn-mind.sh` を経由しない手動 spawn で `AI_ORG_OS_MIND_NAME` を忘れると、Nexus は無認可状態になる
  - 緩和: README に明示、Phase 5 で Warden が spawn を担当する時に強制
- 環境変数で渡すため、シェルログ / プロセスリストに Mind 名が露出する
  - 緩和: Mind 名は秘密ではない（Nexus 上で identity として扱うだけ）

### リスク

- HTTP transport（複数 Mind が同じ Nexus に接続）に進化した場合、本機構は不十分
  - 各リクエストごとに identity を識別する必要があり、`Nexus(identity=...)` のような起動時 bind では対応できない
  - 対応: HTTP 化する時に別 ADR で再設計（MCP のセッション機能を使うか、トークンベース認可か）
- 同じ Mind から複数の Nexus セッションを開いた場合、それらは全て同じ identity を bind するため、認可上の差別化はない（が問題ない）

## 議論ログ（Discussion log）

ユーザーとの壁打ち（2026-05-23）の主要ポイント：

1. **「#19 は (c) でいい気がする」**: ユーザーは当初「Phase 5 で Warden が担う」案を選好
2. **「(a) の工数しだい」**: ただし環境変数経由なら 1-2 時間で実装可能と私が試算
3. **「今やる」採用**: stdio transport 前提なら最小実装で十分な強化が得られる
4. **「並列開発できるときにやる」**: HTTP 化など重い変更は Phase 5+ に持ち越し

## ADR-0007 との関係

ADR-0007 で「消失検知は実装しない、運用責任に委ねる」と決めた。本 ADR では「**なりすましは検知して拒否する**」を実装する。

- **なりすまし** = 機械的に検知可能（identity との不一致をその場で判定できる）→ 実装する
- **消失** = 機械的に検知不能（送信者は受信者の inbox を覗けない、Axiom）→ 運用に委ねる

つまり、認可は Axiom と整合的に強化できるが、配送保証は Axiom と衝突するため強化を諦めた、という対比。

## 関連

- Issue #19 — 本 ADR で Close
- [ADR-0005](./0005-phase-3-mcp-direct-with-nexus.md) — Phase 3 = MCP 直行（base 実装）
- [ADR-0006](./0006-phase-5-realm-warden-guildmaster.md) — Phase 5 = Realm + Warden（spawn 強制の担い手）
- [ADR-0007](./0007-phase-3-reliability-properties.md) — Phase 3 信頼性プロパティ（消失検知は非実装）
- `runtime/nexus/storage.py` — `Nexus.__init__(identity=...)` と `_authorize`
- `runtime/nexus/nexus.py` — env から identity 読み取り、`PermissionError` の MCP 応答化
- `runtime/spawn-mind.sh` — `.mcp.json` の env に identity 注入
