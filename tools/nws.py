#!/usr/bin/env python3
"""
US National Weather Service - Power Outage Risk Checker

Checks NWS for active weather alerts and writes JSON to a file indicating
whether there is a power outage risk in the configured area.

Output format:
  {"power_risk": true}  - Power outage risk detected
  {}                     - No alerts or no power risk

Configuration:
  Set MY_LAT and MY_LON to your location coordinates
  Set OUTPUT_FILE to the desired output file path
"""

import requests
import json
import sys
import os

# --- Configuration ---
MY_LAT = 39.8283  # Geographic center of contiguous US (Lebanon, Kansas)
MY_LON = -98.5795
OUTPUT_FILE = "/tmp/nws.json"  # File path where JSON output will be written
# --- End Configuration ---

NWS_URL = f"https://api.weather.gov/alerts/active?point={MY_LAT},{MY_LON}"

# List of Alert Types most likely to cause power outages
POWER_OUTAGE_EVENT_TYPES = [
    "Severe Thunderstorm Warning",
    "Severe Thunderstorm Watch",
    "Tornado Warning",
    "Tornado Watch",
    "Hurricane Force Wind Warning",
    "Hurricane Force Wind Watch",
    "Hurricane Warning",
    "Hurricane Watch",
    "High Wind Warning",
    "High Wind Watch",
    "Wind Advisory",
    "Blizzard Warning",
    "Blizzard Watch",
    "Ice Storm Warning",
    "Flash Flood Warning",
    "Flash Flood Watch",
    "Flood Warning",
    "Flood Watch",
    "Storm Surge Warning",
    "Storm Surge Watch",
    "Tsunami Warning",
    "Tsunami Watch",
    "Volcano Warning",
    "Extreme Fire Danger",
    "Fire Warning",
    "Red Flag Warning",
    "Winter Storm Warning",
    "Earthquake Warning"
]

def check_power_risk():
    """Check NWS for power outage risk alerts and write to file."""
    try:
        response = requests.get(NWS_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        result = {}
        
        # Check for active alerts
        if 'features' in data and data['features']:
            for feature in data['features']:
                props = feature.get('properties', {})
                
                # Only process Alert or Update message types
                if props.get('messageType') in ["Alert", "Update"]:
                    event_type = props.get('event', '')
                    
                    # Check if this event type poses a power outage risk
                    if event_type in POWER_OUTAGE_EVENT_TYPES:
                        result['power_risk'] = True
                        break
        
        # Write JSON result to file
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(result, f)
        
        print(f"NWS check complete. Power risk: {result.get('power_risk', False)}")
        return 0
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching NWS data: {e}", file=sys.stderr)
        # Write empty JSON on error
        try:
            with open(OUTPUT_FILE, 'w') as f:
                json.dump({}, f)
        except:
            pass
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        # Write empty JSON on error
        try:
            with open(OUTPUT_FILE, 'w') as f:
                json.dump({}, f)
        except:
            pass
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        print("{}")  # Output empty JSON on error
        return 1

if __name__ == "__main__":
    sys.exit(check_power_risk())
