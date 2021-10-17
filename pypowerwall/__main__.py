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

timeout = 0.0
state = 0
color = True

for i in sys.argv:
    if(i==sys.argv[0]):
        continue
    elif(i.lower() == "scan"):
        state = 0
    elif(i.lower() == "-nocolor"):
        color = False
    else:
        try:
            timeout = float(i)
        except:
            state = 2

# State 0 = Run Scan
if(state == 0):
    if(timeout > 0):
        scan.scan(color, timeout)
    else:
        scan.scan(color)

# State 1 = Future
if(state == 1):
    print("Future Feature")

# State 2 = Show Usage
if(state == 2):
    print("pyPowerwall [%s]\n" % (pypowerwall.version))
    print("Usage:\n")
    print("    python -m pypowerwall [command] [<timeout>] [-nocolor] [-h]")
    print("")
    print("      command = scan        Scan local network for Powerwall gateway.")
    print("      timeout               Seconds to wait per host [Default=0.2]")
    print("      -nocolor              Disable color text output.")
    print("      -h                    Show usage.")
    print("")

# End
