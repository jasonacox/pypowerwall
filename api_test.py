# Test Functions of the Powerwall API
import os

import pypowerwall

# Optional: Turn on Debug Mode
pypowerwall.set_debug(True)

# Credentials for your Powerwall - Customer Login Data
password = os.environ.get('PW_PASSWORD', 'password')
email = os.environ.get('PW_EMAIL', 'email@example.com')
host = os.environ.get('PW_HOST', 'localhost')  # Change to the IP of your Powerwall
timezone = os.environ.get('PW_TIMEZONE',
                          'America/Los_Angeles')  # https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
auth_path = os.environ.get('PW_AUTH_PATH', "")
cachefile_path = os.environ.get('PW_CACHEFILE_PATH', ".cachefile")


def test_battery_mode_change(pw):
    original_mode = pw.get_mode(force=True)
    if original_mode != 'backup':
        new_mode = 'backup'
    else:
        new_mode = 'self_consumption'

    resp = pw.set_mode(mode=new_mode)
    if resp and resp.get('set_operation', {}).get('result') == 'Updated':
        # if we got a valid response from API, let's assume it worked :)
        installed_mode = resp.get('set_operation', {}).get('real_mode')
    else:
        # TODO: may need to poll API until change is detected (in cloud mode)
        installed_mode = pw.get_mode(force=True)
    if installed_mode != new_mode:
        print(f"Set battery operation mode to {new_mode} failed.")
    # revert to original value just in case
    pw.set_mode(mode=original_mode)


def test_battery_reserve_change(pw):
    original_reserve_level = pw.get_reserve(force=True)
    if original_reserve_level != 100:
        new_reserve_level = 100
    else:
        new_reserve_level = 50

    resp = pw.set_reserve(level=new_reserve_level)
    if resp and resp.get('set_backup_reserve_percent', {}).get('result') == 'Updated':
        # if we got a valid response from API, let's assume it worked :)
        installed_level = resp.get('set_backup_reserve_percent', {}).get('backup_reserve_percent')
    else:
        # TODO: may need to poll API until change is detected (in cloud mode)
        installed_level = pw.get_reserve(force=True)
    if installed_level != new_reserve_level:
        print(f"Set battery reserve level to {new_reserve_level}% failed.")
    # revert to original value just in case
    pw.set_reserve(level=original_reserve_level)


def test_post_functions(pw):
    # test battery reserve and mode change
    print("Testing set_operation()...")
    test_battery_mode_change(pw)
    test_battery_reserve_change(pw)
    print("Post functions test complete.")


def run(include_post_funcs=False):
    for h in [host, ""]:
        if h:
            print(f"LOCAL MODE: Connecting to Powerwall at {h}")
        else:
            print(f"CLOUD MODE: Connecting to Powerwall via Tesla API")
        print("---------------------------------------------------------")

        # Connect to Powerwall
        pw = pypowerwall.Powerwall(h, password, email, timezone, authpath=auth_path, cachefile=cachefile_path)

        # noinspection PyUnusedLocal
        aggregates = pw.poll('/api/meters/aggregates')
        # noinspection PyUnusedLocal
        coe = pw.poll('/api/system_status/soe')

        # Pull Sensor Power Data
        grid = pw.grid()
        solar = pw.solar()
        battery = pw.battery()
        home = pw.home()

        # Display Data
        battery_level = pw.level()
        combined_power_metrics = pw.power()
        print(f"Battery power level: \033[92m{battery_level:.0f}%\033[0m")
        print(f"Combined power metrics: \033[92m{combined_power_metrics}\033[0m")
        print("")

        # Display Power in kW
        print(f"Grid Power: \033[92m{float(grid) / 1000.0:.2f}kW\033[0m")
        print(f"Solar Power: \033[92m{float(solar) / 1000.0:.2f}kW\033[0m")
        print(f"Battery Power: \033[92m{float(battery) / 1000.0:.2f}kW\033[0m")
        print(f"Home Power: \033[92m{float(home) / 1000.0:.2f}kW\033[0m")
        print()

        # Raw JSON Payload Examples
        print(f"Grid raw: \033[92m{pw.grid(verbose=True)!r}\033[0m\n")
        print(f"Solar raw: \033[92m{pw.solar(verbose=True)!r}\033[0m\n")

        # Test each function
        print("Testing each function:")
        functions = [
            pw.poll,
            pw.level,
            pw.power,
            pw.site,
            pw.solar,
            pw.battery,
            pw.load,
            pw.grid,
            pw.home,
            pw.vitals,
            pw.strings,
            pw.din,
            pw.uptime,
            pw.version,
            pw.status,
            pw.site_name,
            pw.temps,
            pw.alerts,
            pw.system_status,
            pw.battery_blocks,
            pw.grid_status,
            pw.is_connected,
            pw.get_reserve,
            pw.get_mode,
            pw.get_time_remaining
        ]
        for func in functions:
            print(f"{func.__name__}()")
            print(f"{func()}")

        if include_post_funcs:
            test_post_functions(pw)

        print("All functions tested.")
        print("")
        print("Testing all functions and printing result:")
        input("Press Enter to continue...")
        print("")

        for func in functions:
            print(f"{func.__name__}()")
            print("\033[92m", end="")
            print(func())
            print("\033[0m")

        print("All functions tested.")
        print("")
        input("Press Enter to continue...")
        print("")

    print("All tests completed.")
    print("")


if __name__ == "__main__":
    run(include_post_funcs=True)
