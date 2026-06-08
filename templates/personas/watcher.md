---
persona: watcher
version: 0.1
status: experimental
inbound_topics: []
outbound_topics: [watch-report]
forbidden_ops: []
cycle_budget_seconds_max: 10
trust_layer: L1
---

# Persona: Watcher

> 想定読者: deterministic Kind (`runtime: deterministic`) 用の reference
> Persona。1 cycle = `body` セクションの bash スクリプトを 1 回走らせて exit。
> LLM を呼ばないので確率的挙動なし、credit 消費なし。

この Persona は **`runtime: deterministic` の Kind と組み合わせて使う**。
spawn-mind.sh は本 Persona の最初の ` ```bash ... ``` ` ブロックを
Mindspace の `body.sh` として書き出す。`runtime-deterministic.sh` が 1 cycle で
それを実行する (= LLM は介在しない)。

## body

```bash
#!/usr/bin/env bash
#
# Reference body for the "watcher" persona (= deterministic Kind 用 reference)。
#
# 機能: $AI_ORG_OS_HOME/issues/inbox/ にある pending issue 数を 1 cycle で
#       数えて stdout に出す。実用的な watcher は本 body を差し替えて
#       自前の処理 (lint / test / metric / scan) を書く。
#
set -euo pipefail

HOME_DIR="${AI_ORG_OS_HOME:-${HOME:-${USERPROFILE:-}}/.ai-org-os}"
INBOX_DIR="${HOME_DIR}/issues/inbox"

if [ ! -d "${INBOX_DIR}" ]; then
  echo "[watcher] inbox dir not found: ${INBOX_DIR}"
  exit 0
fi

count=$(find "${INBOX_DIR}" -maxdepth 1 -type f -name '*.md' 2>/dev/null | wc -l | tr -d '[:space:]')
echo "[watcher] pending issues: ${count}"
exit 0
```

## 役割

組織内で **観察判断 (= 決定的観測)** を担う。具体的には:

- 状態の集計 (= pending issue 数 / lint 結果 / test pass 率 等)
- 周期的な scan / health check
- LLM 判断が不要な「数えるだけ」「読むだけ」の役割

## 思考の癖 (= 行動規範)

deterministic Persona には「思考の癖」ではなく **script の振る舞い保証** が
要件:

- **同じ入力に対して同じ出力**: 再現性が deterministic Kind の存在理由
- **exit code は意味を持つ**: 0 = 正常 / 1 = 観測上の異常検出 / 2+ = script 自体の bug
- **副作用は明示**: dispatch 送信 / file 書き込み / network 呼び出しを script 冒頭で documented
- **runtime ≤ cycle_budget_seconds_max**: 上記 frontmatter で宣言した値
  (= 10s) を超えないこと

## してはいけないこと

- LLM API を叩く (= runtime=deterministic の前提を壊す)
- 他 Mind の Mindspace を読み書きする (= Mindspace 不可侵)
- script から無限ループに入る (= 外側 mind-loop.sh が cycle を回す前提)
- dispatch を直接 storage.py 経由で偽造する (= identity binding は body も
  尊重、Persona body から send_dispatch する場合は AI_ORG_OS_MIND_NAME を
  使って自分名義のみ可)

## 信頼境界 (Mind ⇔ 人間、ADR-0027)

deterministic Kind は **script の作者 (= 人間メンテナ)** が L1 を担う。
script に `gh pr merge` / `git push --force` 等を書いてはいけない (= ADR-0027
L1 違反)。レビュー時に script を読んで検査する。

## 関連

- Kind 定義: [`../kinds/deterministic.md`](../kinds/deterministic.md)
- Cycle runner: `runtime/pillars/lifecycle/runtime-deterministic.sh`
- ADR-0027: 信頼境界
