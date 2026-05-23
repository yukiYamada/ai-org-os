# bash-editor API リファレンス（外部ツール）

> 想定読者: ai-org-os の Observatory / Phase 3 dogfooding 検証 / Phase 5 Realm 観測ツールを実装・拡張する担当。`local-multi-window-bash-editor` をホスト側で起動して併用する（方式 E）際に、HTTP API / MCP tools / セッションライフサイクル / Status・Category 計算ロジックを参照するための一次資料。

---

## 0. 位置づけと注意事項

本書は **外部リポジトリ `local-multi-window-bash-editor`（以下 bash-editor）の API スナップショット** を ai-org-os 側で参照可能にするためのドキュメント。

- スナップショット時点: 2026-05-23（`server.js`, `lib/pure.js` を精読）
- 流用方針: [ADR-0009](../adr/0009-relationship-with-bash-editor-and-claude-team.md) 「fork / submodule しない、部品流用と並行運用に留める」
- 本書は **参照資料**。実装は本書を参照しつつ、別 issue で行う（**本書では実装コードを ai-org-os 配下に追加しない**）
- bash-editor は localhost のみで動作する設計（DNS rebinding 対策で `127.0.0.1` / `localhost` / `::1` 以外の Host / Origin は 403）
- bash-editor の用語と ai-org-os の用語の対応は [ADR-0009](../adr/0009-relationship-with-bash-editor-and-claude-team.md) 「用語の対応表」を参照

---

## 1. HTTP API エンドポイント一覧

bash-editor は `http://localhost:PORT`（既定 `10000`）で HTTP API を公開する。`server.js` から抽出した 16 エンドポイント。本節は「ai-org-os から叩く可能性が高いもの」を中心にまとめる。

### 1.1. セッション管理

| メソッド | パス | 引数（body / query） | 戻り値 | 用途 |
|---|---|---|---|---|
| `POST` | `/api/terminal` | body: `{ id?, cols?, rows?, meta? }`（`meta = { name?, groupId?, role?, supervisorId? }`） | `{ ok: true, id }` または 400/409 | 新規セッション作成。`id` 未指定なら `${groupId}-${counter}` を払い出す |
| `GET` | `/api/terminals` | query: `groupId?`, `recursive?` (`"true"`) | `[{ id, meta, cwd }, ...]` | セッション一覧。`recursive=true` で子孫 group も含める |
| `GET` | `/api/status` | query: `groupId?`, `recursive?` | `[{ id, status, lastOutputTime, lastViewedTime, elapsedMs, confirmWaitingSince }, ...]` | 全セッションの活動度（§4 参照） |
| `GET` | `/api/terminal/:id/output` | query: `lines?` (1〜500、既定 50) | `{ id, lines: string[] }` | ANSI ストリップ済みの末尾 N 行 |
| `POST` | `/api/terminal/:id/write` | body: `{ body: string }` | `{ ok: true }` | PTY への生入力（`\r` で Enter）。TUI には不向き |
| `DELETE` | `/api/terminal/:id` | — | `{ ok: true, id }` | セッション kill |
| `PATCH` | `/api/terminal/:id` | body: `{ name?, role?, supervisorId? }` | `{ ok: true, id, meta }` | メタ情報更新 |

### 1.2. グループ管理

| メソッド | パス | 引数 | 戻り値 | 用途 |
|---|---|---|---|---|
| `GET` | `/api/group/:id` | — | `{ groupId, name, supervisor, sessions: [...] }` | Group 情報。`supervisor` は role が `supervisor` の sessionId |
| `DELETE` | `/api/group/:id` | query: `recursive?` (`"true"`) | `{ ok: true, deleted: [id, ...] }` | Group 配下を一括 kill |
| `PATCH` | `/api/group/:id` | body: `{ name: string }` | `{ ok: true, groupId, name, updated }` | Group 名変更（配下 session の `meta.groupName` を更新） |

### 1.3. メッセージ

