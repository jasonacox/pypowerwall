from fleetapi import FleetAPI

fleet = FleetAPI()

# Current Status
print(f"Solar: {fleet.solar_power()}")
print(f"Grid: {fleet.grid_power()}")
print(f"Load: {fleet.load_power()}")
print(f"Battery: {fleet.battery_power()}")
print(f"Battery Level: {fleet.battery_level()}")

# Change Reserve to 30%
fleet.set_battery_reserve(80)

# Change Operating Mode to Autonomous
fleet.set_operating_mode("self_consumption")

