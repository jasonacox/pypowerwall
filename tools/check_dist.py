#!/usr/bin/env python3
"""
pyPowerwall Distribution Checker

Verifies built distributions (wheel + sdist) before they are published, so
packaging regressions are caught in CI and before upload.sh:

  - the wheel ships only the pypowerwall package and its .dist-info - nothing
    from proxy/, tools/ or pwsimulator/, even through a local symlink
    (0.17.2-0.17.4 wheels carried a duplicate library under proxy/pypowerwall/)
  - every JSON data file in the source package is in the wheel
  - wheel and sdist metadata versions match the __version__ literal
  - the sdist carries pyproject.toml and no repository-only trees

Usage:
    python -m build
    python tools/check_dist.py dist

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall
"""
import ast
import email
import pathlib
import subprocess
import sys
import tarfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ONLY_TREES = ("proxy", "tools", "pwsimulator")


def source_version():
    """The __version__ string literal in pypowerwall/__init__.py (read, not imported)."""
    tree = ast.parse((ROOT / "pypowerwall" / "__init__.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets):
            return node.value.value
    raise SystemExit("no __version__ literal in pypowerwall/__init__.py")


def source_data_files():
    """Package JSON data files that must ship: git-tracked if possible (a stray
    local file can't cause a false failure), else everything on disk."""
    try:
        out = subprocess.run(["git", "ls-files", "pypowerwall/*.json", "pypowerwall/**/*.json"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
        files = set(out.split())
    except (OSError, subprocess.CalledProcessError):
        files = {str(p.relative_to(ROOT)) for p in (ROOT / "pypowerwall").rglob("*.json")}
    return {f for f in files if "/tests/" not in f}


def check_wheel(path, version, required, failures):
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        meta = email.message_from_bytes(wheel.read(f"pypowerwall-{version}.dist-info/METADATA"))
    top = {name.split("/", 1)[0] for name in names}
    extra = sorted(top - {"pypowerwall", f"pypowerwall-{version}.dist-info"})
    if extra:
        failures.append(f"wheel ships unexpected top-level entries: {extra}")
    missing = sorted(required - set(names))
    if missing:
        failures.append(f"wheel is missing data files: {missing}")
    if meta["Version"] != version:
        failures.append(f"wheel METADATA Version {meta['Version']} != source {version}")


def check_sdist(path, version, failures):
    prefix = f"pypowerwall-{version}/"
    with tarfile.open(path) as sdist:
        names = [n for n in sdist.getnames() if n.startswith(prefix)]
        pkg_info = email.message_from_bytes(sdist.extractfile(prefix + "PKG-INFO").read())
    top = {name[len(prefix):].split("/", 1)[0] for name in names if name != prefix.rstrip("/")}
    leaked = sorted(top & set(REPO_ONLY_TREES))
    if leaked:
        failures.append(f"sdist ships repository-only trees: {leaked}")
    if "pyproject.toml" not in top:
        failures.append("sdist is missing pyproject.toml")
    if pkg_info["Version"] != version:
        failures.append(f"sdist PKG-INFO Version {pkg_info['Version']} != source {version}")


def main(dist_dir):
    version = source_version()
    dist = pathlib.Path(dist_dir)
    wheel = dist / f"pypowerwall-{version}-py3-none-any.whl"
    universal = dist / f"pypowerwall-{version}-py2.py3-none-any.whl"
    sdist = dist / f"pypowerwall-{version}.tar.gz"
    failures = []
    wheels = [w for w in (wheel, universal) if w.exists()]
    if not wheels:
        failures.append(f"no wheel for version {version} in {dist}")
    for w in wheels:
        check_wheel(w, version, source_data_files(), failures)
    if sdist.exists():
        check_sdist(sdist, version, failures)
    else:
        failures.append(f"no sdist for version {version} in {dist}")
    checked = ", ".join(p.name for p in wheels + ([sdist] if sdist.exists() else []))
    if failures:
        print(f"FAIL ({checked}):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"OK: {checked}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "dist"))
