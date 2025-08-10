import asyncio
import datetime
import logging
import requests
import sys
# pip3 install pypowerwall
# Use patched teslapy from pypowerwall
from pypowerwall.cloud import teslapy

"""
 Adapted by Nate Carroll 03/2023 from TesSense w/ SenseLink  -Randy Spencer 2023 Version 9.7
 Python charge monitoring utility for those who have a Tesla Powerwall.
 Uses jasonacox/pypowerwall docker container to get realtime stats from the local gateway for Production 
 and Grid Utilization of electricity to control
 your main Tesla's AC charging amps to charge only with excess production.
 Simply plug in your car, update your info below, and type> python3 tessolarcharge.py
 
 Added: checking of location of Tesla to be sure it's charging at home
 Added: tracks cabin temp and local chargers, vents the car if it gets too hot 
 - removed due to Tesla removal of Vent option from API
 
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE 
 WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND ON INFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR 
 COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR 
 OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

username = 'yourname@example.com'  # Fill in Tesla login email address/account
lat, lon = '##.###', '-###.###'  # Fill in Location where charging will occur (shown at startup)
pypowerwall_IP = '10.x.x.x:8675'  # Fill in IP address and port for pypowerwall docker container
stop_charge_hour = 16  # hour of the day to stop charging (i.e. peak electricity rates to not discharge powerwall or
# when solar production expected to be around min charging rate causing charging to start and
# stop frequently

RedTxt, BluTxt, NormTxt = '\033[31m', '\033[34m', '\033[m'
RedBG, GrnBG, NormBG = '\033[101m', '\033[102m', '\033[0m'

# /c Set stdout as logging handler
root_log = logging.getLogger()
root_log.setLevel(logging.WARNING)  # WARNING or INFO or DEBUG
handler = logging.StreamHandler(sys.stdout)

# define globals
power_diff = 0
volts = 0
vehicles = []


def printerror(error, err):  # Error message with truncated data
    print(str(err).split("}")[0], "}\n", datetime.datetime.now().strftime("%a %I:%M %p"), error)


def printmsg(msg):  # Timestamped message
    print(" ", datetime.datetime.now().strftime("%a %I:%M %p"), msg)


def print_update(chargedata, fast):  # Display stats at every % change
    print("\nLevel:",
          chargedata['battery_level'], "%, Limit",
          chargedata['charge_limit_soc'], "%,",
          chargedata['charge_rate'], "MPH",
          chargedata['charger_voltage'], "Volts",
          chargedata['charge_energy_added'], "kWh added,")
    if fast:
        print("Rate:",
              chargedata['charger_power'], "KWs",
              chargedata['conn_charge_cable'],
              chargedata['fast_charger_type'],
              chargedata['minutes_to_full_charge'], "Minutes remaining\n")
    else:
        print(chargedata['charger_actual_current'], "of a possible",
              chargedata['charge_current_request_max'], "Amps,",
              chargedata['time_to_full_charge'], "Hours remaining\n")


def print_temp(car):
    # Tesla removed vent API in the USA due to NTHSA ~01/2023 - causes API error
    # if car.get_vehicle_data()['climate_state']['inside_temp'] > 40 : # 104°F
    #    if not car.get_vehicle_data()['vehicle_state']['fd_window'] : # Not Open
    #        Vent(car, 'vent')
    # else :
    #    if car.get_vehicle_data()['vehicle_state']['fd_window'] :    # Open
    #        Vent(car, 'close')
    print(car.temp_units(car.get_vehicle_data()['climate_state']['inside_temp']), end='')
    if car.get_vehicle_data()['climate_state']['fan_status']:
        print(car.get_vehicle_data()['climate_state']['fan_status'], end='')
    if car.get_vehicle_data()['climate_state']['cabin_overheat_protection_actively_cooling']:
        print(car.get_vehicle_data()['climate_state']['cabin_overheat_protection_actively_cooling'], end='')


def send_cmd(car, cmd, err):  # Start or Stop charging
    try:
        car.command(cmd)
    except teslapy.VehicleError as e:
        print(err)
        printmsg(e)


def set_amps(car, newrate, err):  # Increase or decrease charging rate
    try:
        car.command('CHARGING_AMPS', charging_amps=newrate)
    except teslapy.VehicleError as e:
        printerror("V: " + err, e)
    except teslapy.HTTPError as e:
        printerror("H: " + err, e)


def set_charging(car, newrate, msg):
    print(msg, "charging to", newrate, "amps")
    if newrate == 2:
        newrate = 1  # For API a newrate of 3=3, 2=3, 1=2
    set_amps(car, newrate, "Failed to change")  # so to set to 2 newrate must be 1
    if newrate < 5:  # if under 5 amps you need to send it twice:
        set_amps(car, newrate, "Failed to change 2")


def start_charging(car):
    try:  # Collect new data from Tesla
        state = car.get_vehicle_data()['charge_state']['charging_state']
    except teslapy.HTTPError as e:
        printerror("Tesla failed to update, please wait a minute...", e)
        return
    print(GrnBG + "Starting" + NormBG + " charge at 2 Amps")  # Underlined
    if state != "Charging":
        send_cmd(car, 'START_CHARGE', "Won't start charging")
        set_amps(car, 1, "Won't start charging 2")
        set_amps(car, 1, "Won't start charging 3")


def stop_charging(car):
    print(RedBG + "Stopping" + NormBG + " charge")  # Underlined
    send_cmd(car, 'STOP_CHARGE', "Failed to stop")


def super_charging(chargedata):  # Loop while DC Fast Charging
    if chargedata['fast_charger_present']:
        printmsg("DC Fast Charging...")
        print_update(chargedata, 1)
        return True


def wake(car):
    printmsg("Waking...")
    try:
        car.sync_wake_up()
    except teslapy.VehicleError as e:
        printerror("Failed to wake", e)
        return False
    return True


# noinspection HttpUrlsUsage
def update_powerwall():  # get site data on solar/grid from local Powerwall gateway via pypowerwall docker container
    instant_stats = requests.get('http://' + pypowerwall_IP + '/aggregates')
    return instant_stats.json()


def update_sense():  # Update Powerwall and charger voltage
    global power_diff, volts
    try:
        power_diff = int(update_powerwall()['site']['instant_power']) * -1
        volts = int(vehicles[0].get_vehicle_data()['charge_state']['charger_voltage'])
    except Exception as e:
        print(e)
        printmsg(RedTxt + "Powerwall data timeout or cannot get charger voltage" + NormTxt)
        power_diff = 0
        volts = 240  # don't change anything in case next call recovers
        return True


def vent(car, command):
    try:
        car.command('WINDOW_CONTROL', command=command, lat=lat, lon=lon)
    except teslapy.VehicleError as e:
        printmsg("Window_Control Failed " + str(e))
    else:
        print(RedTxt + "Windows will now", command + NormTxt)


async def tes_solar_charge():
    # rate = newrate = 0 (never used anywhere)
    limit = level = lastime = full_o_runplugged = 0
    minrate = 2  # Minimum rate you can set the charger to

    # teslapy.Retry is a urllib3.util.Retry instance in a nutshell
    # noinspection PyUnresolvedReferences
    retry = teslapy.Retry(total=3, status_forcelist=(500, 502, 503, 504))

    with teslapy.Tesla(username, retry=retry, timeout=30) as tesla:
        if not tesla.authorized:
            print('Use browser to login. Page Not Found will be shown at success.')
            print('Open this URL: ' + tesla.authorization_url())
            tesla.fetch_token(authorization_response=input('Enter URL after authentication: '))
        global vehicles
        vehicles = tesla.vehicle_list()

        print("Starting connection to", vehicles[0].get_vehicle_summary()['display_name'], end='')
        cardata = vehicles[0].get_vehicle_data()
        # noinspection PyBroadException
        try:
            print("... [", round(cardata['drive_state']['latitude'], 3), round(cardata['drive_state']['longitude'], 3),
                  "]")
        except Exception:
            pass
        # print(' last seen ' + vehicles[0].last_seen(), end='') #last seen timestamp in future error
        if vehicles[0]['charge_state']['battery_level']:
            print(' at ' + str(vehicles[0]['charge_state']['battery_level']) + '% SoC\n')
        else:
            print('\n')

        while True:  # Main loop with nighttime carve out
            if vehicles[0].get_vehicle_summary()['in_service']:
                print("Sorry. Currently this car is in for service")
                exit()

            if datetime.datetime.now().time().hour < 8 or datetime.datetime.now().time().hour >= stop_charge_hour:
                printmsg(BluTxt + "Nighttime" + NormTxt + ", Sleeping until next hour...")
                if stop_charge_hour <= datetime.datetime.now().time().hour < (stop_charge_hour + 1):
                    if vehicles[0].available() and not full_o_runplugged:  # don't stop charging if vehicle not charging
                        stop_charging(vehicles[0])
                        # 4-9pm peak rate when PowerWall is powering house, so don't charge car and drain powerwall
                        printmsg(BluTxt + datetime.datetime.now().strftime("%H:%M") +
                                 NormTxt + ", Defined stop charging hour reached; peak or reduced solar production...")
                await asyncio.sleep(60 * (60 - datetime.datetime.now().time().minute))
                continue

            if update_sense():  # Collect new data from Energy Monitor
                await asyncio.sleep(20)  # Error: Return to top of order
                continue

            minwatts = minrate * volts  # Calc minwatts needed to start charging

            if not vehicles[0].available():  # Car is sleeping
                if power_diff > minwatts and not full_o_runplugged:
                    if wake(vehicles[0]):  # Initial daytime wake() also, to get status
                        # rate = newrate = 0  # Reset rate as things will have changed (not used anywhere)
                        continue
                    else:
                        print("Wake error. Sleeping 20 minutes and trying again")
                        await asyncio.sleep(1200)  # Give the API a chance to find the car
                        continue
                else:
                    if full_o_runplugged == 1:
                        print("Full-", end='')
                    elif full_o_runplugged == 2:
                        print("Unplugged-", end='')
                    print("Sleeping, free power is", power_diff, "watts")
                    if full_o_runplugged:
                        printmsg(" Wait twenty minutes...")
                        await asyncio.sleep(1200)
                        continue

            else:  # Car is awake
                try:
                    cardata = vehicles[0].get_vehicle_data()  # Collect new data from Tesla
                    chargedata = cardata['charge_state']
                except teslapy.HTTPError as e:
                    printerror("Tesla failed to update, please wait a minute...", e)
                    await asyncio.sleep(60)  # Error: Return to top of order
                    continue

                if super_charging(chargedata):  # Display any Supercharging or DCFC data
                    await asyncio.sleep(120)  # Loop while Supercharging back to top
                    continue

                if 'latitude' in cardata['drive_state']:  # Prevent remote charging issues
                    if round(cardata['drive_state']['latitude'], 3) != lat and \
                            round(cardata['drive_state']['longitude'], 3) != lon:
                        print(round(cardata['drive_state']['latitude'], 3),
                              round(cardata['drive_state']['longitude'], 3), end='')
                        printmsg(' Away from home. Wait 5 minutes')
                        full_o_runplugged = 2  # If it's not at home, it's not plugged in nor full
                        await asyncio.sleep(300)
                        continue
                else:
                    print(RedTxt + 'Error: No Location' + NormTxt)

                if not chargedata['charging_state'] == "Charging":  # Not charging, check if need to start

                    if power_diff > minwatts and not full_o_runplugged:  # Minimum free watts to start charge
                        if chargedata['battery_level'] >= chargedata['charge_limit_soc']:
                            print("Full Battery, power at", power_diff, "watts")
                            full_o_runplugged = 1
                        elif chargedata['charging_state'] == "Disconnected":
                            print(RedTxt + "Please plug in" + NormTxt + ", power at", power_diff, "watts")
                            full_o_runplugged = 2
                        else:  # Plugged in and battery is not full so
                            start_charging(vehicles[0])

                    else:
                        print("Not Charging, free power is at", power_diff, "watts")

                else:  # Charging, update status
                    if chargedata['battery_level'] < chargedata['charge_limit_soc']:
                        full_o_runplugged = 0  # Mark it as NOT full and AS plugged-in

                    if level != chargedata['battery_level'] or limit != chargedata['charge_limit_soc']:
                        level, limit = chargedata['battery_level'], chargedata['charge_limit_soc']
                        print_update(chargedata, 0)  # Display charging info every % change

                    rate = chargedata['charger_actual_current']
                    newrate = min(rate + int(power_diff / volts), chargedata['charge_current_request_max'])

                    print("Charging at", rate, "amps, with", power_diff, "watts surplus")

                    if newrate < minrate:  # Stop charging as there's no free power
                        stop_charging(vehicles[0])
                        # newrate = 0 (not used anywhere)
                    elif newrate > rate:  # Charge faster with any surplus
                        set_charging(vehicles[0], newrate, "Increasing")
                    elif newrate < rate:  # Charge slower due to less availablity
                        set_charging(vehicles[0], newrate, "Slowing")

            if lastime != vehicles[0].get_vehicle_data()['climate_state']['timestamp']:
                lastime = vehicles[0].get_vehicle_data()['climate_state']['timestamp']
                print_temp(vehicles[0])  # Display cabin temp and fan use
            printmsg(" Wait two minutes...")  # Message after every complete loop
            # Could use variable to change frequency of updates, but 2 minutes seems
            # reasonable without hitting Tesla API frequently enough to cause lockout
            await asyncio.sleep(120)


# run the main program
if __name__ == "__main__":
    try:
        asyncio.run(tes_solar_charge())
    except KeyboardInterrupt:
        print("\n\n Interrupt received, stopping TesSolarCharge\n")
