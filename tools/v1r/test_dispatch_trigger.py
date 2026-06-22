#!/usr/bin/env python3
"""
test_dispatch_trigger.py — Focused experiment for issue #321.

Does the schedule+cancel TEGMessages cycle trigger dispatch re-evaluation
after a config write on PW3 v1r gateways?

Usage:
    # WITH trigger (should see gateway act on new reserve):
    python3 tools/test_dispatch_trigger.py \
        --host <gw_ip> --password <last5> \
        --rsa-key ~/.pypowerwall/rsa_key.pem --reserve 30

    # WITHOUT trigger (control — config written but gateway may not act):
    python3 tools/test_dispatch_trigger.py \
        --host <gw_ip> --password <last5> \
        --rsa-key ~/.pypowerwall/rsa_key.pem --reserve 30 --no-trigger

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
    password = args.password or (gw_pwd[-5:] if gw_pwd else None)
    if not password:
        print("ERROR: --password or --gw-pwd required")
        sys.exit(1)

    pw = pypowerwall.Powerwall(
        host=args.host,
        password=password,
        email="",
        gw_pwd=gw_pwd,
        rsa_key_path=args.rsa_key,
        wifi_host=args.wifi_host,
    )
    return pw


def main():
    parser = argparse.ArgumentParser(
        description="Test dispatch trigger via schedule+cancel TEGMessages cycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", required=True, help="Gateway IP address")
    parser.add_argument("--password", help="Customer password (last 5 of gateway password)")
    parser.add_argument("--gw-pwd", help="Full gateway password (alternative to --password)")
    parser.add_argument("--rsa-key", required=True, help="Path to RSA private key PEM")
    parser.add_argument("--wifi-host", help="WiFi host IP (for WiFi v1r fallback)")
    parser.add_argument("--reserve", type=float, default=30,
                        help="Target reserve %% to test (default: 30)")
    parser.add_argument("--no-trigger", action="store_true",
                        help="Write config only, no schedule+cancel trigger (control group)")
    parser.add_argument("--monitor", type=int, default=60,
                        help="Monitor duration in seconds (default: 60)")
    parser.add_argument("--trigger-duration", type=int, default=60,
                        help="Schedule duration in seconds before cancel (min 60, default: 60)")

    args = parser.parse_args()

    print("=" * 60)
    print("Dispatch Trigger Experiment (Issue #321)")
    print("=" * 60)
    print(f"  Host:       {args.host}")
    print(f"  WiFi Host:  {args.wifi_host or 'none'}")
    print(f"  Target:     {args.reserve}%")
    print(f"  Trigger:    {'DISABLED (control group)' if args.no_trigger else 'ENABLED'}")
    if not args.no_trigger:
        print(f"  Trigger Dur: {max(60, args.trigger_duration)}s")

    pw = connect(args)

    # Save original state
    orig_reserve = pw.get_reserve()
    orig_mode = pw.get_mode()
    print(f"\n  Original:   reserve={orig_reserve}%, mode={orig_mode}")

    # Step 1: Write config
    print(f"\n--- Step 1: Write config (set_reserve={args.reserve}%) ---")
    result = pw.set_reserve(args.reserve)
    print(f"  Result: {json.dumps(result, indent=2)}")

    if not args.no_trigger:
        # Check for active backup event
        events = pw.get_backup_events()
        if events and events.get("manual_backup", {}).get("active"):
            print("\n  [SKIP] Active manual backup event — not sending trigger")
            print("         (config written, but trigger skipped due to active event)")
        else:
            # Step 2: Schedule + cancel (dispatch trigger)
            # Gateway enforces minimum 60s duration
            duration = max(60, args.trigger_duration)
            print(f"\n--- Step 2: Schedule max backup ({duration}s) ---")
            sched = pw.schedule_max_backup(duration_seconds=duration)
            print(f"  Schedule result: {sched}")

            print(f"\n--- Step 3: Cancel max backup ---")
            cancel = pw.cancel_max_backup()
            print(f"  Cancel result: {cancel}")
    else:
        print("\n--- Steps 2-3: SKIPPED (--no-trigger) ---")

    # Step 4: Monitor
    print(f"\n--- Step 4: Monitor ({args.monitor}s) ---")
    print(f"  {'Time':>6}  {'Reserve':>8}  {'Battery':>8}  {'Solar':>7}  {'Grid':>7}  {'Home':>7}")
    print("  " + "-" * 52)

    readings = []
    start = time.time()
    while time.time() - start < args.monitor:
        elapsed = int(time.time() - start)
        try:
            r = pw.get_reserve()
            b = pw.level()
            s = pw.solar()
            g = pw.grid()
            h = pw.home()
            line = f"  {elapsed:>5}s  {r:>7.1f}%  {b:>7.1f}%  {s:>6.0f}W  {g:>6.0f}W  {h:>6.0f}W"
            print(line)
            readings.append({
                "t": elapsed,
                "reserve": r,
                "battery": b,
                "solar": s,
                "grid": g,
                "home": h,
            })
        except Exception as e:
            print(f"  {elapsed:>5}s  [ERROR] {e}")
        time.sleep(10)

    # Restore
    print(f"\n--- Restoring original state: reserve={orig_reserve}% ---")
    pw.set_reserve(orig_reserve)
    pw.set_mode(orig_mode)

    # Summary
    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    if args.no_trigger:
        print("  Mode: CONTROL (no trigger)")
        print("  Expected: config written, gateway MAY NOT act on new reserve")
    else:
        print("  Mode: TRIGGER (schedule + cancel)")
        print("  Expected: config written, gateway SHOULD act on new reserve")

    if readings:
        first = readings[0]
        last = readings[-1]
        print(f"\n  Reserve at start: {first['reserve']}%")
        print(f"  Reserve at end:   {last['reserve']}%")
        print(f"  Battery at start: {first['battery']}%")
        print(f"  Battery at end:   {last['battery']}%")
        print(f"\n  Compare battery trajectory with vs without trigger.")
        print(f"  If battery moves toward target only with trigger,")
        print(f"  the schedule+cancel cycle is confirmed as dispatch trigger.")

    print("\n  Done. Original values restored.")


if __name__ == "__main__":
    main()
