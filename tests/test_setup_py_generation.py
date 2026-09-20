"""The Cython build writes its own setup.py from pyproject.toml. These tests pin
what that file must carry so a field added to pyproject cannot be silently
dropped from the wheel metadata."""
import ast
from pathlib import Path

import tomlkit

from pkg_deploy.build import CythonBuildStrategy, DeployConfig

PYPROJECT = """
[project]
name = "demo"
version = "1.2.3"
description = "demo package"
requires-python = ">=3.12"
dependencies = ["sqlalchemy", "asyncpg"]

[project.optional-dependencies]
clickhouse = ["clickhouse-connect[async]>=1.0,<2.0"]
mssql = ["pyodbc", "aioodbc"]
all = ["demo[clickhouse,mssql]"]
"""


def _config(tmp_path: Path) -> DeployConfig:
    (tmp_path / "src" / "demo").mkdir(parents=True)
    (tmp_path / "src" / "demo" / "__init__.py").write_text("")
    return DeployConfig(
        package_name="demo",
        project_dir=tmp_path,
        package_dir=tmp_path / "src" / "demo",
        package_entry="src",
        source_root="src",
        pyproject_path=tmp_path / "pyproject.toml",
        version_type="patch",
        new_version="1.2.3",
        use_cython=True,
        use_cibuildwheel=False,
        use_minifier=False,
        is_uv_venv=False,
        repository_name="pypi",
    )


def _generate(tmp_path: Path, pyproject: str = PYPROJECT) -> tuple[str, ast.Module]:
    CythonBuildStrategy.create_setup_py_for_cython(_config(tmp_path), tomlkit.parse(pyproject))
    source = (tmp_path / "setup.py").read_text(encoding="utf-8")
    return source, ast.parse(source)


def _setup_kwargs(tree: ast.Module) -> dict:
    """The keyword arguments of the single setup(...) call, as Python values."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup":
            values = {}
            for kw in node.keywords:
                try:
                    values[kw.arg] = ast.literal_eval(kw.value)
                except ValueError:
                    # e.g. ext_modules=ext_modules, a name bound earlier in the file
                    continue
            return values
    raise AssertionError("no setup() call in generated setup.py")


def test_dependencies_become_install_requires(tmp_path):
    _, tree = _generate(tmp_path)
    assert _setup_kwargs(tree)["install_requires"] == ["sqlalchemy", "asyncpg"]


def test_optional_dependencies_become_extras_require(tmp_path):
    _, tree = _generate(tmp_path)
    assert _setup_kwargs(tree)["extras_require"] == {
        "clickhouse": ["clickhouse-connect[async]>=1.0,<2.0"],
        "mssql": ["pyodbc", "aioodbc"],
        "all": ["demo[clickhouse,mssql]"],
    }


def test_no_extras_when_pyproject_has_none(tmp_path):
    pyproject = PYPROJECT.split("[project.optional-dependencies]")[0]
    source, tree = _generate(tmp_path, pyproject)
    assert "extras_require" not in source
    assert "install_requires" in _setup_kwargs(tree)
