#!/bin/bash
#
# Cronjob to check Powerwall battery charge level and adjust the reserve limit.
#
# This script is set to optimize Powerwall charging during solar production 
# (clean energy) and use the battery during peak grid usage (dirty energy) time.
#
# The script implements the following logic:
#  - MORNING (before 9am):
#    - Reset reserve to minimum (or higher if weather alerts active)
#  - WINTER (Oct, Nov, Dec, Jan):
#    - 9am-4pm: Set reserve to 75% to encourage charging from solar while
#      accounting for lower winter solar production
#  - NOT WINTER (Spring, Summer, Autumn):
#    - 11am-4pm: Set reserve to 80% only if very cloudy (>90%) or hot (>30C)
#      to ensure the battery is charged for peak usage
#  - AFTERNOON (4pm-9pm):
#    - Set reserve to minimum to force battery usage during peak grid hours
#  - EVENING (9pm-10pm):
#    - If it was a very hot day (>30C), set reserve to current battery level
#      to prevent further discharge and save power for the next day
#  - LATE EVENING (after 10pm):
#    - Allow battery use unless it was extremely hot (>30C)
#  - WEATHER ALERTS:
#    - If power risk alerts detected, increase minimum reserve to 79%
#      to ensure adequate backup power during potential outages
#
# Requires:
#  * pypowerwall python module (pip install pypowerwall)
#  * Tesla Cloud authentication setup - Run: python3 -m pypowerwall setup
#    This creates .pypowerwall.auth and .pypowerwall.site files
#  * weather411 service (optional for cloud data)
#    (see https://github.com/jasonacox/Powerwall-Dashboard/tree/main/weather)
#  * InfluxDB (optional for temperature data from Powerwall-Dashboard)

# For robustness, exit on error and undefined variables
set -euo pipefail

# --- Configuration ---
# It is recommended to move sensitive data like passwords to a secure location
# or use environment variables.

# Host Addresses
PYPOWERWALL_HOST=''       # Pypowerwall Proxy Server (optional, e.g., 'localhost:8675')
INFLUXDB_IP='10.1.1.20'   # Comment out if not using Powerwall-Dashboard
WEATHER_IP='10.1.1.11'    # Address of weather411 service
WEATHER_ALERT_URL=''      # NWS weather alerts JSON file path or URL 
                          # (optional, e.g., '/tmp/nws.json' or 'http://localhost:8080/nws.json')

# Tesla Cloud Authentication
# Path to Tesla cloud auth files (.pypowerwall.auth and .pypowerwall.site)
# Run 'python3 -m pypowerwall setup' to create these files
AUTH_PATH='/home/tesla'   # Path where Tesla auth files are stored
EMAIL='your@email.com'    # Tesla account email
TIMEZONE='America/Los_Angeles'  # Your local timezone

# Paths
# Location where the log file will be written
DATA_FOLDER='/home/tesla'
LOGFILE="${DATA_FOLDER}/cron.log"
# Assuming set-reserve.py is in the same directory as this script
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SET_RESERVE_SCRIPT="${SCRIPT_DIR}/set-reserve.py"

# Python Command
PYTHON3='/usr/bin/python3'  # Path to Python 3 executable

# Reserve Settings
MAX_RESERVE=80            # Maximum reserve level for non-winter months
WINTER_MAX_RESERVE=75     # Maximum reserve level for winter (Oct-Jan) when solar production is lower
MIN_RESERVE=20            # Minimum reserve level to maintain
ALERT_RESERVE=79          # Reserve level to use when weather alerts detected (power risk)

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

# --- Validate Tesla Cloud Authentication ---
# Check if Tesla auth files exist
if [[ ! -f "${AUTH_PATH}/.pypowerwall.auth" ]] || [[ ! -f "${AUTH_PATH}/.pypowerwall.site" ]]; then
    echo "ERROR: Tesla authentication files not found in ${AUTH_PATH}" | tee -a "${LOGFILE}"
    echo "Please run 'python3 -m pypowerwall setup' to create authentication files." | tee -a "${LOGFILE}"
    exit 1
fi

