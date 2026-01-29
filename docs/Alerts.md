# Alerts

The following list details alerts potentially returned by the device vitals API (e.g., /api/device/vitals). This data is aggregated from two primary sources:

- [Tesla Residential Powerhub User Manual](https://energylibrary.tesla.com/docs/Public/More/Powerhub/Residential/UserManual/en-us/GUID-C91CB9E0-8909-4440-8796-551470CE9539.html) (Official)
- Community Contributions (Unofficial)

This list is non-exhaustive and may not cover every possible alert code.

> [!WARNING]
> Alert descriptions labeled as `Community Contributed` are generated through user observation and best-effort reverse engineering. These descriptions are not official Tesla documentation. They may contain inaccuracies or incomplete information.

## Alert List

 - [AC Blade Connector Damaged](#ac-blade-connector-damaged)
 - [Backfeed Limited (BackfeedLimited)](#backfeed-limited-(backfeedlimited))
 - [Battery Breaker Open](#battery-breaker-open)
 - [Battery Comms](#battery-comms)
 - [Battery Fault (BatteryFault)](#battery-fault-(batteryfault))
 - [Battery Meter Comms](#battery-meter-comms)
 - [Battery Unexpected Power](#battery-unexpected-power)
 - [Battery Unexpected Reactive Power](#battery-unexpected-reactive-power)
 - [Black Start Failure](#black-start-failure)
 - [Busway Meter Comms](#busway-meter-comms)
 - [Contactor Unresponsive Close](#contactor-unresponsive-close)
 - [DC Bus Bar Shorted](#dc-bus-bar-shorted)
 - [External IO Comms](#external-io-comms)
 - [Frequency Meter Comms](#frequency-meter-comms)
 - [FWUpdateSucceeded](#fwupdatesucceeded)
 - [Generator Breaker Timeout](#generator-breaker-timeout)
 - [Generator Faulted](#generator-faulted)
 - [Generator Meter Comms](#generator-meter-comms)
 - [GridCodesWrite](#gridcodeswrite)
 - [Grid Resynchronization Failed](#grid-resynchronization-failed)
 - [Inverter Not Going To Vf](#inverter-not-going-to-vf)
 - [Islanding Controller MIA](#islanding-controller-mia)
 - [Load Meter Comms](#load-meter-comms)
 - [Lost Connectivity to Tesla Site Controller](#lost-connectivity-to-tesla-site-controller)
 - [No Solar Production](#no-solar-production)
 - [Opticaster Exe](#opticaster-exe)
 - [Permanent Battery Module Fault](#permanent-battery-module-fault)
 - [PINV_a010_can_gtwMIA](#pinv_a010_can_gtwmia)
 - [PINV_a039_can_thcMIA](#pinv_a039_can_thcmia)
 - [PINV_a067_overvoltageNeutralChassis](#pinv_a067_overvoltageneutralchassis)
 - [POD_f029_HW_CMA_OV](#pod_f029_hw_cma_ov)
 - [POD_w024_HW_Fault_Asserted](#pod_w024_hw_fault_asserted)
 - [POD_w029_HW_CMA_OV](#pod_w029_hw_cma_ov)
 - [POD_w031_SW_Brick_OV](#pod_w031_sw_brick_ov)
 - [POD_w044_SW_Brick_UV_Warning](#pod_w044_sw_brick_uv_warning)
 - [POD_w045_SW_Brick_OV_Warning](#pod_w045_sw_brick_ov_warning)
 - [POD_w048_SW_Cell_Voltage_Sens](#pod_w048_sw_cell_voltage_sens)
 - [POD_w058_SW_App_Boot](#pod_w058_sw_app_boot)
 - [POD_w063_SW_SOC_Imbalance](#pod_w063_sw_soc_imbalance)
 - [POD_w067_SW_Not_Enough_Energy_Precharge](#pod_w067_sw_not_enough_energy_precharge)
 - [POD_w090_SW_SOC_Imbalance_Limit_Charge](#pod_w090_sw_soc_imbalance_limit_charge)
 - [POD_w093_SW_Charge_Request](#pod_w093_sw_charge_request)
 - [POD_w105_SW_EOD](#pod_w105_sw_eod)
 - [POD_w109_SW_Self_Test_Request_Not_Serviced](#pod_w109_sw_self_test_request_not_serviced)
 - [POD_w110_SW_EOC](#pod_w110_sw_eoc)
 - [PodCommissionTime](#podcommissiontime)
 - [Powerwall Inverter Failure](#powerwall-inverter-failure)
 - [Powerwall Performance Limited](#powerwall-performance-limited)
 - [PV Inverter Comms](#pv-inverter-comms)
 - [PVS_a018_MciString[A-D]](#pvs_a018_mcistring[a-d])
 - [PVS_a026_Mci1PvVoltage](#pvs_a026_mci1pvvoltage)
 - [PVS_a027_Mci2PvVoltage](#pvs_a027_mci2pvvoltage)
 - [PVS_a031_Mci3PvVoltage](#pvs_a031_mci3pvvoltage)
 - [PVS_a032_Mci4PvVoltage](#pvs_a032_mci4pvvoltage)
 - [PV String Out](#pv-string-out)
 - [Pyranometer Comms](#pyranometer-comms)
 - [Ramp Rate Limited](#ramp-rate-limited)
 - [Reactive Power Limited](#reactive-power-limited)
 - [Real Power Available Limited (RealPowerAvailableLimited)](#real-power-available-limited-(realpoweravailablelimited))
 - [Real Power Config Limited](#real-power-config-limited)
 - [ScheduledIslandContactorOpen](#scheduledislandcontactoropen)
 - [SelfConsumptionReservedLimit](#selfconsumptionreservedlimit)
 - [Site Max Power Limited](#site-max-power-limited)
 - [Site Meter Comms](#site-meter-comms)
 - [Site Min Power Limited (SiteMinPowerLimited)](#site-min-power-limited-(siteminpowerlimited))
 - [Smart Inverter Active](#smart-inverter-active)
 - [Solar Charge Only Limited (SolarChargeOnlyLimited)](#solar-charge-only-limited-(solarchargeonlylimited))
 - [Solar Meter Comms](#solar-meter-comms)
 - [SYNC_a001_SW_App_Boot](#sync_a001_sw_app_boot)
 - [SYNC_a038_DoOpenArguments](#sync_a038_doopenarguments)
 - [System shutdown](#system-shutdown)
 - [THC_w061_CAN_TX_FIFO_Overflow](#thc_w061_can_tx_fifo_overflow)
 - [THC_w155_Backup_Genealogy_Updated](#thc_w155_backup_genealogy_updated)
 - [Wait for Solar](#wait-for-solar)
 - [Waiting for Jumpstart - Low SOE](#waiting-for-jumpstart---low-soe)

---

### AC Blade Connector Damaged

- **UI Name**: `AC Blade Connector Damaged`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `RMA`
- **Device**: 

Detected AC blade connector damage. Solar Inverter/assembly damaged, impacting solar production.

---

### Backfeed Limited (BackfeedLimited)

- **UI Name**: `Backfeed Limited`
- **API Name**: `BackfeedLimited`
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: `STSTSM`

The system is configured for inadvertent export and therefore will not further discharge to respect this limit

---

### Battery Breaker Open

- **UI Name**: `Battery Breaker Open`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

There is an open breaker between the site meter and the powerwall itself. The meter will automatically detect when the breaker is closed again.

---

### Battery Comms

- **UI Name**: `Battery Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Critical`
- **Device**: 

Loss of communication to one or more inverter blocks.

---

### Battery Fault (BatteryFault)

- **UI Name**: `Battery Fault`
- **API Name**: `BatteryFault`
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Critical`
- **Device**: `STSTSM`

One or more inverter blocks is in a faulted state.

---

### Battery Meter Comms

- **UI Name**: `Battery Meter Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with Battery Meter.

---

### Battery Unexpected Power

- **UI Name**: `Battery Unexpected Power`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: 

Commanded real power does not match measured power from battery meter

---

### Battery Unexpected Reactive Power

- **UI Name**: `Battery Unexpected Reactive Power`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: 

Commanded reactive power does not match measured power from battery meter

---

### Black Start Failure

- **UI Name**: `Black Start Failure`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Critical`
- **Device**: 

The battery system was unable to black start.

---

### Busway Meter Comms

- **UI Name**: `Busway Meter Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with Busway Meter.

---

### Contactor Unresponsive Close

- **UI Name**: `Contactor Unresponsive Close`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Critical`
- **Device**: 

The islanding controller was unable to open the islanding contactor/circuit breaker.

---

### DC Bus Bar Shorted

- **UI Name**: `DC Bus Bar Shorted`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `RMA`
- **Device**: 

Detected DC bus bar short. Solar Inverter/assembly is damaged, impacting solar production.

---

### External IO Comms

- **UI Name**: `External IO Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with External IO device.

---

### Frequency Meter Comms

- **UI Name**: `Frequency Meter Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with Frequency Meter.

---

### FWUpdateSucceeded

- **UI Name**: 
- **API Name**: `FWUpdateSucceeded`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `STSTSM`

Firmware Upgrade Succeeded

---

### Generator Breaker Timeout

- **UI Name**: `Generator Breaker Timeout`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

The generator was unable to close its breaker within the timeout window.

---

### Generator Faulted

- **UI Name**: `Generator Faulted`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Critical`
- **Device**: 

The generator is in a faulted state.

---

### Generator Meter Comms

- **UI Name**: `Generator Meter Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with Generator Meter.

---

### GridCodesWrite

- **UI Name**: 
- **API Name**: `GridCodesWrite`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `STSTSM`



---

### Grid Resynchronization Failed

- **UI Name**: `Grid Resynchronization Failed`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

The islanding controller was unable to synchronize and close the islanding contactor/circuit breaker within 5 minutes.

---

### Inverter Not Going To Vf

- **UI Name**: `Inverter Not Going To Vf`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Critical`
- **Device**: 

The battery system is not transitioning to grid-forming mode.

---

### Islanding Controller MIA

- **UI Name**: `Islanding Controller MIA`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Critical`
- **Device**: 

Loss of communications with the islanding controller.

---

### Load Meter Comms

- **UI Name**: `Load Meter Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with Load Meter.

---

### Lost Connectivity to Tesla Site Controller

- **UI Name**: `Lost Connectivity to Tesla Site Controller`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

The Tesla Site Controller (or Gateway) has lost connectivity to Tesla Servers. Monitoring and management capabilities are currently limited.

---

### No Solar Production

- **UI Name**: `No Solar Production`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

One or more of the solar inverters have not produced any energy in the past 24 hours. There might be an issue impacting solar production.

---

### Opticaster Exe

- **UI Name**: `Opticaster Exe`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Critical`
- **Device**: 

Opticaster failed to run on the Tesla Site Controller and the battery system is not being dispatched.

---

### Permanent Battery Module Fault

- **UI Name**: `Permanent Battery Module Fault`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `RMA`
- **Device**: 

The Powerwall battery mode has permanently faulted and product needs replacement.

---

### PINV_a010_can_gtwMIA

- **UI Name**: 
- **API Name**: `PINV_a010_can_gtwMIA`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPINV`

Indicate that gateway/sync is MIA (seen during firmware upgrade reboot)

---

### PINV_a039_can_thcMIA

- **UI Name**: 
- **API Name**: `PINV_a039_can_thcMIA`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPINV`

Seems to indicate that Home Controller is MIA (seen during firmware upgrade reboot)

---

### PINV_a067_overvoltageNeutralChassis

- **UI Name**: 
- **API Name**: `PINV_a067_overvoltageNeutralChassis`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPINV`



---

### POD_f029_HW_CMA_OV

- **UI Name**: 
- **API Name**: `POD_f029_HW_CMA_OV`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w024_HW_Fault_Asserted

- **UI Name**: 
- **API Name**: `POD_w024_HW_Fault_Asserted`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w029_HW_CMA_OV

- **UI Name**: 
- **API Name**: `POD_w029_HW_CMA_OV`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w031_SW_Brick_OV

- **UI Name**: 
- **API Name**: `POD_w031_SW_Brick_OV`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w044_SW_Brick_UV_Warning

- **UI Name**: 
- **API Name**: `POD_w044_SW_Brick_UV_Warning`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w045_SW_Brick_OV_Warning

- **UI Name**: 
- **API Name**: `POD_w045_SW_Brick_OV_Warning`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w048_SW_Cell_Voltage_Sens

- **UI Name**: 
- **API Name**: `POD_w048_SW_Cell_Voltage_Sens`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w058_SW_App_Boot

- **UI Name**: 
- **API Name**: `POD_w058_SW_App_Boot`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w063_SW_SOC_Imbalance

- **UI Name**: 
- **API Name**: `POD_w063_SW_SOC_Imbalance`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w067_SW_Not_Enough_Energy_Precharge

- **UI Name**: 
- **API Name**: `POD_w067_SW_Not_Enough_Energy_Precharge`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w090_SW_SOC_Imbalance_Limit_Charge

- **UI Name**: 
- **API Name**: `POD_w090_SW_SOC_Imbalance_Limit_Charge`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w093_SW_Charge_Request

- **UI Name**: 
- **API Name**: `POD_w093_SW_Charge_Request`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w105_SW_EOD

- **UI Name**: 
- **API Name**: `POD_w105_SW_EOD`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w109_SW_Self_Test_Request_Not_Serviced

- **UI Name**: 
- **API Name**: `POD_w109_SW_Self_Test_Request_Not_Serviced`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### POD_w110_SW_EOC

- **UI Name**: 
- **API Name**: `POD_w110_SW_EOC`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TEPOD`



---

### PodCommissionTime

- **UI Name**: 
- **API Name**: `PodCommissionTime`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `STSTSM`



---

### Powerwall Inverter Failure

- **UI Name**: `Powerwall Inverter Failure`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `RMA`
- **Device**: 

Powerwall inverter has failed permanently. Unit needs replacement.

---

### Powerwall Performance Limited

- **UI Name**: `Powerwall Performance Limited`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `RMA`
- **Device**: 

Powerwall has been locked out due to low energy. Unit needs replacement.

---

### PV Inverter Comms

- **UI Name**: `PV Inverter Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with PV Inverter.

---

### PVS_a018_MciString[A-D]

- **UI Name**: 
- **API Name**: `PVS_a018_MciString[A-D]`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `PVS`

This indicates a solar string (A, B, C or D) that is not connected.

---

### PVS_a026_Mci1PvVoltage

- **UI Name**: 
- **API Name**: `PVS_a026_Mci1PvVoltage`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `PVS`



---

### PVS_a027_Mci2PvVoltage

- **UI Name**: 
- **API Name**: `PVS_a027_Mci2PvVoltage`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `PVS`



---

### PVS_a031_Mci3PvVoltage

- **UI Name**: 
- **API Name**: `PVS_a031_Mci3PvVoltage`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `PVS`



---

### PVS_a032_Mci4PvVoltage

- **UI Name**: 
- **API Name**: `PVS_a032_Mci4PvVoltage`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `PVS`



---

### PV String Out

- **UI Name**: `PV String Out`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

One or more solar inverter strings are not producing power, expect lower than usual solar performance.

---

### Pyranometer Comms

- **UI Name**: `Pyranometer Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with Pyranometer.

---

### Ramp Rate Limited

- **UI Name**: `Ramp Rate Limited`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: 

The output does not currently match the commanded power because the system is ramping to its setpoint

---

### Reactive Power Limited

- **UI Name**: `Reactive Power Limited`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: 

The command is greater than the Available Reactive Power

---

### Real Power Available Limited (RealPowerAvailableLimited)

- **UI Name**: `Real Power Available Limited`
- **API Name**: `RealPowerAvailableLimited`
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: `STSTSM`

The command is greater than the Available Battery Real Charge or Discharge Power

---

### Real Power Config Limited

- **UI Name**: `Real Power Config Limited`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: 

The system is unable to meet the commanded power because of a limit that was configured during commissioning

---

### ScheduledIslandContactorOpen

- **UI Name**: 
- **API Name**: `ScheduledIslandContactorOpen`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `STSTSM`

Manually Disconnected from Grid

---

### SelfConsumptionReservedLimit

- **UI Name**: 
- **API Name**: `SelfConsumptionReservedLimit`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `STSTSM`

Battery reached reserve limit during self-consumption mode and switches to grid

---

### Site Max Power Limited

- **UI Name**: `Site Max Power Limited`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: 

Cannot meet command because the Site Maximum Power Limit has been set

---

### Site Meter Comms

- **UI Name**: `Site Meter Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with Site Meter.

---

### Site Min Power Limited (SiteMinPowerLimited)

- **UI Name**: `Site Min Power Limited`
- **API Name**: `SiteMinPowerLimited`
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: `STSTSM`

Cannot meet command because the Site Minimum Power Limit has been set

---

### Smart Inverter Active

- **UI Name**: `Smart Inverter Active`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: 

Due to grid conditions, a Smart Inverter Feature is now in operation on Battery Block X

---

### Solar Charge Only Limited (SolarChargeOnlyLimited)

- **UI Name**: `Solar Charge Only Limited`
- **API Name**: `SolarChargeOnlyLimited`
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.6`
- **Severity**: 
- **Device**: `STSTSM`

The system has been configured to only charge from solar. Solar is not available; the charge request cannot be met

---

### Solar Meter Comms

- **UI Name**: `Solar Meter Comms`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

Loss of communications with Solar Meter.

---

### SYNC_a001_SW_App_Boot

- **UI Name**: 
- **API Name**: `SYNC_a001_SW_App_Boot`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TESYNC`



---

### SYNC_a038_DoOpenArguments

- **UI Name**: 
- **API Name**: `SYNC_a038_DoOpenArguments`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TESYNC`



---

### System shutdown

- **UI Name**: `System shutdown`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

The system has been shutdown by an external kill switch, or a system shutdown has been triggered by a low GPIO pin.

---

### THC_w061_CAN_TX_FIFO_Overflow

- **UI Name**: 
- **API Name**: `THC_w061_CAN_TX_FIFO_Overflow`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TETHC`



---

### THC_w155_Backup_Genealogy_Updated

- **UI Name**: 
- **API Name**: `THC_w155_Backup_Genealogy_Updated`
- **Source**: `Community Contributed`
- **Severity**: 
- **Device**: `TETHC`

Unknown but seen during firmware upgrade.

---

### Wait for Solar

- **UI Name**: `Wait for Solar`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Performance`
- **Device**: 

The site currently doesn't have enough SOE to form a grid. Waiting for more solar energy. Fix: User command or wait for daytime.

---

### Waiting for Jumpstart - Low SOE

- **UI Name**: `Waiting for Jumpstart - Low SOE`
- **API Name**: 
- **Source**: `Tesla - Residential Powerhub User Manual - Rev. 1.16`
- **Severity**: `Informational`
- **Device**: 

The system has been put to sleep due to a low SOE and being off-grid.

---

