# Customize: web-service-team-bundle v0.2

> 想定読者: 本バンドルを自社へ導入する技術リード／テックリード（受領者）。

## 目的

このバンドルはリファレンス実装（web-service-team）の snapshot だが、固有名詞や数値が随所に残っている。本ファイルを読めば「自社向けに**どこから**書き換え始めればよいか」が 10 分で把握できる。各実体ファイル内には `<!-- CUSTOMIZE: <key> | <hint> -->` 形式のマーカーが埋め込まれており、書き換え対象を機械的に grep できる。

## 必須カスタマイズ（Must）

導入前に必ず置換する項目。これらを書き換えないと自社チームとして機能しない。

- **チーム名**: `web-service-team` を自社チーム名（例: `payments-platform-team`）へ。`teams/<your-team>/` のディレクトリ名・各種参照を統一。
- **対象ドメイン**: `mission.md` の「Web サービス」を自社対象ドメイン（例: 社内 SaaS / データ基盤 / モバイルアプリ）へ。
- **最終承認者名**: `roles/planner_builder_reviewer_contract.md` の「Human が最終決定」箇所に、自社の承認者役職（例: VP of Engineering / Tech Lead 等）を併記。
- **人数規模**: チーム実人数に応じてロール兼任を明記（例: 3 名なら PO=Architect 兼任など）。`mission.md` または独自 README に追記。
- **リリース頻度**: `mission.md` の「短いフィードバックループ」を、自社の実態（日次/週次/隔週）へ具体化。

## 推奨カスタマイズ（Should）

そのままでも動くが、自社文脈に合わせると効果が大きい項目。

- **ロール命名**: `product_owner` / `architect` / `engineer` / `reviewer` を社内呼称（例: PM / TL / SWE / QA）へ。`workflow.md` の標準フローと整合させる。
- **workflow ステップ数**: 現状 6 ステップ。リリース粒度に応じて増減（例: 監査要件があれば security review ステップを追加）。
- **Metrics 閾値**: `workflow.md` の自立実行率・手戻り率などに具体的な目標値（例: 自立実行率 70%）を設定。
- **PR 粒度**: `rules.md` の「1 変更 1 目的」「変更ファイルは原則 3 以下」を自社の妥当ラインへ。
- **レビュー必須範囲**: `rules.md` の「仕様更新なしで挙動変更しない」をプロダクトのリスク階層に応じて緩和/強化。

## 任意カスタマイズ（May）

必要に応じて拡張する項目。導入後の運用で順次追加してよい。

- **テンプレ追記**: `templates/` 配下に自社固有の様式（リリースノート、インシデント報告書など）を追加。
- **追加ロール**: SRE / Security / Data Steward などをチーム実態に応じて `roles/` へ追加。
- **rules 拡張**: 業界規制（個人情報・金融・医療など）に対応する条項を `rules.md` の末尾へ追記。

## カスタマイズの優先順序

Must → Should → May の順に、それぞれ別 PR に分けて段階的に進めることを推奨。

1. **PR #1（Must のみ）**: チーム名・ドメイン・承認者・人数・リリース頻度の置換。最小限で運用開始可能な状態にする。
2. **PR #2（Should）**: ロール命名・workflow ステップ・Metrics 閾値の調整。実運用で違和感が出始めたタイミングで実施。
3. **PR #3 以降（May）**: テンプレ追記・追加ロール・rules 拡張。運用ログが蓄積してから判断する。

各 PR は本バンドルの `rules.md` ルール 1（1 変更 1 目的）に従い、レビュー粒度を保つ。

## 置換マーカーの読み方

各実体ファイル内には Markdown コメント形式で置換ヒントが埋め込まれている。

```
<!-- CUSTOMIZE: <key> | <hint> -->
```

- `<key>`: 置換対象の識別子（例: `domain`, `team-name`, `approver-role`）。
- `<hint>`: 何をどう書き換えるかの短い指示。例示を含むことが多い。

### 置換手順

1. バンドル展開後、`grep -rn "CUSTOMIZE:" teams/<your-team>/` で全マーカーを列挙する。
2. Must レベルの key（`domain`, `team-name`, `approver-role`, `team-size`, `release-cadence`）から順に処理する。
3. 置換完了後、マーカー行は削除してよい（残しても表示に影響しないが、二重置換防止のため削除を推奨）。
4. Should/May は後続 PR で同様に処理する。

マーカーは Markdown コメントなので、レンダリング時に表示崩れはしない。残したままレビュー依頼することも可能。

## 関連

- バンドル構成: [`manifest.md`](./manifest.md)
- 移植手順: [`install.md`](./install.md)
- Product Vision: [`../../docs/product_vision.md`](../../docs/product_vision.md)
