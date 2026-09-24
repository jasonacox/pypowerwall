"""Version contract: the __version__ literal is the single source of truth."""
import re

import pypowerwall


def test_version_is_semver():
    assert re.match(r"^\d+\.\d+\.\d+$", pypowerwall.__version__)


def test_version_tuple_derived_from_version():
    expected = tuple(int(p) for p in pypowerwall.__version__.split("."))
    assert pypowerwall.version_tuple == expected
