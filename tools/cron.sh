#!/bin/bash
#
# Cronjob to check Powerwall battery charge level and adjust the reserve limit.
#
# This script is set to optimize Powerwall charging during solar production 
# (clean energy) and use the battery during peak grid usage (dirty energy) time.
#
# The script implements the following logic:
#  - WINTER (Nov, Dec, Jan):
#    - 9am-4pm: Set reserve to MAX to encourage charging from solar.
#  - NOT WINTER (Spring, Summer, Autumn):
#    - 11am-4pm: Set reserve to MAX if it is very cloudy (>90%) or hot (>30C)
#      to ensure the battery is charged for peak usage.
#  - AFTERNOON (4pm-9pm):
#    - Set reserve to MIN to force battery usage during peak grid hours.
#  - EVENING (9pm onwards):
#    - If it was a hot day (>25C), set reserve to the current battery level
#      to prevent further discharge and save power for the next day.
#
# Requires:
#  * pypowerwall python module (pip install pypowerwall)
#  * Tesla auth file setup - see instructions at:
#    https://github.com/jasonacox/pypowerwall/tree/main/tools
#  * weather411 service (optional for cloud data)
#    (see https://github.com/jasonacox/Powerwall-Dashboard/tree/main/weather)
#  * InfluxDB (optional for temperature data from Powerwall-Dashboard)

# For robustness, exit on error and undefined variables
set -euo pipefail

# --- Configuration ---
# It is recommended to move sensitive data like passwords to a secure location
# or use environment variables.

# Network Addresses
POWERWALL_IP='10.1.1.10'
INFLUXDB_IP='10.1.1.20'   # Comment out if not using Powerwall-Dashboard
WEATHER_IP='10.1.1.11'    # Address of weather411 service

# Credentials
POWERWALL_PASSWORD='yourPassword'

# Paths
# Location of Tesla auth file and where the log file will be written
DATA_FOLDER='/home/tesla'
LOGFILE="${DATA_FOLDER}/cron.log"
# Assuming set-reserve.py is in the same directory as this script
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SET_RESERVE_SCRIPT="${SCRIPT_DIR}/set-reserve.py"

# Reserve Settings
MAX_RESERVE=80
MIN_RESERVE=20

# --- End of Configuration ---

# --- Error Handling ---
# This function will be called when an error occurs.
handle_error() {
  local exit_code=$?
  local line_number=$1
  echo "---" >> "${LOGFILE}"
  echo "$(date) - ERROR: An error occurred in the cron script." >> "${LOGFILE}"
  echo "Exit Code: ${exit_code}" >> "${LOGFILE}"
  echo "Line Number: ${line_number}" >> "${LOGFILE}"
  echo "Failing Command: '$BASH_COMMAND'" >> "${LOGFILE}"
  echo "---" >> "${LOGFILE}"
}

# Trap errors and call the error handler.
# The trap is executed when a command returns a non-zero exit code.
trap 'handle_error $LINENO' ERR

# Ensure the data folder exists
mkdir -p "${DATA_FOLDER}"
cd "${DATA_FOLDER}"

# --- Data Fetching ---

# Fetch cloud conditions from jasonacox/weather411 container (optional)
CLOUDS=0
if [[ -n "${WEATHER_IP:-}" ]]; then
    # The following command requires curl and jq to be installed.
    CLOUDS=$(curl --silent "http://${WEATHER_IP}:8676/clouds" | jq -r '.clouds')
fi

# Fetch current stats from Powerwall
POWERWALL_STATS=$(python3 << END
import pypowerwall
import sys
try:
    pw = pypowerwall.Powerwall("${POWERWALL_IP}", "${POWERWALL_PASSWORD}")
    # grid, home, solar, battery, level, reserve
    print("%d,%d,%d,%d,%d,%d" % (pw.grid(), pw.home(), pw.solar(), pw.battery(), pw.level(True), pw.get_reserve(True)))
except Exception as e:
    print(f"Error connecting to Powerwall: {e}", file=sys.stderr)
    exit(1)
END
)

# Parse Powerwall stats
IFS=',' read -r GRID HOUSE SOLAR PW LEVEL CUR <<< "${POWERWALL_STATS}"