# --- Data Fetching ---

# Fetch cloud conditions from jasonacox/weather411 container (optional)
CLOUDS=0
if [[ -n "${WEATHER_IP:-}" ]]; then
    # The following command requires curl and jq to be installed.
    CLOUDS=$(curl --silent "http://${WEATHER_IP}:8676/clouds" | jq -r '.clouds')
fi

# Fetch current stats from Powerwall
# Try pypowerwall proxy server first (if configured), then fall back to Cloud Mode
POWERWALL_STATS=""
if [[ -n "${PYPOWERWALL_HOST:-}" ]]; then
    # Try to fetch from pypowerwall proxy server
    CSV_DATA=$(curl --silent --fail --max-time 5 "http://${PYPOWERWALL_HOST}/csv/v2" 2>/dev/null)
    if [[ $? -eq 0 ]] && [[ -n "${CSV_DATA}" ]]; then
        # Parse CSV response (skip header line, get data line)
        # Format: Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve
        DATA_LINE=$(echo "${CSV_DATA}" | tail -n 1)
        if [[ -n "${DATA_LINE}" ]]; then
            # Extract values and convert to integers
            IFS=',' read -r GRID HOUSE SOLAR PW LEVEL GRIDSTATUS CUR <<< "${DATA_LINE}"
            GRID=$(printf "%.0f" "${GRID}")
            HOUSE=$(printf "%.0f" "${HOUSE}")
            SOLAR=$(printf "%.0f" "${SOLAR}")
            PW=$(printf "%.0f" "${PW}")
            LEVEL=$(printf "%.0f" "${LEVEL}")
            CUR=$(printf "%.0f" "${CUR}")
            POWERWALL_STATS="${GRID},${HOUSE},${SOLAR},${PW},${LEVEL},${CUR}"
        fi
    fi
fi

# Fall back to Cloud Mode if proxy server failed or not configured
if [[ -z "${POWERWALL_STATS}" ]]; then
    POWERWALL_STATS=$(${PYTHON3} << END
import pypowerwall
import sys
try:
    # Connect using Tesla Cloud API
    pw = pypowerwall.Powerwall(
        host="",
        password="",
        email="${EMAIL}",
        timezone="${TIMEZONE}",
        cloudmode=True,
        authpath="${AUTH_PATH}"
    )
    # grid, home, solar, battery, level, reserve
    print("%d,%d,%d,%d,%d,%d" % (pw.grid(), pw.home(), pw.solar(), pw.battery(), pw.level(True), pw.get_reserve(True)))
except Exception as e:
    print(f"Error connecting to Powerwall: {e}", file=sys.stderr)
    exit(1)
END
)
    # Parse Powerwall stats from Python output
    IFS=',' read -r GRID HOUSE SOLAR PW LEVEL CUR <<< "${POWERWALL_STATS}"
fi

# Fetch max temperature from InfluxDB for past 24 hours (optional)
MAX_TEMP=0
if [[ -n "${INFLUXDB_IP:-}" ]]; then
    MAX_TEMP=$(${PYTHON3} << END
import influxdb
import sys
try:
    client = influxdb.InfluxDBClient("${INFLUXDB_IP}", database='powerwall')
    query = 'SELECT max("temp_max") FROM "autogen"."weather" WHERE time > now() - 24h GROUP BY time(1d) fill(none)'
    result = client.query(query)
    points = list(result.get_points())
    if len(points) > 0 and 'max' in points[0] and points[0]['max'] is not None:
        print(int(points[0]['max']))
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
        ${PYTHON3} "${SET_RESERVE_SCRIPT}" --current
    else
        ${PYTHON3} "${SET_RESERVE_SCRIPT}" --set "${new_reserve}"
    fi

    echo "${MONTH} ${DATE} ${YEAR} ${HOUR}:${MINUTE}: Updated reserve to ${new_reserve}% - Battery: ${LEVEL}%, Grid: ${GRID}W, House: ${HOUSE}W, Solar: ${SOLAR}W, PW: ${PW}W, Old Reserve: ${CUR}%" | tee -a "${LOGFILE}"
}

