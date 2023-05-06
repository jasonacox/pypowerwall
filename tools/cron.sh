#!/bin/bash
#
# Cronjob to check Powerwall battery charge level and
# adjust the reserve limit. 
#
# This script is set to optimize Powerwall charging during
# solar production (clean energy) and use battery during
# peak grid usage (dirty energy) time. 
#
# Requires:
#  * pypowerwall python module (pip install pypowerwall)
#  * Tesla auth file setup - see instructions at:
#    https://github.com/jasonacox/pypowerwall/tree/main/tools
#  * weather411 service (optional)
#    (see https://github.com/jasonacox/Powerwall-Dashboard/tree/main/weather)

# SET THIS 
POWERWALL='10.1.1.10'     # address of Powerwall
WEATHER='10.1.1.11'       # address of weather411 service
PASSWORD='yourPassword'   # Powerwall password
FOLDER='/home/tesla'      # Location of Tesla auth file

# Reserve Settigs
MAX=80
MIN=20
CLOUDS=0

LOGFILE=cron.log
cd $FOLDER

# Fetch cloud conditions from jasonacox/weather411 container
# Note: comment out if you do not have weather411 service
CLOUDS=`curl --silent http://${WEATHER}:8676/clouds | jq -r '.clouds'`

# Fetch current stats from Powerwall 1=grid, 2=house, 3=solar, 4=pw, 5=level, 6=reserve
STATE=`python3 << END
import pypowerwall
pw = pypowerwall.Powerwall("${POWERWALL}","${PASSWORD}")
print("%d,%d,%d,%d,%d,%d" % (pw.grid(),pw.home(),pw.solar(),pw.battery(),pw.level(True),pw.get_reserve(True)))
END`

# Data from pypowerwall 1=grid, 2=house, 3=solar, 4=pw, 5=level
GRID=`echo ${STATE} | cut -f1 -d,`
HOUSE=`echo ${STATE} | cut -f2 -d,`
SOLAR=`echo ${STATE} | cut -f3 -d,`
PW=`echo ${STATE} | cut -f4 -d,`
LEVEL=`echo ${STATE} | cut -f5 -d,`
CUR=`echo ${STATE} | cut -f6 -d,`

# Current date and time
MONTH=`date +%m`
DATE=`date +%d`
YEAR=`date +%Y`
HOUR=`date +%H`
MINUTE=`date +%M`
H=`date +%H | bc` # remove leading zero
M=`date +%M | bc`
echo "$MONTH/$DATE/$YEAR ${HOUR}:${MINUTE}: The battery level is ${LEVEL}, Grid=${GRID}, House=${HOUSE}, Solar=${SO
LAR}, PW=${PW}, Reserve Setting=${CUR}, Clouds=${CLOUDS}"

# Function to change reserve
change() {
    echo "Change to ${1}"
    /usr/bin/python3 set-reserve.py --set $1
    echo "$MONTH/$DATE/$YEAR ${HOUR}:${MINUTE}: Updated to ${1} - The battery level is ${LEVEL}, Grid=${GRID}, Hous
e=${HOUSE}, Solar=${SOLAR}, PW=${PW}, Reserve was=${CUR}" >> $LOGFILE
}

# Logic for operations

# WINTER - Nov, Dec and Jan - Adjust Reserve to save energy for peak
if (( "${MONTH}" == "11" )) || ((  "${MONTH}" == "12")) || (( "${MONTH}" == "01" )); then
    # From 9am to 4pm - Peak solar production time - charge battery
    if (( $H >= 9 )) && (( $H < 16 )); then
        # 9am to 4pm
        if (( $(echo "$LEVEL < $MAX" |bc -l) )); then
            # If not charged
            if (( $(echo "$CUR < $MAX" |bc -l) )); then
                # change reserve if not already set
                change $MAX
            fi
        fi
    fi
else
# NOT WINTER
    # From 11am to 4pm - Peak solar production time - charge battery if cloudy
    if (( $H >= 11 )) && (( $H < 16 )) && (( $CLOUDS > 90 )); then
        # 11am to 4pm
        if (( $(echo "$LEVEL < $MAX" |bc -l) )); then
            # If not charged
            if (( $(echo "$CUR < $MAX" |bc -l) )); then
                # change reserve if not already set
                change $MAX
            fi
        fi
    fi
fi

# Afternoon - Peak grid usage - force switch to battery
if (( $H >= 16 )); then
    if (( $(echo "$CUR > $MIN" |bc -l) )); then
        # change reserve if not already set
        change $MIN
    fi
fi

# Powerwall Protection

# Never let reserve go below MIN
if (( $CUR < $MIN )); then
    change $MIN
fi