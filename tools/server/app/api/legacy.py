"""
Legacy Proxy-Compatible API Endpoints

This router provides backward compatibility with the original pypowerwall proxy server.
Routes are registered WITHOUT a prefix (included directly at root level in main.py).

Key Routes (all cache-backed for graceful degradation):
    - /aggregates, /api/meters/aggregates -> Power meter data
    - /soe, /api/system_status/soe -> Battery state of energy
    - /csv, /csv/v2 -> CSV formatted data for Telegraf/InfluxDB
    - /vitals -> Detailed system vitals
    - /strings -> Solar string data
    - /temps, /temps/pw -> Temperature data
    - /alerts, /alerts/pw -> System alerts
    - /version -> Firmware version
    - /stats -> Server statistics
    - /api/networks, /api/system/networks -> Network configuration
    - /api/powerwalls -> Powerwall device list

Control Routes (require authentication):
    - POST /control/{path} -> Control operations (reserve, mode, etc.)

Design Principles:
    1. EXPLICIT ENDPOINTS ONLY - No catch-all /api/{path:path} routes
       Every endpoint is explicitly defined to ensure predictable behavior.
    
    2. CACHE-BACKED DATA - All data comes from background polling cache
       This ensures graceful degradation when gateway is slow/offline.
       No on-demand blocking calls during HTTP requests.
    
    3. SAFE DEFAULTS - Returns empty arrays/nulls on errors
       Keeps UI responsive even during outages.
    
    4. FAST-FAIL - Checks cached gateway status before attempting calls
       Prevents request pile-up during network issues.

Adding New Endpoints:
    If you need a new /api/* endpoint, add it explicitly with cache support.
    Do NOT add catch-all routes - they break graceful degradation.
"""
import logging
import os
import time
from datetime import datetime, timedelta

import psutil
import pypowerwall
from fastapi import APIRouter, HTTPException, Response, Header
from typing import Optional

from app.core.gateway_manager import gateway_manager
from app.config import settings, SERVER_VERSION

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_control_token(authorization: Optional[str] = Header(None)):
    """Verify control token for authenticated operations."""
    if not settings.control_enabled or not settings.control_secret:
        raise HTTPException(status_code=403, detail="Control features not enabled")
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # Support both "Bearer token" and plain token
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    if token != settings.control_secret:
        raise HTTPException(status_code=401, detail="Invalid control token")
    
    return True


@router.post("/control/{path:path}")
async def control_api(path: str, data: dict, authorization: Optional[str] = Header(None)):
    """Authenticated control endpoint for POST operations."""
    verify_control_token(authorization)
    
    gateway_id = get_default_gateway()
    
    result = await gateway_manager.call_api(gateway_id, 'post', f"/api/{path}", data, timeout=10.0)
    if result is None:
        raise HTTPException(status_code=503, detail="Control operation failed or gateway not available")
    return result


def get_default_gateway():
    """Get the default gateway (first one or 'default' id)."""
    if "default" in gateway_manager.gateways:
        return "default"
    if gateway_manager.gateways:
        return list(gateway_manager.gateways.keys())[0]
    raise HTTPException(status_code=503, detail="No gateways configured")


