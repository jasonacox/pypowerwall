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
from . import scan
from . import cloud

# Global Variables
AUTHFILE = ".pypowerwall.auth"
authpath = os.getenv("PW_AUTH_PATH", "")
timeout = 1.0
hosts = 30
state = 0
color = True
ip = None
email = None

for i in sys.argv:
    if(i==sys.argv[0]):
        continue
    elif(i.lower() == "scan"):
        state = 0
    elif(i.lower() == "setup"):
        state = 1
    elif(i.lower() == "-nocolor"):
        color = False
    elif(i.lower()[0:4] == "-ip="):
        ip = i[4:]
    elif(i.lower()[0:7] == "-hosts="):
        try:
            hosts = int(i[7:])
        except:
            state = 2
    elif(i.lower()[0:7] == "-email="):
        email = i[7:]
    else:
        try:
            timeout = float(i)
        except:
            state = 2

# State 0 = Run Scan
if(state == 0):
    scan.scan(color, timeout, hosts, ip)

# State 1 = Cloud Mode Setup
if(state == 1):
    print("pyPowerwall [%s] - Cloud Mode Setup\n" % (pypowerwall.version))
    # Run Setup
    c = cloud.TeslaCloud(None, authpath=authpath)
    if c.setup(email):
        print("Setup Complete. Auth file %s ready to use." % (AUTHFILE))
    else:
        print("ERROR: Failed to setup Tesla Cloud Mode")
        exit(1)

# State 2 = Show Usage
if(state == 2):
    print("pyPowerwall [%s]\n" % (pypowerwall.version))
    print("Usage:\n")
    print("    python -m pypowerwall [command] [<timeout>] [-nocolor] [-ip=<ip>] [-hosts=<hosts>] [-email=<email>] [-h]")
    print("")
    print("      command = scan        Scan local network for Powerwall gateway.")
    print("      command = setup       Setup Tesla Login for Cloud Mode access.")
    print("      timeout               (Scan option) Seconds to wait per host [Default=%0.1f]" % (timeout))
    print("      -nocolor              (Scan option) Disable color text output.")
    print("      -ip=<ip>              (Scan option) IP address within network to scan.")
    print("      -hosts=<hosts>        (Scan option) Number of hosts to scan simultaneously [Default=%d]" % (hosts))
    print("      -email=<email>        (Setup option) Email address for Tesla Login.")
    print("      -h                    Show usage.")
    print("")

# End
