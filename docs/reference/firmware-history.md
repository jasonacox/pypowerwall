# Firmware Version History

Firmware version of the Powerwall can be seen with `pw.version()`. An estimate of Firmware versions in the wild can be seen here: https://www.netzeroapp.io/firmware_versions 

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
| [22.9](https://www.tesla.com/support/energy/powerwall/mobile-app/software-updates) | 1-Apr-2022 | * More options for 'Advanced Settings' in the Tesla app to control grid charging and export behavior * Improved Powerwall performance when charge level is below backup reserve and Powerwall is importing from the grid * Capability to configure the charge rate of Powerwall below backup reserve * Improved metering accuracy when loads are not balanced across phases | v0.4.0 | 4.8.0 |
| 22.9.1 | 12-Apr-2022 | Unknown | v0.4.0 | 4.8.0 |
| 22.9.1.1 75c90bda | 2-May-2022 | Unknown | v0.4.0 | 4.8.0-1025 |
| 22.9.2 a54352e6 | 2-May-2022 | Unknown | v0.4.0 Proxy t11 | 4.8.0-1025 |
| 22.18.3 21c0ad81 | 28-Jun-2022 | Two new alerts did show up in device vitals: HighCPU and SystemConnectedToGrid * The HighCPU was particularly interesting. If you updated your customer password on the gateway, it seems to have reverted during the firmware upgrade. Any monitoring tools using the new password were getting errors. The gateway was presenting "API rate limit" errors (even for installer mode). Reverting the password to the older one fixes the issue but revealed the HighCPU alert. | v0.4.0 Proxy t15 | 4.9.2-1087 |
| 22.18.6 7884188e | 27-Sep-2022 | STSTSM HighCPU Alert appeared after upgrade. The firmwareVersion now shows "2022-08-01-g8b6399632f". Alerts during upgrade: "PINV_a010_can_gtwMIA", "PINV_a039_can_thcMIA". | v0.4.0 Proxy t15 | 4.13.1-1312 |
| 22.26.1-foxtrot 4d562eaf | 13-Oct-2022 | This release seems to have introduced a Powerwall charging slowdown mode. After 95% full, the charging will slow dramatically with excess solar production getting pushed to the grid even if the battery is less than 100% (see [discussion](https://github.com/jasonacox/Powerwall-Dashboard/discussions/109)).  This upgrade also upgrades the Neurio Revenue Grade Meter (RGM) to 1.7.2-Tesla with STSTSM firmware showing 2022-09-28-g7cb0d69c2b.  [Tesla Release Notes](https://www.tesla.com/support/energy/powerwall/mobile-app/software-updates): Time-Based Control mode updates, Improved off-grid retry, improved commissioning, improved metering accuracy on Neurio Smart CTs | v0.6.0 Proxy t19 | 4.13.1-1334 |
| 22.26.2 8cd8cac4 | 26-Oct-2022 | STSTSM firmware showing 2022-10-24-g64e8c689f9 - This version seems to have fixed a slow charging issue with the Powerwall. With version 22.26.1, it started trickle charging at around 85-90% and would never get above 95%. With this new version it charges up to 98% and then starts trickle charging to the final 100%.| v0.6.0 Proxy t19 | 4.14.1-1395 |
| 22.26.4 fc00d5dd | 22-Nov-2022 | STSTSM firmware showing 2022-10-26-g9b8e445626 - No noticeable changes so far. | v0.6.0 Proxy t22 | 4.14.4-1455 |
| 22.36.4 71cc31f1 | 23-Feb-2023 | Added Tesla Pro app graphic/link to Gateway login screen | v0.6.0 Proxy t24 | 4.18.0-1607 |
| 22.36.6 cf1839cb | 11-Mar-2023 | STSTSM firmware showing 2023-03-04-gd9f19c06f2 - Improved detection of open circuit breakers on Powerwall systems ([see Tesla release notes](https://www.tesla.com/support/energy/powerwall/mobile-app/software-updates)). Change was reverted and rolled back to 22.26.4 | v0.6.0 Proxy t24 | 4.18.0-1607 |
| 22.36.7 08d06dad | 21-Mar-2023 | STSTSM firmware showing 2023-03-04-gd9f19c06f2 - No noticeable changes so far. | v0.6.1 Proxy t24 | 4.18.0-1607 |
| 22.36.8 | 27-Mar-2023 | "Battery Unexpected Power" alert reported during firmware upgrade | v0.6.2 Proxy t25 | 4.19.5-1665|
| 22.36.9 c55384d2 | 11-Apr-2023 | STSTSM firmware showing 2023-03-29-g66549e6ca7 - Power flow animation panel had "Aw, snap!" error | v0.6.2 Proxy t25 | 4.19.5-1665|
| 23.4.2-1 fe55682a | 3-May-2023 | STSTSM firmware showing `localbuild` | v0.6.2 Proxy t25 | 4.20.69-1691|
| 23.12.10 30f95d0b | 1-Jul-2023 | STSTSM firmware showing 2023-07-11-geb56bf57ab | v0.6.2 Proxy t26 | 4.23.6-1844 |
| 23.12.11 452c76cb | 4-Aug-2023 | STSTSM firmware showing 2023-07-20-ga38210a892 | v0.6.2 Proxy t26 | 4.23.6-1844 |
| 23.28.1 fa0c1ad0 | 11-Sep-2023 | STSTSM firmware showing 2023-08-22-g807640ca4a | v0.6.2 Proxy t26 | 4.24.5-1931 |
| 23.28.2 27626f98 | 13-Oct-2023 | STSTSM firmware showing 2023-09-12-gafa2393b50 | v0.6.2 Proxy t26 | 4.25.6-1976 |
| 23.36.3 aa269d353 | 22-Dec-2023 | STSTSM firmware showing 2023-11-30-g6e07d12eea | .. | .. |
| 23.36.4 4064fc6a | 17-Jan-2024 | STSTSM firmware showing 2023-11-30-g6e07d12eea |  .. | .. |
| 24.4.0 0fe780c9 | 15-Mar-2024 | No vitals available |  .. | .. |
| 24.12.3 1feaff3a | May-2024 | No vitals available |  .. | .. |
| 23.44.0 eb113390 | 25-Jan-2024 | STSTSM firmware showing Unknown - No vitals available |  .. | .. |
| 23.44.3-msa | 7-Feb-2024 | No vitals available |  .. | .. |
| 25.2.2 | 2024 | Unknown | .. | .. |
| 25.2.6 | 2024 | Unknown | .. | .. |
| 25.2.7 bca3fdc8 | 2024 | Updated from 25.2.6, kept working | .. | .. |
| 25.10.1 | 2024 | Local (LAN) access to TEDAPI on Powerwall blocked | .. | .. |
| 25.10.2 9325e147 | 2024 | Unknown | .. | .. |
| 25.10.3 | 2024 | Updated from 25.10.1 | .. | .. |
| 25.10.4 4a4191ff | 2024 | TEDAPI via wifi still working | .. | .. |
| 25.18.1 9eca33eb | 2024 | Good with PD v4.7.1 and TEDAPI (via wi-fi) | .. | .. |
| 25.18.2 e1f565d8 | 2024 | Unknown | .. | .. |
| 25.18.4 b6b41ca8 | 2024 | "Battery Unexpected Power" alert | .. | .. |
| 25.18.5 a411ff15 | 2024 | Multiple reports of "Powerwall Disabled - Service Required - Low Energy Lockout" | .. | .. |
| 25.26.0 0d5436e | 5-Aug-2025 | Possibly bug in this version (see [issue #680](https://github.com/jasonacox/Powerwall-Dashboard/issues/680)) - WiFi stability improvements reported | .. | .. |
| 25.26.1 2c4bb00e | 18-Aug-2025 | Unknown | .. | .. |
| 25.34.1 930a7700 | 29-Sep-2025 | Updated for PW2 and PW+ units | .. | .. |
| 25.34.3 82272c3b | 21-Oct-2025 | PW3 - Grid charging rates dropped from 3.3 kW to 1.9 kW | .. | .. |
| 25.42.0 2cd3dcfd | Nov-2025 | Charging on Solar and PW2 stops/start due to high temperature - Firmware branch split: PW3 on separate line from PW2/inverters/Powerwall+ | .. | .. |
| 25.42.1 1d1ff4c6 | Dec-2025 | Unknown | .. | .. |
| 25.42.1 ab1ab81d | 3-Dec-2025 | PW3 variant - Grid charging rates continue to be lower (~1.5 kW) | .. | .. |
| 25.42.1 b5289d33 | 25-Nov-2025 | Operational variant - Resolved "fan_speed_mismatch_detected" alert | .. | .. |

**For more details on firmware versions, see [Tesla Powerwall Firmware Upgrades - Observations](https://github.com/jasonacox/Powerwall-Dashboard/discussions/109).**

## Important Notes

* Beginning with firmware version 23.44.0, Tesla has removed the `/api/devices/vitals` API endpoint. For discussion about this and future updates, see [Tesla Powerwall Firmware Upgrades - Observations](https://github.com/jasonacox/Powerwall-Dashboard/discussions/109).

* As of firmware version 25.10.0, network routing to the TEDAPI endpoint (`192.168.91.1`) is no longer supported by Tesla. You must connect directly to the Powerwall's Wi‑Fi access point to access TEDAPI data.