| メソッド | パス | 引数 | 戻り値 | 用途 |
|---|---|---|---|---|
| `POST` | `/api/message` | body: `{ from, to, type?, body }` | `{ ok: true, id }` または 400/404 | session 間メッセージ送信。受信側の PTY にも `[Message from X]: ...` が書き込まれる |
| `GET` | `/api/messages` | query: `to`（必須）, `since?` (ms) | `Message[]` | 受信メッセージ取得 |
| `DELETE` | `/api/messages/:id` | — | `{ ok: true }` | メッセージ削除 |

### 1.4. 運用補助

| メソッド | パス | 引数 | 戻り値 | 用途 |
|---|---|---|---|---|
| `GET` | `/api/usage` | — | Claude 使用量（ccusage CLI 結果） | トークン消費の俯瞰 |
| `GET` | `/api/usage/per-cwd` | — | cwd 別の使用量 JSONL 集計 | リポジトリ単位の使用量分析 |
| `POST` | `/api/prepare-shutdown` | — | `{ ok: true, pending: [id, ...] }` | 再起動前に Claude session に保存指示 |
| `POST` | `/api/shutdown-ack` | body or query: `id` | `{ ok: true, remaining }` | session 側から「保存完了」を通知 |
| `GET` | `/api/shutdown-status` | — | `{ ready: bool, pending: [id, ...] }` | 全 session の保存完了状況 |

> ai-org-os から「セッション一覧と状態」だけ欲しい場合、`GET /api/terminals` と `GET /api/status` の 2 本だけで十分。書き込み（`POST /api/terminal/:id/write`、`POST /api/message`）は方式 E 自動化の段階で初めて使う。

---

## 2. MCP tool 一覧

bash-editor は HTTP API と同等の操作を MCP server（`http://localhost:PORT/mcp`、Streamable HTTP transport、ステートレス）として公開する。`server.js` の `createMcpServer()` から抽出した 13 tools。

### 2.1. セッションライフサイクル系

| Tool | 引数 | 戻り値 | 用途 |
|---|---|---|---|
| `create_session` | `groupId?`, `name?`, `role?` (`"none"\|"supervisor"\|"worker"`), `cols?`, `rows?`, `cwd?` | `{ ok: true, id, meta }` | session 新規作成。HTTP の `POST /api/terminal` 相当 |
| `delete_session` | `id`, `callerId?` | `{ ok: true, id }` | session kill。`callerId` 指定時は group access チェック |
| `rename_session` | `id`, `name?`, `role?`, `callerId?` | `{ ok: true, id, meta }` | メタ情報更新 |

### 2.2. 観測系

| Tool | 引数 | 戻り値 | 用途 |
|---|---|---|---|
| `get_status` | `groupId?`, `recursive?` | session 一覧 + 各 `status` / `lastViewedTime` / `elapsedMs` / `confirmWaitingSince` | 全 session の活動度（§4 参照） |
| `get_output` | `id`, `lines?` (1〜500), `callerId?` | ANSI ストリップ済みの末尾 N 行（文字列） | 末尾出力の閲覧 |
| `get_messages` | `to`, `since?` (ms) | `Message[]` | 受信メッセージ取得 |
| `get_group_info` | `groupId` | `{ groupId, name, supervisor, sessions }` | Group 情報 |

### 2.3. 介入系

| Tool | 引数 | 戻り値 | 用途 |
|---|---|---|---|
| `write_terminal` | `id`, `data`（`\r` で Enter）, `callerId?` | `"ok"` | PTY 生書き込み。TUI には不向き、shell には信頼性高い |
| `send_message` | `from`, `to`, `body`, `type?` | `{ ok: true, id }` | session 間メッセージ。受信 PTY にも書き込まれる。group access チェックあり |
| `send_to_supervisor` | `groupId`, `from`, `body`, `type?` | `{ ok: true, id, supervisorId }` | Group の supervisor 宛にメッセージ。supervisor が居なければ 404 |
| `wait_for_claude` | `id`, `timeout?` (秒、最大 60) | `{ ok: true, elapsed }` または `{ error: "timeout" }` | Claude session のプロンプト（`❯`）出現を待つ。**DEPRECATED**（Agent View 使用が推奨） |

