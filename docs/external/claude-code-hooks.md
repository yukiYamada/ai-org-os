# Claude Code hooks 詳細（外部仕様メモ）

> 想定読者: Phase 6 で Axiom enforcement を実装するメンテナ（Warden / `spawn-mind.sh` まわりを触る担当）、および「Mind が暴走したときに物理的に止める層」を設計する意思決定者。

> 本書はあくまで **文書化のみ**。**実装は本書の参照下、別 issue で行う**。
> ハードコーディングや `.claude/settings.json` の同梱は本 PR では行わない。

## 0. 本書の位置づけ

ai-org-os の Mind は Claude Code CLI を 1 プロセスとして起動する（`spawn-mind.sh`）。Claude Code には **hooks** という機構があり、ツール呼び出しの直前・直後など特定のライフサイクル点で外部スクリプトを差し込める。`PreToolUse` フックはツール実行前に発火し、終了コードや JSON 出力で **ツール実行を拒否できる** ため、ai-org-os の Axiom（不変項）をランタイムで enforce する候補機構となる。

ADR-0009 で claude-team の PreToolUse hooks は **「思想参照」** のみと位置づけ、機構そのものを流用しないと決めた。本書は「思想だけでなく、具体的にどう設定すれば何が止まるのか」をファクトベースで残し、Phase 6 着手時の参照資料とする。

仕様は公式ドキュメント（`https://docs.claude.com/en/docs/claude-code/hooks` → `https://code.claude.com/docs/en/hooks` にリダイレクト、2026-05-23 時点）と、claude-team リポジトリの実装を突き合わせて作成した。バージョン依存の挙動は §4 に隔離してある。

---

## 1. PreToolUse hooks の正式仕様サマリ

### 1.1. 設定ファイルの形式

`.claude/settings.json`（プロジェクト共有）、`~/.claude/settings.json`（ユーザー全体）、`.claude/settings.local.json`（gitignore 対象、個人用）、Plugin `hooks/hooks.json` のいずれかに次の構造で記述する。

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm.sh",
            "timeout": 600
          }
        ]
      }
    ]
  }
}
```

- `matcher`: 文字列。tool name にマッチする条件（§1.4）。
- `hooks[].type`: `command` / `http` / `mcp_tool` / `prompt` / `agent` のいずれか。ai-org-os では `command` をメインに使う想定。
- `hooks[].command`: 実行するコマンド。`${CLAUDE_PROJECT_DIR}` は Claude が解決する変数。
- `hooks[].timeout`: 秒。`command` のデフォルトは 600 秒（PreToolUse の場合）。
- `if`: 任意。permission rule 構文で発火条件を絞れる（例: `"Bash(rm *)"`）。

### 1.2. PreToolUse の入力スキーマ（hook script の stdin）

`PreToolUse` フックの stdin には次の JSON が渡る：

```json
{
  "session_id": "abc123",
  "transcript_path": "/home/user/.claude/projects/.../transcript.jsonl",
  "cwd": "/home/user/my-project",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "rm -rf /tmp/build"
  },
  "tool_use_id": "string"
}
```

ツール別の `tool_input` 構造：

| tool_name | 主要フィールド |
|---|---|
| `Bash` | `command`, `description`, `timeout`, `run_in_background` |
| `Write` | `file_path`, `content` |
| `Edit` | `file_path`, `old_string`, `new_string`, `replace_all` |
| `Read` | `file_path` |
| `mcp__<server>__<tool>` | server / tool ごとに異なる |

ai-org-os の Mind は Nexus 経由で `send_dispatch` / `read_inbox` / `ack_dispatch` を呼ぶ。これらは `mcp__nexus__send_dispatch` のような名前で PreToolUse フックから観測できる（§4 で制限あり）。

### 1.3. ツール実行をブロックする 3 通りの方法

公式が示すブロック手段は次の 3 通り。`PreToolUse` で実用上推奨されるのは **(C)** だが、claude-team の実装は **(A) + (B)** を併用しているため両方押さえておく。

#### (A) Exit code 2（blocking error）

```bash
#!/bin/bash
COMMAND=$(jq -r '.tool_input.command' < /dev/stdin)
if echo "$COMMAND" | grep -q 'rm -rf'; then
  echo "Blocked: rm -rf commands are not allowed" >&2
  exit 2
