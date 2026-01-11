"""Legacy proxy-compatible API endpoints."""
from fastapi import APIRouter, HTTPException, Response, Header
from typing import Optional
import json

from app.core.gateway_manager import gateway_manager
from app.config import settings

router = APIRouter()


def verify_control_token(authorization: Optional[str] = Header(None)):
    """Verify control token for authenticated operations."""
    if not settings.control_enabled or not settings.control_token:
        raise HTTPException(status_code=403, detail="Control features not enabled")
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # Support both "Bearer token" and plain token
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    if token != settings.control_token:
        raise HTTPException(status_code=401, detail="Invalid control token")
    
    return True


@router.post("/control/{path:path}")
async def control_api(path: str, data: dict, authorization: Optional[str] = Header(None)):
    """Authenticated control endpoint for POST operations."""
    verify_control_token(authorization)
    
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        result = pw.post(f"/api/{path}", data)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Control operation failed: {str(e)}")


def get_default_gateway():
    """Get the default gateway (first one or 'default' id)."""
    if "default" in gateway_manager.gateways:
        return "default"
    if gateway_manager.gateways:
        return list(gateway_manager.gateways.keys())[0]
    raise HTTPException(status_code=503, detail="No gateways configured")


@router.get("/vitals")
async def get_vitals():
    """Get vitals data (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.online or not status.data:
        raise HTTPException(status_code=503, detail="Gateway offline or no data available")
    
    return status.data.vitals or {}


@router.get("/strings")
async def get_strings():
    """Get strings data (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.online or not status.data:
        raise HTTPException(status_code=503, detail="Gateway offline or no data available")
    
    return status.data.strings or {}


@router.get("/aggregates")
async def get_aggregates():
    """Get aggregates data (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status:
        raise HTTPException(status_code=503, detail="Gateway not found")
    
    if not status.online:
        raise HTTPException(status_code=503, detail="Gateway offline")
    
    if not status.data:
        raise HTTPException(status_code=503, detail="No data available from gateway")
    
    if not status.data.aggregates:
        raise HTTPException(status_code=503, detail="Aggregates data not available")
    
    return status.data.aggregates


@router.get("/soe")
async def get_soe():
    """Get state of energy (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.online or not status.data:
        raise HTTPException(status_code=503, detail="Gateway offline or no data available")
    
    if status.data.soe is None:
        raise HTTPException(status_code=503, detail="SOE data not available")
    
    return {"percentage": status.data.soe}


@router.get("/freq")
async def get_freq():
    """Get grid frequency (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.online or not status.data:
        raise HTTPException(status_code=503, detail="Gateway offline or no data available")
    
    if status.data.freq is None:
        raise HTTPException(status_code=503, detail="Frequency data not available")
    
    return {"freq": status.data.freq}


@router.get("/csv")
async def get_csv(headers: bool = False):
    """Get CSV format data (legacy proxy endpoint).
    
    Returns: Grid,Home,Solar,Battery,BatteryLevel
    Add ?headers=true to include CSV headers.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.online or not status.data:
        # Return zeros for CSV (backwards compatibility)
        csv_data = "Grid,Home,Solar,Battery,BatteryLevel\n" if headers else ""
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
    if headers:
        csv_data += "Grid,Home,Solar,Battery,BatteryLevel\n"
    csv_data += f"{grid:.2f},{home:.2f},{solar:.2f},{battery:.2f},{level:.2f}\n"
    
    return Response(content=csv_data, media_type="text/plain; charset=utf-8")


@router.get("/csv/v2")
async def get_csv_v2(headers: bool = False):
    """Get CSV v2 format data (legacy proxy endpoint).
    
    Returns: Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve
    Add ?headers=true to include CSV headers.
    """
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    pw = gateway_manager.get_connection(gateway_id)
    
    if not status or not status.online or not status.data or not pw:
        # Return zeros for CSV (backwards compatibility)
        csv_data = "Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve\n" if headers else ""
        csv_data += "0.00,0.00,0.00,0.00,0.00,0,0\n"
        return Response(content=csv_data, media_type="text/plain; charset=utf-8")
    
    # Extract power values from aggregates
    aggregates = status.data.aggregates or {}
    grid = aggregates.get('site', {}).get('instant_power', 0)
    solar = aggregates.get('solar', {}).get('instant_power', 0)
    battery = aggregates.get('battery', {}).get('instant_power', 0)
    home = aggregates.get('load', {}).get('instant_power', 0)
    level = status.data.soe or 0
    
    # Get grid status (1=UP, 0=DOWN)
    try:
        grid_status_str = pw.grid_status()
        gridstatus = 1 if grid_status_str == "UP" else 0
    except:
        gridstatus = 0
    
    # Get reserve level
    try:
        reserve = pw.get_reserve() or 0
    except:
        reserve = 0
    
    # Build CSV response
    csv_data = ""
    if headers:
        csv_data += "Grid,Home,Solar,Battery,BatteryLevel,GridStatus,Reserve\n"
    csv_data += f"{grid:.2f},{home:.2f},{solar:.2f},{battery:.2f},{level:.2f},{gridstatus},{reserve:.0f}\n"
    
    return Response(content=csv_data, media_type="text/plain; charset=utf-8")


@router.get("/temps")
async def get_temps():
    """Get Powerwall temperatures (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        temps = pw.temps()
        return temps or {}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get temperatures: {str(e)}")


@router.get("/temps/pw")
async def get_temps_pw():
    """Get Powerwall temperatures with simple keys (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        temps = pw.temps()
        pwtemp = {}
        idx = 1
        if temps:
            for i in temps:
                key = f"PW{idx}_temp"
                pwtemp[key] = temps[i]
                idx += 1
        return pwtemp
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get temperatures: {str(e)}")


@router.get("/alerts")
async def get_alerts():
    """Get Powerwall alerts (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        alerts = pw.alerts()
        return alerts or []
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get alerts: {str(e)}")


@router.get("/alerts/pw")
async def get_alerts_pw():
    """Get Powerwall alerts in dictionary format (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        alerts = pw.alerts()
        pwalerts = {}
        if alerts:
            for alert in alerts:
                pwalerts[alert] = 1
        return pwalerts
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get alerts: {str(e)}")


@router.get("/fans")
async def get_fans():
    """Get fan speeds in raw format (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        if hasattr(pw, 'tedapi') and pw.tedapi:
            return pw.tedapi.get_fan_speeds() or {}
        return {}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get fan speeds: {str(e)}")


@router.get("/fans/pw")
async def get_fans_pw():
    """Get fan speeds in simplified format (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        if hasattr(pw, 'tedapi') and pw.tedapi:
            fans = {}
            fan_speeds = pw.tedapi.get_fan_speeds() or {}
            for i, (_, value) in enumerate(sorted(fan_speeds.items())):
                key = f"FAN{i+1}"
                fans[f"{key}_actual"] = value.get("PVAC_Fan_Speed_Actual_RPM")
                fans[f"{key}_target"] = value.get("PVAC_Fan_Speed_Target_RPM")
            return fans
        return {}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get fan speeds: {str(e)}")


@router.get("/tedapi")
@router.get("/tedapi/")
async def get_tedapi_info():
    """Get TEDAPI information (legacy proxy endpoint)."""
    return {
        "error": "Use /tedapi/config, /tedapi/status, /tedapi/components, /tedapi/battery, /tedapi/controller"
    }


@router.get("/tedapi/config")
async def get_tedapi_config():
    """Get TEDAPI config (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    if not hasattr(pw, 'tedapi') or not pw.tedapi:
        return {"error": "TEDAPI not enabled"}
    
    try:
        return pw.tedapi.get_config()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get TEDAPI config: {str(e)}")


@router.get("/tedapi/status")
async def get_tedapi_status():
    """Get TEDAPI status (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    if not hasattr(pw, 'tedapi') or not pw.tedapi:
        return {"error": "TEDAPI not enabled"}
    
    try:
        return pw.tedapi.get_status()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get TEDAPI status: {str(e)}")


@router.get("/tedapi/components")
async def get_tedapi_components():
    """Get TEDAPI components (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    if not hasattr(pw, 'tedapi') or not pw.tedapi:
        return {"error": "TEDAPI not enabled"}
    
    try:
        return pw.tedapi.get_components()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get TEDAPI components: {str(e)}")


@router.get("/tedapi/battery")
async def get_tedapi_battery():
    """Get TEDAPI battery blocks (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    if not hasattr(pw, 'tedapi') or not pw.tedapi:
        return {"error": "TEDAPI not enabled"}
    
    try:
        return pw.tedapi.get_battery_blocks()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get TEDAPI battery: {str(e)}")


@router.get("/tedapi/controller")
async def get_tedapi_controller():
    """Get TEDAPI device controller (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    if not hasattr(pw, 'tedapi') or not pw.tedapi:
        return {"error": "TEDAPI not enabled"}
    
    try:
        return pw.tedapi.get_device_controller()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get TEDAPI controller: {str(e)}")


@router.get("/pod")
async def get_pod():
    """Get Powerwall battery data (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    status = gateway_manager.get_gateway(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        pod = {}
        
        # Get Individual Powerwall Battery Data from system_status
        system_status = pw.system_status()
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
        if status and status.data and status.data.vitals:
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
        
        # Aggregate data
        if system_status:
            pod["nominal_full_pack_energy"] = system_status.get("nominal_full_pack_energy")
            pod["nominal_energy_remaining"] = system_status.get("nominal_energy_remaining")
        
        try:
            pod["time_remaining_hours"] = pw.get_time_remaining()
        except:
            pod["time_remaining_hours"] = None
        
        try:
            pod["backup_reserve_percent"] = pw.get_reserve()
        except:
            pod["backup_reserve_percent"] = None
        
        return pod
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to get battery data: {str(e)}")


@router.get("/battery")
async def get_battery_power():
    """Get battery power (legacy proxy endpoint)."""
    gateway_id = get_default_gateway()
    status = gateway_manager.get_gateway(gateway_id)
    
    if not status or not status.online or not status.data:
        return {"power": 0}
    
    aggregates = status.data.aggregates or {}
    battery_power = aggregates.get('battery', {}).get('instant_power', 0)
    
    return {"power": battery_power}


@router.get("/api/{path:path}")
async def proxy_api(path: str):
    """Proxy arbitrary API calls to default gateway (legacy)."""
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        result = pw.poll(f"/api/{path}")
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"API call failed: {str(e)}")


@router.post("/api/{path:path}")
async def proxy_api_post(path: str, data: dict):
    """Proxy POST requests to default gateway (legacy)."""
    from app.config import settings
    from fastapi import Header
    
    # Check if control is enabled
    if settings.control_enabled:
        raise HTTPException(
            status_code=403, 
            detail="Control operations require authentication. Use /control endpoint."
        )
    
    gateway_id = get_default_gateway()
    pw = gateway_manager.get_connection(gateway_id)
    
    if not pw:
        raise HTTPException(status_code=503, detail="Gateway not available")
    
    try:
        result = pw.post(f"/api/{path}", data)
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"API call failed: {str(e)}")
