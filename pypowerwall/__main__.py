# pyPowerWall Module - Scan Function
# -*- coding: utf-8 -*-
"""
 Python module to interface with Tesla Solar Powerwall Gateway

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Scan Function:
    python -m pypowerwall <scan>

"""

# Modules
import pypowerwall
import sys
import os
import json
from . import scan
from . import cloud

# Global Variables
AUTHFILE = ".pypowerwall.auth"
timeout = 1.0
state = 0
color = True

for i in sys.argv:
    if(i==sys.argv[0]):
        continue
    elif(i.lower() == "scan"):
        state = 0
    elif(i.lower() == "setup"):
        state = 1
    elif(i.lower() == "-nocolor"):
        color = False
    else:
        try:
            timeout = float(i)
        except:
            state = 2

# State 0 = Run Scan
if(state == 0):
    scan.scan(color, timeout)

# State 1 = Cloud Mode Setup
if(state == 1):
    print("pyPowerwall [%s]\n" % (pypowerwall.version))
    print("Cloud Mode Setup\n")

    # Check for existing auth file
    if os.path.isfile(AUTHFILE):
        with open(AUTHFILE) as json_file:
            try:
                data = json.load(json_file)
                tuser = list(data.keys())[0]
            except Exception as err:
                tuser = None
        # Ask to overwrite
        print(f"Found {AUTHFILE} configuration file for {tuser}")
        answer = input("Overwrite and run setup? (y/n) ")
        if answer.lower() == "y":
            os.remove(AUTHFILE)
        else:
            print("Exiting")
            exit(0)

    # Run Setup
    c = cloud.TeslaCloud(None)
    c.setup()
    tuser = c.email

    # Test Connection
    print("Testing connection to Tesla Cloud...")
    c = cloud.TeslaCloud(tuser) 
    if c.connect():
        print("Connected to Tesla Cloud...")   
        sites = c.getsites()
        print("Found %d Powerwall Sites:" % (len(sites)))
        """
        "energy_site_id": 255476044283,
        "resource_type": "battery",
        "site_name": "Cox Energy Gateway",
        """
        for s in sites:
            print("  %s (%s) - Type: %s" % (s["site_name"], 
                    s["energy_site_id"], s["resource_type"]))
        print(f"\nSetup Complete. Auth file {AUTHFILE} ready to use.")
    else:
        print("ERROR: Failed to connect to Tesla Cloud")
        exit(1)

# State 2 = Show Usage
if(state == 2):
    print("pyPowerwall [%s]\n" % (pypowerwall.version))
    print("Usage:\n")
    print("    python -m pypowerwall [command] [<timeout>] [-nocolor] [-h]")
    print("")
    print("      command = scan        Scan local network for Powerwall gateway.")
    print("      command = setup       Setup Tesla Login for Cloud Mode access.")
    print("      timeout               Seconds to wait per host [Default=%0.1f]" % (timeout))
    print("      -nocolor              Disable color text output.")
    print("      -h                    Show usage.")
    print("")

# End
