#!/usr/bin/env python3
"""
test_v1r_control.py — Test v1r TEDAPI control paths on Powerwall 3 gateways.

Usage:
    python3 tools/test_v1r_control.py \
        --host <gateway_ip> --password <last5_of_gw_pwd> \
        --rsa-key ~/.pypowerwall/rsa_key.pem --test all

Tests:
    read      — Read current state (mode, reserve, meters, firmware)
    control   — Write config via set_reserve/set_mode, verify, restore
    backup    — TEGMessages cycle: schedule -> get -> verify -> cancel
    dispatch  — Write config -> schedule+cancel trigger -> monitor behavior
    grid      — Read grid charging and export settings

Requirements:
    pip install pypowerwall
"""

import argparse
import json
import sys
import time

try:
    import pypowerwall
except ImportError:
    print("ERROR: pypowerwall not installed. Run: pip install pypowerwall")
    sys.exit(1)


def connect(args):
    """Create a pypowerwall connection in v1r mode."""
    gw_pwd = args.gw_pwd or ""
    # If gw_pwd provided but password not, derive from last 5 chars
    password = args.password or (gw_pwd[-5:] if gw_pwd else None)
    if not password:
        print("ERROR: --password (last 5 of gateway password) or --gw-pwd required")
        sys.exit(1)

    pw = pypowerwall.Powerwall(
        host=args.host,
        password=password,
        email="",  # not needed for local v1r
        gw_pwd=gw_pwd,
        rsa_key_path=args.rsa_key,
        wifi_host=args.wifi_host,
    )
    return pw


def test_read(pw):
    """Read current state: mode, reserve, meters, firmware."""
    print("\n" + "=" * 60)
    print("TEST: read — Current State")
    print("=" * 60)

    mode = pw.get_mode()
    reserve = pw.get_reserve()
    level = pw.level()
    version = pw.version()
    site_name = pw.site_name()
    grid = pw.grid_status()

    print(f"  Site:          {site_name}")
    print(f"  Firmware:      {version}")
    print(f"  Mode:          {mode}")
    print(f"  Reserve:       {reserve}%")
    print(f"  Battery Level: {level}%")
    print(f"  Grid Status:   {grid}")

    # Power flows
    solar = pw.solar()
    battery = pw.battery()
    home = pw.home()
    grid_w = pw.grid()

    print(f"\n  Power Flows:")
    print(f"    Solar:   {solar} W")
    print(f"    Battery: {battery} W")
    print(f"    Home:    {home} W")
    print(f"    Grid:    {grid_w} W")

    print("\n  [PASS] Read test complete")
    return True


def test_control(pw):
    """Write config via set_reserve/set_mode, verify, restore."""
    print("\n" + "=" * 60)
    print("TEST: control — Config Write (set_reserve / set_mode)")
    print("=" * 60)

    # Save original values
    orig_mode = pw.get_mode()
    orig_reserve = pw.get_reserve()
    print(f"  Original: mode={orig_mode}, reserve={orig_reserve}%")

    # Test reserve write
    test_reserve = max(5, int(orig_reserve) + 5) if orig_reserve else 10
    if test_reserve > 95:
        test_reserve = max(5, int(orig_reserve) - 5)

    print(f"\n  Setting reserve to {test_reserve}%...")
    result = pw.set_reserve(test_reserve)
    print(f"    Result: {json.dumps(result, indent=2)}")

    # Verify
    time.sleep(2)
    new_reserve = pw.get_reserve()
    print(f"  Read back: reserve={new_reserve}%")
    if new_reserve is not None and abs(new_reserve - test_reserve) < 2:
        print("  [PASS] Reserve write verified")
    else:
        print(f"  [WARN] Reserve mismatch: wrote {test_reserve}, read {new_reserve}")

    # Restore
    print(f"\n  Restoring reserve to {orig_reserve}%...")
    pw.set_reserve(orig_reserve)

    # Test mode write (cycle through self_consumption -> backup -> self_consumption)
    print(f"\n  Setting mode to 'backup'...")
    result = pw.set_mode("backup")
    print(f"    Result: {json.dumps(result, indent=2)}")

    time.sleep(2)
    new_mode = pw.get_mode()
    print(f"  Read back: mode={new_mode}")
    if new_mode == "backup":
        print("  [PASS] Mode write verified")
    else:
        print(f"  [WARN] Mode mismatch: wrote 'backup', read '{new_mode}'")

    # Restore
    print(f"\n  Restoring mode to '{orig_mode}'...")
    pw.set_mode(orig_mode)

    print("\n  [PASS] Control test complete")
    return True