fi
exit 0
```

- exit code 2 で **ツール実行を阻止**し、stderr の内容が Claude へエラーとして返る。
- exit code 0 は「決定なし」、exit code 1 などその他の非ゼロは「non-blocking error」（実行は継続）。
- 例外: `WorktreeCreate` は非ゼロ終了で必ず abort する。

#### (B) Top-level `decision: "block"`

```json
{
  "decision": "block",
  "reason": "This operation is not allowed"
}
```

- 主に `UserPromptSubmit` / `PostToolUse` / `Stop` 系で使われる。
- `PreToolUse` で出すこと自体は可能で claude-team も併用しているが、公式は (C) を推奨。

#### (C) `hookSpecificOutput.permissionDecision`（PreToolUse の主流）

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Destructive command blocked by hook"
  }
}
```

exit code 0 で標準出力に上記 JSON を返すと、Claude 側で permission flow が override される。

### 1.4. decision control フィールド

`hookSpecificOutput.permissionDecision` が取りうる値：

| 値 | 挙動 |
|---|---|
| `"allow"` | ツール実行を承認（permission dialog をスキップ） |
| `"deny"` | ツール実行をブロック |
| `"ask"` | ユーザーへ permission dialog を出す |
| `"defer"` | 通常の permission flow に委ねる |

その他の PreToolUse 固有フィールド：

| フィールド | 用途 |
|---|---|
| `permissionDecisionReason` | deny 時にユーザー / Claude に提示する理由 |
| `updatedInput` | tool_input を書き換える（例: 引数の正規化） |
| `additionalContext` | Claude のコンテキストへ注入する補足文字列 |

トップレベルの共通フィールド：

| フィールド | デフォルト | 用途 |
|---|---|---|
| `continue` | `true` | `false` で Claude 全体の処理を停止 |
| `stopReason` | — | `continue: false` 時に表示するメッセージ |
| `suppressOutput` | `false` | hook の stdout を transcript から隠す |
| `systemMessage` | — | ユーザーに表示する警告 |
| `terminalSequence` | — | OSC ベースのターミナル通知（v2.1.139 以降） |

### 1.5. matcher 構文

| matcher 値 | 解釈 |
|---|---|
| `"*"`, `""`, 省略 | 全 tool にマッチ |
| 英数字 / `_` / `\|` のみ | 厳密文字列、または `\|` 区切りリスト（例: `Edit\|Write`） |
| その他の文字を含む | JavaScript 正規表現として評価（例: `mcp__nexus__.*`） |

MCP tool は必ず `mcp__<server>__<tool>` の命名で観測される。

### 1.6. hook event 一覧（PreToolUse 以外）

実装時の検討材料として、Block 可否を含めて要約する。詳細は公式参照。

| event | 発火タイミング | Block 可？ |
|---|---|---|
| `SessionStart` | セッション開始時 | No |
| `UserPromptSubmit` | ユーザー入力が submit された時 | Yes |
| `PreToolUse` | ツール実行直前 | **Yes** |
| `PostToolUse` | ツール実行成功直後 | No |
| `PostToolUseFailure` | ツール失敗直後 | No |
| `PreCompact` / `PostCompact` | コンテキスト圧縮の前後 | Pre のみ Yes |
| `SubagentStart` / `SubagentStop` | サブエージェント spawn / 終了 | Stop のみ Yes |
| `Stop` | Claude が応答を終えた時 | Yes |
| `SessionEnd` | セッション終了時 | No |

ai-org-os 用途で当面注目するのは `PreToolUse`（実行阻止）と `Stop`（暴走停止条件の差し込み）、必要に応じて `SessionStart`（Mindspace 整合性チェック）。

---

## 2. 実装例（スケッチ）

実装は別 issue で行うが、本書の理解を確実にするため最小スケッチを掲載する。**そのまま `runtime/` に commit してはいけない。**

### 2.1. `.claude/settings.json` の最小例

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-mindspace-escape.sh",
            "timeout": 30
          }
        ]
      },
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-other-mindspace.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

