"""
test_workspace.py — workspace.py のユニットテスト (Phase 5d-1 / ADR-0022)。

検証する性質:
- happy path: 必須フィールド揃った template が parse / load される
- 必須フィールド欠落で WorkspaceValidationError
- schema_version 違反で WorkspaceValidationError
- vcs / mode の値違反で WorkspaceValidationError
- vcs=git で repo / mode 欠落は WorkspaceValidationError
- 名前と workspace フィールドの不一致を検出
- 2 layer overlay: home が template を mask
- shadow consistency: 上位 source malformed なら listing 除外 + 下位 fallback 無し
- list_workspaces のソート / 不正名 skip
- CLI smoke (list / show / check の戻り値)

標準ライブラリのみ (unittest + tempfile)。
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

from workspace import (  # noqa: E402
    ALLOWED_MODE,
    ALLOWED_VCS,
    DEFAULT_WORKSPACE_NAME,
    WorkspaceNotFoundError,
    WorkspaceTemplate,
    WorkspaceValidationError,
    is_registered,
    list_workspaces,
    load_workspace,
    main,
)


def _write_workspace(
    workspaces_dir: Path,
    name: str,
    *,
    schema_version: str = "0.1",
    vcs: str = "none",
    repo: str = "",
    mode: str = "",
    branch_prefix: str = "",
    allowed_cli: str = "",
    purpose: str = "test workspace",
    workspace_field: str | None = None,
    extra_fields: dict[str, str] | None = None,
    omit: tuple[str, ...] = (),
) -> Path:
    """Helper: write `<workspaces_dir>/<name>.md` with given frontmatter."""
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    fm: dict[str, str] = {
        "workspace": workspace_field if workspace_field is not None else name,
        "schema_version": schema_version,
        "vcs": vcs,
        "repo": repo,
        "mode": mode,
        "branch_prefix": branch_prefix,
        "allowed_cli": allowed_cli,
        "purpose": purpose,
    }
    if extra_fields:
        fm.update(extra_fields)
    for key in omit:
        fm.pop(key, None)
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Workspace: {name}")
    path = workspaces_dir / f"{name}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class TestLoadWorkspaceHappyPath(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_none_vcs_no_repo_ok(self) -> None:
        _write_workspace(self.dir, "default", vcs="none")
        w = load_workspace("default", workspaces_dir=self.dir)
        self.assertIsInstance(w, WorkspaceTemplate)
        self.assertEqual(w.name, "default")
        self.assertEqual(w.vcs, "none")
        self.assertEqual(w.repo, "")
        self.assertEqual(w.mode, "")
        self.assertEqual(w.schema_version, "0.1")

    def test_git_worktree_with_repo_ok(self) -> None:
        _write_workspace(
            self.dir, "developer-default",
            vcs="git", repo="/home/me/proj", mode="worktree",
            branch_prefix="mind",
            allowed_cli="[git, gh]",
        )
        w = load_workspace("developer-default", workspaces_dir=self.dir)
        self.assertEqual(w.vcs, "git")
        self.assertEqual(w.repo, "/home/me/proj")
        self.assertEqual(w.mode, "worktree")
        self.assertEqual(w.branch_prefix, "mind")
        self.assertEqual(w.allowed_cli, ("git", "gh"))


class TestValidationErrors(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_invalid_name_format(self) -> None:
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("../escape", workspaces_dir=self.dir)
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("has space", workspaces_dir=self.dir)

    def test_no_frontmatter(self) -> None:
        (self.dir / "x.md").write_text("just body, no frontmatter\n", encoding="utf-8")
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("x", workspaces_dir=self.dir)

    def test_missing_required_field(self) -> None:
        _write_workspace(self.dir, "x", omit=("vcs",))
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("x", workspaces_dir=self.dir)
        _write_workspace(self.dir, "y", omit=("schema_version",))
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("y", workspaces_dir=self.dir)
        _write_workspace(self.dir, "z", omit=("workspace",))
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("z", workspaces_dir=self.dir)

    def test_workspace_field_name_mismatch(self) -> None:
        _write_workspace(self.dir, "x", workspace_field="y")
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("x", workspaces_dir=self.dir)

    def test_unsupported_schema_version(self) -> None:
        _write_workspace(self.dir, "x", schema_version="0.2")
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("x", workspaces_dir=self.dir)

    def test_invalid_vcs_value(self) -> None:
        _write_workspace(self.dir, "x", vcs="svn")
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("x", workspaces_dir=self.dir)

    def test_invalid_mode_value(self) -> None:
        _write_workspace(self.dir, "x", vcs="git", repo="/r", mode="weird")
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("x", workspaces_dir=self.dir)

    def test_git_vcs_requires_repo(self) -> None:
        _write_workspace(self.dir, "x", vcs="git", mode="worktree", repo="")
        with self.assertRaises(WorkspaceValidationError) as ctx:
            load_workspace("x", workspaces_dir=self.dir)
        self.assertIn("repo", str(ctx.exception))

    def test_git_vcs_requires_mode(self) -> None:
        _write_workspace(self.dir, "x", vcs="git", repo="/r", mode="")
        with self.assertRaises(WorkspaceValidationError) as ctx:
            load_workspace("x", workspaces_dir=self.dir)
        self.assertIn("mode", str(ctx.exception))

    def test_not_found(self) -> None:
        with self.assertRaises(WorkspaceNotFoundError):
            load_workspace("ghost", workspaces_dir=self.dir)


class TestOverlay(unittest.TestCase):
    """ADR-0020 と同じ 2 layer overlay の挙動を検証する。

    `_search_dirs` の挙動を AI_ORG_OS_WORKSPACES_DIR で override せず、
    home_workspaces_dir + template_workspaces_dir のセットで切り替える。
    本テストは AI_ORG_OS_HOME を tmp に向けた状態で、本物の templates/
    と混ぜないように **workspaces_dir 引数で全制御** する形にする
    (single source override) 単体テストと、env を使った overlay テストを
    分ける。
    """

    def setUp(self) -> None:
        self.tmp_home = tempfile.TemporaryDirectory()
        self.tmp_templates = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp_home.name)
        self.templates = Path(self.tmp_templates.name)
        self._old_env = os.environ.get("AI_ORG_OS_WORKSPACES_DIR")
        # 本テストは workspaces_dir 引数で精密制御するため env はクリア
        os.environ.pop("AI_ORG_OS_WORKSPACES_DIR", None)

    def tearDown(self) -> None:
        if self._old_env is not None:
            os.environ["AI_ORG_OS_WORKSPACES_DIR"] = self._old_env
        self.tmp_home.cleanup()
        self.tmp_templates.cleanup()

    def test_single_source_override(self) -> None:
        """workspaces_dir 引数を渡すと overlay を無視してその dir 単体で動く。
        """
        _write_workspace(self.home, "default", vcs="none")
        w = load_workspace("default", workspaces_dir=self.home)
        self.assertEqual(w.path.parent, self.home)


class TestListWorkspacesShadow(unittest.TestCase):
    """shadow consistency: malformed 上位は listing 除外 + 下位フォールバック禁止。
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _silent_list(self) -> list[str]:
        with redirect_stderr(io.StringIO()):
            return list_workspaces(workspaces_dir=self.dir)

    def test_empty_dir(self) -> None:
        self.assertEqual(self._silent_list(), [])

    def test_lists_valid_only_sorted(self) -> None:
        _write_workspace(self.dir, "default", vcs="none")
        _write_workspace(self.dir, "developer-default",
                          vcs="git", repo="/r", mode="worktree")
        _write_workspace(self.dir, "docs-only", vcs="none")
        result = self._silent_list()
        self.assertEqual(
            result,
            ["default", "developer-default", "docs-only"],
        )

    def test_malformed_file_hidden_from_listing(self) -> None:
        _write_workspace(self.dir, "good", vcs="none")
        # malformed: workspace 名と field 不一致
        _write_workspace(self.dir, "bad", workspace_field="other")
        result = self._silent_list()
        self.assertEqual(result, ["good"])
        # 直接 load も fail する (= list と挙動が一致)
        with self.assertRaises(WorkspaceValidationError):
            load_workspace("bad", workspaces_dir=self.dir)

    def test_invalid_filename_skipped(self) -> None:
        _write_workspace(self.dir, "good", vcs="none")
        # 不正なファイル名 (regex 違反) は無視される
        (self.dir / "has space.md").write_text(
            "---\nworkspace: hs\nschema_version: 0.1\nvcs: none\n---\n",
            encoding="utf-8",
        )
        result = self._silent_list()
        self.assertEqual(result, ["good"])

    def test_non_md_files_ignored(self) -> None:
        _write_workspace(self.dir, "good", vcs="none")
        (self.dir / "README.txt").write_text("not a workspace", encoding="utf-8")
        result = self._silent_list()
        self.assertEqual(result, ["good"])


