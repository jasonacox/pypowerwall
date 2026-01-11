"""Gateway Manager - Manages connections to multiple Powerwall gateways."""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime

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
        self._poll_interval = 5  # seconds
    
    async def initialize(self, gateway_configs: List[GatewayConfig]):
        """Initialize gateway connections."""
        for config in gateway_configs:
            try:
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
                
                # Create pypowerwall connection
                if config.cloud_mode and config.email:
                    # Cloud mode - requires email and auth token files
                    pw = pypowerwall.Powerwall(
                        email=config.email,
                        authpath=config.authpath,  # Path to .pypowerwall.auth/.site files
                        cloudmode=True,
                        fleetapi=config.fleetapi,
                        timezone=config.timezone
                    )
                elif config.host and config.gw_pwd:
                    # TEDAPI mode - local gateway access via 192.168.91.1
                    pw = pypowerwall.Powerwall(
                        host=config.host,
                        gw_pwd=config.gw_pwd,  # Gateway Wi-Fi password for TEDAPI
                        email=config.email,
                        authpath=config.authpath,  # Optional: for cloud control operations
                        timezone=config.timezone,
                        timeout=3  # Short timeout to prevent blocking
                    )
                else:
                    logger.error(f"Invalid configuration for gateway {config.id}: need host+gw_pwd or email+authpath")
                    continue
                
                self.gateways[config.id] = gateway
                self.connections[config.id] = pw
                self.cache[config.id] = GatewayStatus(
                    gateway=gateway,
                    online=False
                )
                
                logger.info(f"Initialized gateway: {config.id} ({config.name})")
            except Exception as e:
                logger.error(f"Failed to initialize gateway {config.id}: {e}")
        
        # Start polling task
        if self.gateways:
            self._poll_task = asyncio.create_task(self._poll_gateways())
    
    async def shutdown(self):
        """Shutdown gateway manager and cleanup resources."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
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
    
    async def _poll_gateway(self, gateway_id: str):
        """Poll a single gateway for data."""
        try:
            pw = self.connections.get(gateway_id)
            if not pw:
                logger.warning(f"No connection object for gateway {gateway_id}")
                return
            
            # Run blocking pypowerwall calls in executor with timeout protection
            loop = asyncio.get_event_loop()
            
            # Fetch core data - aggregates is required, vitals/strings are optional
            # Use asyncio.wait_for to timeout if pypowerwall hangs
            try:
                aggregates = await asyncio.wait_for(
                    loop.run_in_executor(None, pw.poll, '/api/meters/aggregates'),
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
                    loop.run_in_executor(None, pw.vitals),
                    timeout=10.0
                )
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Vitals not available for {gateway_id}: {e}")
            
            try:
                data.strings = await asyncio.wait_for(
                    loop.run_in_executor(None, pw.strings),
                    timeout=10.0
                )
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Strings not available for {gateway_id}: {e}")
            
            # Try to get additional data
            try:
                data.soe = await asyncio.wait_for(loop.run_in_executor(None, pw.level), timeout=5.0)
                data.freq = await asyncio.wait_for(loop.run_in_executor(None, pw.freq), timeout=5.0)
                data.status = await asyncio.wait_for(loop.run_in_executor(None, pw.status), timeout=5.0)
                data.version = await asyncio.wait_for(loop.run_in_executor(None, pw.version), timeout=5.0)
                logger.debug(f"Gateway {gateway_id} aggregates: {data.aggregates}")
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Failed to fetch additional data for {gateway_id}: {e}")
            
            # Update cache
            gateway = self.gateways[gateway_id]
            
            # Log connection success on first connection or reconnection
            was_offline = not gateway.online
            gateway.online = True
            gateway.last_error = None
            
            if was_offline:
                logger.info(f"Successfully connected to gateway {gateway_id} ({gateway.host})")
            
            self.cache[gateway_id] = GatewayStatus(
                gateway=gateway,
                data=data,
                online=True,
                last_updated=data.timestamp
            )
            
        except Exception as e:
            gateway = self.gateways[gateway_id]
            
            # Log connection failures with full context
            if gateway.online:
                # Just went offline
                logger.error(f"Lost connection to gateway {gateway_id} ({gateway.host}): {e}")
            else:
                # Still offline, attempting to reconnect
                logger.warning(f"Unable to connect to gateway {gateway_id} ({gateway.host}): {e} - will retry in {self._poll_interval}s")
            
            gateway.online = False
            gateway.last_error = str(e)
            
            self.cache[gateway_id] = GatewayStatus(
                gateway=gateway,
                online=False,
                error=str(e),
                last_updated=datetime.now().timestamp()
            )
    
    def get_gateway(self, gateway_id: str) -> Optional[GatewayStatus]:
        """Get status for a specific gateway."""
        return self.cache.get(gateway_id)
    
    def get_all_gateways(self) -> Dict[str, GatewayStatus]:
        """Get status for all gateways."""
        return self.cache.copy()
    
    def get_connection(self, gateway_id: str) -> Optional[pypowerwall.Powerwall]:
        """Get pypowerwall connection for a gateway."""
        return self.connections.get(gateway_id)
    
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
        
        # Calculate grid power (site - solar)
        # This represents net import/export from grid
        aggregate.total_grid_power = aggregate.total_site_power - aggregate.total_solar_power
        
        return aggregate


# Global gateway manager instance
gateway_manager = GatewayManager()