### 2.4. グループ系

| Tool | 引数 | 戻り値 | 用途 |
|---|---|---|---|
| `delete_group` | `groupId`, `recursive?`, `callerId?` | `{ ok: true, deleted: [id, ...] }` | Group 配下を一括 kill |
| `rename_group` | `groupId`, `name`, `callerId?` | `{ ok: true, groupId, name, updated }` | Group 名変更 |

### 2.5. Resources / Prompts

MCP の `resources` と `prompts` も提供される（本書では tool 数 13 に含めない）：

- Resource `docs://supervisor-guide` — Supervisor 用ガイド（Markdown）
- Resource `docs://setup-claude` — Claude セットアップ手順（Markdown）
- Resource `session://status` — 全 session の現状（JSON、`get_status` と同等）
- Prompt `supervisor-setup` — Supervisor 用 `CLAUDE.md` テンプレート生成
- Prompt `monitor-sessions` — 監視ループ実行指示の生成

> ai-org-os の Nexus（MCP server）と bash-editor の MCP server は **役割が異なる**（Nexus = Mind 間 Dispatch、bash-editor = ローカル PTY 監視）。両方を mcp.json に登録する形になる（ADR-0009 §3 並行運用方針）。

---

## 3. セッションライフサイクル図

```
                    +-----------------------------------+
                    |   bash-editor server (Node.js)    |
                    |   server.js + pty-host (IPC)      |
                    +-----------------------------------+
                                  |
            POST /api/terminal    | createTerminal(id, cols, rows, meta, cwd)
            create_session  ----->|
                                  v
                  +---------------------------+
                  |  buildTerminalEntry(id)   |  ← terminals.set(id, entry)
                  +---------------------------+
                                  |
                                  | ipcClient.spawn({ id, shell, args, cwd, ... })
                                  v
                  +---------------------------+
                  |  pty-host が PTY を spawn |
                  |  SESSION_ID=<id> を inject |
                  +---------------------------+
                                  |
                                  | ipcClient.subscribe(id)
                                  v
                  +---------------------------+
                  |  output stream            |  ← lastOutputTime 更新
                  |  ipcClient.on('output')   |  ← outputBuffer 蓄積
                  +---------------------------+
                                  |
                                  | 5秒ごとに setInterval
                                  v
                  +---------------------------+
                  |  detectConfirmPrompt()    |  ← §4 参照
                  +---------------------------+
                       |               |
        マッチあり     |               | マッチなし
                       v               v
        confirmWaitingSince=now    confirmWaitingSince=null
        supervisor に通知              （ライフサイクル継続）
                       |
                       v
        +---------------------------------+
        |  Supervisor が write_terminal / |
        |  send_message で介入            |
        +---------------------------------+
                       |
                       v
        プロンプト消失 → confirmWaitingSince リセット
                       |
                       v
        ……（活動継続 or idle）……
                       |
        DELETE /api/terminal/:id    |
        delete_session  ----------->|
                                    v
                  +---------------------------+
                  |  ipcClient.kill(id)       |
                  |  ipcClient.on('exit')     |
                  |  terminals.delete(id)     |
                  |  saveSessions() 即実行    |
                  +---------------------------+
```

補助イベント:

- ブラウザリロード時: `terminal:subscribe` で `outputBuffer` をリプレイ
- 60 秒ごとに `saveSessions()` で `.sessions.json` に永続化
- 10 秒ごとに `pollGitBranches()` で OSC 9999 経由の repo/branch を再確認
- `POST /api/prepare-shutdown` 時: role !== 'none' の session に保存指示を送り、`POST /api/shutdown-ack` の戻りで全完了待ち

---

## 4. Status と Category 計算ロジック（`lib/pure.js`）