def test_backup(pw):
    """TEGMessages cycle: schedule -> get -> verify -> cancel."""
    print("\n" + "=" * 60)
    print("TEST: backup — TEGMessages (Schedule/Get/Cancel)")
    print("=" * 60)

    # Check for active backup event first
    print("  Checking for active backup events...")
    events = pw.get_backup_events()
    print(f"    Current events: {json.dumps(events, indent=2, default=str)}")

    if events and events.get("manual_backup", {}).get("active"):
        print("  [SKIP] Active manual backup event found — skipping schedule test")
        print("         (would interfere with existing event)")
        return True

    # Schedule with minimum safe duration (gateway requires >= 60s)
    duration = 60
    print(f"\n  Scheduling max backup for {duration}s...")
    result = pw.schedule_max_backup(duration_seconds=duration)
    print(f"    Result: {result}")

    if not result:
        print("  [FAIL] schedule_max_backup returned False")
        return False

    # Verify the event exists
    time.sleep(2)
    print("\n  Verifying event was created...")
    events = pw.get_backup_events()
    print(f"    Events: {json.dumps(events, indent=2, default=str)}")

    if events and events.get("manual_backup"):
        mb = events["manual_backup"]
        print(f"    Manual backup active: {mb.get('active')}")
        print(f"    Duration: {mb.get('duration_seconds')}s")
        print("  [PASS] Backup event scheduled successfully")
    else:
        print("  [WARN] No manual backup event found after scheduling")

    # Cancel
    print("\n  Cancelling max backup...")
    result = pw.cancel_max_backup()
    print(f"    Result: {result}")

    # Verify cancellation
    time.sleep(2)
    events = pw.get_backup_events()
    if events and events.get("manual_backup", {}).get("active"):
        print("  [WARN] Manual backup still active after cancel")
    else:
        print("  [PASS] Manual backup cancelled successfully")

    print(f"\n  Final events: {json.dumps(events, indent=2, default=str)}")
    print("\n  [PASS] Backup test complete")
    return True


