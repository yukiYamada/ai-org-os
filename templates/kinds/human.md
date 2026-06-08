---
kind: human
version: 0.1
status: spec
runtime: human
---

# Kind: Human (spec only)

> 想定読者: human-in-the-loop seat (= 「ここの判断は人間がやる」を組織図に
> 明示したい人)。
>
> **本 Kind は Phase 5g.A #169 の spec 段階**。実装は将来の PR で。spawn は
> 完了するが `mind-loop.sh` が「human runtime is not implemented yet」と
> exit する。

## なぜ Human Kind が要るか

ai-org-os の組織は当面「LLM Mind だけ」だが、現実の組織は人間も含む。Human
Kind は **人間 seat を組織図に組み込む primitive**:

- **承認者の seat**: PR merge / release approval を行う人間 (= reviewer
  Persona の "決定者" 側)
- **オペレーターの seat**: 障害対応 / 運用判断を行う人間 (= warden が
  notify-human で叩く先)
- **顧客の seat**: 組織の外部要望を受ける窓口 (= Issue / Slack / Email
  経由で組織に入ってくる人間入力)

人間は **dispatch を非同期で受け取り、応答する** という意味で Mind と同じ
インターフェースを持ちうる (= ADR-0017 layer B、人間も organizational unit)。

## Body Spec (spec only)

| 項目 | 値 | 備考 |
|---|---|---|
| **runtime** | human seat (= ファイル / Slack / Email / CLI) | 応答媒体は環境別 |
| **execution** | `runtime/pillars/lifecycle/runtime-human.py` (= 未実装) | mind-loop.sh が dispatch の存在を観測 |
| **mindspace** | CLAUDE.md は「seat owner 向けの説明書」 | 人間が読む |
| **dispatch** | inbox/outbox は通常通り | 人間は別 UI から書く |
| **lifecycle** | 通常の Mind と同じ | seat owner が席を立つ = kill |

## 主要な設計判断 (= 実装時に決める)

- **応答媒体**:
  - file-based: `<mindspace>/outbox/` に応答 .md を置く → ファイル変更を
    watcher が dispatch に変換 (= 同期的にチェック不要)
  - chatops: Slack / Discord に dispatch を bridge、応答もそこから取り込む
  - cli-tool: `ai-org-os reply <dispatch-id> --body "..."` のような明示的入力
- **timeout / SLA**: 人間応答は非同期で遅い (= 数時間〜日単位)。mind-loop
  cycle period とは noir 違うスケール。fallback path (= guildmaster へ
  escalate) が要る
- **idle 扱い**: 人間 Mind は応答が来ない限り「観測上は idle」。これを
  ADR-0010 (idle なし) とどう整合させるか — 「待ちは idle ではなく `inbox
  poll` で続けている」と解釈する
- **identity binding**: human Mind の dispatch は誰が書いたかを偽れない
  ようにする (= ADR-0008、人間にも適用)。秘密 token / OAuth / 物理鍵 等

## Phase 5g.A における扱い

spec only。spawn-mind.sh は kind=human を見ても spawn は完了するが、
`mind-loop.sh` が「human runtime is not implemented yet」と exit 1 する。

## 関連

- spec only Persona: [`../personas/human-operator.md`](../personas/human-operator.md)
- 連動: ADR-0028 の notify-human signal (L1 logs/notify.jsonl) は本 Kind が
  実装されると **human Mind の inbox に直接届く** ようになりうる

## 関連 ADR

- ADR-0017 — layer A (Warden) / layer B (Mind) — 人間も B 層に住める
- ADR-0021 — A / B / C 軸 (本 Kind は C 層)
- ADR-0022 — kinds / personas / guilds / workspaces
- ADR-0027 — 信頼境界 (Mind ⇔ 人間)
- ADR-0028 — 機械強制 / notify-human L1 logs