bash-editor の活動度判定は **純粋関数のみ** で完結する（`lib/pure.js`、依存ゼロ）。ai-org-os の Observatory は同じ判定軸を Python に移植して使う（ADR-0009 §2.1）。

### 4.1. しきい値

```js
ACTIVE_THRESHOLD_MS  = 2_000      // 2 秒
WAITING_THRESHOLD_MS = 300_000    // 5 分
STALE_THRESHOLD_MS   = 3_600_000  // 1 時間
```

### 4.2. `calcStatus(t)` — 「時間経過から推測される活動度」

優先順位（上から判定）:

1. `confirmWaitingSince` がセットされている → `"waiting_confirmation"`
2. `now - lastOutputTime < 2_000` → `"active"`
3. `now - lastOutputTime < 300_000` → `"waiting"`
4. それ以外 → `"idle"`

`STALE_THRESHOLD_MS` は `calcStatus` では使わない（4 と区別しない）。

### 4.3. `calcCategory(t)` — 「ユーザーがいま気にする必要があるか」

優先順位（上から判定）:

1. `confirmWaitingSince` あり → `"attention"`
2. `now - lastOutputTime < 2_000` → `"running"`
3. `lastOutputTime > lastViewedTime` → `"unread"`（未読）
4. `now - lastOutputTime > 3_600_000` → `"stale"`
5. それ以外 → `"read"`

`calcStatus` は「活動度」、`calcCategory` は「未読モデル」。両者は **別軸** で、ダッシュボード UI では `calcCategory` を使う設計。

### 4.4. `detectConfirmPrompt(text)` — 確認待ち検出

末尾 2000 文字に対して以下のパターンを順に試行し、最初にマッチしたら `m[0]` を返す（マッチなしは `null`）:

```
/Do you want to/i, /Would you like to/i,
/\by\/n\b/i, /\byes\/no\b/i,
/Esc to cancel/i,
/\[y\/N\]/i, /\[Y\/n\]/i,
/Press Enter to continue/i, /Continue\?/i,
/続けますか/, /実行しますか/
```

検出時、5 秒ポーリングループ（`server.js` 内）が `confirmWaitingSince = Date.now()` をセットし、supervisor が登録されていれば `[自動通知] <id> が確認待ちです。出力: ...` メッセージを supervisor に送る（30 秒に 1 回まで）。

### 4.5. ai-org-os 側での扱い

Observatory（`runtime/observatory/pure.py`、ADR-0009 §5）は同じしきい値・同じ判定順序で Python ポートしてある。Mind の `lastDispatchAt` に対しても `calcStatus` を適用する想定（§5 シナリオ B 参照）。

---

## 5. ai-org-os 統合シナリオ

bash-editor と ai-org-os の統合は **「持っていれば便利、無くても動く」** を維持する（ADR-0009 §3）。以下は将来の実装候補となるシナリオ。**いずれも本書では設計案として記述し、実装は別 issue で行う**。

### 5.1. シナリオ A: Mind を bash-editor の session として登録

**動機**: Phase 3 dogfooding で複数 Mind を並走させるとき、各 Mind の出力を 1 ブラウザタブで眺めたい。

**流れ**:

1. ai-org-os が Mind コンテナを spawn する直前に、bash-editor の `POST /api/terminal` を叩いて session を予約
2. `meta.groupId` に Guild 名を入れる、`meta.role` を `worker`、`meta.supervisorId` を Guildmaster の session に
3. Mind コンテナ起動時に環境変数 `SESSION_ID` を渡し、Mind が `POST /api/message` で報告できるようにする
4. Mind の出力は PTY 経由で bash-editor のブラウザ UI にも流れる

**境界**: 本シナリオを実装しても、ai-org-os の Nexus / Mind は bash-editor の生死に依存しない。bash-editor が落ちていれば「観測ができない」だけで、Mind 自体は動く。

### 5.2. シナリオ B: Observatory が bash-editor から補完情報を取得