@router.get("/vitals")
async def get_vitals():
    """Get vitals data (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    Returns empty object if no data available yet.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {}
    
    return status.data.vitals or {}


@router.get("/strings")
async def get_strings():
    """Get strings data (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    Returns empty object if no data available yet.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {}
    
    return status.data.strings or {}


@router.get("/aggregates")
async def get_aggregates():
    """Get aggregates data (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    Returns empty object if no data available yet.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data or not status.data.aggregates:
        return {}
    
    return status.data.aggregates


@router.get("/soe")
async def get_soe():
    """Get state of energy (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    Returns null percentage if no data available yet.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data or status.data.soe is None:
        return {"percentage": None}
    
    return {"percentage": status.data.soe}


@router.get("/freq")
async def get_freq():
    """Get grid frequency (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    Returns null freq if no data available yet.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data or status.data.freq is None:
        return {"freq": None}
    
    return {"freq": status.data.freq}


@router.get("/csv")
async def get_csv(headers: Optional[str] = None):
    """Get CSV format data (legacy proxy endpoint).
    
    Returns: Grid,Home,Solar,Battery,BatteryLevel
    Add ?headers (any value) to include CSV headers.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    # Graceful degradation: return cached data even if offline
    if not status or not status.data:
        # Return zeros for CSV (backwards compatibility)
        csv_data = "Grid,Home,Solar,Battery,BatteryLevel\n" if headers is not None else ""
        csv_data += "0.00,0.00,0.00,0.00,0.00\n"
        return Response(content=csv_data, media_type="text/plain; charset=utf-8")
    
    # Extract power values from aggregates
    aggregates = status.data.aggregates or {}
    grid = aggregates.get('site', {}).get('instant_power', 0)
    solar = aggregates.get('solar', {}).get('instant_power', 0)
    battery = aggregates.get('battery', {}).get('instant_power', 0)
    home = aggregates.get('load', {}).get('instant_power', 0)
    level = status.data.soe or 0
    
    # Build CSV response
    csv_data = ""
    if headers is not None:
        csv_data += "Grid,Home,Solar,Battery,BatteryLevel\n"
    csv_data += f"{grid:.2f},{home:.2f},{solar:.2f},{battery:.2f},{level:.2f}\n"
    
    return Response(content=csv_data, media_type="text/plain; charset=utf-8")


@router.get("/csv/v2")
async def get_csv_v2(headers: Optional[str] = None):
    """Get CSV v2 format data (legacy proxy endpoint).
    
    Returns: Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve
    Add ?headers (any value) to include CSV headers.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    pw = gateway_manager.get_connection(gateway_id)
    
    # Graceful degradation: return cached data even if offline
    if not status or not status.data:
        # Return zeros for CSV (backwards compatibility)
        csv_data = "Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve\n" if headers is not None else ""
        csv_data += "0.00,0.00,0.00,0.00,0.00,0,0\n"
        return Response(content=csv_data, media_type="text/plain; charset=utf-8")
    
    # Extract power values from aggregates
    aggregates = status.data.aggregates or {}
    grid = aggregates.get('site', {}).get('instant_power', 0)
    solar = aggregates.get('solar', {}).get('instant_power', 0)
    battery = aggregates.get('battery', {}).get('instant_power', 0)
    home = aggregates.get('load', {}).get('instant_power', 0)
    level = status.data.soe or 0
    
    # Get grid status from cache (1=UP, 0=DOWN)
    grid_status_str = status.data.grid_status
    gridstatus = 1 if grid_status_str == "UP" else 0
    
    # Get reserve level from cache
    reserve = status.data.reserve or 0
    
    # Build CSV response
    csv_data = ""
    if headers is not None:
        csv_data += "Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve\n"
    csv_data += f"{grid:.2f},{home:.2f},{solar:.2f},{battery:.2f},{level:.2f},{gridstatus},{reserve:.0f}\n"
    
    return Response(content=csv_data, media_type="text/plain; charset=utf-8")


@router.get("/temps")
async def get_temps():
    """Get Powerwall temperatures (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached temps even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {}
    
    return status.data.temps or {}


@router.get("/temps/pw")
async def get_temps_pw():
    """Get Powerwall temperatures with simple keys (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached temps even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    pwtemp = {}
    if status and status.data and status.data.temps:
        temps = status.data.temps
        idx = 1
        for i in temps:
            key = f"PW{idx}_temp"
            pwtemp[key] = temps[i]
            idx += 1
    return pwtemp


@router.get("/alerts")
async def get_alerts():
    """Get Powerwall alerts (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached alerts even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return []
    
    return status.data.alerts or []


@router.get("/alerts/pw")
async def get_alerts_pw():
    """Get Powerwall alerts in dictionary format (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached alerts even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    pwalerts = {}
    if status and status.data and status.data.alerts:
        for alert in status.data.alerts:
            pwalerts[alert] = 1
    return pwalerts


@router.get("/fans")
async def get_fans():
    """Get fan speeds in raw format (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {}
    
    return status.data.fan_speeds or {}


@router.get("/fans/pw")
async def get_fans_pw():
    """Get fan speeds in simplified format (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {}
    
    fan_speeds = status.data.fan_speeds or {}
    fans = {}
    for i, (_, value) in enumerate(sorted(fan_speeds.items())):
        key = f"FAN{i+1}"
        fans[f"{key}_actual"] = value.get("PVAC_Fan_Speed_Actual_RPM")
        fans[f"{key}_target"] = value.get("PVAC_Fan_Speed_Target_RPM")
    return fans


@router.get("/tedapi")
@router.get("/tedapi/")
async def get_tedapi_info():
    """Get TEDAPI information (legacy proxy endpoint)."""
    return {
        "error": "Use /tedapi/config, /tedapi/status, /tedapi/components, /tedapi/battery, /tedapi/controller"
    }


@router.get("/tedapi/config")
async def get_tedapi_config():
    """Get TEDAPI config (legacy proxy endpoint).
    
    Note: This diagnostic endpoint makes on-demand calls and does not use cache.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    # Fast fail if no connection
    if not status or not status.online:
        return {"error": "Gateway offline - TEDAPI unavailable"}
    
    config = await gateway_manager.call_tedapi(gateway_id, 'get_config', timeout=5.0)
    if config is None:
        return {"error": "TEDAPI not enabled or unavailable"}
    return config


@router.get("/tedapi/status")
async def get_tedapi_status():
    """Get TEDAPI status (legacy proxy endpoint).
    
    Note: This diagnostic endpoint makes on-demand calls and does not use cache.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    # Fast fail if no connection
    if not status or not status.online:
        return {"error": "Gateway offline - TEDAPI unavailable"}
    
    result = await gateway_manager.call_tedapi(gateway_id, 'get_status', timeout=5.0)
    if result is None:
        return {"error": "TEDAPI not enabled or unavailable"}
    return result


@router.get("/tedapi/components")
async def get_tedapi_components():
    """Get TEDAPI components (legacy proxy endpoint).
    
    Note: This diagnostic endpoint makes on-demand calls and does not use cache.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    # Fast fail if no connection
    if not status or not status.online:
        return {"error": "Gateway offline - TEDAPI unavailable"}
    
    components = await gateway_manager.call_tedapi(gateway_id, 'get_components', timeout=5.0)
    if components is None:
        return {"error": "TEDAPI not enabled or unavailable"}
    return components


@router.get("/tedapi/battery")
async def get_tedapi_battery():
    """Get TEDAPI battery blocks (legacy proxy endpoint).
    
    Note: This diagnostic endpoint makes on-demand calls and does not use cache.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    # Fast fail if no connection
    if not status or not status.online:
        return {"error": "Gateway offline - TEDAPI unavailable"}
    
    battery = await gateway_manager.call_tedapi(gateway_id, 'get_battery_blocks', timeout=5.0)
    if battery is None:
        return {"error": "TEDAPI not enabled or unavailable"}
    return battery


@router.get("/tedapi/controller")
async def get_tedapi_controller():
    """Get TEDAPI device controller (legacy proxy endpoint).
    
    Note: This diagnostic endpoint makes on-demand calls and does not use cache.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    # Fast fail if no connection
    if not status or not status.online:
        return {"error": "Gateway offline - TEDAPI unavailable"}
    
    controller = await gateway_manager.call_tedapi(gateway_id, 'get_device_controller', timeout=5.0)
    if controller is None:
        return {"error": "TEDAPI not enabled or unavailable"}
    return controller


@router.get("/pod")
async def get_pod():
    """Get Powerwall battery data (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {}
    
    pod = {}
    
    # Get Individual Powerwall Battery Data from cached system_status
    system_status = status.data.system_status
    if system_status and "battery_blocks" in system_status:
        idx = 1
        for block in system_status["battery_blocks"]:
            # Initialize with None placeholders
            pod[f"PW{idx}_name"] = None
            pod[f"PW{idx}_POD_ActiveHeating"] = None
            pod[f"PW{idx}_POD_ChargeComplete"] = None
            pod[f"PW{idx}_POD_ChargeRequest"] = None
            pod[f"PW{idx}_POD_DischargeComplete"] = None
            pod[f"PW{idx}_POD_PermanentlyFaulted"] = None
            pod[f"PW{idx}_POD_PersistentlyFaulted"] = None
            pod[f"PW{idx}_POD_enable_line"] = None
            pod[f"PW{idx}_POD_available_charge_power"] = None
            pod[f"PW{idx}_POD_available_dischg_power"] = None
            pod[f"PW{idx}_POD_nom_energy_remaining"] = None
            pod[f"PW{idx}_POD_nom_energy_to_be_charged"] = None
            pod[f"PW{idx}_POD_nom_full_pack_energy"] = None
            
            # System Status Data
            pod[f"PW{idx}_POD_nom_energy_remaining"] = block.get("nominal_energy_remaining")
            pod[f"PW{idx}_POD_nom_full_pack_energy"] = block.get("nominal_full_pack_energy")
            pod[f"PW{idx}_PackagePartNumber"] = block.get("PackagePartNumber")
            pod[f"PW{idx}_PackageSerialNumber"] = block.get("PackageSerialNumber")
            pod[f"PW{idx}_pinv_state"] = block.get("pinv_state")
            pod[f"PW{idx}_pinv_grid_state"] = block.get("pinv_grid_state")
            pod[f"PW{idx}_p_out"] = block.get("p_out")
            pod[f"PW{idx}_q_out"] = block.get("q_out")
            pod[f"PW{idx}_v_out"] = block.get("v_out")
            pod[f"PW{idx}_f_out"] = block.get("f_out")
            pod[f"PW{idx}_i_out"] = block.get("i_out")
            pod[f"PW{idx}_energy_charged"] = block.get("energy_charged")
            pod[f"PW{idx}_energy_discharged"] = block.get("energy_discharged")
            pod[f"PW{idx}_off_grid"] = int(block.get("off_grid") or 0)
            pod[f"PW{idx}_vf_mode"] = int(block.get("vf_mode") or 0)
            pod[f"PW{idx}_wobble_detected"] = int(block.get("wobble_detected") or 0)
            pod[f"PW{idx}_charge_power_clamped"] = int(block.get("charge_power_clamped") or 0)
            pod[f"PW{idx}_backup_ready"] = int(block.get("backup_ready") or 0)
            pod[f"PW{idx}_OpSeqState"] = block.get("OpSeqState")
            pod[f"PW{idx}_version"] = block.get("version")
            idx += 1
    
    # Augment with Vitals Data if available
    if status.data.vitals:
        vitals = status.data.vitals
        idx = 1
        for device in vitals:
            v = vitals[device]
            if device.startswith("TEPOD"):
                pod[f"PW{idx}_name"] = device
                pod[f"PW{idx}_POD_ActiveHeating"] = int(v.get("POD_ActiveHeating") or 0)
                pod[f"PW{idx}_POD_ChargeComplete"] = int(v.get("POD_ChargeComplete") or 0)
                pod[f"PW{idx}_POD_ChargeRequest"] = int(v.get("POD_ChargeRequest") or 0)
                pod[f"PW{idx}_POD_DischargeComplete"] = int(v.get("POD_DischargeComplete") or 0)
                pod[f"PW{idx}_POD_PermanentlyFaulted"] = int(v.get("POD_PermanentlyFaulted") or 0)
                pod[f"PW{idx}_POD_PersistentlyFaulted"] = int(v.get("POD_PersistentlyFaulted") or 0)
                pod[f"PW{idx}_POD_enable_line"] = int(v.get("POD_enable_line") or 0)
                pod[f"PW{idx}_POD_available_charge_power"] = v.get("POD_available_charge_power")
                pod[f"PW{idx}_POD_available_dischg_power"] = v.get("POD_available_dischg_power")
                pod[f"PW{idx}_POD_nom_energy_remaining"] = v.get("POD_nom_energy_remaining")
                pod[f"PW{idx}_POD_nom_energy_to_be_charged"] = v.get("POD_nom_energy_to_be_charged")
                pod[f"PW{idx}_POD_nom_full_pack_energy"] = v.get("POD_nom_full_pack_energy")
                idx += 1
    
    # Aggregate data from cached system_status
    if system_status:
        pod["nominal_full_pack_energy"] = system_status.get("nominal_full_pack_energy")
        pod["nominal_energy_remaining"] = system_status.get("nominal_energy_remaining")
    
    # Use cached time_remaining and reserve
    pod["time_remaining_hours"] = status.data.time_remaining
    pod["backup_reserve_percent"] = status.data.reserve
    
    return pod


@router.get("/battery")
async def get_battery_power():
    """Get battery power (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {"power": 0}
    
    aggregates = status.data.aggregates or {}
    battery_power = aggregates.get('battery', {}).get('instant_power', 0)
    
    return {"power": battery_power}


# NOTE: Specific /api/* routes must be defined BEFORE the catch-all /api/{path:path}
# Otherwise FastAPI will match the catch-all first.

@router.get("/api/system_status/soe")
async def get_api_soe():
    """Get battery state of energy - API format (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {"percentage": None}
    
    level = status.data.soe
    if level is not None:
        # Scale to 95% like the original proxy
        level = level * 0.95
    
    return {"percentage": level}


@router.get("/api/system_status/grid_status")
async def get_api_grid_status():
    """Get grid status - API format (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {"grid_status": "Unknown"}
    
    # Try to get grid status from vitals or aggregates
    vitals = status.data.vitals or {}
    grid_status = vitals.get('grid_status', 'SystemGridConnected')
    
    return {"grid_status": grid_status}


@router.get("/api/sitemaster")
async def get_api_sitemaster():
    """Get sitemaster status - API format (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    If we have cached data, report as running even if currently offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    # If we have data (even stale), report as running
    if status and status.data:
        return {
            "status": "StatusUp",
            "running": True,
            "connected_to_tesla": status.online  # True only if actually connected
        }
    
    return {
        "status": "StatusDown",
        "running": False,
        "connected_to_tesla": False
    }


@router.get("/api/troubleshooting/problems")
async def get_api_problems():
    """Get troubleshooting problems - API format (legacy proxy endpoint)."""
    # Return empty problems list - this endpoint is for Tesla app diagnostics
    return {"problems": []}


@router.get("/api/auth/toggle/supported")
async def get_api_auth_toggle():
    """Get auth toggle support - API format (legacy proxy endpoint)."""
    # This endpoint indicates whether the gateway supports auth toggling
    return {"toggle_auth_supported": False}


@router.get("/api/status")
async def get_api_status():
    """Get API status - API format (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if status and status.data:
        return {
            "start_time": status.data.timestamp or 0,
            "up_time_seconds": status.data.uptime or "0s",
            "is_new": False,
            "version": status.data.version or "Unknown"
        }
    
    return {
        "start_time": 0,
        "up_time_seconds": "0s",
        "is_new": False,
        "version": "Unknown"
    }


@router.get("/api/site_info")
async def get_api_site_info():
    """Get site info - API format (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    site_name = "My Powerwall"
    if status and status.gateway:
        site_name = status.gateway.name or site_name
    
    return {
        "site_name": site_name,
        "timezone": status.gateway.timezone if status and status.gateway else "America/Los_Angeles",
        "grid_code": {
            "grid_code": "60Hz_240V_s_UL1741SA:2019_California",
            "grid_voltage_setting": 240,
            "grid_freq_setting": 60
        }
    }


@router.get("/api/site_info/site_name")
async def get_api_site_name():
    """Get site name - API format (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    site_name = "My Powerwall"
    if status and status.gateway:
        site_name = status.gateway.name or site_name
    
    return {"site_name": site_name}


@router.get("/api/customer/registration")
async def get_api_customer_registration():
    """Get customer registration - API format (legacy proxy endpoint)."""
    return {
        "privacy_notice": True,
        "limited_warranty": True,
        "grid_services": False,
        "marketing": False,
        "registered": True,
        "timed_out_registration": False
    }


@router.get("/api/system_status/grid_faults")
async def get_api_grid_faults():
    """Get grid faults - API format (legacy proxy endpoint)."""
    # Return empty faults list
    return []


@router.get("/api/meters/aggregates")
async def get_api_aggregates():
    """Get power aggregates - API format (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    Returns empty object if no data available yet (e.g., during startup).
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    # Graceful degradation: return cached data or empty object
    if not status or not status.data:
        return {}
    
    return status.data.aggregates or {}


@router.get("/api/networks")
@router.get("/api/system/networks")
async def get_api_networks():
    """Get network configuration - API format (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return []
    
    return status.data.networks or []


@router.get("/api/powerwalls")
async def get_api_powerwalls():
    """Get powerwalls list - API format (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached data even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.data:
        return {}
    
    return status.data.powerwalls or {}


# NOTE: No catch-all /api/{path:path} routes!
# All API endpoints must be explicitly defined to ensure:
# 1. Graceful degradation - all data comes from cache
# 2. Predictable behavior - documented, testable endpoints
# 3. Security - no passthrough to arbitrary Powerwall endpoints
# 4. Performance - no on-demand blocking calls during requests
#
# If you need a new /api/* endpoint, add it explicitly above with cache support.


@router.get("/stats")
async def get_stats():
    """Get proxy statistics (legacy proxy endpoint)."""
    # Get process info
    process = psutil.Process(os.getpid())
    
    # Calculate uptime
    create_time = process.create_time()
    uptime_seconds = int(time.time() - create_time)
    uptime = str(timedelta(seconds=uptime_seconds))
    
    # Count online/offline gateways
    total_gateways = len(gateway_manager.gateways)
    online_count = 0
    gateway_statuses = []
    
    for gateway_id, gw in gateway_manager.gateways.items():
        status = gateway_manager.get_gateway(gateway_id)
        if status and status.online:
            online_count += 1
        
        # Get backoff info from gateway_manager
        failures = gateway_manager._consecutive_failures.get(gateway_id, 0)
        next_poll = gateway_manager._next_poll_time.get(gateway_id, 0)
        now = datetime.now().timestamp()
        backoff_remaining = max(0, int(next_poll - now))
        
        gateway_statuses.append({
            "id": gateway_id,
            "name": gw.name,
            "host": gw.host,
            "online": status.online if status else False,
            "last_error": status.error if status and status.error else None,
            "last_updated": status.last_updated if status and status.last_updated else None,
            "consecutive_failures": failures,
            "backoff_seconds": backoff_remaining if failures > 0 else 0
        })
    
    # Build stats response
    stats = {
        "ts": int(time.time()),
        "uptime": uptime,
        "mem": process.memory_info().rss,
        "memory_mb": process.memory_info().rss / (1024 * 1024),
        "server_version": SERVER_VERSION,
        "pypowerwall_version": pypowerwall.__version__,
        "gateways": {
            "total": total_gateways,
            "online": online_count,
            "offline": total_gateways - online_count
        },
        "cloudmode": False,
        "fleetapi": False,
        "gateway_statuses": gateway_statuses
    }
    
    # Add default gateway info for backward compatibility
    if gateway_manager.gateways:
        gateway_id = list(gateway_manager.gateways.keys())[0]
        status = gateway_manager.get_gateway(gateway_id)
        if status:
            stats["site_name"] = status.gateway.name
    
    return stats


@router.get("/version")
async def get_version():
    """Get firmware version (legacy proxy endpoint).
    
    Uses graceful degradation: returns cached version even if gateway is temporarily offline.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    version = None
    if status and status.data:
        version = status.data.version
    
    if version is None:
        return {
            "version": "Unknown",
            "vint": 0
        }
    
    # Parse version string to integer (basic implementation)
    vint = 0
    try:
        # Extract numbers from version string like "23.44.0"
        parts = version.split('.')
        if len(parts) >= 2:
            vint = int(parts[0]) * 100 + int(parts[1])
    except Exception:
        pass
    
    return {
        "version": version,
        "vint": vint
    }
