# Conductor Pillar

> 想定読者: Realm を起動する人、Warden の cycle 挙動を理解したい人、判断ルートを
> 拡張するメンテナ。

**Conductor Pillar は Warden の心拍**。各 Pillar (Observation / Inbox / Judgment / Lifecycle / Conduit / Registry) は「呼ばれれば動く関数」として揃っていたが、それらを **周期的に呼ぶ常駐エンジン** が無かった。Conductor がそれを担う。

ADR との位置づけ:
- **ADR-0010 §5**: Warden は機能の集合体、Judgment はループなし呼び出し駆動。Conductor が「呼ぶ側」。
- **ADR-0011**: Pillar として `runtime/pillars/conductor/` 配下、編集不可。
- **ADR-0013 §1 F3**: Pillar 異常 (Judgment 失敗等) は Realm 停止を意味しない。Conductor は各 step を try/except で吸収。

## 1 cycle の流れ

```
[ Conductor cycle N ]
   │
   ▼
1. Inbox poll                 (list_pending_issues)
2. Observation snapshot       (write_snapshot)
3. Judgment Claude            (judge_snapshot or rule-based fallback)
4. status JSON 書き出し       (conductor-status.json)
5. sleep period 秒
   │
   ▼
[ Conductor cycle N+1 ]
```

各 step は例外で**前段を止めない**。例えば Inbox 読みが失敗しても snapshot は試行する。Judgment が API key 不在で失敗しても rule-based fallback で続行する。

## 設定

| 環境変数 | デフォルト | 用途 |
|---|---|---|
| `AI_ORG_OS_CONDUCTOR_PERIOD` | `30` | cycle 間隔 (秒) |
| `AI_ORG_OS_CONDUCTOR_MAX_CYCLES` | `0` (= 無限) | 上限 cycle 数 (テスト用) |
| `AI_ORG_OS_CONDUCTOR_STATUS_PATH` | `runtime/realm/conductor-status.json` | status JSON 書き込み先 (テスト用) |
| `AI_ORG_OS_CONDUCTOR_ISSUES_DIR` | `runtime/issues/` | Inbox のルート (テスト用) |
| `AI_ORG_OS_CONDUCTOR_SNAPSHOTS_DIR` | `runtime/pillars/observation/snapshots/` | snapshot 出力先 (テスト用) |
| `ANTHROPIC_API_KEY` | (未設定) | Judgment 用。未設定なら fallback |

## 起動

### Docker (本番想定)

`runtime/realm/docker-compose.yml` の CMD で自動起動。

```bash
cd runtime/realm
docker compose up -d --build
docker logs -f ai-org-os-realm
```

### ホストで直接 (開発時)

```bash
python3 runtime/pillars/conductor/conductor.py
# または
bash runtime/pillars/conductor/conductor.sh
```

### テスト用に短いループ

```bash
AI_ORG_OS_CONDUCTOR_PERIOD=0 \
AI_ORG_OS_CONDUCTOR_MAX_CYCLES=3 \
python3 runtime/pillars/conductor/conductor.py
```

## 停止

- SIGTERM / SIGINT → 進行中 cycle を完走してから graceful 停止 (mind-loop.sh と同じ)
- `docker compose down` で Realm 全体停止 = Conductor も止まる
- SIGKILL は使わない方が安全 (status JSON 書き込み中に殺すと不完全 JSON が残る可能性、ただし atomic write なので tmp 残骸のみ)

## conductor-status.json

最新 cycle のサマリ。`observe.py --realm` が読んで Realm 統合ビューに表示する。

```json
{
  "schema": "conductor-status/v1",
  "last_cycle": {
    "cycle": 42,
    "started_at": "2026-05-24T01:00:00Z",
    "ended_at": "2026-05-24T01:00:01Z",
    "pending_issues": 2,
    "snapshot_path": "/realm/runtime/pillars/observation/snapshots/...json",
    "judgments_count": 3,
    "judgments_action_breakdown": {"ok": 1, "monitor": 2},
    "judgment_status": "ok",
    "judgment_error": null
  },
  "total_cycles": 42,
  "updated_at": "2026-05-24T01:00:01Z"
}
```

`judgment_status` の値:

| 値 | 意味 |
|---|---|
| `ok` | Judgment Claude が valid な判定を返した |
| `skipped` | Mind が 0 件、Judgment 呼び出しなし |
| `fallback-no-key` | ANTHROPIC_API_KEY 不在で fallback (全 Mind → `monitor`) |
| `fallback-error` | Judgment 呼び出しが例外、fallback (全 Mind → `monitor`) |

## テスト

```bash
# Conductor の unit test (mock client、API key 不要)
python3 -m unittest discover runtime/pillars/conductor -p 'test_*.py'

# E2E smoke (Inbox 投入 → Conductor 2 cycle → status / snapshot 検証)
bash runtime/tests/test-warden-e2e.sh

# 全体
./runtime/tests/run-tests.sh
```

## Phase 5b-1 の非スコープ (後続フェーズ)

| 項目 | 扱い |
|---|---|
| Issue → Mind spawn の orchestration | Phase 5b-2 以降。今は Inbox を poll するだけで claim/spawn はしない |
| Judgment 結果から action 実行 (Kill / Quarantine) | 同上。今は status JSON に記録のみ |
| 複数 Judgment Claude の並走 | ADR-0013 §1 の F1-F4 ごとの専用 Judgment が来たら本 Pillar から振り分け |
| 失敗 cycle の再試行 / バックオフ | 今は単純に次 cycle で再観測 |
| Conductor の冗長化 (HA) | Phase 6 以降。今は 1 Realm = 1 Conductor の前提 |

## 関連

- [ADR-0010](../../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md) §5 — Warden = 機能集合体
- [ADR-0011](../../../docs/adr/0011-warden-claude-naming-and-separation.md) — Pillar 編集不可
- [ADR-0013](../../../docs/adr/0013-failure-handling-and-failsafe.md) §1 F3 — Pillar 異常の扱い
- Issue #71 — 本 Pillar の起票元
- 入力提供元: [Inbox](../inbox/README.md), [Observation](../observation/README.md), [Judgment](../judgment/README.md)