**動機**: Observatory v0.2+ で「Mind の状態一覧」を表示するとき、Nexus storage だけでは「Mind のターミナル末尾出力」が分からない。bash-editor を併用していればその情報を取れる。

**流れ**:

1. Observatory CLI が `runtime/nexus/storage/` から Mind の一覧と `lastDispatchAt` を読む
2. bash-editor が起動中（`GET /api/status` が 200 を返す）なら、Mind 名 ≒ session id として `GET /api/terminal/:id/output?lines=20` を叩く
3. Nexus 情報と bash-editor 情報をマージして、Observatory ダッシュボードに表示

**境界**: bash-editor が居なければ Nexus 情報だけで動く。マージはあくまで「あれば補完」。実装は `runtime/observatory/` に `supplement_with_bash_editor.py`（仮称、§6 参照）として追加するイメージだが、**本書では設計案のみ**。

### 5.3. シナリオ C: 方式 E（dogfooding）を自動化

**動機**: `runtime/verification/phase-3-dogfooding/README.md` に「方式 E: bash-editor 併用」を追記する（ADR-0009 §3）。手順を自動化スクリプトに落としたい。

**流れ**:

1. ai-org-os 側の dogfooding driver スクリプト（仮称 `dogfooding_with_bash_editor.py`）を起動
2. bash-editor が動いていなければ起動指示を出して終了（依存を最小化）
3. `simulate_two_minds.py` 相当のロジックを bash-editor 経由に置き換え:
   - 2 つの session を `create_session` で作成（同じ Guild）
   - 一方の supervisor を Guildmaster ロール、もう一方を Worker ロール
   - `send_message` で初期 Dispatch を流し込む
4. 5 秒ごとに `get_status` をポーリングして `waiting_confirmation` を検出
5. 検出されたら `get_output` で末尾を取り、シナリオ対応の応答を `write_terminal` で送る
6. 一定回数のラウンドが終わったら `delete_group` で片付け

**境界**: 本シナリオは「Mind が実体としてコンテナで動く前段階のスタブ検証」用。Phase 5 で Realm + Warden が enforce するようになっても、bash-editor 経由の dogfooding は補助検証として残る可能性がある。

---

## 6. Python 擬似コード（urllib のみ、副作用なし）

参考実装の **設計案**。urllib（標準ライブラリ）のみで書ける。**本書ではコードを ai-org-os 配下に追加しない**。実装する場合は別 issue（Observatory v0.2+ のスコープ、もしくは Issue #43 配下）で行う。

### 6.1. `supplement_with_bash_editor.py`（仮想、シナリオ B 用）

```python
"""bash-editor が起動していれば補完情報を取得する。落ちていれば空 dict を返す。

ADR-0009 §3 並行運用方針: 依存追加なし、urllib のみ。
"""
import json
import urllib.request
import urllib.error
from typing import Optional


BASH_EDITOR_BASE = "http://localhost:10000"
TIMEOUT_SEC = 2.0


def _get_json(path: str) -> Optional[object]:
    """bash-editor の HTTP API を叩く。接続失敗・タイムアウトは None。"""
    url = f"{BASH_EDITOR_BASE}{path}"
    req = urllib.request.Request(url, headers={"Host": "localhost"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def is_bash_editor_alive() -> bool:
    """bash-editor が稼働中か判定（GET /api/status が 200 を返すか）。"""
    return _get_json("/api/status") is not None


def supplement_mind_info(mind_name: str) -> dict:
    """Mind 名（≒ bash-editor の session id）に対する補完情報を返す。

    キー:
      - bash_editor_alive: bool
      - status: str | None      （active / waiting / idle / waiting_confirmation）
      - last_output_lines: list[str] | None
      - confirm_waiting_since: int | None
    """
    if not is_bash_editor_alive():
        return {"bash_editor_alive": False}

    statuses = _get_json("/api/status") or []
    me = next((s for s in statuses if s.get("id") == mind_name), None)

    output = _get_json(f"/api/terminal/{mind_name}/output?lines=20")
    lines = output.get("lines") if isinstance(output, dict) else None

    return {
        "bash_editor_alive": True,
        "status": me.get("status") if me else None,
        "last_output_lines": lines,
        "confirm_waiting_since": me.get("confirmWaitingSince") if me else None,
    }


# CLI 用エントリポイント。スクリプト単体で動かすと最初の Mind の情報を表示。
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: supplement_with_bash_editor.py <mind_name>", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(supplement_mind_info(sys.argv[1]), indent=2, ensure_ascii=False))
```