### 2.2. `block-mindspace-escape.sh` のスケッチ

Mind が自分の Mindspace（`runtime/minds/<mind-name>/`）の外で `cd` / `git` / 破壊的コマンドを実行することを防ぐ案。

```bash
#!/usr/bin/env bash
# block-mindspace-escape.sh - Mindspace 外への Bash 実行を阻止する PreToolUse hook
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "${INPUT}" | jq -r '.tool_input.command // ""')
CWD=$(echo "${INPUT}" | jq -r '.cwd // ""')

# Mindspace 判定: runtime/minds/<mind-name>/ 配下で動いていることを期待
if [[ "${CWD}" != *"/runtime/minds/"* ]]; then
  cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "[Axiom] Mind is running outside its Mindspace (cwd=${CWD}). Bash is blocked."
  }
}
EOF
  exit 0
fi

# realm/audit/ や他 Mind の Mindspace への直接書き込みを止める
for pattern in 'realm/audit' 'runtime/minds/' 'rm -rf /' ':(){:|:&};:'; do
  if echo "${COMMAND}" | grep -qF "${pattern}"; then
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "[Axiom] Command touches forbidden path '${pattern}'. Route via Nexus / Warden instead."
  }
}
EOF
    exit 0
  fi
done

exit 0
```

`runtime/minds/` を一律 deny にすると自分の Mindspace 内コマンドまで殺すので、実装時は「**自分の** Mindspace は除外、他 Mind の Mindspace は deny」というロジックを `AI_ORG_OS_MIND_NAME` 環境変数（`spawn-mind.sh` で既に bind 済み、ADR-0008）と突き合わせて書く必要がある。

### 2.3. `block-other-mindspace.sh` のスケッチ

`Edit` / `Write` の `tool_input.file_path` を `AI_ORG_OS_MIND_NAME` と照合し、他 Mind の Mindspace を編集しようとしたら deny する。claude-team の `block-tools.sh` が allowlist 方式の実装例として参考になる。

ポイント：

- `..` を含むパスは無条件で deny（path traversal 対策、claude-team も同じガードを入れている）。
- `jq` が無い環境（Git Bash on Windows など）向けに bash 正規表現の fallback を残す。
- exit code は 0 を返し、JSON で `permissionDecision: "deny"` を出す（公式推奨）。

---

## 3. ai-org-os への適用案

### 3.1. `spawn-mind.sh` が配置すべき hook 設定

`spawn-mind.sh` は現状、Mindspace に `CLAUDE.md` / `.mind-meta.md` / `.mcp.json` を書き込む。ここに `.claude/settings.json` を追加して **Mind 起動時から hooks が有効** な状態にする案。

書き込む内容（案）：

```text
runtime/minds/<mind-name>/
├── CLAUDE.md
├── .mind-meta.md
├── .mcp.json
└── .claude/
    ├── settings.json        ← PreToolUse hooks を宣言
    └── hooks/
        ├── block-mindspace-escape.sh
        ├── block-other-mindspace.sh
        └── block-git-push.sh
```

各 hook script は `runtime/hooks/` にテンプレートを置き、`spawn-mind.sh` がコピーする運用を推奨。テンプレートは Realm 全体で共通になるため、Mind ごとの差分は環境変数（`AI_ORG_OS_MIND_NAME`）で吸収する。

止めたい操作の初期セット（優先度順）：

1. **Mindspace 離脱防止**: `cwd` が `runtime/minds/<own-name>/` 配下でない `Bash` を deny。
2. **他 Mind の Mindspace への Edit/Write 防止**: `tool_input.file_path` をチェック。
3. **`realm/audit/` 直接操作禁止**: Warden 以外は audit log を直接編集できない。
4. **`git push` の要承認化**: claude-team の `block-bash-commands.sh` 同様にパターンマッチで deny し、reason に「`request_dispatch` 経由で Guildmaster の承認を取れ」と書く。
5. **`spawn-mind.sh` の Mind からの直接実行禁止**: 新しい Mind を生やすのは Warden の責務（ADR-0006 の 3 段階プロセス）。

### 3.2. Realm 全体で enforce する案

