#!/bin/bash
set -euo pipefail

# Development run script for PyPowerwall Server
# This script attempts to detect the desired connection mode (TEDAPI/Cloud/FleetAPI)
# based on environment variables and local auth files, and will prompt interactively
# if the required information isn't present.

# Default environment variables (override with .env or export)
export SERVER_HOST=${SERVER_HOST:-"127.0.0.1"}
export SERVER_PORT=${SERVER_PORT:-8580}

# PW_AUTHPATH default
export PW_AUTHPATH=${PW_AUTHPATH:-"."}

# Helper: check if a variable was set at all (even if empty)
was_set() {
    local var_name="$1"
    if [ -z "${!var_name+x}" ]; then
        return 1
    fi
    return 0
}

# If PW_HOST was not set at all, provide the common default; if it was set to
# an empty string explicitly, respect that (used to signal Cloud mode).
if ! was_set PW_HOST; then
    export PW_HOST="192.168.91.1"
fi

# Default other ENV values if not set
export PW_GW_PWD=${PW_GW_PWD:-""}
export PW_EMAIL=${PW_EMAIL:-""}
export PW_TIMEZONE=${PW_TIMEZONE:-"America/Los_Angeles"}

# Example multi-gateway configuration (JSON format)
# export PW_GATEWAYS='[
#   {"id":"home","name":"Home","host":"192.168.91.1","gw_pwd":"gw_pwd_1","email":"tesla@email.com","authpath":"/auth"},
#   {"id":"cabin","name":"Cabin","host":"192.168.91.1","gw_pwd":"gw_pwd_2","email":"tesla@email.com","authpath":"/auth"}
# ]'

echo "Starting PyPowerwall Server..."
echo "Server: http://${SERVER_HOST}:${SERVER_PORT}"
echo "API Docs: http://${SERVER_HOST}:${SERVER_PORT}/docs"
echo ""

# Detect mode
MODE=""
if [ -n "${PW_GW_PWD:-}" ]; then
    MODE="TEDAPI"
elif [ -n "${PW_EMAIL:-}" ]; then
    # Check for fleet indicator file first
    if [ -f "${PW_AUTHPATH}/.pypowerwall.fleetapi" ]; then
        MODE="FLEETAPI"
    elif [ -f "${PW_AUTHPATH}/.pypowerwall.auth" ] && [ -f "${PW_AUTHPATH}/.pypowerwall.site" ]; then
        MODE="CLOUD"
    else
        # Auth files missing - we'll prompt the user
        MODE="CLOUD_PENDING"
    fi
else
    MODE="UNKNOWN"
fi

if [ "$MODE" = "UNKNOWN" ] || [ "$MODE" = "CLOUD_PENDING" ]; then
    echo "No complete connection config detected. Choose mode:" 
    echo "  1) TEDAPI (local gateway via PW_HOST + PW_GW_PWD)"
    echo "  2) Cloud Mode (PW_EMAIL + auth files in PW_AUTHPATH)"
    echo "  3) FleetAPI (PW_EMAIL + .pypowerwall.fleetapi in PW_AUTHPATH)"
    read -r -p "Select mode [1-3] (default 1): " choice || true
    choice=${choice:-1}
    if [ "$choice" = "1" ]; then
        MODE="TEDAPI"
        if [ -z "${PW_HOST:-}" ]; then
            read -r -p "Enter PW_HOST (gateway IP, default 192.168.91.1): " input_host || true
            PW_HOST=${input_host:-"192.168.91.1"}
            export PW_HOST
        fi
        if [ -z "${PW_GW_PWD:-}" ]; then
            read -r -s -p "Enter PW_GW_PWD (gateway Wi-Fi password): " input_pwd || true
            echo
            PW_GW_PWD=${input_pwd}
            export PW_GW_PWD
        fi
    elif [ "$choice" = "2" ]; then
        MODE="CLOUD"
        if [ -z "${PW_EMAIL:-}" ]; then
            read -r -p "Enter PW_EMAIL (Tesla account email): " input_email || true
            PW_EMAIL=${input_email}
            export PW_EMAIL
        fi
        if [ ! -f "${PW_AUTHPATH}/.pypowerwall.auth" ] || [ ! -f "${PW_AUTHPATH}/.pypowerwall.site" ]; then
            echo "Auth files not found in ${PW_AUTHPATH}. Please run 'python3 -m pypowerwall setup' or place .pypowerwall.auth and .pypowerwall.site in ${PW_AUTHPATH}."
            read -r -p "Continue anyway? [y/N]: " cont || true
            if [ "${cont,,}" != "y" ]; then
                echo "Aborting startup. Provide auth files or choose another mode." >&2
                exit 1
            fi
        fi
    elif [ "$choice" = "3" ]; then
        MODE="FLEETAPI"
        if [ -z "${PW_EMAIL:-}" ]; then
            read -r -p "Enter PW_EMAIL (Tesla account email): " input_email || true
            PW_EMAIL=${input_email}
            export PW_EMAIL
        fi
        if [ ! -f "${PW_AUTHPATH}/.pypowerwall.fleetapi" ]; then
            echo "FleetAPI marker file .pypowerwall.fleetapi not found in ${PW_AUTHPATH}. Create the file to indicate FleetAPI usage or place your auth files accordingly." >&2
            read -r -p "Continue anyway? [y/N]: " cont || true
            if [ "${cont,,}" != "y" ]; then
                echo "Aborting startup. Provide .pypowerwall.fleetapi or choose another mode." >&2
                exit 1
            fi
        fi
    else
        echo "Invalid selection" >&2
        exit 1
    fi
fi

echo "Detected mode: ${MODE}"
case "$MODE" in
    TEDAPI)
        echo "Using TEDAPI: PW_HOST=${PW_HOST}, PW_GW_PWD=${PW_GW_PWD:+***}" ;;
    CLOUD)
        unset PW_HOST
        echo "Using Cloud Mode: PW_EMAIL=${PW_EMAIL}, PW_AUTHPATH=${PW_AUTHPATH}" ;;
    FLEETAPI)
        unset PW_HOST
        echo "Using FleetAPI: PW_EMAIL=${PW_EMAIL}, PW_AUTHPATH=${PW_AUTHPATH}" ;;
    *)
        echo "Starting in default (TEDAPI) mode" ;;
esac

# Run with uvicorn
uvicorn app.main:app --host "$SERVER_HOST" --port "$SERVER_PORT" --reload
