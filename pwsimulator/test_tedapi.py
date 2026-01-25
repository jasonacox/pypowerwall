#!/usr/bin/env python3
# Test script for TEDAPI simulator endpoints
# -*- coding: utf-8 -*-
"""
Test the TEDAPI endpoints in the simulator
"""

import requests
import urllib3
import json

# Disable SSL warnings for self-signed certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Test configuration
SIMULATOR_HOST = "localhost"
SIMULATOR_PORT = 443
BASE_URL = f"https://{SIMULATOR_HOST}:{SIMULATOR_PORT}"
GW_PASSWORD = "ABCDEFGHIJ"  # Gateway password (matches example.py)

print("Testing TEDAPI Simulator Endpoints\n")
print("=" * 60)

# Test 1: GET /tedapi/din
print("\n1. Testing GET /tedapi/din")
try:
    response = requests.get(
        f"{BASE_URL}/tedapi/din",
        auth=('Tesla_Energy_Device', GW_PASSWORD),
        verify=False,
        timeout=5
    )
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        din = response.text.strip()
        print(f"   DIN: {din}")
        print("   ✓ Success")
    else:
        print(f"   ✗ Failed: {response.text}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 2: POST /tedapi/v1 (small request - config)
print("\n2. Testing POST /tedapi/v1 (config request)")
try:
    # Simulate a small protobuf request (config)
    small_payload = b'\x0a\x10\x08\x01\x12\x04\x1a\x02\x08\x01\x1a\x06\x32\x04\x08\x01\x12\x00\x12\x02\x08\x01'
    response = requests.post(
        f"{BASE_URL}/tedapi/v1",
        auth=('Tesla_Energy_Device', GW_PASSWORD),
        data=small_payload,
        headers={'Content-type': 'application/octet-stream'},
        verify=False,
        timeout=5
    )
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        try:
            config = json.loads(response.content)
            print(f"   VIN: {config.get('vin', 'N/A')}")
            print(f"   Battery Blocks: {len(config.get('battery_blocks', []))}")
            print(f"   Site Name: {config.get('site_info', {}).get('site_name', 'N/A')}")
            print("   ✓ Success")
        except json.JSONDecodeError:
            print(f"   Response (first 100 bytes): {response.content[:100]}")
            print("   ✓ Success (raw response)")
    else:
        print(f"   ✗ Failed: {response.text}")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 3: POST /tedapi/v1 (large request - status)
print("\n3. Testing POST /tedapi/v1 (status request)")
try:
    # Simulate a larger protobuf request (status/controller query)
    large_payload = b'\x0a' + b'\x00' * 1500  # Just padding to make it larger
    response = requests.post(
        f"{BASE_URL}/tedapi/v1",
        auth=('Tesla_Energy_Device', GW_PASSWORD),
        data=large_payload,
        headers={'Content-type': 'application/octet-stream'},
        verify=False,
        timeout=5
    )
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        try:
            status = json.loads(response.content)
            energy_remaining = status.get('control', {}).get('systemStatus', {}).get('nominalEnergyRemainingWh', 0)
            energy_full = status.get('control', {}).get('systemStatus', {}).get('nominalFullPackEnergyWh', 0)
            battery_percent = (energy_remaining / energy_full * 100) if energy_full > 0 else 0
            print(f"   Battery Level: {battery_percent:.1f}%")
            
            meters = status.get('control', {}).get('meterAggregates', [])
            for meter in meters:
                location = meter.get('location', 'Unknown')
                power = meter.get('realPowerW', 0)
                print(f"   {location}: {power}W")
            print("   ✓ Success")
        except json.JSONDecodeError:
            print(f"   Response (first 100 bytes): {response.content[:100]}")
            print("   ✓ Success (raw response)")
    else:
        print(f"   ✗ Failed: {response.text}")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("Tests completed!\n")
