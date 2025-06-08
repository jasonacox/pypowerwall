# PyPowerwall Proxy Server API

This document describes the HTTP API endpoints provided by the PyPowerwall Proxy Server. These endpoints allow users and applications to access Tesla Powerwall metrics and control features via web or API calls.

---

## Overview

The proxy server exposes a RESTful API for accessing Powerwall data, including site, battery, solar, vitals, alerts, and more. It can be run locally or in a container, and supports both local gateway and cloud modes.

**Base URL:**
- By default: `http://<host>:8675/`
- If using a reverse proxy, set the `PROXY_BASE_URL` environment variable accordingly.

**Setup:**
- See [proxy/README.md](https://github.com/jasonacox/pypowerwall/blob/main/proxy/README.md) for setup instructions.
- See the main project [README.md](https://github.com/jasonacox/pypowerwall/blob/main/README.md) for general usage.

---

## Common Endpoints

### Metrics and Status

| Endpoint                        | Description                                      |
|---------------------------------|--------------------------------------------------|
| `/aggregates`                   | Site, solar, battery, and load metrics (JSON)    |
| `/soe`                          | Battery state of energy (JSON)                   |
| `/api/system_status/soe`        | Battery state of energy (95% scale, JSON)        |
| `/api/system_status/grid_status`| Grid status (JSON)                               |
| `/vitals`                       | Device vitals (JSON)                             |
| `/strings`                      | Solar string data (JSON)                         |
| `/temps`                        | Powerwall temperatures (JSON)                    |
| `/alerts`                       | Alerts (JSON array)                              |
| `/alerts/pw`                    | Alerts (JSON object)                             |
| `/stats`                        | Internal proxy stats (JSON)                      |
| `/stats/clear`                  | Clear internal stats (JSON)                      |
| `/freq`                         | Frequency, current, voltage, grid status (JSON)  |
| `/pod`                          | Powerwall battery data (JSON)                    |
| `/json`                         | Combined metrics and status (JSON)               |
| `/version`                      | Firmware version info (JSON)                     |
| `/help`                         | HTML help and stats page                         |
| `/example.html` or `/`          | HTML page showing power flow animation           |

### CSV Output

| Endpoint         | Description                                      |
|------------------|--------------------------------------------------|
| `/csv`           | Grid, Home, Solar, Battery, Level (CSV)          |
| `/csv/v2`        | Adds GridStatus and Reserve (CSV)                |

_Add `?headers` to include CSV headers._

### Control Endpoints

| Endpoint                | Description                                      |
|-------------------------|--------------------------------------------------|
| `/control/reserve`      | Get/set battery reserve (POST/GET)               |
| `/control/mode`         | Get/set battery mode (POST/GET)                  |

> **Note:** Control endpoints require `PW_CONTROL_SECRET` to be set.

### Powerwall API Endpoints

| Endpoint                         | Description                                      |
|-----------------------------------|--------------------------------------------------|
| `/api/meters/aggregates`          | Raw aggregates from Powerwall API                |
| `/api/status`                     | Powerwall Firmware and Uptime Status             |
| `/api/site_info/site_name`        | Site name information                            |
| `/api/meters/site`                | Site meter data                                  |
| `/api/meters/solar`               | Solar meter data                                 |
| `/api/sitemaster`                 | Sitemaster status                                |
| `/api/powerwalls`                 | Powerwall details                                |
| `/api/customer/registration`      | Customer registration info                       |
| `/api/system_status`              | System status information                        |
| `/api/system_status/grid_status`  | Grid status details                              |
| `/api/system/update/status`       | System update status                             |
| `/api/site_info`                  | Site information                                 |
| `/api/system_status/grid_faults`  | Grid fault information                           |
| `/api/operation`                  | Operation status                                 |
| `/api/site_info/grid_codes`       | Grid codes information                           |
| `/api/solars`                     | Solar system information                         |
| `/api/solars/brands`              | Solar system brands                              |
| `/api/customer`                   | Customer information                             |
| `/api/meters`                     | Meter information                                |
| `/api/installer`                  | Installer information                            |
| `/api/networks`                   | Network configuration                            |
| `/api/system/networks`            | System network status                            |
| `/api/meters/readings`            | Meter readings data                              |

### Optional API Endpoints (TEDAPI, Cloud, FleetAPI)

_These endpoints require specific configuration to be enabled._

| Endpoint                | Description                                      |
|-------------------------|--------------------------------------------------|
| `/tedapi/config`        | TEDAPI configuration                             |
| `/tedapi/status`        | TEDAPI status information                        |
| `/tedapi/components`    | TEDAPI component data                            |
| `/tedapi/battery`       | TEDAPI battery metrics                           |
| `/tedapi/controller`    | TEDAPI controller data                           |
| `/cloud/battery`        | Cloud API battery information                    |
| `/cloud/power`          | Cloud API power metrics                          |
| `/cloud/config`         | Cloud API configuration                          |
| `/fleetapi/info`        | Tesla Fleet API system information               |
| `/fleetapi/status`      | Tesla Fleet API status data                      |

---

## Example Usage

**Get site aggregates:**
```sh
curl http://localhost:8675/aggregates
```

**Get battery state of energy:**
```sh
curl http://localhost:8675/soe
```

**Get device vitals:**
```sh
curl http://localhost:8675/vitals
```

**Get alerts:**
```sh
curl http://localhost:8675/alerts
```

**Set battery reserve (requires control secret):**
```sh
curl -X POST -d "value=20&token=<secret>" http://localhost:8675/control/reserve
```

---

## Notes
- All endpoints return JSON unless otherwise noted.
- Some endpoints require local mode or specific configuration (see server documentation).
- For more details, see the main project [README.md](https://github.com/jasonacox/pypowerwall/blob/main/README.md).