# Fetch max temperature from InfluxDB for past 24 hours (optional)
MAX_TEMP=0
if [[ -n "${INFLUXDB_IP:-}" ]]; then
    MAX_TEMP=$(python3 << END
import influxdb
import sys
try:
    client = influxdb.InfluxDBClient("${INFLUXDB_IP}", database='powerwall')
    query = 'SELECT max("temp_max") FROM "autogen"."weather" WHERE time > now() - 24h GROUP BY time(1d) fill(none)'
    result = client.query(query)
    points = list(result.get_points())
    if len(points) > 0 and 'max' in points[0] and points[0]['max'] is not None:
        print(points[0]['max'])
    else:
        print(0)
except Exception as e:
    print(f"Error connecting to InfluxDB: {e}", file=sys.stderr)
    exit(1)
END
)
fi

# --- Current Time ---
# Using date command to get current time components
# The '10#' is to force base-10 interpretation for numbers with leading zeros (e.g. '08', '09')
MONTH=$(date +%b)
DATE=$(date +%d)
YEAR=$(date +%Y)
HOUR=$(date +%H)
MINUTE=$(date +%M)
H=$((10#${HOUR}))
M=$((10#${MINUTE}))

echo "${MONTH} ${DATE} ${YEAR} ${HOUR}:${MINUTE}: The battery level is ${LEVEL}%, Grid=${GRID}W, House=${HOUSE}W, Solar=${SOLAR}W, PW=${PW}W, Reserve Setting=${CUR}%, Clouds=${CLOUDS}%"

# --- Functions ---

# Function to change reserve setting
change_reserve() {
    local new_reserve=$1
    echo "Changing reserve to ${new_reserve}%"

    if [[ "${new_reserve}" == "current" ]]; then
        python3 "${SET_RESERVE_SCRIPT}" --current
    else
        python3 "${SET_RESERVE_SCRIPT}" --set "${new_reserve}"
    fi

    echo "${MONTH} ${DATE} ${YEAR} ${HOUR}:${MINUTE}: Updated reserve to ${new_reserve}% - Battery: ${LEVEL}%, Grid: ${GRID}W, House: ${HOUSE}W, Solar: ${SOLAR}W, PW: ${PW}W, Old Reserve: ${CUR}%" | tee -a "${LOGFILE}"
}

# --- Logic for operations ---

# Target reserve for this cycle, default to current reserve
TARGET_RESERVE=${CUR}

# WINTER - Nov, Dec and Jan - Adjust Reserve to save energy for peak
if [[ "${MONTH}" =~ ^(Nov|Dec|Jan)$ ]]; then
    # From 9am to 4pm (09:00-15:59) - Peak solar production time - charge battery
    if (( H >= 9 && H < 16 )); then
        if (( LEVEL < MAX_RESERVE )); then
            TARGET_RESERVE=${MAX_RESERVE}
        fi
    fi
else # NOT WINTER (Spring, Summer, Autumn)
    # From 11am to 4pm (11:00-15:59) - Peak solar production time - charge battery if cloudy or hot
    if (( H >= 11 && H < 16 && (CLOUDS > 90 || MAX_TEMP > 30) )); then
        if (( LEVEL < MAX_RESERVE )); then
            TARGET_RESERVE=${MAX_RESERVE}
        fi
    fi
fi

# Afternoon - 4pm to 9pm (16:00-20:59) - Peak grid usage - force switch to battery
if (( H >= 16 && H < 21 )); then
    TARGET_RESERVE=${MIN_RESERVE}
fi

# Evening 9pm to Midnight (21:00-23:59) - Non-peak grid usage
# Stop using battery if 24h max temp was above 25C - Heavy A/C Use
if (( H >= 21 && MAX_TEMP > 25 )); then
    # Make sure reserve is not set below current level, and not below MIN_RESERVE
    if (( LEVEL > MIN_RESERVE )); then
        TARGET_RESERVE=${LEVEL}
    else
        TARGET_RESERVE=${MIN_RESERVE}
    fi
fi

# --- Execution ---

# Powerwall Protection: Never let reserve go below MIN_RESERVE
if (( TARGET_RESERVE < MIN_RESERVE )); then
    TARGET_RESERVE=${MIN_RESERVE}
fi

# Only change reserve if it's different from current setting
if (( TARGET_RESERVE != CUR )); then
    change_reserve "${TARGET_RESERVE}"
else
    echo "Reserve setting ${CUR}% is already correct. No change needed."
fi
