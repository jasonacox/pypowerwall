# PyPowerwall Proxy Server API

This document describes the HTTP API endpoints provided by the PyPowerwall Proxy Server (`server.py`). These endpoints allow users and applications to access Tesla Powerwall metrics and control features via web or API calls.

---

## Overview

The proxy server exposes a RESTful API for accessing Powerwall data, including site, battery, solar, vitals, alerts, and more. It can be run locally or in a container, and supports both local gateway and cloud modes.

**Base URL:**
- By default: `http://<host>:8675/`
- If using a reverse proxy, set the `PROXY_BASE_URL` environment variable accordingly.

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

### CSV Output

| Endpoint         | Description                                      |
|------------------|--------------------------------------------------|
| `/csv`           | Grid, Home, Solar, Battery, Level (CSV)          |
| `/csv/v2`        | Adds GridStatus and Reserve (CSV)                |

Add `?headers` to include CSV headers.

### Control Endpoints

| Endpoint                | Description                                      |
|-------------------------|--------------------------------------------------|
| `/control/reserve`      | Get/set battery reserve (POST/GET)               |
| `/control/mode`         | Get/set battery mode (POST/GET)                  |

> **Note:** Control endpoints require `PW_CONTROL_SECRET` to be set.

### Advanced/Raw Endpoints

| Endpoint                | Description                                      |
|-------------------------|--------------------------------------------------|
| `/api/meters/aggregates`| Raw aggregates from Powerwall API                |
| `/api/system_status/...`| Other raw Powerwall API endpoints                |

### TEDAPI, Cloud, and FleetAPI

If enabled, the following endpoints are available:
- `/tedapi/config`, `/tedapi/status`, `/tedapi/components`, `/tedapi/battery`, `/tedapi/controller`
- `/cloud/battery`, `/cloud/power`, `/cloud/config`
- `/fleetapi/info`, `/fleetapi/status`

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
- For more details, see the [proxy/HELP.md](HELP.md) file or the main project [README.md](../README.md).
