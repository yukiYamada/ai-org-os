# Changelog

ai-org-os の **framework foundation** の変更履歴。書式は
[Keep a Changelog](https://keepachangelog.com/) に従う。バージョニングは
[Semantic Versioning](https://semver.org/) に準拠。

ここで扱う「framework version」は `runtime/VERSION` で declare される **コア
の不変項フレームワーク** のバージョン。利用者の組織 (= C 層 manifest:
Kind / Guild / Workspace / Persona / Org) のバージョンとは別物。

## 何を SemVer の MAJOR / MINOR / PATCH に乗せるか

- **MAJOR** — 既存 C 層 manifest を **書き換えないと動かなくなる** 変更
  - 例: axiom (A 層) の追加 / 削除 / 強制条件の変更、Pillar API の互換破壊、
    Mindspace 配置規約 (ADR-0011 / 0020) の変更
  - 必ず migration 手順を本 CHANGELOG に書く
- **MINOR** — **後方互換のまま機能追加**
  - 例: 新 Pillar、新 MCP tool、新 frontmatter field (= 既存 manifest は
    そのまま動く)、新 ADR の追加
- **PATCH** — bug fix / 内部リファクタ / docs
  - C 層 manifest と Mind の振る舞いに観測上の影響を与えない変更

## C 層 manifest の `framework_version` 制約

利用者の Kind / Guild / Workspace / Persona は frontmatter に optional な
`framework_version: ">=X.Y"` constraint を宣言できる。runtime/VERSION が
constraint を満たさない場合、registry validator は WARN を stderr に出す:

```yaml
---
kind: my-special-kind
version: 0.1
status: experimental
framework_version: ">=1.0"
---
```

サポートする operator: `>=` `>` `<=` `<` `==`、カンマ区切りで AND
(`">=1.0,<2.0"`)。詳細は `runtime/pillars/registry/version.py`。

## 自分の org を ai-org-os v1.0 → v1.1 に上げる

1. `git pull origin main` で ai-org-os を更新
2. `python runtime/pillars/registry/version.py print` で新 VERSION を確認
3. 本 CHANGELOG の **\[Unreleased\] / 該当 MINOR 節** の "Breaking" / "Migration"
   をすべて読む
4. 必要なら自分の `~/.ai-org-os/{kinds,guilds,workspaces,personas}/` 配下の
   manifest を migration 手順に従って更新する
5. 再起動 (= 既存 Mind を kill して spawn し直す) で新 VERSION が effective

MAJOR bump 時は `framework_version: ">=X.0"` constraint を持つ既存 manifest が
warning を出す可能性がある。warning ログを確認して constraint を更新する。

## CI bump rule

framework に観測上の変更を入れる PR は本 CHANGELOG の `[Unreleased]` セクション
に entry を追加すること。`runtime/VERSION` の bump は **release commit** で
まとめて行う (= 毎 PR で bump しない、release cadence は維持する側で決める)。

---

## [Unreleased]

(変更を入れた PR は本セクションに entry を追加してください)

### Added
- (TBA)

### Changed
- (TBA)

### Deprecated
- (TBA)

### Removed
- (TBA)

### Fixed
- **[Security P1 #194]** L3 notify: JSON string escaping for Mind-originated fields
  (severity / event / message / actor) to prevent malformed JSON when Mind sends
  quotes / backslashes / control chars. Added `_json_escape_string` helper in
  `mind-loop.sh` (ADR-0021 A 層 field encoding).

### Migration
- (TBA — MAJOR bump 時のみ)

---

## [1.0.0] — 2026-06-08

最初の **framework foundation v2** リリース。Phase 5g.A で primitive 完成度を
上げ、他人が `git clone` で利用可能な状態に。

### Added
- Mind / Realm / Warden / Pillar の不変項フレームワーク (ADR-0001〜0028)
- C 層 manifest の overlay lookup と schema validation
  (`templates/<category>/` ← `$AI_ORG_OS_HOME/<category>/`)
- Persona composition primitive (`mixins: [...]`)
- Persona contract harness (#168) — declarative ルールの machine-readable 化
  + drift detection
- Framework versioning + `framework_version` constraint (#170、本変更)
- 観察軸: cost meter / L3 notify / Realm health view / Mindspace persistence
  / chain visualization
- 信頼境界 (ADR-0027) と機械強制 (ADR-0028) の安全網

### Notes
- これは最初の MAJOR 版なので migration 手順は無い
- 「**既存利用者いないから**」の段階での publishable 状態として 1.0 と
  declare する (= 後で v0.x に下げる可能性は無い、後方互換が破れたら 2.0)
- 既存 C 層 manifest はすべて `framework_version` 制約を **持たない** が、
  v1.x の間は省略可 (`>=1.0` を暗黙の意味とする)
