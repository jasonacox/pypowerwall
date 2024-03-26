# Test Functions of the Powerwall API

import pypowerwall

# Optional: Turn on Debug Mode
pypowerwall.set_debug(True)

# Credentials for your Powerwall - Customer Login Data
password='local_password'
email='name@example.com'
host = "localhost"                # e.g. 10.0.1.123
timezone = "America/Los_Angeles"  # https://en.wikipedia.org/wiki/List_of_tz_database_time_zones 

for h in [host, ""]:
    if h:
        print(f"LOCAL MODE: Connecting to Powerwall at {h}")
    else:
        print(f"CLOUD MODE: Connecting to Powerwall via Tesla API")
    print("---------------------------------------------------------")

    # Connect to Powerwall
    pw = pypowerwall.Powerwall(h,password,email,timezone)

    aggregates = pw.poll('/api/meters/aggregates')
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
    print(f"Grid Power: \033[92m{float(grid)/1000.0:.2f}kW\033[0m")
    print(f"Solar Power: \033[92m{float(solar)/1000.0:.2f}kW\033[0m")
    print(f"Battery Power: \033[92m{float(battery)/1000.0:.2f}kW\033[0m")
    print(f"Home Power: \033[92m{float(home)/1000.0:.2f}kW\033[0m")
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
        pw.get_time_remaining
    ]
    for func in functions:
        print(f"{func.__name__}()")
        func()

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