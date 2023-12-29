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
    print("pyPowerwall [%s] - Cloud Mode Setup\n" % (pypowerwall.version))
    # Run Setup
    c = cloud.TeslaCloud(None)
    if c.setup():
        print("Setup Complete. Auth file %s ready to use." % (AUTHFILE))
    else:
        print("ERROR: Failed to setup Tesla Cloud Mode")
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
