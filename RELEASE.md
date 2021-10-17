# RELEASE NOTES

## v0.0.2 - Scan Function

* PyPI 0.0.2
* pyPowerwall now has a network scan function to find the IP address of Powerwalls
```bash
# Scan Network for Powerwalls
python -m pypowerwall scan
```
Output Example:
```
pyPowerwall Network Scanner [0.0.2]
Scan local network for Tesla Powerwall Gateways

    Your network appears to be: 10.0.3.0/24

    Enter Network or press enter to use 10.0.3.0/24: 

    Running Scan...
      Host: 10.0.3.22 ... OPEN - Not a Powerwall
      Host: 10.0.3.45 ... OPEN - Found Powerwall 1234567-00-E--TG123456789ABC
      Done                           

Discovered 1 Powerwall Gateway
     10.0.1.45 [1234567-00-E--TG123456789ABC]
```

## v0.0.1 - Initial Release

* PyPI 0.0.1
* Initial Beta Release 0.0.1