# Judgment Pillar

> 想定読者: Phase 5a-3 (#38) で Warden の判断機能を実装・運用するメンテナ。
> 後続 Pillar (Inbox / Registry) から Judgment を呼び出す設計者。

**Judgment Pillar は Warden 内の「判断 Claude」**（[ADR-0010](../../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md) / [ADR-0011](../../../docs/adr/0011-warden-claude-naming-and-separation.md)）。
Mind と違い **Anthropic SDK 直叩き**で動く。対話せず決定論的 (temperature=0)、ループも持たず、他 Pillar から関数として呼ばれて 1 判定を返して終わる。

## 責務（Phase 5a-3 スコープ）

| 項目 | 値 |
|---|---|
| 入力 | [Observation v0.1](../observation/snapshot.py) の snapshot JSON |
| 処理 | snapshot.minds の各 Mind に対し action を判定 |
| 出力 | `MindJudgment(mind_name, action, reason)` のリスト |
| 副作用 | なし（action の実行は呼び出し側） |

語彙 (`VALID_ACTIONS`):

| Action | 意味 | ADR-0013 §3 対応 |
|---|---|---|
| `ok` | 問題なし、何もしない | — |
| `monitor` | 経過観察、次回 cycle で再判定 | Hard block / Quarantine の手前 |
| `investigate` | 詳細観測必要、人間 / Warden が見る | Quarantine 相当の検討 |
| `notify-human` | 致命的、failsafe 経路 | ADR-0012 責務 5 |

Phase 5a-3 では **判定のみ**。Kill / Destroy 等の実行は本 Pillar の責務外（後続フェーズ）。

## 使い方

### Python から

```python
from runtime.pillars.observation.snapshot import write_snapshot, load_snapshot
from runtime.pillars.judgment.judgment import judge_snapshot, make_client

# 1. Observation で snapshot を取る
snapshot_path = write_snapshot()
snapshot = load_snapshot(snapshot_path)

# 2. Judgment Claude に判定させる（client は遅延 import / API key は env から）
client = make_client()  # ANTHROPIC_API_KEY を読む
judgments = judge_snapshot(snapshot, client=client)

# 3. 呼び出し側で action を実行
for j in judgments:
    if j.action == "notify-human":
        # ADR-0012 §3 failsafe 経路（未実装、Phase 5b）
        ...
```

### CLI（動作確認用）

```bash
python3 runtime/pillars/observation/observe.py --snapshot \
  | python3 runtime/pillars/judgment/judgment.py
```

stdin から snapshot JSON、stdout に judgments JSON。

## 依存

| ライブラリ | バージョン | 用途 |
|---|---|---|
| anthropic | >= 0.40.0 | Claude API クライアント |

requirements.txt に固定。Realm Dockerfile で install される。

## モデル設定

| 設定 | 値 | 根拠 |
|---|---|---|
| model | `claude-haiku-4-5-20251001` | 判断系で十分、速くて安い |
| temperature | 0.0 | 決定論的 (ADR-0010 §5) |
| max_tokens | 1024 | 判定 JSON は数行で済む |
| timeout | 30s | API 障害時の早期 abort |

定数は `judgment.py` 冒頭。

## エラー設計

| 例外 | 発生条件 | 呼び出し側の推奨対応 |
|---|---|---|
| `AnthropicNotConfigured` | API key 不在 / SDK 未インストール | rule-based fallback (e.g., 全 Mind を `monitor` 扱い) |
| `JudgmentParseError` | Claude 応答が JSON でない / 語彙違反 / Mind 欠落 | rule-based fallback、ログに raw 応答を残す |
| `anthropic.APIError` 等 | API 失敗 (rate limit / network / 5xx) | retry + fallback |

判断機能の故障は **Realm 全体の停止を意味しない**（ADR-0013 §1 F3、Pillar 異常）。

## API key の扱い（ADR-0012 §2 責務 3 / 5）

`ANTHROPIC_API_KEY` 環境変数で渡す。これは **人間が管理する secret**:

- Realm container に `${ANTHROPIC_API_KEY}` をパススルー (docker-compose.yml)
- repo には commit しない (.gitignore + .env.example のみ)
- key 漏洩は人間の責務 (Realm の外側、ADR-0014 カテゴリ C: 外部依存)

未設定でも Realm 自体は起動可能。Judgment Pillar だけ disabled になり、他 Pillar は普通に動く。

## テスト

```bash
# ユニットテスト（API key 不要、SDK 未インストールでも動く）
python3 -m unittest discover runtime/pillars/judgment -p 'test_*.py'

# 統合（実際の API を叩く、opt-in）— Phase 5a-3 では未提供
# 将来 RUN_ANTHROPIC_TESTS=1 で有効化予定
```

mock 戦略: `unittest.mock.MagicMock` で `anthropic.Anthropic` client を差し替える。
SDK 自体の挙動はテスト対象外（SDK 側でテストされている前提）。

## Phase 5a-3 の非スコープ

| 項目 | 扱い |
|---|---|
| 複数 Judgment Claude の並走 | Phase 5b 以降 |
| 判定結果のキャッシュ / TTL | 同上 |
| 観測判断以外の判定（spawn 承認 / Axiom 違反確定 等） | Phase 5b 以降。本 Pillar に `judge_*` 関数を追加していく |
| Realm 内常駐 daemon 化 | 不要（呼び出し駆動、ADR-0010 §5「ループ無し」と整合） |

## 関連

- [ADR-0010](../../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md) §5 — Warden は SDK 直叩き
- [ADR-0011](../../../docs/adr/0011-warden-claude-naming-and-separation.md) — Pillar 命名と編集不可
- [ADR-0012](../../../docs/adr/0012-human-position-outside-realm.md) §2 責務 3/5 — API key と failsafe
- [ADR-0013](../../../docs/adr/0013-failure-handling-and-failsafe.md) §1 F3 — Pillar 異常の扱い
- [ADR-0014](../../../docs/adr/0014-realm-physical-boundary.md) §3 カテゴリ C — Anthropic API は外部依存
- Issue #38 — 本 Pillar の起票元
- [Observation snapshot](../observation/snapshot.py) — 入力データの提供元
