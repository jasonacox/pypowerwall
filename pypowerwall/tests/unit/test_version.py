"""Version contract: the __version__ literal is the single source of truth."""
import ast
import pathlib
import re

import pytest

import pypowerwall


def test_version_is_a_static_literal():
    # pyproject.toml's attr: reads __version__ without importing the package,
    # which only works while it stays a plain string literal in __init__.py
    tree = ast.parse(pathlib.Path(pypowerwall.__file__).read_text(encoding="utf-8"))
    values = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)]
    assert len(values) == 1
    assert isinstance(values[0], ast.Constant) and values[0].value == pypowerwall.__version__


def test_public_version_aliases_unchanged():
    # pypowerwall.version (read by the proxy) and version_tuple are public API
    assert pypowerwall.version == pypowerwall.__version__
    assert all(isinstance(p, int) for p in pypowerwall.version_tuple)


@pytest.mark.parametrize("version_string, expected", [
    ("0.18.0", (0, 18, 0)),
    ("0.18.0b1", (0, 18, 0)),
    ("0.18.0rc1", (0, 18, 0)),
    ("0.18.0.dev0", (0, 18, 0)),
    ("0.18.0.post1", (0, 18, 0)),
    ("0.18.0+local.1", (0, 18, 0)),
    ("not-a-version", ()),
])
def test_release_tuple_never_raises(version_string, expected):
    # version_tuple is derived at import time - a pre-release string must not
    # be able to break `import pypowerwall`
    assert pypowerwall._release_tuple(version_string) == expected


def test_version_is_semver():
    assert re.match(r"^\d+\.\d+\.\d+$", pypowerwall.__version__)


def test_version_tuple_derived_from_version():
    expected = tuple(int(p) for p in pypowerwall.__version__.split("."))
    assert pypowerwall.version_tuple == expected
