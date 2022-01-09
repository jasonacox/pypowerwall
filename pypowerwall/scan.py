# pyPowerWall Module - Scan Function
# -*- coding: utf-8 -*-
"""
 Python module to interface with Tesla Solar Powerwall Gateway

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall

 Scan Function
    This tool will scan your local network looking for a Tesla Energy Gateway
    and Powerwall.  It uses your local IP address as a default.

"""

# Modules
from __future__ import print_function
from logging import disable   # make python 2 compatible 
import pypowerwall
import socket
import ipaddress  
import requests
import json


# for addr in ipaddress.IPv4Network('192.0.2.0/24'):
# ipaddress.IPv4Interface(ip+'/24').network

# Backward compatability for python2
try:
    input = raw_input
except NameError:
    pass

# Helper Functions
def getmyIP():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    r = s.getsockname()[0]
    s.close()
    return r

def scan(color=True, timeout=0.4):
    """
    pyPowerwall Network Scanner

    Parameter:
        color = True or False, print output in color [Default: True]

    Description
            This tool will scan your local network looking for a Telsa Energy Gateway
            and Powerwall.  It trys to use your local IP address as a default.

    """
    if(color == False):
        # Disable Terminal Color Formatting
        bold = subbold = normal = dim = alert = alertdim = ""
    else:
        # Terminal Color Formatting
        bold = "\033[0m\033[97m\033[1m"
        subbold = "\033[0m\033[32m"
        normal = "\033[97m\033[0m"
        dim = "\033[0m\033[97m\033[2m"
        alert = "\033[0m\033[91m\033[1m"
        alertdim = "\033[0m\033[91m\033[2m"

    # Fetch my IP address and assume /24 network
    try: 
        ip = getmyIP()
        network = ipaddress.IPv4Interface(u''+ip+'/24').network
    except:
        print(alert + 'ERROR: Unable to get your IP address and network automatically.' + normal)
        network = '192.168.0.0/24'
        ip = None

    print(bold + '\npyPowerwall Network Scanner' + dim + ' [%s]' % (pypowerwall.version) + normal)
    print(dim + 'Scan local network for Tesla Powerwall Gateways')
    print('')

    if(timeout < 0.2):
        print(alert + 
            '    WARNING: Setting a low timeout (%0.2fs) may cause misses.\n' % timeout)

    # Ask user to verify network
    print(dim + '    Your network appears to be: ' + bold + '%s' % network + normal)
    print('')

    try:
        response = input(subbold + "    Enter " + bold + "Network" + subbold +
                                    " or press enter to use %s: " % network + normal)
    except:
        # Assume user aborted
        print(alert + '  Cancel\n\n' + normal)
        exit()

    if(response != ''):
        # Verify we have a valid network 
        try:
            network = ipaddress.IPv4Network(u''+response)
        except:
            print('')
            print(alert + '    ERROR: %s is not a valid network.' % response + normal)
            print(dim + '           Proceeding with %s instead.' % network)
    
    # Scan network
    discovered = {}
    print('')
    print(bold + '    Running Scan...' + dim)
    # Loop through each host
    for addr in ipaddress.IPv4Network(network):
        print(dim + '\r      Host: ' + subbold + '%s ...' % addr + normal, end='')
        a_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        a_socket.settimeout(timeout)
        location = (str(addr), 443)
        result_of_check = a_socket.connect_ex(location)
        if result_of_check == 0:
            print(" OPEN", end='')
            # Check to see if it is a Powerwall
            url = 'https://%s/api/status' % addr
            try:
                g = requests.get(url, verify=False, timeout=5)
                data = json.loads(g.text)
                print(dim + ' - ' + subbold + 'Found Powerwall %s' % data['din'])
                discovered[addr] = data['din']
            except:
                print(dim + ' - Not a Powerwall')
 
        a_socket.close()
    
    print(dim + '\r      Done                           ')
    print('')

    print(normal + 'Discovered %d Powerwall Gateway' % len(discovered))
    for ip in discovered:
        print(dim + '     %s [%s]' % (ip,discovered[ip]))

    print(normal + ' ')



    
    