### 6.2. 方式 E 自動化スクリプト（仮想、シナリオ C 用）

```python
"""dogfooding 方式 E: bash-editor 経由で 2 Mind のシナリオを回す（設計案）。

ADR-0009 §3: bash-editor は外部ツール。本スクリプトは「無くても動く」前提を
維持するため、起動チェックに失敗したら即終了する。
"""
import json
import time
import urllib.request
import urllib.error
from typing import Optional


BASE = "http://localhost:10000"
GUILD_ID = "dogfooding-e"
POLL_INTERVAL_SEC = 5
MAX_ROUNDS = 12  # 60 秒程度


def _http_json(method: str, path: str, body: Optional[dict] = None) -> Optional[dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Host": "localhost", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def ensure_alive() -> bool:
    return _http_json("GET", "/api/status") is not None


def create_mind(name: str, role: str, supervisor_id: Optional[str] = None) -> Optional[str]:
    meta = {"name": name, "groupId": GUILD_ID, "role": role}
    if supervisor_id:
        meta["supervisorId"] = supervisor_id
    res = _http_json("POST", "/api/terminal", {"meta": meta})
    return res.get("id") if res else None


def get_statuses() -> list:
    res = _http_json("GET", f"/api/status?groupId={GUILD_ID}")
    return res if isinstance(res, list) else []


def get_output_tail(session_id: str, lines: int = 30) -> list:
    res = _http_json("GET", f"/api/terminal/{session_id}/output?lines={lines}")
    return res.get("lines", []) if res else []


def write_to(session_id: str, body: str) -> None:
    _http_json("POST", f"/api/terminal/{session_id}/write", {"body": body})


def send_message(sender: str, recipient: str, body: str) -> None:
    _http_json(
        "POST", "/api/message",
        {"from": sender, "to": recipient, "type": "dispatch", "body": body},
    )


def cleanup() -> None:
    _http_json("DELETE", f"/api/group/{GUILD_ID}?recursive=true")


def run() -> int:
    if not ensure_alive():
        print("bash-editor not running, abort")
        return 1

    guildmaster = create_mind("guildmaster", "supervisor")
    if guildmaster is None:
        print("guildmaster create failed")
        return 1
    worker = create_mind("worker", "worker", supervisor_id=guildmaster)
    if worker is None:
        cleanup()
        return 1

    send_message(guildmaster, worker, "initial dispatch: run task A")

    for _ in range(MAX_ROUNDS):
        time.sleep(POLL_INTERVAL_SEC)
        for s in get_statuses():
            if s.get("status") == "waiting_confirmation":
                # 末尾を見て対応する応答を組み立てるのは別関数に切り出す
                _tail = get_output_tail(s["id"], 30)
                write_to(s["id"], "y\r")

    cleanup()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run())
```

> **注意**: 上記いずれも **擬似コード**。本書を参照下、`runtime/observatory/` または `runtime/verification/phase-3-dogfooding/` に正式実装するときは、別 issue（Issue #43 配下や新規 issue）で設計レビューを通してから着手する。

---

## 7. 制限とリスク

bash-editor を ai-org-os から利用する際の留意点。ADR-0009 と整合させる。

### 7.1. 仕様変更追従

- bash-editor は ai-org-os 外部のリポジトリ。API は予告なく変わり得る
- 本書は **2026-05-23 スナップショット**。半年ごと（ADR-0009 R1 緩和策）に差分を本書に追記する運用を想定
- 重要な仕様変更（エンドポイント削除、引数互換破壊）は Issue として別途立てる