class TestShadowAcrossSources(unittest.TestCase):
    """2 source overlay で「上位 malformed → 下位 fallback 禁止」を検証する。

    workspaces_dir 引数では 1 source しか制御できないので、
    AI_ORG_OS_WORKSPACES_DIR env trick を使わず、_search_dirs と
    workspaces_dir=None を組み合わせて home + templates 模倣する。

    本クラスは workspace._search_dirs を直に検証せず、`home`/`templates`
    の挙動を `_home_workspaces_dir` / `_template_workspaces_dir` の戻り値
    を mock することで実現する。
    """

    def setUp(self) -> None:
        self.tmp_home = tempfile.TemporaryDirectory()
        self.tmp_templates = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp_home.name)
        self.templates = Path(self.tmp_templates.name)
        # 同梱 templates dir を mock 化
        import workspace as _ws  # noqa: PLC0415
        self._orig_home = _ws._home_workspaces_dir
        self._orig_tpl = _ws._template_workspaces_dir
        _ws._home_workspaces_dir = lambda: self.home
        _ws._template_workspaces_dir = lambda: self.templates
        # env クリア
        self._old_env = os.environ.get("AI_ORG_OS_WORKSPACES_DIR")
        os.environ.pop("AI_ORG_OS_WORKSPACES_DIR", None)

    def tearDown(self) -> None:
        import workspace as _ws  # noqa: PLC0415
        _ws._home_workspaces_dir = self._orig_home
        _ws._template_workspaces_dir = self._orig_tpl
        if self._old_env is not None:
            os.environ["AI_ORG_OS_WORKSPACES_DIR"] = self._old_env
        self.tmp_home.cleanup()
        self.tmp_templates.cleanup()

    def _silent_list(self) -> list[str]:
        with redirect_stderr(io.StringIO()):
            return list_workspaces()

    def test_home_overrides_template(self) -> None:
        """同名が両 source にあれば home が勝つ (load の path で確認)。"""
        _write_workspace(self.home, "default", vcs="git", repo="/h", mode="worktree")
        _write_workspace(self.templates, "default", vcs="none")
        with redirect_stderr(io.StringIO()):
            w = load_workspace("default")
        self.assertEqual(w.vcs, "git")
        self.assertEqual(w.repo, "/h")
        self.assertEqual(w.path.parent, self.home)

    def test_malformed_home_shadows_template(self) -> None:
        """上位 (home) が malformed なら下位 (templates) の同名にも fallback しない。
        list_workspaces からは除外、is_registered も False。
        """
        _write_workspace(
            self.home, "default", workspace_field="other",  # malformed
        )
        _write_workspace(self.templates, "default", vcs="none")  # 正常
        # list には現れない
        self.assertEqual(self._silent_list(), [])
        # is_registered も False (= 「list と load の挙動が一致」)
        with redirect_stderr(io.StringIO()):
            self.assertFalse(is_registered("default"))

    def test_template_only_visible_when_home_absent(self) -> None:
        """home に同名が無ければ templates が見える。"""
        _write_workspace(self.templates, "developer-default",
                          vcs="git", repo="/r", mode="worktree")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(self._silent_list(), ["developer-default"])
            self.assertTrue(is_registered("developer-default"))