def test_dispatch(pw, monitor_seconds=60):
    """Write config -> schedule+cancel trigger -> monitor behavior."""
    print("\n" + "=" * 60)
    print("TEST: dispatch — Config Write + Schedule/Cancel Trigger")
    print("=" * 60)

    orig_reserve = pw.get_reserve()
    orig_mode = pw.get_mode()
    test_reserve = max(5, int(orig_reserve) + 10) if orig_reserve else 20
    if test_reserve > 90:
        test_reserve = max(5, int(orig_reserve) - 10)

    print(f"  Original: mode={orig_mode}, reserve={orig_reserve}%")
    print(f"  Target:   reserve={test_reserve}%")

    # Step 1: Write config
    print(f"\n  Step 1: Writing reserve={test_reserve}% via set_reserve()...")
    result = pw.set_reserve(test_reserve)
    print(f"    Result: {json.dumps(result, indent=2)}")

    # Step 2: Check for active backup event
    events = pw.get_backup_events()
    if events and events.get("manual_backup", {}).get("active"):
        print("\n  [SKIP] Active manual backup found — skipping trigger")
        print("         Config written but no dispatch trigger applied")
        pw.set_reserve(orig_reserve)
        return True

    # Step 3: Schedule + cancel cycle (dispatch trigger)
    # Gateway enforces minimum 60s duration
    duration = 60
    print(f"\n  Step 2: Schedule max backup ({duration}s) as dispatch trigger...")
    sched_result = pw.schedule_max_backup(duration_seconds=duration)
    print(f"    Schedule result: {sched_result}")

    print(f"\n  Step 3: Immediate cancel...")
    cancel_result = pw.cancel_max_backup()
    print(f"    Cancel result: {cancel_result}")

    # Step 4: Monitor
    print(f"\n  Step 4: Monitoring for {monitor_seconds}s...")
    print(f"  {'Time':>6}  {'Reserve':>8}  {'Battery':>8}  {'Solar':>7}  {'Grid':>7}  {'Home':>7}")
    print("  " + "-" * 50)

    start = time.time()
    while time.time() - start < monitor_seconds:
        elapsed = int(time.time() - start)
        try:
            r = pw.get_reserve()
            b = pw.level()
            s = pw.solar()
            g = pw.grid()
            h = pw.home()
            print(f"  {elapsed:>5}s  {r:>7.1f}%  {b:>7.1f}%  {s:>6.0f}W  {g:>6.0f}W  {h:>6.0f}W")
        except Exception as e:
            print(f"  {elapsed:>5}s  [ERROR] {e}")
        time.sleep(10)

    # Restore
    print(f"\n  Restoring reserve to {orig_reserve}%...")
    pw.set_reserve(orig_reserve)
    pw.set_mode(orig_mode)

    print("\n  [PASS] Dispatch test complete")
    print("  Compare this output with the --no-trigger variant from test_dispatch_trigger.py")
    return True


def test_grid(pw):
    """Read grid charging and export settings."""
    print("\n" + "=" * 60)
    print("TEST: grid — Grid Charging and Export Settings")
    print("=" * 60)

    charging = pw.get_grid_charging()
    export = pw.get_grid_export()

    print(f"  Grid Charging: {charging}")
    print(f"  Grid Export:   {export}")

    print("\n  [PASS] Grid settings test complete")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Test pypowerwall v1r control paths on Powerwall 3 gateways",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", required=True, help="Gateway IP address")
    parser.add_argument("--password", help="Customer password (last 5 of gateway password)")
    parser.add_argument("--gw-pwd", help="Full gateway password from QR sticker (alternative to --password)")
    parser.add_argument("--rsa-key", required=True, help="Path to RSA private key PEM for v1r")
    parser.add_argument("--wifi-host", help="WiFi host IP (for WiFi v1r fallback)")
    parser.add_argument("--test", default="all",
                        choices=["all", "read", "control", "backup", "dispatch", "grid"],
                        help="Test to run (default: all)")
    parser.add_argument("--monitor", type=int, default=60,
                        help="Monitor duration in seconds for dispatch test (default: 60)")

    args = parser.parse_args()

    print(f"pyPowerwall v1r Control Test")
    print(f"Host: {args.host}")
    print(f"RSA Key: {args.rsa_key}")
    print(f"WiFi Host: {args.wifi_host or 'none'}")
    print(f"Test: {args.test}")

    pw = connect(args)

    tests = {
        "read": lambda: test_read(pw),
        "control": lambda: test_control(pw),
        "backup": lambda: test_backup(pw),
        "dispatch": lambda: test_dispatch(pw, args.monitor),
        "grid": lambda: test_grid(pw),
    }

    if args.test == "all":
        results = {}
        for name, func in tests.items():
            try:
                results[name] = func()
            except Exception as e:
                print(f"\n  [FAIL] {name} test raised: {e}")
                results[name] = False

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for name, passed in results.items():
            status = "PASS" if passed else "FAIL"
            print(f"  {name:>10}: {status}")
    else:
        try:
            tests[args.test]()
        except Exception as e:
            print(f"\n  [FAIL] {args.test} test raised: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