### 7.2. 依存の方向性

- ai-org-os 本体（Nexus / Mind / 将来の Realm / Warden）は bash-editor に依存しない
- bash-editor との結合は **「あれば補完、無くても動く」** に限定する
- バイナリ依存（npm パッケージ、Node.js ランタイム）を ai-org-os 側に持ち込まない（ADR-0005 / ADR-0009 §2）

### 7.3. 結合度

- 「使えるものは使う」が広く解釈されて bash-editor 前提の運用が広がるリスク（ADR-0009 R3）
- 新規流用は必ず ADR-0009 「Decision §2」に列挙された対象に限定し、それ以外は別 ADR で追加する
- 本書を「実装許可証」と読まないこと。本書は **参照資料**

### 7.4. localhost-only セキュリティ

- bash-editor は DNS rebinding 対策で `127.0.0.1` / `localhost` / `[::1]` 以外の Host / Origin を 403 で拒否する（`server.js` §0 上部）
- ai-org-os から叩く HTTP クライアントは `Host: localhost` ヘッダが必須（urllib は既定で付くが、明示しておくと安全）
- リモートホストから bash-editor を叩く構成は **未サポート**（SSH トンネル等で localhost に持ち込むのが正攻法）

### 7.5. Supervisor / Worker スケーラビリティ

- bash-editor の 5 秒ポーリング（`setInterval` で `detectConfirmPrompt` を全 session に対して走らせる）は session 数に対して O(N)
- 数百セッションになるとポーリングコストが顕在化する可能性。Phase 5 で Realm 内 Mind 数が増える場合は別途検証が必要
- supervisor 通知は 30 秒に 1 回までで抑止されているため、通知ストームは起きない設計
- Issue #47（[Discussion F] 失敗・暴走の扱い）と合わせて「Mind が waiting_confirmation のまま放置された場合の挙動」を将来議論する余地

---

## 8. 関連

### 8.1. ai-org-os 内部

- [ADR-0009: bash-editor / claude-team との関係性と流用方針](../adr/0009-relationship-with-bash-editor-and-claude-team.md) — 本書の上位方針。fork / submodule しない決定、部品流用と並行運用の境界
- [ADR-0002: 用語と「メタのメタ」構造の確定](../adr/0002-vocabulary-and-meta-meta-structure.md) — Mind / Guild / Warden / Observatory の定義
- [ADR-0006: Phase 5（Realm + Warden + Guildmaster）の設計案](../adr/0006-phase-5-realm-warden-guildmaster.md) — Phase 5 観測コンテキスト
- `runtime/observatory/` — Observatory v0.1 実装。`pure.py` が bash-editor `lib/pure.js` の Python ポート
- `runtime/verification/phase-3-dogfooding/` — Phase 3 dogfooding 検証。方式 E（bash-editor 併用）の追記候補

### 8.2. GitHub Issues

- Issue #43 — [Observatory] v0.2〜v1.0 ロードマップの実装。シナリオ B / C の実装は本 issue 配下で進める想定
- Issue #47 — [Discussion F] 失敗・暴走の扱い。Mind が waiting_confirmation のまま放置されたときの方針議論
- Issue #49 — 本書の起票元（closes 対象）

### 8.3. 外部リポジトリ

- `local-multi-window-bash-editor`（本書の対象） — `C:\Users\kokoro068\git\local-multi-window-bash-editor`
  - `server.js`（HTTP API + MCP server 実装）
  - `lib/pure.js`（依存ゼロの判定純粋関数群）
  - `lib/group-tree.js`（group 階層とアクセス制御）
  - `docs/supervisor-guide.md`（MCP resource として配信される運用ガイド）

---

> **再掲**: 本書は **参照資料**。**実装は本書の参照下、別 issue で行う**。bash-editor を ai-org-os に組み込む決定は ADR-0009 が SSOT であり、本書はその決定下で API スナップショットを保管するだけのドキュメント。
