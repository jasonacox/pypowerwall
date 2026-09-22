"""VERSION file is the single source of truth for the package version."""
import os
import re

import pypowerwall

VERSION_FILE = os.path.join(
    os.path.dirname(os.path.abspath(pypowerwall.__file__)), "VERSION"
)


def test_version_file_exists():
    assert os.path.isfile(VERSION_FILE)


def test_dunder_version_matches_version_file():
    with open(VERSION_FILE, "r") as f:
        assert pypowerwall.__version__ == f.read().strip()


def test_version_is_semver():
    assert re.match(r"^\d+\.\d+\.\d+$", pypowerwall.__version__)


def test_version_tuple_derived_from_version():
    expected = tuple(int(p) for p in pypowerwall.__version__.split("."))
    assert pypowerwall.version_tuple == expected
