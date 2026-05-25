"""
Unit tests for the Guild Catalog (Phase 5c-1 / ADR-0019).

Standard library only (unittest + tempfile). Each test fabricates a temporary
`guilds_dir` / `minds_dir` so the suite is independent from the real
templates/guilds/ and $AI_ORG_OS_HOME/minds/.

設計の根拠:
- ADR-0019 §1 + Phase 5c-2 P1 fix (#91): members は派生情報。authoritative
  source は **Mind registry** (`$AI_ORG_OS_HOME/registry/minds/<name>.md`)
  であり、Mindspace 内 `.mind-meta.md` ではない (caller-writable 排除)。
- ADR-0019 §3: axiom v0.1 = claim-only-own-guild。
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from guild import (  # noqa: E402
    DEFAULT_GUILD,
    GuildManifest,
    GuildNotFoundError,
    GuildValidationError,
    _parse_yaml_list,
    enumerate_members,
    get_mind_guild,
    list_guilds,
    load_manifest,
    main,
    validate_membership,
)


def _write_manifest(
    guilds_dir: Path,
    name: str,
    *,
    schema_version: str = "0.1",
    purpose: str = "test guild",
    kinds: str = "[generic]",
    personas: str = "[designer, implementer, reviewer]",
    guild_field: str | None = None,
    extra_fields: dict[str, str] | None = None,
    omit: tuple[str, ...] = (),
) -> Path:
    """Helper: write `<guilds_dir>/<name>/manifest.md` with the given frontmatter.

    `guild_field` lets a test deliberately set the `guild:` value to something
    other than `<name>` (e.g., to test the mismatch check).
    """
    dir_path = guilds_dir / name
    dir_path.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    fm: dict[str, str] = {
        "guild": guild_field if guild_field is not None else name,
        "schema_version": schema_version,
        "purpose": purpose,
        "kinds": kinds,
        "personas": personas,
    }
    if extra_fields:
        fm.update(extra_fields)
    for key in omit:
        fm.pop(key, None)
    for key, value in fm.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Guild: {name}")
    path = dir_path / "manifest.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_mind_meta(
    registry_dir: Path,
    mind_name: str,
    *,
    guild: str | None = "default",
    persona: str = "designer",
) -> Path:
    """Helper: write `<registry_dir>/<mind_name>.md`.

    Phase 5c-2 P1 fix (#91): authoritative source は Mind registry。引数名
    `registry_dir` で意味を明示する (旧名 minds_dir からの改名)。`guild=None`
    omits the field entirely (back-compat case)。
    """
    registry_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"mind_name: {mind_name}",
        "kind: generic",
        f"persona: {persona}",
    ]
    if guild is not None:
        lines.append(f"guild: {guild}")
    lines.append("---")
    lines.append("")
    path = registry_dir / f"{mind_name}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class TestParseYamlList(unittest.TestCase):
    def test_bracket_form(self) -> None:
        self.assertEqual(_parse_yaml_list("[a, b, c]"), ("a", "b", "c"))

    def test_bracket_no_spaces(self) -> None:
        self.assertEqual(_parse_yaml_list("[a,b,c]"), ("a", "b", "c"))

    def test_bracket_empty(self) -> None:
        self.assertEqual(_parse_yaml_list("[]"), ())

    def test_bracket_only_whitespace(self) -> None:
        self.assertEqual(_parse_yaml_list("[   ]"), ())

    def test_bare_scalar(self) -> None:
        # bare value (not a list) → 単一要素扱い
        self.assertEqual(_parse_yaml_list("generic"), ("generic",))

    def test_empty_string(self) -> None:
        self.assertEqual(_parse_yaml_list(""), ())

    def test_drops_empty_items(self) -> None:
        self.assertEqual(_parse_yaml_list("[a, , b]"), ("a", "b"))


class TestLoadManifest(unittest.TestCase):
    def test_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "default")
            m = load_manifest("default", guilds_dir=base)
            self.assertIsInstance(m, GuildManifest)
            self.assertEqual(m.name, "default")
            self.assertEqual(m.schema_version, "0.1")
            self.assertEqual(m.kinds, ("generic",))
            self.assertEqual(
                m.personas, ("designer", "implementer", "reviewer")
            )

    def test_purpose_optional(self) -> None:
        # purpose は必須リストには無い。空文字で OK。
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "g1", purpose="")
            m = load_manifest("g1", guilds_dir=base)
            self.assertEqual(m.purpose, "")

    def test_missing_manifest_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with self.assertRaises(GuildNotFoundError):
                load_manifest("no-such", guilds_dir=base)

    def test_missing_frontmatter_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "g1").mkdir()
            (base / "g1" / "manifest.md").write_text(
                "# no frontmatter here\n", encoding="utf-8"
            )
            with self.assertRaises(GuildValidationError):
                load_manifest("g1", guilds_dir=base)

    def test_missing_required_field_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "g1", omit=("kinds",))
            with self.assertRaises(GuildValidationError) as ctx:
                load_manifest("g1", guilds_dir=base)
            self.assertIn("kinds", str(ctx.exception))

    def test_schema_version_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "g1", schema_version="0.2")
            with self.assertRaises(GuildValidationError) as ctx:
                load_manifest("g1", guilds_dir=base)
            self.assertIn("schema_version", str(ctx.exception))

    def test_guild_field_must_match_dir_name(self) -> None:
        # frontmatter の guild: が dir 名と違ったら拒否 (file 偽装防御)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "g1", guild_field="something-else")
            with self.assertRaises(GuildValidationError):
                load_manifest("g1", guilds_dir=base)

    def test_invalid_guild_name_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with self.assertRaises(GuildValidationError):
                load_manifest("../escape", guilds_dir=base)
            with self.assertRaises(GuildValidationError):
                load_manifest("has space", guilds_dir=base)
            with self.assertRaises(GuildValidationError):
                load_manifest("", guilds_dir=base)


class TestListGuilds(unittest.TestCase):
    def test_empty_when_dir_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(list_guilds(Path(td) / "nope"), [])

    def test_lists_dirs_with_manifest_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "zeta")
            _write_manifest(base, "alpha")
            _write_manifest(base, "mid")
            self.assertEqual(
                list_guilds(base), ["alpha", "mid", "zeta"]
            )

    def test_skips_dirs_without_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "good")
            (base / "no-manifest").mkdir()
            self.assertEqual(list_guilds(base), ["good"])

    def test_skips_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "good")
            (base / "stray.md").write_text("not a dir", encoding="utf-8")
            self.assertEqual(list_guilds(base), ["good"])

    def test_skips_invalid_names(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "good")
            # 不正な名前の dir を作る (path traversal などはそもそも mkdir
            # できないので、ここは空白入りで代用)
            (base / "has space").mkdir()
            (base / "has space" / "manifest.md").write_text(
                "---\nguild: good\nschema_version: 0.1\nkinds: [generic]\n"
                "personas: [designer]\n---\n",
                encoding="utf-8",
            )
            self.assertEqual(list_guilds(base), ["good"])

    def test_excludes_malformed_manifest(self) -> None:
        """Codex P2 (#88): parse 不能な manifest を持つ Guild は listing から除外。

        理由: list_guilds が「manifest.md がある」だけで listed すると、
        観察者 (observe.py --realm / CLI list) には Guild が見える一方
        spawn-mind / claim_issue は load_manifest で fail する。この不整合は
        利用者を「Guild は在るはずなのに使えない」と困らせるので、parse まで
        含めて検証して見えない化する。
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "ok")
            # schema_version 違反の manifest を持つ Guild
            bad_dir = base / "bad"
            bad_dir.mkdir()
            (bad_dir / "manifest.md").write_text(
                "---\nguild: bad\nschema_version: 9.9\n"
                "kinds: [generic]\npersonas: [designer]\n---\n",
                encoding="utf-8",
            )
            # 必須フィールド欠落の manifest を持つ Guild
            broken_dir = base / "broken"
            broken_dir.mkdir()
            (broken_dir / "manifest.md").write_text(
                "---\nguild: broken\nschema_version: 0.1\n"
                "kinds: [generic]\n---\n",  # personas 欠落
                encoding="utf-8",
            )
            self.assertEqual(list_guilds(base), ["ok"])


class TestValidateMembership(unittest.TestCase):
    def test_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "default")
            m = validate_membership(
                "default",
                kind="generic",
                persona="designer",
                guilds_dir=base,
            )
            self.assertEqual(m.name, "default")

    def test_unknown_guild_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with self.assertRaises(GuildNotFoundError):
                validate_membership(
                    "no-such", kind="generic", persona="designer",
                    guilds_dir=base,
                )

    def test_kind_not_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "g1", kinds="[generic]")
            with self.assertRaises(GuildValidationError) as ctx:
                validate_membership(
                    "g1", kind="specialist", persona="designer",
                    guilds_dir=base,
                )
            self.assertIn("kind", str(ctx.exception))

    def test_persona_not_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _write_manifest(base, "g1", personas="[designer]")
            with self.assertRaises(GuildValidationError) as ctx:
                validate_membership(
                    "g1", kind="generic", persona="reviewer",
                    guilds_dir=base,
                )
            self.assertIn("persona", str(ctx.exception))


