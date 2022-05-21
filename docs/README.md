# pyPowerwall Helpful Documentation

## View Local Tesla Powerwall Portal

The Powerwall gateway has a web based portal that you can access to the power flow animation. This requires that you find the local IP address of you Powerwall.  You can do that using `pypowerwall`:


```bash
# Install pyPowerwall if you haven't already
python -m pip install pypowerwall

# Scan Network for Powerwall
python -m pypowerwall scan
```

After confirming your local network address space, it will scan your network looking for a Tesla Powerwall and respond with something like this:

```
Discovered 1 Powerwall Gateway
     10.0.1.23 [1234567-00-E--TG123456789ABC]
```

Point your browser to that address http://10.0.1.23 and you will be able to log in and see the power details and flow animation:

[![portal.png](portal.png)](portal.png)


## Solar Panel Strings

You can use pyPowerwall to grab individual string data.  It uses the protobuf payload from the 'vitals' API.

```python
import pypowerwall

# Credentials for your Powerwall
password='password'
email='email@example.com'
host = "10.0.1.123"               # Address of your Powerwall Gateway
timezone = "America/Los_Angeles"  # Your local timezone

# Connect to Powerwall
pw = pypowerwall.Powerwall(host,password,email,timezone)

# Print String Data in JSON
print(pw.strings(True))   # True = JSON format output
```

Output example:

```json
{
    "A": {
        "Connected": true,
        "Current": 1.81,
        "Power": 422.0,
        "State": "PV_Active",
        "Voltage": 230.0
    },
    "B": {
        "Connected": false,
        "Current": 0.0,
        "Power": 0.0,
        "State": "PV_Active",
        "Voltage": -2.5
    },
    "C": {
        "Connected": true,
        "Current": 4.47,
        "Power": 892.0,
        "State": "PV_Active",
        "Voltage": 202.4
    },
    "D": {
        "Connected": true,
        "Current": 4.44,
        "Power": 889.0,
        "State": "PV_Active_Parallel",
        "Voltage": 202.10000000000002
    }
}
```

## Firmware Version History

Firmware version of the Powerwall can be seen with `pw.version()`.

| Powerwall Firmware | Date Seen | Features | pyPowerwall | Tesla App |
| --- | --- | --- | --- | --- |
| 20.49.0 | Unknown | Unknown | N/A | |
| 21.13.2 | May-2021 | Improved Powerwall behavior during power outage. Push notification when charge level is low during outage. | N/A | |
| 21.31.2 | Sep-2021 | Unknown | N/A | |
| 21.39.1 7759c368 | Nov-2021 | Unknown | v0.1.0 | |
| 21.44 223a5cd | Unknown | Issue with this firmware is that when the Neurio meter (1.6.1-Tesla) loses connection with gateway (happens frequently) it stops solar generation. | v0.1.0 | |
| 21.44.1 c58c2df3 | 1-Jan-2022 | Neurio converted to RGM only so that when it disconnects it no longer stop solar power generation | v0.2.0 | |
| 22.1 92118b67 | 21-Jan-2022 | Upgrades Neurio Revenue Grade Meter (RGM) to 1.7.1-Tesla addressing Neurio instability and missing RGM data | v0.3.0 | |
| 22.1.1 | 22-Feb-2022 | Unknown | v0.3.0 | |
| 22.1.2 34013a3f | N/A | Unknown | N/A | |
| 22.9.1 | 12-Apr-2022 | Unknown | v0.4.0 | 4.7.1-925 |
| 22.9.1.1 75c90bda | 2-May-2022 | Unknown | v0.4.0 | 4.8.0-1025 |
| 22.9.2 a54352e6 | 2-May-2022 | Unknown | v0.4.0 Proxy t11 | 4.8.0-1025 |

## Devices and Alerts

Devices and Alerts will show up in the device vitals API (e.g. /api/device/vitals).  Below are a list of the devices and alerts that I have seen.  I'm looking for information on what these mean. Please submit an Issue or PR if you have more alerts or definitions we can add.  The device details below are mostly educated guesses.

```python
    import pypowerwall

    # Connect to Powerwall
    pw = pypowerwall.Powerwall(host,password,email,timezone)

    # Display Device Vitals
    print("Device Vitals:\n %s\n" % pw.vitals(True))
```