Phase 5 で Realm が Docker Compose になった場合、`.claude/settings.json` を **bind mount** で各 Mind コンテナへ注入する方式が現実的：

```yaml
services:
  mind-1:
    image: ai-org-os/mind-generic
    volumes:
      - ./runtime/minds/mind-1:/workspace
      - ./runtime/hooks:/workspace/.claude/hooks:ro     # 共通 hook script
      - ./runtime/hooks/settings.json:/workspace/.claude/settings.json:ro
    environment:
      AI_ORG_OS_MIND_NAME: mind-1
```

これにより：

- hook script は Realm 単位で共通管理（更新は Warden 起因の Realm rebuild で反映）。
- Mind 個別の上書きは `.claude/settings.local.json` を Mindspace 内で書ければ可能だが、運用上は禁止する（Axiom violation）。

Phase 6 では Warden が `realm/audit/` から hook 違反のログを取得し、`Persona` の改稿や Axiom refinement の素材にする想定（ADR-0009 §2.4 の learned-patterns 思想に対応）。

---

## 4. 制限と注意点

### 4.1. MCP / container 経由は hook が効かない場面がある

- **MCP tool 自体は hook で観測できる**。命名は `mcp__<server>__<tool>`（例: `mcp__nexus__send_dispatch`）で、matcher は `"mcp__nexus__.*"` のような正規表現で網羅できる。
- ただし **MCP server 内部で起きる動作は hook の管轄外**。Nexus が Dispatch を `runtime/nexus/storage/` に書き込む処理に対して PreToolUse は発火しない。これは Nexus 内（Python 側）で検証する必要がある。
- **subprocess / コンテナ越しの実行も hook の管轄外**。Mind が `Bash` で `docker exec` を打って別コンテナを操作した場合、`docker exec` 自体はフックされるが、コンテナ内の挙動は届かない。
- Mind が `mcp__nexus__send_dispatch` でメッセージを送れば hook で検証できるが、Nexus が `to_mind` の正当性を改めて検証しなければ多層防御にならない（ADR-0008 の identity binding が前提）。

### 4.2. version 依存

- `hookSpecificOutput.permissionDecision` のフィールド名は Claude Code 2.x 系で公式化された。古い CLI バージョンでは `decision: "block"` のみが効くケースがある。
- `terminalSequence` などターミナル制御フィールドは v2.1.139 以降。
- `WorktreeCreate` などのライフサイクル event は v2.x 系で増加中。本書のリストは 2026-05-23 時点。

`spawn-mind.sh` で `claude --version` を確認し、Phase 6 の最低バージョンを `runtime/` 配下に明記する運用を推奨。

### 4.3. 複合コマンドの解析限界

- `if` フィールドの permission rule は「`VAR=value` の prefix を剥がして subcommand 単位で判定」「複雑すぎる場合は常に hook を発火」というセマンティクス。
- 結果として `bash -c "git commit && git push"` のような複合コマンドはサブコマンド単位で照合される保証はなく、**最終的には hook script 側で `;` / `&&` / `|` を考慮した文字列マッチが必要**。
- claude-team の `block-bash-commands.sh` は `grep -qF` の固定文字列マッチを使う割り切り方式。誤検知（プロジェクト名に `git push` の文字列が入っているなど）は手動で許可リストを足す運用。
- 完璧な構文解析は不可能と割り切り、**False positive 寄り（疑わしきは block）** で運用するのが Axiom 思想に合う。

### 4.4. その他の落とし穴

- hook script は **controlling terminal を持たない**（v2.1.139 以降）。`read` / `tty` は使えない。通知は `terminalSequence` フィールドへ。
- timeout デフォルトは `command` で 600 秒だが、PreToolUse のような UX critical path で 10 分待たせるのは事故。本書のスケッチでは 30 秒に短縮した。
- `disableAllHooks: true` を `.claude/settings.local.json` に書かれると **全 hook が無効化される**。Mindspace 内に gitignore 対象の `settings.local.json` を持ち込めないよう、`spawn-mind.sh` 側で生成しない & Realm の bind mount は read-only にする。
- `jq` の有無は環境依存（特に Windows / Git Bash）。フォールバックを必ず実装する。