class TestGetMindGuild(unittest.TestCase):
    def test_returns_explicit_guild(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            minds = Path(td)
            _write_mind_meta(minds, "m1", guild="backend")
            self.assertEqual(get_mind_guild("m1", registry_dir=minds), "backend")

    def test_missing_meta_defaults_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            minds = Path(td)
            self.assertEqual(
                get_mind_guild("ghost", registry_dir=minds), DEFAULT_GUILD
            )

    def test_meta_without_guild_field_defaults(self) -> None:
        # Phase 5c-1 以前に生成された Mind との後方互換
        with tempfile.TemporaryDirectory() as td:
            minds = Path(td)
            _write_mind_meta(minds, "old", guild=None)
            self.assertEqual(
                get_mind_guild("old", registry_dir=minds), DEFAULT_GUILD
            )

    def test_meta_with_empty_guild_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            minds = Path(td)
            _write_mind_meta(minds, "m1", guild="")
            self.assertEqual(
                get_mind_guild("m1", registry_dir=minds), DEFAULT_GUILD
            )


class TestEnumerateMembers(unittest.TestCase):
    def test_collects_minds_with_matching_guild(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            minds = Path(td)
            _write_mind_meta(minds, "a", guild="default")
            _write_mind_meta(minds, "b", guild="backend")
            _write_mind_meta(minds, "c", guild="default")
            self.assertEqual(
                enumerate_members("default", registry_dir=minds), ["a", "c"]
            )
            self.assertEqual(
                enumerate_members("backend", registry_dir=minds), ["b"]
            )

    def test_missing_dir_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                enumerate_members("default", registry_dir=Path(td) / "nope"),
                [],
            )

    def test_skips_non_md_entries(self) -> None:
        """registry dir 内に .md でない file / dir があれば無視する
        (registry は <name>.md のフラットファイル構造)。"""
        with tempfile.TemporaryDirectory() as td:
            minds = Path(td)
            (minds / "no-meta").mkdir()
            (minds / "stray.txt").write_text("not registry", encoding="utf-8")
            _write_mind_meta(minds, "real", guild="default")
            self.assertEqual(
                enumerate_members("default", registry_dir=minds), ["real"]
            )

    def test_meta_without_guild_field_counted_as_default(self) -> None:
        # 旧 Mind は guild: フィールドが無くても default Guild の member。
        with tempfile.TemporaryDirectory() as td:
            minds = Path(td)
            _write_mind_meta(minds, "old", guild=None)
            self.assertEqual(
                enumerate_members("default", registry_dir=minds), ["old"]
            )


class TestRealRuntimeGuilds(unittest.TestCase):
    """Smoke test against the actual `templates/guilds/default/` shipped with
    the repo, to catch regressions in the manifest format itself
    (Phase 5c-1 / ADR-0020 で旧 runtime/guilds/ から移行)。

    `default` Guild はテンプレ層に必ず同梱されているため、`$AI_ORG_OS_HOME/guilds/`
    が空でも overlay の fallback として load_manifest("default") は成功する。
    """

    def test_default_guild_loads(self) -> None:
        m = load_manifest("default")
        self.assertEqual(m.name, "default")
        self.assertEqual(m.schema_version, "0.1")
        self.assertIn("generic", m.kinds)
        self.assertIn("designer", m.personas)

    def test_default_guild_listed(self) -> None:
        self.assertIn("default", list_guilds())


class TestOverlayResolution(unittest.TestCase):
    """Phase 5c-1 / ADR-0020: home (AI_ORG_OS_HOME/guilds) → templates の overlay。"""

    def setUp(self) -> None:
        # 既存環境変数を退避
        self._old_home = os.environ.pop("AI_ORG_OS_HOME", None)
        self._old_guilds = os.environ.pop("AI_ORG_OS_GUILDS_DIR", None)
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        os.environ["AI_ORG_OS_HOME"] = str(self.home)

    def tearDown(self) -> None:
        os.environ.pop("AI_ORG_OS_HOME", None)
        os.environ.pop("AI_ORG_OS_GUILDS_DIR", None)
        if self._old_home is not None:
            os.environ["AI_ORG_OS_HOME"] = self._old_home
        if self._old_guilds is not None:
            os.environ["AI_ORG_OS_GUILDS_DIR"] = self._old_guilds
        self.tmp.cleanup()

    def test_home_empty_falls_back_to_templates(self) -> None:
        """home が空でも templates 同梱の default が見える。"""
        m = load_manifest("default")
        self.assertEqual(m.name, "default")
        # path は templates 側を指していること
        self.assertIn("templates", str(m.path).replace("\\", "/"))

    def test_home_overlay_shadows_templates(self) -> None:
        """同名 Guild を home に作ると templates の同名は隠れる (overlay)。"""
        # default Guild を home 側で再定義 (purpose を変えて区別)
        home_guilds = self.home / "guilds" / "default"
        home_guilds.mkdir(parents=True)
        (home_guilds / "manifest.md").write_text(
            "---\n"
            "guild: default\n"
            "schema_version: 0.1\n"
            "purpose: HOME OVERRIDE\n"
            "kinds: [generic]\n"
            "personas: [designer]\n"
            "---\n",
            encoding="utf-8",
        )
        m = load_manifest("default")
        self.assertEqual(m.purpose, "HOME OVERRIDE")
        self.assertIn(
            str(self.home).replace("\\", "/"),
            str(m.path).replace("\\", "/"),
        )

    def test_malformed_home_manifest_shadows_templates(self) -> None:
        """Codex P2 (#88): home の同名 manifest が malformed なら templates の
        同名 (parse 可) でも listing / load_manifest にフォールバックさせない。

        registry.list_kinds と同じ shadow consistency。
        """
        # home に default を malformed で再定義 (schema_version 違反)
        home_default = self.home / "guilds" / "default"
        home_default.mkdir(parents=True)
        (home_default / "manifest.md").write_text(
            "---\nguild: default\nschema_version: 9.9\n"
            "kinds: [generic]\npersonas: [designer]\n---\n",
            encoding="utf-8",
        )
        # list_guilds は default を含まない (home が shadow、templates も見ない)
        names = list_guilds()
        self.assertNotIn(
            "default", names,
            "home の malformed manifest が templates をマスクすべき "
            "(shadow 原則、Codex P2 #88)",
        )
        # load_manifest は home の壊れた manifest を返す (= shadow consistency:
        # list に出ない && load も fail という両立、利用者には「home の default
        # を直せ」のシグナルとして一貫)
        with self.assertRaises(GuildValidationError):
            load_manifest("default")

    def test_home_only_guild_visible_via_list(self) -> None:
        """home にだけ存在する Guild も list_guilds に出る。"""
        home_g = self.home / "guilds" / "my-team"
        home_g.mkdir(parents=True)
        (home_g / "manifest.md").write_text(
            "---\n"
            "guild: my-team\n"
            "schema_version: 0.1\n"
            "purpose: home-only\n"
            "kinds: [generic]\n"
            "personas: [designer]\n"
            "---\n",
            encoding="utf-8",
        )
        names = list_guilds()
        self.assertIn("my-team", names)
        self.assertIn("default", names, "templates の default も同時に見える")


class TestCli(unittest.TestCase):
    def _run_main(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_validate_ok(self) -> None:
        # 実 templates/guilds/default/ を使う (CLI は env override 経由でしか
        # guilds_dir を変えられないため)。
        code, out, _ = self._run_main(
            ["validate", "--guild", "default", "--kind", "generic",
             "--persona", "designer"]
        )
        self.assertEqual(code, 0, out)
        self.assertIn("ok", out)

    def test_validate_unknown_guild(self) -> None:
        # Note: 実 runtime に存在しない Guild を指定。env override で空 dir に。
        with tempfile.TemporaryDirectory() as td:
            import os as _os
            old = _os.environ.get("AI_ORG_OS_GUILDS_DIR")
            _os.environ["AI_ORG_OS_GUILDS_DIR"] = td
            try:
                code, _out, err = self._run_main(
                    ["validate", "--guild", "ghost", "--kind", "generic",
                     "--persona", "designer"]
                )
            finally:
                if old is None:
                    _os.environ.pop("AI_ORG_OS_GUILDS_DIR", None)
                else:
                    _os.environ["AI_ORG_OS_GUILDS_DIR"] = old
            self.assertEqual(code, 3)
            self.assertIn("ghost", err)

    def test_validate_kind_not_allowed(self) -> None:
        code, _out, err = self._run_main(
            ["validate", "--guild", "default", "--kind", "specialist",
             "--persona", "designer"]
        )
        self.assertEqual(code, 4)
        self.assertIn("kind", err)

    def test_list_includes_default(self) -> None:
        code, out, _ = self._run_main(["list"])
        self.assertEqual(code, 0)
        self.assertIn("default", out)

    def test_show_default(self) -> None:
        code, out, _ = self._run_main(["show", "default"])
        self.assertEqual(code, 0)
        self.assertIn("default", out)
        self.assertIn("schema_version", out)

    def test_show_unknown_returns_3(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            import os as _os
            old = _os.environ.get("AI_ORG_OS_GUILDS_DIR")
            _os.environ["AI_ORG_OS_GUILDS_DIR"] = td
            try:
                code, _out, _err = self._run_main(["show", "ghost"])
            finally:
                if old is None:
                    _os.environ.pop("AI_ORG_OS_GUILDS_DIR", None)
                else:
                    _os.environ["AI_ORG_OS_GUILDS_DIR"] = old
            self.assertEqual(code, 3)

    def test_members_subcommand(self) -> None:
        # members CLI は env override (AI_ORG_OS_HOME) で registry dir を指せる。
        # Phase 5c-2 P1 fix (#91): registry path = <home>/registry/minds/
        import os as _os
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            registry_minds = base / "registry" / "minds"
            _write_mind_meta(registry_minds, "alice", guild="default")
            _write_mind_meta(registry_minds, "bob", guild="default")
            old = _os.environ.get("AI_ORG_OS_HOME")
            _os.environ["AI_ORG_OS_HOME"] = str(base)
            try:
                code, out, _err = self._run_main(["members", "default"])
            finally:
                if old is None:
                    _os.environ.pop("AI_ORG_OS_HOME", None)
                else:
                    _os.environ["AI_ORG_OS_HOME"] = old
        self.assertEqual(code, 0)
        self.assertIn("alice", out)
        self.assertIn("bob", out)


if __name__ == "__main__":
    unittest.main()
