# Install: web-service-team-bundle v0

> 想定読者: 自社リポジトリへこのバンドルを導入する技術リード。

v0.1 で実体ファイルが揃った状態を前提とした移植手順の骨子。

## 手順（最小 5 ステップ）

1. **ディレクトリ初期化**: 自社リポジトリのトップに `org/`, `teams/`, `projects/` の 3 ディレクトリを作成する。（Build）

2. **チーム配下にバンドルを展開**: 本バンドルの `mission.md` / `rules.md` / `roles/` / `workflow.md` / `templates/` を、自社の `teams/<your-team>/` 配下へコピーする。（Build / Share）

3. **コア規約を取り込み**: `L2_product-core-os/` から `org/charter.md` と `org/global_rules.md` を自社リポジトリの `org/` 配下へコピーする。これはバンドルが依存する基盤であり、自社運用中も差分追従する。（Maintain）

4. **最初の brief を起票**: `projects/<your-project>/brief.md` を `templates/` をベースに作成し、対象プロダクトの目的・スコープ・成功条件を書く。（Build）

5. **人間承認者を決め、初回レビュー**: チャーターと brief に対する最終承認者（人間）を 1 名以上決定し、初回レビュー会を実施する。これ以降の学習ループは `teams/<your-team>/memory/` に記録する。（Maintain / Share）

6. **カスタマイズ実施**: `customize.md` を参照し、各実体ファイル内の `<!-- CUSTOMIZE: ... -->` マーカーを置換する。Must（チーム名・対象ドメイン・最終承認者・人数・リリース頻度）→ Should（ロール命名・workflow ステップ・Metrics 閾値）→ May（テンプレ追記・追加ロール・rules 拡張）の順に**別 PR** へ分けて段階的に進めること。Must の PR がマージできれば最小運用は開始できる。（Build / Maintain）

## 補足

- 各ステップ末尾の括弧は、Product Vision の 3 軸（Build / Maintain / Share）への寄与を示す。
- 差分マージ指針は v0.3 で明示する予定（`CHANGELOG.md` 参照）。カスタマイズポイントは v0.2 で `customize.md` として収録済み。
- 各実体ファイル内の `関連: Product Vision` 等の相対リンクは、ターゲットリポジトリへの移植後の位置（`teams/<team>/...` 等）で正しく解決するよう設計されている。バンドル内ディレクトリで直接開くと一部リンクが解決しない場合があるが、移植後は問題なく機能する。
