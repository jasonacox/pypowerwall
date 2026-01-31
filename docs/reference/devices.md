# Powerwall Devices

Devices appear in the device vitals API (e.g., `/api/device/vitals`). Below is a list of the devices I have seen. The device details below are mostly educated guesses. If you have more information or corrections, please submit an issue or PR.

## Accessing Device Vitals

```python
import pypowerwall

# Connect to Powerwall
pw = pypowerwall.Powerwall(host, password, email, timezone, gw_pwd=gw_pwd, auto_select=True)

# Display Device Vitals
print("Device Vitals:\n %s\n" % pw.vitals(True))
```

Example Output: [vitals-example.json](../vitals-example.json)

## Device List

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
| NEURIO | x | Wireless Revenue Grade Solar Meter |

---

## STSTSM - Tesla Energy System

**Details:**
* This appears to be the primary control unit for the Tesla Energy Systems. 
* ECU Type is 207
* Part Numbers: 1232100-XX-Y, 1152100-XX-Y, 1118431-xx-y
* Tesla Gateway 1 (1118431-xx-y) or Tesla Gateway 2 (1232100-xx-y)
* Tesla Backup Switch (1624171-xx-y)

**Alerts:**
* BackfeedLimited - The system is configured for inadvertent export and therefore will not further discharge to respect this limit. It appears this controls backfeed before PTO, under the "Permission to Operate" option under the settings menu. Prior to PTO the backfeed rate is limited, as the system needs to produce over the load, but by the minimum possible. The system seems to regulate this by switching MCI's open/closed, to minimize the overage that must be backfed, as the power has to go somewhere, and at this point the batteries are 100%. This seems to toggle that setting per inverter.
* BatteryBreakerOpen - Battery disabled via breaker
* BatteryComms - Communication issue with Battery
* BatteryFault - Powerwall Failure
* BatteryUnexpectedPower - Commanded real power does not match measured power from battery meter.
* CANUsageAlert - Unknown
* DeviceShutdownRequested
* ExcessiveVoltageDrop
* FWUpdateFailed - Firmware Upgrade Failed
* FWUpdateSucceeded - Firmware Upgrade Succeeded
* GridCodesWrite - Unknown
* GridCodesWriteError - Unknown
* GridFaultContactorTrip
* HighCPU - Occurs when too many API calls are made against the gateway especially with bad credentials
* IslandingControllerMIA
* OpticasterExe - See [Opticaster](https://www.tesla.com/en_eu/support/energy/tesla-software/opticaster)
* PanelMaxCurrentLimited
* PodCommissionTimeError - Unknown but happened when some of the Powerwalls failed during a firmware upgrade and was disabled (see [discussion](https://github.com/jasonacox/Powerwall-Dashboard/discussions/47))
* PodCommissionTime - Unknown
* PVInverterComms - Communication issue with Solar Inverter (abnormal)
* RealPowerAvailableLimited - The command is greater than the Available Battery Real Charge or Discharge Power (seen when Powerwall 100% full). Seems related to BackfeedLimited.
* RealPowerConfigLimited - The system is unable to meet the commanded power because a limit that was configured during commissioning
* ScheduledIslandContactorOpen - Manually Disconnected from Grid (nominal)
* SelfConsumptionReservedLimit - Battery reached reserve limit during self-consumption mode and switches to grid (nominal)
* SiteMaxPowerLimited - Unknown
* SiteMeterComms - Communication issue with Site Meter (abnormal)
* SiteMinPowerLimited - Cannot meet command because the Site Minimum Power Limit has been set
* SolarChargeOnlyLimited - The system has been configured to only charge from solar. Solar is not available, therefore the charge request cannot be met.
* SolarMeterComms - Communication issue with Solar Meter (abnormal)
* SolarRGMMeterComms - Communication issue with Solar Revenue Grade Meter (abnormal)
* SystemConnectedToGrid - Connected successfully to Grid (nominal)
* SystemShutdown
* UnscheduledIslandContactorOpen
* WaitForUserNoInvertersReady - Occurs during grid outage when battery shuts down more than once due to load or error. Requires user intervention to restart.

---

## TETHC - Tesla Energy Total Home Controller

**Details:**
* Appears to be controller for Powerwall/2/+ Systems
* ECU Type is 224
* Part 1092170-XX-Y (Powerwall 2)
* Part 2012170-XX-Y (Powerwall 2.1)
* Part 3012170-XX-Y (Powerwall +)

**Alerts:**
* THC_w042_POD_MIA - Unknown (abnormal)
* THC_w051_Thermal_Power_Req_Not_Met - Unknown but seen during firmware upgrade.
* THC_w061_CAN_TX_FIFO_Overflow - Unknown (abnormal)
* THC_w155_Backup_Genealogy_Updated - Unknown but seen during firmware upgrade.

---

## TEPOD - Tesla Energy Powerwall

**Details:**
* Appears to be the Powerwall battery system (not sure of what POD stands for)
* ECU Type is 226
* Part 1081100-XX-Y
* Component of TETHC

**Alerts:**
* POD_f029_HW_CMA_OV
* POD_f053_SW_CMA_Cell_MIA
* POD_w017_SW_Batt_Volt_Sens_Irrational
* POD_w024_HW_Fault_Asserted
* POD_w029_HW_CMA_OV
* POD_w031_SW_Brick_OV - It seems that the Brick warnings are related to preventing the condition where the Powerwall doesn't have the minimum amount of power it needs to turn back on. When this happens, a third‑party charger is needed to get the Powerwall back to its minimum operating battery requirement to turn back on, or it's "bricked." Solar cannot return it to this state because it needs power to make power.
* POD_w041_SW_CMA_Comm_Integrity
* POD_w044_SW_Brick_UV_Warning - see POD_w031_SW_Brick_OV
* POD_w045_SW_Brick_OV_Warning - see POD_w031_SW_Brick_OV
* POD_w048_SW_Cell_Voltage_Sens
* POD_w049_SW_CMA_Voltage_Mismatch
* POD_w058_SW_App_Boot - Possibly indicating autostart of a generator.
* POD_w063_SW_SOC_Imbalance
* POD_w064_SW_Brick_Low_Capacity - see POD_w031_SW_Brick_OV
* POD_w067_SW_Not_Enough_Energy_Precharge
* POD_w090_SW_SOC_Imbalance_Limit_Charge
* POD_w093_SW_Charge_Request
* POD_w105_SW_EOD 
* POD_w109_SW_Self_Test_Request_Not_Serviced - Unknown
* POD_w110_SW_EOC - "End of Charge" This triggers when full backfeed starts and battery at 100%.

---

## TEPINV - Tesla Energy Powerwall Inverter

**Details:**
* Appears to be the Powerwall Inverter for battery energy storage/release
* ECU Type is 253
* Part 1081100-XX-Y
* Component of TETHC

**Alerts:**  
* PINV_a001_vfCheckPIIErrorHigh
* PINV_a006_vfCheckUnderFrequency
* PINV_a010_can_gtwMIA - Indicate that gateway/sync is MIA (seen during firmware upgrade reboot)
* PINV_a011_can_podMIA - Unknown (abnormal)
* PINV_a016_basicAcCheckUnderVoltage
* PINV_a022_SwitchingBridgeIrrational - Reported during grid outage and on the transition back to grid.
* PINV_a023_LossOfCurrentControl
* PINV_a039_can_thcMIA - Seems to indicate that Home Controller is MIA (seen during firmware upgrade reboot)
* PINV_a041_sensedGridDisturbance - Reported during "lights flickering" events and after "grid outage"
* PINV_a043_gridResistanceTooHigh - Unknown (see https://github.com/jasonacox/Powerwall-Dashboard/discussions/323)
* PINV_a047_BusCatcherActivated
* PINV_a067_overvoltageNeutralChassis - Unknown (nominal)
* PINV_a086_motorStarting

---

## TESYNC - Tesla Energy Synchronizer

**Details:**
* Tesla Backup Gateway includes a synchronizer constantly monitoring grid voltage and frequency to relay grid parameters to Tesla Powerwall during Backup to Grid-tied transition.
* ECU Type is 259
* Part 1493315-XX-Y
* Component of TETHC

**Alerts:**
* SYNC_a001_SW_App_Boot - Unknown
* SYNC_a005_vfCheckUnderVoltage
* SYNC_a020_LoadsDropped
* SYNC_a030_Sitemaster_MIA
* SYNC_a036_LoadsDroppedLong
* SYNC_a038_DoOpenArguments - Request to disconnect from grid (nominal)
* SYNC_a044_IslanderDisconnectWithin2s
* SYNC_a046_DoCloseArguments - Request to join the grid (nominal)

---

## TEMSA - Tesla Backup Switch

**Details:**
* Tesla Backup Switch is designed to simplify installation of your Powerwall system. It plugs into your meter socket panel, with the meter plugging directly into the Backup Switch. Within the Backup Switch housing, the contactor controls your system's connection to the grid. The controller provides energy usage monitoring, providing you with precise, real-time data of your home's energy consumption.
* ECU Type is 300
* Part 1624171-XX-E - Tesla Backup Switch (1624171-xx-y)

---

## PVAC - Photovoltaic AC - Solar Inverter

**Details:**
* ECU Type is 296
* Part 1534000-xx-y - 3.8kW
* Part 1538000-xx-y - 7.6kW
* Component of TETHC

**Alerts:**
* PVAC_a014_PVS_disabled_relay - Happens during solar startup where PVS shows PVS_SelfTesting, PVS_SelfTestMci (nominal)
* PVAC_a019_ambient_overtemperature - Temp warning (abnormal)
* PVAC_a024_PVACrx_Command_mia - Unknown (abnormal)
* PVAC_a025_PVS_Status_mia - Unknown (abnormal)
* PVAC_a028_inv_K2_relay_welded
* PVAC_a030_fan_faulted - Inverter fan failure (abnormal)
* PVAC_a035_VFCheck_RoCoF - Unknown
* PVAC_a041_excess_PV_clamp_triggered
* PVAC_a041_virtual_clamper_triggered
* PVAC_a043_fan_speed_mismatch_detected

---

## PVS - Photovoltaic Strings

**Details:**
* ECU Type is 297
* This terminates the Photovoltaic DC power strings
* Component of PVAC
* This includes the Tesla PV Rapid Shutdown MCI ("mid-circuit interrupter") devices which ensure that if one photovoltaic cell stops working, the others continue working.

**Alerts:**
* PVS_a010_PvIsolationTotal
* PVS_a0[17-20]_MciString[A-D] - This indicates a solar string (A, B, C or D) that is not connected.
* PVS_a021_RapidShutdown
* PVS_a026_Mci1PvVoltage
* PVS_a027_Mci2PvVoltage
* PVS_a031_Mci3PvVoltage
* PVS_a032_Mci4PvVoltage
* PVS_a036_PvArcLockout
* PVS_a039_SelfTestRelayFault
* PVS_a044_FaultStatePvStringSafety
* PVS_a048_DcSensorIrrationalFault
* PVS_a050_RelayCoilIrrationalWarning
* PVS_a058_MciOpenOnFault
* PVS_a059_MciOpen - "Mid-Circuit Interrupter" is open, this happens when there is not enough solar power to turn on the string, or the emergency shut down button is pressed.  These are safety devices on the strings to turn them on and off.
* PVS_a060_MciClose - "Mid-Circuit Interrupter" is closed, this is normal operation. An AC signal is sent from the inverter up the DC string triggering the MCI relay to close, allowing for DC solar production to start.

---

## NEURIO - Wireless Revenue Grade Solar Meter

**Details:**
* This is a third‑party (Generac) meter with Tesla proprietary firmware. It is generally installed as a wireless meter to report on solar production. [Link](https://neur.io/)
* Component of STSTSM

---

## TESLA - Internal Device Attributes

**Details:**
* This is used to describe attributes of the inverter, meters and others
* Component of STSTSM

---

## See Also

* [Alert Codes](Alerts.md) - Comprehensive list of alert codes with descriptions
* [Firmware History](firmware-history.md) - Historical firmware versions and changes