class TestCli(unittest.TestCase):
    """list / show / check CLI subcommands のスモークテスト。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # CLI は AI_ORG_OS_WORKSPACES_DIR env で source override 可
        self._old_env = os.environ.get("AI_ORG_OS_WORKSPACES_DIR")
        os.environ["AI_ORG_OS_WORKSPACES_DIR"] = str(self.dir)

    def tearDown(self) -> None:
        if self._old_env is None:
            os.environ.pop("AI_ORG_OS_WORKSPACES_DIR", None)
        else:
            os.environ["AI_ORG_OS_WORKSPACES_DIR"] = self._old_env
        self.tmp.cleanup()

    def _capture(self, fn) -> tuple[int, str, str]:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = fn()
        return rc, out_buf.getvalue(), err_buf.getvalue()

    def test_list_empty(self) -> None:
        rc, out, _ = self._capture(lambda: main(["list"]))
        self.assertEqual(rc, 0)
        self.assertIn("(no workspaces)", out)

    def test_list_shows_names(self) -> None:
        _write_workspace(self.dir, "default", vcs="none")
        _write_workspace(self.dir, "developer-default",
                          vcs="git", repo="/r", mode="worktree")
        rc, out, _ = self._capture(lambda: main(["list"]))
        self.assertEqual(rc, 0)
        self.assertIn("default", out)
        self.assertIn("developer-default", out)

    def test_show_existing(self) -> None:
        _write_workspace(self.dir, "default", vcs="none", purpose="hello")
        rc, out, _ = self._capture(lambda: main(["show", "default"]))
        self.assertEqual(rc, 0)
        self.assertIn("vcs:", out)
        self.assertIn("none", out)
        self.assertIn("hello", out)

    def test_show_missing(self) -> None:
        rc, _, err = self._capture(lambda: main(["show", "ghost"]))
        self.assertEqual(rc, 3)
        self.assertIn("ghost", err)

    def test_check_registered(self) -> None:
        _write_workspace(self.dir, "default", vcs="none")
        rc, out, _ = self._capture(lambda: main(["check", "default"]))
        self.assertEqual(rc, 0)
        self.assertIn("registered", out)

    def test_check_unknown(self) -> None:
        rc, _, _ = self._capture(lambda: main(["check", "ghost"]))
        self.assertEqual(rc, 3)

    def test_check_malformed(self) -> None:
        _write_workspace(self.dir, "bad", workspace_field="other")
        rc, _, _ = self._capture(lambda: main(["check", "bad"]))
        self.assertEqual(rc, 4)


class TestQuotedScalarSupport(unittest.TestCase):
    """Codex P2 (#99): ADR-0022 例のように引用符付き scalar (\"0.1\") も受理する。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_double_quoted_schema_version(self) -> None:
        path = self.dir / "default.md"
        path.write_text(
            '---\n'
            'workspace: default\n'
            'schema_version: "0.1"\n'
            'vcs: none\n'
            '---\n',
            encoding="utf-8",
        )
        w = load_workspace("default", workspaces_dir=self.dir)
        self.assertEqual(w.schema_version, "0.1")
        self.assertEqual(w.vcs, "none")

    def test_single_quoted_scalar(self) -> None:
        path = self.dir / "dev.md"
        path.write_text(
            "---\n"
            "workspace: dev\n"
            "schema_version: '0.1'\n"
            "vcs: 'git'\n"
            "repo: '/home/me/proj'\n"
            "mode: 'worktree'\n"
            "---\n",
            encoding="utf-8",
        )
        w = load_workspace("dev", workspaces_dir=self.dir)
        self.assertEqual(w.schema_version, "0.1")
        self.assertEqual(w.vcs, "git")
        self.assertEqual(w.repo, "/home/me/proj")
        self.assertEqual(w.mode, "worktree")

    def test_unquoted_still_works(self) -> None:
        """既存の unquoted 形式も維持されること (regression 防止)。"""
        path = self.dir / "mixed.md"
        path.write_text(
            "---\n"
            "workspace: mixed\n"
            "schema_version: 0.1\n"
            "vcs: git\n"
            'repo: "/home/me/q"\n'  # quoted の混在ケース
            "mode: worktree\n"
            "---\n",
            encoding="utf-8",
        )
        w = load_workspace("mixed", workspaces_dir=self.dir)
        self.assertEqual(w.schema_version, "0.1")
        self.assertEqual(w.repo, "/home/me/q")


class TestRepoEnvExpansion(unittest.TestCase):
    """Codex P2 (#100): ADR-0022 §2 で documented な env var / ~ 形式の repo を
    workspace.py 側で展開する。
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # 環境変数 fixture
        self._old_target_repo = os.environ.get("AI_ORG_OS_TEST_TARGET_REPO")
        os.environ["AI_ORG_OS_TEST_TARGET_REPO"] = "/home/test/myrepo"

    def tearDown(self) -> None:
        if self._old_target_repo is None:
            os.environ.pop("AI_ORG_OS_TEST_TARGET_REPO", None)
        else:
            os.environ["AI_ORG_OS_TEST_TARGET_REPO"] = self._old_target_repo
        self.tmp.cleanup()

    def test_dollar_var_expansion(self) -> None:
        _write_workspace(
            self.dir, "dev", vcs="git",
            repo="$AI_ORG_OS_TEST_TARGET_REPO", mode="worktree",
        )
        w = load_workspace("dev", workspaces_dir=self.dir)
        self.assertEqual(w.repo, "/home/test/myrepo")

    def test_braced_var_expansion(self) -> None:
        _write_workspace(
            self.dir, "dev", vcs="git",
            repo="${AI_ORG_OS_TEST_TARGET_REPO}/sub", mode="worktree",
        )
        w = load_workspace("dev", workspaces_dir=self.dir)
        self.assertEqual(w.repo, "/home/test/myrepo/sub")

    def test_tilde_expansion(self) -> None:
        _write_workspace(
            self.dir, "dev", vcs="git",
            repo="~/projects/foo", mode="worktree",
        )
        w = load_workspace("dev", workspaces_dir=self.dir)
        self.assertNotIn("~", w.repo)
        self.assertTrue(w.repo.endswith("projects/foo")
                        or w.repo.endswith("projects\\foo"))

    def test_undefined_var_left_literal(self) -> None:
        """未定義 env var は literal を残す。spawn-mind 側の dir 存在 check で
        configuration error として顕在化する (= 沈黙の失敗を作らない)。"""
        _write_workspace(
            self.dir, "dev", vcs="git",
            repo="$AI_ORG_OS_TEST_UNDEFINED_VAR_XYZ/path", mode="worktree",
        )
        w = load_workspace("dev", workspaces_dir=self.dir)
        # expandvars は未定義 var を literal で残す
        self.assertIn("$AI_ORG_OS_TEST_UNDEFINED_VAR_XYZ", w.repo)

    def test_no_expansion_for_plain_path(self) -> None:
        """普通の絶対 path は変更されない。"""
        _write_workspace(
            self.dir, "dev", vcs="git",
            repo="/absolute/path/no/vars", mode="worktree",
        )
        w = load_workspace("dev", workspaces_dir=self.dir)
        self.assertEqual(w.repo, "/absolute/path/no/vars")


class TestConstants(unittest.TestCase):
    """値域定数の verify (将来拡張時の sanity check)。"""

    def test_allowed_vcs(self) -> None:
        self.assertIn("git", ALLOWED_VCS)
        self.assertIn("none", ALLOWED_VCS)

    def test_allowed_mode_includes_empty(self) -> None:
        self.assertIn("worktree", ALLOWED_MODE)
        self.assertIn("shared", ALLOWED_MODE)
        self.assertIn("", ALLOWED_MODE)  # vcs=none で許容

    def test_default_name(self) -> None:
        self.assertEqual(DEFAULT_WORKSPACE_NAME, "default")


if __name__ == "__main__":
    unittest.main()
