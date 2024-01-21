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
import threading
import json
import time

# Backward compatibility for python2
try:
    input = raw_input
except NameError:
    pass

# Globals
discovered = {}
firmware = {}

# Terminal Color Formatting
bold = "\033[0m\033[97m\033[1m"
subbold = "\033[0m\033[32m"
normal = "\033[97m\033[0m"
dim = "\033[0m\033[97m\033[2m"
alert = "\033[0m\033[91m\033[1m"
alertdim = "\033[0m\033[91m\033[2m"

# Helper Functions
def getmyIP():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    r = s.getsockname()[0]
    s.close()
    return r

def scanIP(color, timeout, addr):
    global discovered, firmware
    global bold, subbold, normal, dim, alert, alertdim

    if(color == False):
        # Disable Terminal Color Formatting
        bold = subbold = normal = dim = alert = alertdim = ""

    host = dim + '\r      Host: ' + subbold + '%s ...' % addr + normal
    print(host, end='')
    a_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    a_socket.settimeout(timeout)
    location = (str(addr), 443)
    while True:
        result_of_check = a_socket.connect_ex(location)
        if not result_of_check == socket.errno.EAGAIN:
            break
        time.sleep(0.1)
    if result_of_check == 0:
        # Check to see if it is a Powerwall
        url = 'https://%s/api/status' % addr
        try:
            g = requests.get(url, verify=False, timeout=5)
            # Check if 404 response
            if(g.status_code == 404):
                # Check if it is a Powerwall 3
                url = 'https://%s/tedapi/din' % addr
                g = requests.get(url, verify=False, timeout=5)
                # Expected response from PW3 {"code":403,"error":"Unable to GET to resource","message":"User does not have adequate access rights"}
                if "User does not have adequate access rights" in g.text:
                    # Found PW3
                    print(host + ' OPEN' + dim + ' - ' + subbold + 'Found Powerwall 3 [Supported in Cloud Mode only]')
                    discovered[addr] = 'Powerwall-3'
                    firmware[addr] = 'Supported in Cloud Mode only - See https://tinyurl.com/pw3support'
                else:
                    # Not a Powerwall
                    print(host + ' OPEN' + dim + ' - Not a Powerwall')
            else:
                data = json.loads(g.text)
                print(host + ' OPEN' + dim + ' - ' + subbold + 'Found Powerwall %s' % data['din'] + subbold + '\n                                     [Firmware %s]' % data['version'])
                discovered[addr] = data['din']
                firmware[addr] = data['version']
        except:
            print(host + ' OPEN' + dim + ' - Not a Powerwall')

    a_socket.close()

def scan(color=True, timeout=1.0, hosts=30, ip=None):
    """
    pyPowerwall Network Scanner

    Parameter:
        color = True or False, print output in color [Default: True]
        timeout = Seconds to wait per host [Default: 1.0]
        hosts = Number of hosts to scan simultaneously [Default: 30]
        ip = IP address within network to scan [Default: None (detect IP)]

    Description
            This tool will scan your local network looking for a Tesla Energy Gateway
            and Powerwall.  It tries to use your local IP address as a default.

    """
    global discovered, firmware
    global bold, subbold, normal, dim, alert, alertdim

    if(color == False):
        # Disable Terminal Color Formatting
        bold = subbold = normal = dim = alert = alertdim = ""

    # Fetch my IP address and assume /24 network
    try: 
        if ip is None:
            ip = getmyIP()
        network = ipaddress.IPv4Interface(u''+ip+'/24').network
    except:
        print(alert + 'ERROR: Unable to get your IP address and network automatically.' + normal)
        network = '192.168.0.0/24'
        ip = None

    print(bold + '\npyPowerwall Network Scanner' + dim + ' [%s]' % (pypowerwall.version) + normal)
    print(dim + 'Scan local network for Tesla Powerwall Gateways')
    print('')

    if(hosts > 100):
        # Limit simultaneous host scan to no more than 100
        hosts = 100

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
    print('')
    print(bold + '    Running Scan...' + dim)
    # Loop through each host
    try:
        threads = []
        for addr in ipaddress.IPv4Network(network):
            # Scan each host in a separate thread
            thread = threading.Thread(target=scanIP, args=(color, timeout, addr))
            thread.start()
            threads.append(thread)
            if threading.active_count() >= hosts:
                # Wait for thread to exit when max simultaneous hosts reached
                threads[0].join()
                threads.pop(0)
        for thread in threads:
            # Wait for remaining threads to exit
            thread.join()
        
        print(dim + '\r      Done                           ')
        print('')

    except KeyboardInterrupt:
        print(dim + '\r      ** Interrupted by user **                        ')
        print('')

    print(normal + 'Discovered %d Powerwall Gateway' % len(discovered))
    for ip in discovered:
        print(dim + '     %s [%s] Firmware %s' % (ip,discovered[ip],firmware[ip]))

    print(normal + ' ')



    
    


