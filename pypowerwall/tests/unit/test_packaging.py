"""Packaging consistency: the published dependency list must match what CI tests."""
import pathlib
import re

import pytest

tomllib = pytest.importorskip("tomllib")  # stdlib from Python 3.11

ROOT = pathlib.Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"


def _normalize(requirement):
    return re.sub(r"\s+", "", requirement.lower().replace("_", "-"))


@pytest.mark.skipif(not (PYPROJECT.exists() and REQUIREMENTS.exists()),
                    reason="needs the source tree (not an installed distribution)")
def test_pyproject_dependencies_match_requirements_txt():
    # CI installs requirements.txt; users get pyproject.toml's list. If they
    # drift, the published package declares versions CI never tested.
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"]
    lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    tested = [line.split("#")[0].strip() for line in lines]
    assert {_normalize(d) for d in declared} == {_normalize(t) for t in tested if t}
