#!/bin/bash

# Development run script for PyPowerwall Server

# Default environment variables (override with .env or export)
export SERVER_HOST=${SERVER_HOST:-"127.0.0.1"}
export SERVER_PORT=${SERVER_PORT:-8580}

# Example single gateway configuration
export PW_HOST=${PW_HOST:-"192.168.91.1"}
export PW_GW_PWD=${PW_GW_PWD:-""}  # Gateway Wi-Fi password for TEDAPI (from QR code)
export PW_EMAIL=${PW_EMAIL:-""}
export PW_AUTHPATH=${PW_AUTHPATH:-""}  # Path to .pypowerwall.auth/.site files
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

# Run with uvicorn
uvicorn app.main:app --host "$SERVER_HOST" --port "$SERVER_PORT" --reload
