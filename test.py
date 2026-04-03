import socket
import psutil
from pyroute2 import IPRoute

def get_local_ip() -> str:
    try:
        with IPRoute() as ip:
            iface_index = next(
                (iface_index
                 for route in ip.get_routes(family=socket.AF_INET)
                 if route.get('dst_len', 0) == 0
                 for key, iface_index in route.get('attrs', [])
                 if key == 'RTA_OIF'),
                None
            )
            if iface_index is None:
                return "Default network interface not found."

            iface_name = next(
                (name for key, name in ip.link('get', index=iface_index)[0].get('attrs', [])
                 if key == 'IFLA_IFNAME'),
                None
            )
        if not iface_name:
            return "Interface name not found."

        return next(
            (addr.address for addr in psutil.net_if_addrs().get(iface_name, [])
             if addr.family == socket.AF_INET),
            f"No IPv4 address found for interface '{iface_name}'."
        )
    except Exception as e:
        return f"Error retrieving local IP: {e}"


print(get_local_ip())
