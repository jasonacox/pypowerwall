# PyPowerwall Proxy Server API

This document describes the HTTP API endpoints provided by the PyPowerwall Proxy Server. These endpoints allow users and applications to access Tesla Powerwall metrics and control features via web or API calls.

---

Jump To: [Quick Examples](#quick-examples) | [Control](#control-endpoints) | [Convenience /pw](#convenience-pw-endpoints) | [Fans](#fans-endpoints) | [Raw API](#powerwall-api-endpoints) | [Optional APIs](#optional-api-endpoints-tedapi-cloud-fleetapi) | [Cache](#cache-and-error-handling) | [Notes](#notes)

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
| `/health`                       | Connection health status and cache info (JSON)   |
| `/health/reset`                 | Reset health counters and clear cache (JSON)     |
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

**Aggregates Variants**
- `/aggregates` Processed & cached combined metrics.
- `/pw/aggregates` Same as above via convenience namespace.
- `/api/meters/aggregates` Raw gateway API payload (unprocessed fields).

### Quick Examples

```bash
# Get site aggregates
curl http://localhost:8675/aggregates

# Get battery state of energy
curl http://localhost:8675/soe

# Get device vitals
curl http://localhost:8675/vitals

# Check connection health and cache status
curl http://localhost:8675/health

# Get alerts
curl http://localhost:8675/alerts

# Get power summary (shortcut)
curl http://localhost:8675/pw/power

# CSV Examples
curl "http://localhost:8675/csv/v2?headers"
```

## Control Endpoints

| Endpoint                | Description                                      |
|-------------------------|--------------------------------------------------|
| `/control/reserve`      | Get/set battery reserve (POST/GET)               |
| `/control/mode`         | Get/set battery mode (POST/GET)                  |
| `/control/grid_charging`| Get/set grid charging enable (POST/GET)          |
| `/control/grid_export`  | Get/set grid export policy (POST/GET)            |

> **Note:** Control endpoints require `PW_CONTROL_SECRET` to be set. See [Control Examples](#control-examples) below.

### Control API Usage & Security

Control operations are DISABLED by default. To enable, set the environment variable `PW_CONTROL_SECRET` (any non-empty value). All control POST requests must include a `token` parameter matching this secret.

Security guidelines:
1. Use HTTPS (terminate TLS at a reverse proxy like nginx, Caddy, Traefik) if exposing beyond localhost.
2. Do not expose the control endpoints publicly unless necessary. Prefer firewall / VPN restrictions.
3. Rotate the secret periodically; treat it like a password. A restart is required after changing it.
4. Limit clients allowed to call these endpoints (IP allowlists, auth gateway, etc.).
5. Log monitoring: watch for unusual spikes in control POST requests.

Supported control values:
- Reserve: integer 0–100 (% of battery to reserve)
- Mode: `self_consumption`, `backup`, `autonomous`, `time_of_use`
- Grid Charging: `true` or `false`
- Grid Export: `battery_ok`, `pv_only`, `never`

### Control Examples

```bash
# Get current reserve
curl 'http://localhost:8675/control/reserve?token=<secret>'

# Set reserve to 20%
curl -X POST -d 'value=20&token=<secret>' http://localhost:8675/control/reserve

# Get current operating mode
curl 'http://localhost:8675/control/mode?token=<secret>'

# Set operating mode
curl -X POST -d 'value=backup&token=<secret>' http://localhost:8675/control/mode

# Get grid charging state
curl 'http://localhost:8675/control/grid_charging?token=<secret>'

# Enable grid charging
curl -X POST -d 'value=true&token=<secret>' http://localhost:8675/control/grid_charging

# Get grid export policy
curl 'http://localhost:8675/control/grid_export?token=<secret>'

# Set grid export policy (options: battery_ok, pv_only, never)
curl -X POST -d 'value=pv_only&token=<secret>' http://localhost:8675/control/grid_export
```

POST success responses return a JSON object with the updated field, or an error object on failure. GET requests return the current setting. Missing or invalid `token` returns an authorization error.

Mode clarification:
- `self_consumption` / `autonomous`: Maximize local solar usage (firmware may use either term; treat as equivalent).
- `backup`: Preserve charge for outage protection.
- `time_of_use`: Optimize around configured TOU rates.

---

## Convenience /pw Endpoints

The proxy provides shorthand endpoints under `/pw/` that map to common library calls. All return JSON.

| Endpoint                  | Description                             |
|---------------------------|-----------------------------------------|
| `/pw/level`               | Battery state of energy (%)             |
| `/pw/power`               | Site, solar, battery, load power (W)    |
| `/pw/site`                | Site power data                         |
| `/pw/solar`               | Solar power data                        |
| `/pw/battery`             | Battery power data                      |
| `/pw/battery_blocks`      | Battery block details                   |
| `/pw/load`                | Load power data                         |
| `/pw/grid`                | Grid power data                         |
| `/pw/home`                | Home consumption data                   |
| `/pw/vitals`              | Device vitals                           |
| `/pw/temps`               | Temperature metrics                     |
| `/pw/strings`             | Solar string data                       |
| `/pw/din`                 | Device identifier                       |
| `/pw/uptime`              | Uptime (seconds)                        |
| `/pw/version`             | Firmware version                        |
| `/pw/status`              | Status summary                          |
| `/pw/system_status`       | System status                           |
| `/pw/grid_status`         | Grid status                             |
| `/pw/aggregates`          | Aggregated meter data                   |
| `/pw/site_name`           | Site name                               |
| `/pw/alerts`              | Alerts array/object                     |
| `/pw/is_connected`        | Connection boolean                      |
| `/pw/get_reserve`         | Current reserve setting (%)             |
| `/pw/get_mode`            | Current operating mode                  |
| `/pw/get_time_remaining`  | Estimated backup time remaining         |

---

## Fans Endpoints

Available when TEDAPI provides fan telemetry (e.g., Powerwall 3 systems):

| Endpoint     | Description                                         |
|--------------|-----------------------------------------------------|
| `/fans`      | Raw fan speed objects keyed by internal component   |
| `/fans/pw`   | Simplified fan RPM (FANn_actual / FANn_target)      |

If fan data is unavailable, these return an empty JSON object `{}`.

Update interval: Fan metrics refresh with standard polling (same cadence as vitals/strings) and appear only when TEDAPI + compatible hardware (e.g., PW3) are present.

## Powerwall API Endpoints

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

## Optional API Endpoints (TEDAPI, Cloud, FleetAPI)

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

## Cache and Error Handling

The proxy server implements robust error handling and caching:

- **Cached Responses**: Key endpoints (`/aggregates`, `/soe`, `/vitals`, `/strings`) cache responses for improved reliability
- **TTL Behavior**: After cache TTL expires (default 30 seconds), endpoints return `null` instead of stale data
- **Network Resilience**: Graceful handling of network errors with configurable retry and fallback behavior
- **Health Monitoring**: Track connection health and cache status via `/health` endpoint
- **SOE Scaling Note**: `/soe` reports true 0–100% whereas `/api/system_status/soe` reports a 0–95% firmware-limited scale.

Environment Variables Influencing Behavior:
- `PW_CACHE_TTL` Cache duration (seconds) for key endpoints (default 30).
- `PW_GRACEFUL_DEGRADATION` If enabled, reduces hard failures under transient errors.
- `PW_FAIL_FAST` Return quickly on errors instead of longer retries.
- `PW_SUPPRESS_NETWORK_ERRORS` Suppress repetitive network error logs.
- `PW_NETWORK_ERROR_RATE_LIMIT` Rate limit interval (seconds) for repeated network error messages.
- `PW_CONTROL_SECRET` Enables control endpoints & required `token` value.

Authentication Overview:
- Read-only endpoints generally need no client token; underlying gateway/cloud auth is handled internally.
- Control endpoints always require `token=<PW_CONTROL_SECRET>`.

Error Responses (examples):
| Scenario | HTTP | JSON |
|----------|------|------|
| Control disabled | 200 | `{ "error": "Control Commands Disabled - Set PW_CONTROL_SECRET to enable" }` |
| Missing/invalid token | 403 | `{ "error": "Unauthorized" }` |
| Invalid value | 400 | `{ "error": "Invalid Value" }` |
| Upstream failure | 500 | `{ "error": "Request Failed" }` |

Sample JSON Snippets:
```json
// /aggregates - abbreviated
{
    "site": {
        "instant_power": -2626,
    },
    "battery": {
        "instant_power": -2280.0000000000005,
    },
    "load": {
        "instant_power": 946.25,
    },
    "solar": {
        "instant_power": 5860,
    }
}

// /health - abbreviated
{
    "pypowerwall": "0.14.1 Proxy t81",
    "cache_ttl_seconds": 30,
    "graceful_degradation": true,
    "fail_fast_mode": false,
    "health_check_enabled": true,
    "startup_time": "2025-09-05T23:21:42",
    "current_time": "2025-09-14T11:58:57.239988",
    "proxy_stats": {},
    "connection_health": {},
    "cached_data": {},
    "endpoint_statistics": {}
}

// POST /control/reserve success
{"reserve": "Set Successfully"}

// POST /control/reserve invalid token
{"error": "Unauthorized"}

// /fans/pw
{"FAN1_actual": 1180, "FAN1_target": 1200, "FAN2_actual": 1175, "FAN2_target": 1200}
```

For configuration options, see [proxy/README.md](https://github.com/jasonacox/pypowerwall/blob/main/proxy/README.md).

---

## Notes
- All endpoints return JSON unless otherwise noted.
- Key metric endpoints (`/aggregates`, `/soe`, `/vitals`, `/strings`) return `null` when no fresh or valid cached data is available (after TTL expiry).
- Some endpoints require local mode or specific configuration (see server documentation).
- For more details, see the main project [README.md](https://github.com/jasonacox/pypowerwall/blob/main/README.md).

### API Changes
Refer to `proxy/RELEASE.md` for history (e.g., t82 added `/control/grid_charging` & `/control/grid_export`).
