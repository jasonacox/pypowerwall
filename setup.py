import setuptools

# Compatibility shim: all package metadata lives in pyproject.toml (PEP 621),
# including the version ([tool.setuptools.dynamic] reads the __version__
# literal in pypowerwall/__init__.py at build time). Kept so legacy
# setup.py-based tooling (python setup.py --version, etc.) keeps working.
setuptools.setup()