---

## 5. 推奨実装ステップ

Phase 6 を 2 段階に分ける案を提示する。

### 5.1. Phase 6a: hooks 試験導入（小さく失敗できる範囲）

ゴール: 「hook で 1 つだけ何かを止める」が成立することを確認する。

- 対象を **`Bash` のみ** に絞り、`block-mindspace-escape.sh` だけを実装する。
- 既存 Mind（Phase 3 で立てたもの）に `.claude/settings.json` を手動で配り、`runtime/minds/<own>/` の外で `ls` を叩いてみて block されるかをテストする。
- 結果を `runtime/verification/phase-6a-hooks/README.md`（仮）に記録する。
- 学習: `permission_mode` フィールドの実値、`AI_ORG_OS_MIND_NAME` を hook script から読めるかの確認。

成功条件: 「自 Mindspace 外で `ls` が deny される」「同じ操作を JSON 出力で確認できる」「`exit 2` 経路 / `permissionDecision: "deny"` 経路の両方を試した」。

### 5.2. Phase 6b: Warden 統合

ゴール: Mind 生成時に hook が自動で配置され、違反が `realm/audit/` に蓄積される。

- `spawn-mind.sh` を改修し、`runtime/hooks/` からテンプレートをコピーする。
- Warden が `realm/audit/hook-violations/` を監視し、頻発するパターンを Persona / Axiom 改稿の入力にする（ADR-0009 §2.4 思想の具体化）。
- Realm が Docker Compose 化されている場合は bind mount に切り替え、共通 hook を 1 箇所で管理。
- 失敗系のテスト（hook を意図的に壊して mind が暴走するシナリオ）を `runtime/tests/` に追加。

### 5.3. やらないこと（明示）

- Phase 6 で **MCP server 側の検証を捨てない**。hook はあくまで多層防御の 1 層。Nexus（ADR-0008 の identity binding）と並列で機能させる。
- `disableAllHooks` の挙動を hooks 自身で防ぐことはできない（自己言及問題）。Realm の bind mount を ro にする / `spawn-mind.sh` で個人設定を書かない、という外側の制約で守る。
- ハードコードの allowlist を `runtime/hooks/` に大量に詰め込まない。Axiom の数は最小に保つ（ADR-0001）。

---

## 6. 関連

- [ADR-0009: bash-editor / claude-team との関係性と流用方針](../adr/0009-relationship-with-bash-editor-and-claude-team.md) — claude-team の PreToolUse hooks を「思想参照」する宣言。本書はその参照ファクトの解像度を上げたもの。
- ADR-0006: Phase 5（Realm + Warden + Guildmaster）— `spawn-mind` を Warden 経由にする 3 段階プロセスの原典。本書 §3 と §5.2 の前提。
- ADR-0008: Nexus identity binding — `AI_ORG_OS_MIND_NAME` 環境変数の根拠。本書のスケッチで hook script が読む値。
- Issue #46: Discussion E（人間の位置づけ再考） — Realm の外から人間が監督する場合の責務整理。本書 §3.1 の「`git push` 要承認」は、人間レビューを必要とする境界を hook で enforce する例。
- 外部リポジトリ（参照のみ、ai-org-os は依存しない）:
  - `claude-team/plugins/supervisor-mode/scripts/block-tools.sh` — `Edit` / `Write` の file_path allowlist 実装例。
  - `claude-team/plugins/supervisor-mode/scripts/block-bash-commands.sh` — `Bash` の固定文字列ブロックリスト実装例。
  - `claude-team/plugins/supervisor-mode/hooks/hooks.json` — plugin 形式での `.claude/settings.json` 同等の宣言例。
- 公式ドキュメント: `https://docs.claude.com/en/docs/claude-code/hooks`（2026-05-23 時点で `https://code.claude.com/docs/en/hooks` へ 301 redirect）。

---

> **改めて**: 本書は **文書化のみ**。**`.claude/settings.json` の同梱 / `runtime/hooks/` の実体追加 / `spawn-mind.sh` の改修は、本書を参照しつつ別 issue で行う**。Phase 6a の試験導入 issue を切る際に本書の §5.1 を引用すること。
