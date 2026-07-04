# pyPowerwall Proxy Regression Test Tool
# -*- coding: utf-8 -*-
"""
 Compare all non-control proxy endpoints between two running proxies
 (e.g. a new build and a known-good build against the same Powerwall)
 and flag endpoints whose responses have drifted.

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Usage:
    python3 regression_test.py --new http://localhost:9999 --old http://10.0.1.26:8675
    python3 regression_test.py --new ... --old ... --verbose      # show WARN details
    python3 regression_test.py --new ... --old ... --uri /pod     # single endpoint

 Comparison rules:
    * FAIL - structural drift: one side null/error/unparseable while the
      other has data, missing keys on the new side, type changes, missing
      vitals devices, CSV field-count changes
    * WARN - additive keys on the new side, numeric values outside the
      live-data tolerance (power readings legitimately swing between polls)
    * Volatile fields (timestamps, uptime, counters, versions, memory,
      session stats) are ignored entirely
 Exit code: number of FAILed endpoints (0 = pass)
"""
import argparse
import json
import sys
import urllib.request

# Non-control endpoints, assembled from proxy/server.py routing
METRIC_URIS = [
    "/aggregates", "/api/meters/aggregates", "/soe", "/api/system_status/soe",
    "/vitals", "/strings", "/temps", "/temps/pw", "/alerts", "/alerts/pw",
    "/freq", "/pod", "/json", "/version",
    "/fans", "/fans/pw",
]
API_URIS = [  # ALLOWLIST minus DISABLED (/api/customer/registration tested separately)
    "/api/status", "/api/site_info/site_name", "/api/meters/site",
    "/api/meters/solar", "/api/sitemaster", "/api/powerwalls",
    "/api/system_status", "/api/system_status/grid_status",
    "/api/system/update/status", "/api/site_info",
    "/api/system_status/grid_faults", "/api/operation",
    "/api/site_info/grid_codes", "/api/solars", "/api/solars/brands",
    "/api/customer", "/api/meters", "/api/installer", "/api/networks",
    "/api/system/networks", "/api/meters/readings",
    "/api/synchrometer/ct_voltage_references", "/api/troubleshooting/problems",
    "/api/auth/toggle/supported", "/api/solar_powerwall",
    "/api/customer/registration",  # disabled - both sides should refuse
]
PW_URIS = ["/pw/" + p for p in [
    "level", "power", "site", "solar", "battery", "battery_blocks", "load",
    "grid", "home", "vitals", "temps", "strings", "din", "uptime", "version",
    "status", "system_status", "grid_status", "aggregates", "site_name",
    "alerts", "is_connected", "get_reserve", "get_mode", "get_time_remaining",
]]
TEDAPI_URIS = ["/tedapi/config", "/tedapi/status", "/tedapi/components",
               "/tedapi/battery", "/tedapi/controller"]
CSV_URIS = ["/csv", "/csv/v2"]
KEYS_ONLY_URIS = ["/stats", "/health"]  # values are proxy-instance specific

ALL_URIS = METRIC_URIS + API_URIS + PW_URIS + TEDAPI_URIS + CSV_URIS + KEYS_ONLY_URIS

# Value differences in fields matching these substrings are ignored
VOLATILE = [
    "time", "ts", "timestamp", "uptime", "up_time", "counter", "gets",
    "posts", "errors", "timeout", "uri", "mem", "cache", "version",
    "pypowerwall", "build", "start", "git_hash", "session", "clients",
    "freq", "score", "checksum", "nonce", "token", "cookie", "auth",
]
# Numeric tolerance for live readings: pass if within EITHER bound
REL_TOL = 0.5       # 50% relative - live power values swing between polls
ABS_TOL = 500.0     # or 500 absolute (watts-scale jitter, voltage wobble)


def is_volatile(key_path):
    lk = key_path.lower()
    return any(v in lk for v in VOLATILE)


def fetch(base, uri, timeout=15):
    """Return (status_code, text) - never raises."""
    try:
        with urllib.request.urlopen(base.rstrip("/") + uri, timeout=timeout) as r:
            return r.status, r.read().decode("utf8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf8", errors="replace")
    except Exception as e:
        return None, f"<<fetch error: {e}>>"


def parse(text):
    try:
        return True, json.loads(text)
    except (ValueError, TypeError):
        return False, text


def close_enough(a, b):
    if a == b:
        return True
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return False
    if abs(fa - fb) <= ABS_TOL:
        return True
    biggest = max(abs(fa), abs(fb))
    return biggest > 0 and abs(fa - fb) / biggest <= REL_TOL