# --- Logic for operations ---

# Check for weather alerts that may make it good to charge at night
# This checks a local file or HTTP endpoint for NWS (National Weather Service) power risk alerts
ALERT_MIN=${MIN_RESERVE}
WEATHER_ALERT_ACTIVE=false
if [[ -n "${WEATHER_ALERT_URL:-}" ]]; then
    # Determine if WEATHER_ALERT_URL is a file or HTTP URL
    if [[ "${WEATHER_ALERT_URL}" =~ ^https?:// ]]; then
        # HTTP/HTTPS URL - use curl
        if curl -s -f "${WEATHER_ALERT_URL}" 2>/dev/null | grep -q "\"power_risk\""; then
            ALERT_MIN=${ALERT_RESERVE}
            WEATHER_ALERT_ACTIVE=true
            echo "Weather alert detected - setting minimum reserve to ${ALERT_MIN}%"
        fi
    else
        # File path - read the file
        if [[ -f "${WEATHER_ALERT_URL}" ]] && grep -q "\"power_risk\"" "${WEATHER_ALERT_URL}" 2>/dev/null; then
            ALERT_MIN=${ALERT_RESERVE}
            WEATHER_ALERT_ACTIVE=true
            echo "Weather alert detected - setting minimum reserve to ${ALERT_MIN}%"
        fi
    fi
fi

# Target reserve for this cycle, default to current reserve
TARGET_RESERVE=${CUR}

# Morning - Before 9am (00:00-08:59) - Reset reserve after overnight
if (( H < 9 && CUR > MIN_RESERVE )); then
    TARGET_RESERVE=${ALERT_MIN}
fi

# WINTER - Oct, Nov, Dec and Jan - Adjust Reserve to save energy for peak
if [[ "${MONTH}" =~ ^(Oct|Nov|Dec|Jan)$ ]]; then
    # From 9am to 4pm (09:00-15:59) - Peak solar production time - charge battery
    if (( H >= 9 && H < 16 )); then
        if (( LEVEL < WINTER_MAX_RESERVE )); then
            TARGET_RESERVE=${WINTER_MAX_RESERVE}
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

# Afternoon - 4pm to 9pm (16:00-20:59) - CRITICAL: Peak grid usage - ALWAYS force switch to battery
# This overrides everything including weather alerts to avoid expensive peak electricity rates
if (( H >= 16 && H < 21 )); then
    TARGET_RESERVE=${MIN_RESERVE}
fi

# Evening 9pm to 10pm (21:00-21:59) - Non-peak grid usage
# Stop using battery if 24h max temp was above 30C to save for next day
if (( H >= 21 && H < 22 && MAX_TEMP > 30 )); then
    # Make sure reserve is not set below current level, and not below MIN_RESERVE
    if (( LEVEL > MIN_RESERVE )); then
        TARGET_RESERVE=${LEVEL}
    else
        TARGET_RESERVE=${MIN_RESERVE}
    fi
fi

# Evening after 10pm (22:00-23:59) - Allow battery use unless it was very hot
if (( H >= 22 && MAX_TEMP < 31 )); then
    if (( CUR > MIN_RESERVE )); then
        TARGET_RESERVE=${ALERT_MIN}
    fi
fi

# --- Execution ---

# Powerwall Protection: Never let reserve go below MIN_RESERVE
if (( TARGET_RESERVE < MIN_RESERVE )); then
    TARGET_RESERVE=${MIN_RESERVE}
fi

# Weather Alert Override: Outside of peak hours (4pm-9pm), raise reserve if alert is active
# This ensures backup power during potential outages, but never during peak rate times
if [[ "${WEATHER_ALERT_ACTIVE}" == "true" ]] && (( H < 16 || H >= 21 )) && (( TARGET_RESERVE < ALERT_RESERVE )); then
    TARGET_RESERVE=${ALERT_RESERVE}
fi

# Only change reserve if it's different from current setting
if (( TARGET_RESERVE != CUR )); then
    change_reserve "${TARGET_RESERVE}"
else
    echo "Reserve setting ${CUR}% is already correct. No change needed."
fi
