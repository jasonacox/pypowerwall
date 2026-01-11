"""
Gateway Manager - Manages connections to multiple Powerwall gateways.

This is the central hub of the server that manages all pypowerwall connections,
performs background polling, caches data, and provides fast API responses.

Architecture:
    - Singleton pattern (single gateway_manager instance)
    - Background polling task runs every PW_CACHE_EXPIRE seconds (default: 5s)
    - Concurrent polling of all gateways using asyncio.gather
    - Cached data for instant API responses without blocking
    - Automatic reconnection on failure

Connection Modes:
    TEDAPI (Local Gateway):
        pw = pypowerwall.Powerwall(
            host="192.168.91.1",
            gw_pwd="gateway_wifi_password",
            timeout=3
        )
    
    Cloud Mode:
        pw = pypowerwall.Powerwall(
            email="user@example.com",
            authpath="/path/to/auth/files",
            cloudmode=True
        )
    
    FleetAPI:
        pw = pypowerwall.Powerwall(
            email="user@example.com",
            authpath="/path/to/auth/files",
            fleetapi=True
        )

Data Flow:
    1. Background task calls _poll_gateway() for each gateway every N seconds
    2. _poll_gateway() makes blocking pypowerwall calls in executor with timeouts
    3. Results cached in self.cache[gateway_id] as GatewayStatus objects
    4. API endpoints read from cache (instant response, no blocking)
    5. Failed polls update gateway status to offline (automatic retry next cycle)

Error Handling:
    - Connection failures logged but don't crash server
    - Timeouts on pypowerwall calls (3-10s depending on operation)
    - Offline gateways excluded from aggregates
    - Cached data remains available during outages
    - Automatic reconnection every poll cycle

Thread Safety:
    - All operations use asyncio (no threads/locks needed)
    - Single event loop handles all concurrency
    - Background task coordinated via asyncio.create_task()
    - Graceful shutdown via task cancellation

Performance:
    - Concurrent gateway polling for speed
    - Short timeouts prevent blocking
    - Cached responses for instant API access
    - Minimal memory footprint (only latest data cached)
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import pypowerwall
from app.models.gateway import Gateway, GatewayStatus, PowerwallData, AggregateData
from app.config import GatewayConfig

logger = logging.getLogger(__name__)


class GatewayManager:
    """Manages multiple Powerwall gateway connections."""
    
    def __init__(self):
        self.gateways: Dict[str, Gateway] = {}
        self.connections: Dict[str, pypowerwall.Powerwall] = {}
        self.cache: Dict[str, GatewayStatus] = {}
        self._poll_task: Optional[asyncio.Task] = None
        self._poll_interval = 5  # Default, will be set from config during initialize()
        
        # Exponential backoff tracking per gateway
        self._consecutive_failures: Dict[str, int] = {}  # Track failure count
        self._next_poll_time: Dict[str, float] = {}  # Track when to poll next (Unix timestamp)
        self._last_successful_data: Dict[str, PowerwallData] = {}  # Keep last good data for graceful degradation
        self._pending_configs: Dict[str, GatewayConfig] = {}  # Gateways waiting for lazy initialization
        
        # Dedicated thread pool for blocking pypowerwall operations
        # Will be sized during initialize() based on gateway count
        self._executor: Optional[ThreadPoolExecutor] = None
    
    async def initialize(self, gateway_configs: List[GatewayConfig], poll_interval: int = 5):
        """Initialize gateway manager - non-blocking.
        
        This method sets up gateways for lazy initialization. Actual pypowerwall
        connections are created during the first poll cycle to ensure the server
        starts accepting connections immediately.
        
        Args:
            gateway_configs: List of gateway configurations
            poll_interval: Polling frequency in seconds (from PW_CACHE_EXPIRE, default: 5)
        """
        self._poll_interval = poll_interval
        
        # Size thread pool based on gateway count
        # Formula: max(10, num_gateways * 3) to support concurrent API calls
        num_gateways = len(gateway_configs)
        pool_size = max(10, num_gateways * 3)
        self._executor = ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix="pypowerwall")
        logger.info(f"Thread pool initialized with {pool_size} workers for {num_gateways} gateway(s)")
        
        for config in gateway_configs:
            try:
                # Validate configuration
                # TEDAPI mode: need host + gw_pwd
                # Cloud mode: need email (authpath is optional, pypowerwall has defaults)
                has_tedapi = config.host and config.gw_pwd
                has_cloud = config.email  # cloud_mode is auto-set, email is sufficient
                
                if not (has_tedapi or has_cloud):
                    logger.error(f"Invalid configuration for gateway {config.id}: need host+gw_pwd (TEDAPI) or email (Cloud)")
                    continue
                
                # Auto-enable cloud_mode if email is set but no host
                if config.email and not config.host:
                    config.cloud_mode = True
                
                gateway = Gateway(
                    id=config.id,
                    name=config.name,
                    host=config.host,
                    gw_pwd=config.gw_pwd,
                    email=config.email,
                    timezone=config.timezone,
                    cloud_mode=config.cloud_mode,
                    fleetapi=config.fleetapi
                )
                
                # Store gateway - connection will be created lazily on first poll
                self.gateways[config.id] = gateway
                self._pending_configs[config.id] = config  # All start as pending
                
                self.cache[config.id] = GatewayStatus(
                    gateway=gateway,
                    online=False,
                    error="Initializing..."
                )
                
                # Initialize backoff tracking
                self._consecutive_failures[config.id] = 0
                self._next_poll_time[config.id] = 0  # Poll immediately
                
                # Determine and log connection mode
                if config.fleetapi:
                    mode = "FleetAPI"
                elif config.cloud_mode:
                    mode = "Cloud"
                else:
                    mode = "TEDAPI"
                
                logger.info(f"Registered gateway: {config.id} ({config.name}) - {mode} mode - connection pending")
            except Exception as e:
                logger.error(f"Failed to initialize gateway {config.id}: {e}")
        
        # Start polling task
        if self.gateways:
            self._poll_task = asyncio.create_task(self._poll_gateways())
            logger.info(f"Gateway manager ready - {len(self.gateways)} gateway(s) will connect on first poll")
    
    async def shutdown(self):
        """Shutdown gateway manager and cleanup resources."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                # Expected when cancelling the polling task during shutdown
                pass
        
        # Shutdown thread pool executor
        if self._executor:
            self._executor.shutdown(wait=False)
        logger.info("Gateway manager shutdown complete")
    
    async def _poll_gateways(self):
        """Background task to poll all gateways periodically."""
        while True:
            try:
                # Poll all gateways concurrently
                tasks = [
                    self._poll_gateway(gateway_id) 
                    for gateway_id in self.gateways.keys()
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in polling task: {e}")
                await asyncio.sleep(self._poll_interval)
    
    async def _poll_gateway(self, gateway_id: str) -> None:
        """Poll a single gateway for data with exponential backoff on failures."""
        try:
            # Check if we're in backoff period
            now = datetime.now().timestamp()
            next_poll = self._next_poll_time.get(gateway_id, 0)
            
            if now < next_poll:
                # Skip this poll cycle - in backoff period
                logger.debug(f"Gateway {gateway_id} in backoff, skipping poll (next poll at {next_poll - now:.0f}s)")
                return
            
            # Check for lazy initialization - create connection if pending
            if gateway_id in self._pending_configs and gateway_id not in self.connections:
                config = self._pending_configs[gateway_id]
                logger.info(f"Attempting lazy initialization of gateway {gateway_id}")
                
                from app.config import settings
                loop = asyncio.get_running_loop()
                
                try:
                    if config.cloud_mode and config.email:
                        cloud_kwargs = {
                            "email": config.email,
                            "cloudmode": True,
                            "fleetapi": config.fleetapi,
                            "timezone": config.timezone
                        }
                        if config.authpath:
                            cloud_kwargs["authpath"] = config.authpath
                        pw = await asyncio.wait_for(
                            loop.run_in_executor(self._executor, lambda kw=cloud_kwargs: pypowerwall.Powerwall(**kw)),
                            timeout=15.0
                        )
                    else:
                        tedapi_kwargs = {
                            "host": config.host,
                            "gw_pwd": config.gw_pwd,
                            "timezone": config.timezone,
                            "timeout": settings.timeout,
                            "poolmaxsize": settings.pool_maxsize,
                        }
                        if settings.pw_password:
                            tedapi_kwargs["password"] = settings.pw_password
                        if config.email:
                            tedapi_kwargs["email"] = config.email
                        if config.authpath:
                            tedapi_kwargs["authpath"] = config.authpath
                        if settings.cache_file:
                            tedapi_kwargs["cachefile"] = settings.cache_file
                        if settings.siteid:
                            tedapi_kwargs["siteid"] = settings.siteid
                        pw = await asyncio.wait_for(
                            loop.run_in_executor(self._executor, lambda kw=tedapi_kwargs: pypowerwall.Powerwall(**kw)),
                            timeout=15.0
                        )
                    
                    self.connections[gateway_id] = pw
                    del self._pending_configs[gateway_id]
                    
                    # Try to get site_id for cloud mode gateways
                    gateway = self.gateways[gateway_id]
                    mode_label = "FleetAPI" if gateway.fleetapi else ("Cloud" if gateway.cloud_mode else "TEDAPI")
                    
                    if gateway.cloud_mode or gateway.fleetapi:
                        try:
                            site_id = getattr(pw, 'siteid', None) or getattr(pw, 'site_id', None)
                            if site_id:
                                gateway.site_id = str(site_id)
                                logger.info(f"Connected to gateway {gateway_id} - {mode_label} mode (Site ID: {site_id}, Email: {gateway.email})")
                            else:
                                logger.info(f"Connected to gateway {gateway_id} - {mode_label} mode (Email: {gateway.email})")
                        except Exception:
                            logger.info(f"Connected to gateway {gateway_id} - {mode_label} mode")
                    else:
                        logger.info(f"Connected to gateway {gateway_id} - {mode_label} mode ({gateway.host})")
                    
                except asyncio.TimeoutError:
                    logger.warning(f"Lazy initialization timeout for gateway {gateway_id} - will retry next cycle")
                    raise Exception("Connection initialization timeout")
                except Exception as e:
                    logger.warning(f"Lazy initialization failed for gateway {gateway_id}: {e}")
                    raise
            
            pw = self.connections.get(gateway_id)
            if not pw:
                logger.debug(f"No connection object for gateway {gateway_id} - waiting for lazy init")
                raise Exception("Connection not yet initialized")
            
            # Run blocking pypowerwall calls in dedicated executor with timeout protection
            loop = asyncio.get_running_loop()
            
            # Fetch core data - aggregates is required, vitals/strings are optional
            # Use asyncio.wait_for to timeout if pypowerwall hangs
            try:
                aggregates = await asyncio.wait_for(
                    loop.run_in_executor(self._executor, pw.poll, '/api/meters/aggregates'),
                    timeout=10.0  # 10 second timeout
                )
            except asyncio.TimeoutError:
                raise Exception(f"Timeout fetching aggregates from {gateway_id}")
            except Exception as e:
                # If we can't get aggregates, this is a real connection failure
                raise Exception(f"Failed to fetch aggregates: {e}")
            
            # Build PowerwallData with required aggregates
            data = PowerwallData(
                aggregates=aggregates,
                timestamp=datetime.now().timestamp()
            )
            
            # Try to get optional vitals and strings (don't fail if these aren't available)
            try:
                data.vitals = await asyncio.wait_for(
                    loop.run_in_executor(self._executor, pw.vitals),
                    timeout=10.0
                )
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Vitals not available for {gateway_id}: {e}")
            
            try:
                data.strings = await asyncio.wait_for(
                    loop.run_in_executor(self._executor, pw.strings),
                    timeout=10.0
                )
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Strings not available for {gateway_id}: {e}")
            
            # Try to get additional data
            try:
                data.soe = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.level), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"SOE not available for {gateway_id}: {e}")
            
            try:
                data.freq = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.freq), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Frequency not available for {gateway_id}: {e}")
            
            try:
                data.status = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.status), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Status not available for {gateway_id}: {e}")
            
            try:
                data.version = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.version), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Version not available for {gateway_id}: {e}")
            
            logger.debug(f"Gateway {gateway_id} aggregates: {data.aggregates}")
            
            # Try to get alerts (for caching)
            try:
                data.alerts = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.alerts), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Alerts not available for {gateway_id}: {e}")
            
            # Try to get temps (for caching)
            try:
                data.temps = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.temps), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Temps not available for {gateway_id}: {e}")
            
            # Try to get grid status (for caching)
            try:
                data.grid_status = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.grid_status), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Grid status not available for {gateway_id}: {e}")
            
            # Try to get reserve and time remaining (for caching)
            try:
                data.reserve = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.get_reserve), timeout=5.0)
                data.time_remaining = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.get_time_remaining), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Reserve/time remaining not available for {gateway_id}: {e}")
            
            # Try to get system status for /pod endpoint (for caching)
            try:
                data.system_status = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.system_status), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"System status not available for {gateway_id}: {e}")
            
            # Try to get fan speeds for /fans endpoint (TEDAPI only)
            try:
                if hasattr(pw, 'get_fan_speeds'):
                    data.fan_speeds = await asyncio.wait_for(loop.run_in_executor(self._executor, pw.get_fan_speeds), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Fan speeds not available for {gateway_id}: {e}")
            
            # Try to get networks for /api/system/networks endpoint
            try:
                networks_result = await asyncio.wait_for(loop.run_in_executor(self._executor, lambda: pw.poll('/api/networks')), timeout=5.0)
                if networks_result and isinstance(networks_result, list):
                    data.networks = networks_result
                elif networks_result and isinstance(networks_result, str):
                    import json
                    try:
                        data.networks = json.loads(networks_result)
                    except json.JSONDecodeError:
                        pass
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Networks not available for {gateway_id}: {e}")
            
            # Try to get powerwalls for /api/powerwalls endpoint
            try:
                powerwalls_result = await asyncio.wait_for(loop.run_in_executor(self._executor, lambda: pw.poll('/api/powerwalls')), timeout=5.0)
                if powerwalls_result and isinstance(powerwalls_result, dict):
                    data.powerwalls = powerwalls_result
                elif powerwalls_result and isinstance(powerwalls_result, str):
                    import json
                    try:
                        data.powerwalls = json.loads(powerwalls_result)
                    except json.JSONDecodeError:
                        pass
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Powerwalls not available for {gateway_id}: {e}")
            
            # Update cache
            gateway = self.gateways[gateway_id]
            
            # Log connection success on first connection or reconnection
            was_offline = not gateway.online
            gateway.online = True
            gateway.last_error = None
            
            # Reset backoff on success
            previous_failures = self._consecutive_failures.get(gateway_id, 0)
            self._consecutive_failures[gateway_id] = 0
            self._next_poll_time[gateway_id] = 0  # Poll normally next cycle
            
            # Store successful data for graceful degradation
            self._last_successful_data[gateway_id] = data
            
            if was_offline:
                logger.info(f"Successfully connected to gateway {gateway_id} ({gateway.host})")
                if previous_failures > 0:
                    logger.debug(f"Exponential backoff reset for {gateway_id} after {previous_failures} failures")
            
            self.cache[gateway_id] = GatewayStatus(
                gateway=gateway,
                data=data,
                online=True,
                last_updated=data.timestamp
            )
            
        except Exception as e:
            gateway = self.gateways[gateway_id]
            
            # Increment failure count and calculate exponential backoff
            self._consecutive_failures[gateway_id] = self._consecutive_failures.get(gateway_id, 0) + 1
            failure_count = self._consecutive_failures[gateway_id]
            
            # Exponential backoff: 5s, 10s, 30s, 60s, 120s (max 2 minutes)
            backoff_intervals = [5, 10, 30, 60, 120]
            backoff_index = min(failure_count - 1, len(backoff_intervals) - 1)
            backoff_seconds = backoff_intervals[backoff_index]
            
            now = datetime.now().timestamp()
            self._next_poll_time[gateway_id] = now + backoff_seconds
            
            logger.debug(f"Exponential backoff for {gateway_id}: failure #{failure_count}, waiting {backoff_seconds}s before retry")
            
            # Log connection failures with full context
            if gateway.online:
                # Just went offline
                logger.error(f"Lost connection to gateway {gateway_id} ({gateway.host}): {e}")
                logger.info(f"Will retry gateway {gateway_id} in {backoff_seconds}s (failure #{failure_count})")
            else:
                # Still offline, attempting to reconnect
                logger.warning(f"Unable to connect to gateway {gateway_id} ({gateway.host}): {e} - backoff {backoff_seconds}s (failure #{failure_count})")
            
            gateway.online = False
            gateway.last_error = str(e)
            
            self.cache[gateway_id] = GatewayStatus(
                gateway=gateway,
                online=False,
                error=str(e),
                last_updated=now
            )
    
    def get_gateway(self, gateway_id: str) -> Optional[GatewayStatus]:
        """Get status for a specific gateway with graceful degradation support.
        
        Graceful Degradation (PW_GRACEFUL_DEGRADATION=yes):
            - If gateway is offline but went offline recently (within PW_CACHE_TTL seconds)
            - Return cached data with last_updated timestamp
            - After PW_CACHE_TTL expires, return status with data=None
        
        This allows UI to remain responsive during brief network outages while
        indicating stale data, and eventually showing "offline" after extended downtime.
        """
        from app.config import settings
        
        status = self.cache.get(gateway_id)
        if not status:
            return None
        
        # If gateway is online, return current status
        if status.online:
            return status
        
        # Gateway is offline - check graceful degradation settings
        if not settings.graceful_degradation:
            # Graceful degradation disabled - return offline status with no data
            logger.debug(f"Gateway {gateway_id} offline, graceful degradation disabled (PW_GRACEFUL_DEGRADATION=no)")
            return status
        
        # Check if we have cached data that's still fresh
        last_success_data = self._last_successful_data.get(gateway_id)
        if not last_success_data or not last_success_data.timestamp:
            # No cached data available
            logger.debug(f"Gateway {gateway_id} offline, no cached data available for graceful degradation")
            return status
        
        # Calculate age of cached data
        now = datetime.now().timestamp()
        data_age = now - last_success_data.timestamp
        
        # If cached data is within TTL, return it with offline status
        if data_age <= settings.cache_ttl:
            logger.debug(f"Graceful degradation active for {gateway_id}: serving stale data (age: {data_age:.0f}s / TTL: {settings.cache_ttl}s)")
            return GatewayStatus(
                gateway=status.gateway,
                data=last_success_data,  # Return last good data
                online=False,  # Still indicate gateway is offline
                last_updated=last_success_data.timestamp,
                error=status.error
            )
        
        # Cached data too old - return offline status with no data
        logger.debug(f"Graceful degradation expired for {gateway_id}: cached data too old (age: {data_age:.0f}s > TTL: {settings.cache_ttl}s), returning null")
        return status
    
    def get_all_gateways(self) -> Dict[str, GatewayStatus]:
        """Get status for all gateways with graceful degradation applied."""
        result = {}
        for gateway_id in self.gateways.keys():
            status = self.get_gateway(gateway_id)  # Use get_gateway for graceful degradation
            if status:
                result[gateway_id] = status
        return result
    
    def get_connection(self, gateway_id: str) -> Optional[pypowerwall.Powerwall]:
        """Get pypowerwall connection for a gateway."""
        return self.connections.get(gateway_id)
    
    async def call_api(self, gateway_id: str, method: str, *args, timeout: float = 5.0, fail_if_offline: bool = True, **kwargs) -> Optional[Any]:
        """Safely call a pypowerwall API method with timeout protection.
        
        This wraps blocking pypowerwall calls in the dedicated executor to prevent
        blocking the FastAPI event loop. All direct pypowerwall calls from API
        endpoints should use this method.
        
        Fast-Fail Behavior:
            By default, returns None immediately if gateway is offline (fail_if_offline=True).
            This prevents wasting time on connections that will likely fail.
            Set fail_if_offline=False for operations that should attempt connection
            regardless of cached status (e.g., reconnection attempts).
        
        Args:
            gateway_id: Gateway identifier
            method: Method name to call on pypowerwall object (e.g., 'grid_status', 'get_reserve')
            *args: Positional arguments to pass to method
            timeout: Timeout in seconds (default: 5.0)
            fail_if_offline: Return None immediately if gateway offline (default: True)
            **kwargs: Keyword arguments to pass to method
            
        Returns:
            Result of the pypowerwall method call, or None on error/timeout/offline
            
        Example:
            grid_status = await gateway_manager.call_api('default', 'grid_status', timeout=3.0)
            reserve = await gateway_manager.call_api('default', 'get_reserve')
        """
        # Fast-fail if gateway is offline
        if fail_if_offline:
            status = self.cache.get(gateway_id)
            if status and not status.online:
                logger.debug(f"[{gateway_id}] call_api({method}) fast-fail: gateway offline")
                return None
        
        pw = self.connections.get(gateway_id)
        if not pw:
            logger.warning(f"[{gateway_id}] call_api({method}): no connection object")
            return None
        
        try:
            method_func = getattr(pw, method)
            loop = asyncio.get_running_loop()
            logger.debug(f"[{gateway_id}] call_api({method}) starting (timeout={timeout}s)")
            result = await asyncio.wait_for(
                loop.run_in_executor(self._executor, lambda: method_func(*args, **kwargs)),
                timeout=timeout
            )
            logger.debug(f"[{gateway_id}] call_api({method}) completed successfully")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"[{gateway_id}] call_api({method}) timeout after {timeout}s")
            return None
        except AttributeError:
            logger.error(f"[{gateway_id}] call_api({method}): method not found")
            return None
        except Exception as e:
            logger.warning(f"[{gateway_id}] call_api({method}) error: {e}")
            return None
    
    async def call_tedapi(self, gateway_id: str, method: str, *args, timeout: float = 5.0, fail_if_offline: bool = True, **kwargs) -> Optional[Any]:
        """Safely call a TEDAPI method with timeout protection.
        
        Args:
            gateway_id: Gateway identifier
            method: Method name to call on tedapi object (e.g., 'get_config', 'get_status')
            timeout: Timeout in seconds (default: 5.0)
            fail_if_offline: Return None immediately if gateway offline (default: True)
            
        Returns:
            Result of the TEDAPI method call, or None if TEDAPI not available/offline
        """
        # Fast-fail if gateway is offline
        if fail_if_offline:
            status = self.cache.get(gateway_id)
            if status and not status.online:
                logger.debug(f"[{gateway_id}] call_tedapi({method}) fast-fail: gateway offline")
                return None
        
        pw = self.connections.get(gateway_id)
        if not pw or not hasattr(pw, 'tedapi') or not pw.tedapi:
            logger.debug(f"[{gateway_id}] call_tedapi({method}): TEDAPI not available")
            return None
        
        try:
            method_func = getattr(pw.tedapi, method)
            loop = asyncio.get_running_loop()
            logger.debug(f"[{gateway_id}] call_tedapi({method}) starting (timeout={timeout}s)")
            result = await asyncio.wait_for(
                loop.run_in_executor(self._executor, lambda: method_func(*args, **kwargs)),
                timeout=timeout
            )
            logger.debug(f"[{gateway_id}] call_tedapi({method}) completed successfully")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"[{gateway_id}] call_tedapi({method}) timeout after {timeout}s")
            return None
        except AttributeError:
            logger.error(f"[{gateway_id}] call_tedapi({method}): method not found")
            return None
        except Exception as e:
            logger.warning(f"[{gateway_id}] call_tedapi({method}) error: {e}")
            return None
    
    def get_aggregate_data(self) -> AggregateData:
        """Get aggregated data from all gateways.
        
        SMART AGGREGATION NOTES:
        This is a first-pass implementation that will need tuning as we get real-world
        multi-gateway deployments. Current approach:
        
        - Battery %: Simple average (TODO: weight by capacity when available)
        - Power flows: Simple sum (works for most cases)
        - Grid power: Calculated as site - solar
        
        Future considerations:
        - Different aggregation strategies per metric type
        - Weighted averages based on system capacity
        - Handling mixed local/cloud gateways
        - Time synchronization across gateways
        - Outlier detection and handling
        """
        aggregate = AggregateData(
            timestamp=datetime.now().timestamp()
        )
        
        for gateway_id, status in self.cache.items():
            aggregate.num_gateways += 1
            
            if not status.online or not status.data:
                continue
            
            aggregate.num_online += 1
            data = status.data
            
            # Aggregate battery percentage
            # TODO: Weight by capacity when battery capacity info is available
            if data.soe is not None:
                aggregate.total_battery_percent += data.soe
            
            # Aggregate power flows (simple sum - works well for separate systems)
            if data.aggregates:
                site = data.aggregates.get("site", {})
                battery = data.aggregates.get("battery", {})
                load = data.aggregates.get("load", {})
                solar = data.aggregates.get("solar", {})
                
                site_power = site.get("instant_power", 0)
                battery_power = battery.get("instant_power", 0)
                load_power = load.get("instant_power", 0)
                solar_power = solar.get("instant_power", 0)
                
                logger.debug(f"Gateway {gateway_id} power: site={site_power}, battery={battery_power}, load={load_power}, solar={solar_power}")
                
                aggregate.total_site_power += site_power
                aggregate.total_battery_power += battery_power
                aggregate.total_load_power += load_power
                aggregate.total_solar_power += solar_power
            
            aggregate.gateways[gateway_id] = status
        
        # Calculate average battery percentage (simple average for now)
        if aggregate.num_online > 0:
            aggregate.total_battery_percent /= aggregate.num_online
        
        # Grid power is the site power (positive = importing, negative = exporting)
        # The "site" meter in aggregates measures grid interaction directly
        aggregate.total_grid_power = aggregate.total_site_power
        
        return aggregate


# Global gateway manager instance
gateway_manager = GatewayManager()