def compare(old, new, path=""):
    """Recursively compare parsed JSON. Returns (fails, warns) lists."""
    fails, warns = [], []
    if is_volatile(path):
        return fails, warns
    if old is None and new is None:
        return fails, warns
    if (old is None) != (new is None):
        fails.append(f"{path or '/'}: old={old!r} new={new!r} (null drift)")
        return fails, warns
    if isinstance(old, bool) != isinstance(new, bool) or \
            (not isinstance(old, (int, float)) or not isinstance(new, (int, float))) and \
            type(old) is not type(new):
        fails.append(f"{path or '/'}: type changed {type(old).__name__} -> {type(new).__name__}")
        return fails, warns
    if isinstance(old, dict):
        missing = set(old) - set(new)
        extra = set(new) - set(old)
        if missing:
            fails.append(f"{path or '/'}: keys missing in new: {sorted(missing)[:8]}")
        if extra:
            warns.append(f"{path or '/'}: additive keys in new: {sorted(extra)[:8]}")
        for k in set(old) & set(new):
            f, w = compare(old[k], new[k], f"{path}.{k}" if path else k)
            fails += f
            warns += w
    elif isinstance(old, list):
        if len(old) != len(new):
            warns.append(f"{path or '/'}: list length {len(old)} -> {len(new)}")
        elif all(not isinstance(x, (dict, list)) for x in old + new):
            # Scalar lists (e.g. alert names) are order-insensitive - the
            # library builds several of these from sets
            if sorted(map(str, old)) != sorted(map(str, new)):
                only_old = set(map(str, old)) - set(map(str, new))
                only_new = set(map(str, new)) - set(map(str, old))
                warns.append(f"{path or '/'}: list members changed "
                             f"(-{sorted(only_old)[:5]} +{sorted(only_new)[:5]})")
            return fails, warns
        for i, (o, n) in enumerate(zip(old, new)):
            f, w = compare(o, n, f"{path}[{i}]")
            fails += f
            warns += w
    elif isinstance(old, (int, float)) and isinstance(new, (int, float)):
        if not close_enough(old, new):
            warns.append(f"{path or '/'}: numeric drift {old} -> {new}")
    elif old != new:
        warns.append(f"{path or '/'}: value changed {old!r} -> {new!r}")
    return fails, warns


def compare_csv(old_text, new_text):
    fails, warns = [], []
    old_fields = old_text.strip().split("\n")[-1].split(",")
    new_fields = new_text.strip().split("\n")[-1].split(",")
    if len(old_fields) != len(new_fields):
        fails.append(f"field count {len(old_fields)} -> {len(new_fields)}")
        return fails, warns
    for i, (o, n) in enumerate(zip(old_fields, new_fields)):
        if not close_enough(o.strip(), n.strip()) and o.strip() != n.strip():
            warns.append(f"field[{i}]: {o.strip()} -> {n.strip()}")
    return fails, warns


def check_uri(old_base, new_base, uri):
    """Return (verdict, details) where verdict is PASS/WARN/FAIL/SKIP."""
    old_status, old_text = fetch(old_base, uri)
    new_status, new_text = fetch(new_base, uri)
    if old_status is None and new_status is None:
        return "SKIP", ["both unreachable"]
    if old_status is None or new_status is None:
        return "FAIL", [f"unreachable on one side: old={old_status} new={new_status}",
                        old_text if old_status is None else new_text]
    if old_status != new_status:
        return "FAIL", [f"HTTP status: old={old_status} new={new_status}"]

    if uri in CSV_URIS:
        fails, warns = compare_csv(old_text, new_text)
    else:
        old_ok, old_data = parse(old_text)
        new_ok, new_data = parse(new_text)
        if old_ok != new_ok:
            return "FAIL", [f"parse drift: old json={old_ok} new json={new_ok}",
                            f"old: {old_text[:120]}", f"new: {new_text[:120]}"]
        if not old_ok:  # both non-JSON (HTML etc.) - status match is enough
            return "PASS", ["non-JSON, status match"]
        if uri in KEYS_ONLY_URIS:
            fails, warns = [], []
            if isinstance(old_data, dict) and isinstance(new_data, dict):
                missing = set(old_data) - set(new_data)
                extra = set(new_data) - set(old_data)
                if missing:
                    fails.append(f"keys missing in new: {sorted(missing)[:10]}")
                if extra:
                    warns.append(f"additive keys in new: {sorted(extra)[:10]}")
        else:
            fails, warns = compare(old_data, new_data)

    if fails:
        return "FAIL", fails + warns
    if warns:
        return "WARN", warns
    return "PASS", []


def main():
    ap = argparse.ArgumentParser(description="Compare proxy endpoints between two builds")
    ap.add_argument("--new", required=True, help="Base URL of the new proxy")
    ap.add_argument("--old", required=True, help="Base URL of the known-good proxy")
    ap.add_argument("--uri", action="append", help="Test only these URIs (repeatable)")
    ap.add_argument("--verbose", action="store_true", help="Show WARN details")
    args = ap.parse_args()

    uris = args.uri or ALL_URIS
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
    failures = []
    print(f"Comparing {len(uris)} endpoints: old={args.old}  new={args.new}\n")
    for uri in uris:
        verdict, details = check_uri(args.old, args.new, uri)
        counts[verdict] += 1
        mark = {"PASS": "\x1b[32mPASS\x1b[0m", "WARN": "\x1b[33mWARN\x1b[0m",
                "FAIL": "\x1b[31mFAIL\x1b[0m", "SKIP": "\x1b[90mSKIP\x1b[0m"}[verdict]
        print(f"  [{mark}] {uri}")
        if verdict == "FAIL":
            failures.append(uri)
            for d in details[:6]:
                print(f"         - {d}")
        elif verdict in ("WARN", "SKIP") and (args.verbose or verdict == "SKIP"):
            for d in details[:4]:
                print(f"         - {d}")

    print(f"\nSummary: {counts['PASS']} pass, {counts['WARN']} warn, "
          f"{counts['FAIL']} fail, {counts['SKIP']} skip")
    if failures:
        print("Failed endpoints: " + ", ".join(failures))
    sys.exit(len(failures))


if __name__ == "__main__":
    main()