Example Output: [here](https://github.com/jasonacox/pypowerwall/blob/main/docs/vitals-example.json)

### Devices

| Device | ECU Type | Description |
| --- | --- | --- |
| STSTSM | 207 | Tesla Energy System |
| TETHC | 224 | Tesla Energy Total Home Controller - Energy Storage System (ESS) |
| TEPOD | 226 | Tesla Energy Powerwall |
| TEPINV | 253 | Tesla Energy Powerwall Inverter |
| TESYNC | 259 | Tesla Energy Synchronizer |
| TEMSA | 300 | Tesla Backup Switch |
| PVAC | 296 | Photovoltaic AC - Solar Inverter |
| PVS | 297 | Photovoltaic Strings |
| TESLA | x | Internal Device Attributes |
| NERUIO | x | Wireless Revenue Grade Solar Meter |

#### STSTSM - Tesla Energy System

* Details
    * This appears to be the primary control unit for the Tesla Energy Systems. 
    * ECU Type is 207
    * Part Numbers: 1232100-XX-Y, 1152100-XX-Y, 1118431-xx-y
    * Tesla Gateway 1 (1118431-xx-y) or Tesla Gateway 2 (1232100-xx-y)
    * Tesla Backup Switch (1624171-xx-y)

* Alerts
    * GridCodesWrite - Unknown
    * SiteMinPowerLimited - Unknown
    * FWUpdateSucceeded - Firmware Upgrade Succeeded
    * PodCommissionTime - Unknown
    * BackfeedLimited - Unknown
    * RealPowerAvailableLimited - Unknown but seems to happen when Powerwall reaches 100% full
    * BatteryFault - Powerwall Failure
    * ScheduledIslandContactorOpen - Manually Disconnected from Grid

#### TETHC - Tesla Energy Total Home Controller

* Details
    * Appears to be controller for Powerwall/2/+ Systems
    * ECU Type is 224
    * Part 1092170-XX-Y (Powerwall 2)
    * Part 2012170-XX-Y (Powerwall 2.1)
    * Part 3012170-XX-Y (Powerwall +)

 * Alerts
    * THC_w061_CAN_TX_FIFO_Overflow
    * THC_w155_Backup_Genealogy_Updated - Unknown but seen during firmware upgrade.

#### TEPOD - Tesla Energy Powerwall

* Details
    * Appears to be the Powerwall battery system (not sure of what POD stands for)
    * ECU Type is 226
    * Part 1081100-XX-Y
    * Component of TETHC

 * Alerts
    * POD_f029_HW_CMA_OV
    * POD_w024_HW_Fault_Asserted
    * POD_w029_HW_CMA_OV
    * POD_w031_SW_Brick_OV
    * POD_w044_SW_Brick_UV_Warning
    * POD_w045_SW_Brick_OV_Warning
    * POD_w048_SW_Cell_Voltage_Sens
    * POD_w058_SW_App_Boot
    * POD_w063_SW_SOC_Imbalance
    * POD_w067_SW_Not_Enough_Energy_Precharge
    * POD_w090_SW_SOC_Imbalance_Limit_Charge
    * POD_w093_SW_Charge_Request
    * POD_w105_SW_EOD
    * POD_w109_SW_Self_Test_Request_Not_Serviced - Unknown
    * POD_w110_SW_EOC - Unknown

#### TEPINV - Tesla Energy Powerwall Inverter

* Details
    * Appears to be the Powerwall Inverter for battery energy storage/release
    * ECU Type is 253
    * Part 1081100-XX-Y
    * Component of TETHC

* Alerts  
    * PINV_a010_can_gtwMIA - Indicate that gateway/sync is MIA (seen during firmware upgrade reboot)
    * PINV_a039_can_thcMIA - Seems to indicate that Home Controller is MIA (seen during firmware upgrade reboot)
    * PINV_a067_overvoltageNeutralChassis - Unknown

#### TESYNC - Tesla Energy Synchronizer

* Details
    * Telsa Backup Gateway includes a synchronizer constantly monitoring grid voltage and frequency to relay grid parameters to Tesla Powerwall during Backup to Grid-tied transition.
    * ECU Type is 259
    * Part 1493315-XX-Y
    * Component of TETHC

* Alerts
    * SYNC_a001_SW_App_Boot - Unknown
    * SYNC_a038_DoOpenArguments - Unknown

#### TEMSA - Tesla Backup Switch

* Details
    * Tesla Backup Switch is designed to simplify installation of your Powerwall system. It plugs into your meter socket panel, with the meter plugging directly into the Backup Switch. Within the Backup Switch housing, the contactor controls your system’s connection to the grid. The controller provides energy usage monitoring, providing you with precise, real-time data of your home’s energy consumption.
    * ECU Type is 300
    * Part 1624171-XX-E - Tesla Backup Switch (1624171-xx-y)

#### PVAC - Photovoltaic AC - Solar Inverter

* Details
    * ECU Type is 296
    * Part 1534000-xx-y - 3.8kW
    * Part 1538000-xx-y - 7.6kW
    * Component of TETHC

#### PVS - Photovoltaic Strings

* Details
    * ECU Type is 297
    * This terminates the Photovoltaic DC power strings
    * Component of PVAC

* Alerts
    * PVS_a018_MciString[A-D] - This indicates a solar string (A, B, C or D) that is not connected.
    * PVS_a026_Mci1PvVoltage
    * PVS_a027_Mci2PvVoltage
    * PVS_a031_Mci3PvVoltage
    * PVS_a032_Mci4PvVoltage

#### NEURIO - Wireless Revenue Grade Solar Meter

* Details
    * This is a third party (Generac) meter with Tesla proprietary firmware.  It is generally installed as a wireless meter to report on solar production.  [Link](https://neur.io/)
    * Component of STSTSM

#### TESLA - Internal Device Attributes

* Details
    * This is used to describe attributes of the inverter, meters and others
    * Component of STSTSM
