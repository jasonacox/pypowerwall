# This file contains two examples of how to use the `route` command from Linux in Python.
# 1. manage_ip_route_pyroute: Recommended approach. Less error-prone due to use of encapsulated pyroute2 framework.
# 2. manage_ip_route_subprocess: Simpler, straightforward approach that utilizes Python subprocces.

import socket
import subprocess
from enum import Enum, auto
from typing import Optional

from pyroute2 import IPRoute, NetlinkError


class Tense(Enum):
    """ String/tense variation on the route operations.
    """    
    BASE = auto()
    PRESENT = auto()
    PAST = auto()


class RouteOperation(Enum):
    """Whether to add or remove a route.
    """
    ADD = {
        Tense.BASE: "add",
        Tense.PRESENT: "adding",
        Tense.PAST: "added"   
    }
    DELETE = {
        Tense.BASE: "del",
        Tense.PRESENT: "deleting",
        Tense.PAST: "deleted"
    }

    def get_action(self, tense: Tense) -> str:
        """Retrieve string representation appropriate to each RouteOperation tense.

        Args:
            tense (Tense): Tense for each operation.

        Returns:
            str: String representation of operation tense.
        """        
        return self.value.get(tense, "Tense Missing")


def manage_ip_route_pyroute(operation: RouteOperation, destination: str, gateway: str, interface: Optional[str] = None, interactive: bool = False) -> None:
    """ Manages an IP route using pyroute2's IPRoute, utilizing onlink to ensure the route works.
        For instance, if you want to map all requests that go from a CIDR range of 192.168.91.0/24 => 192.168.1.250,
        use this to add/delete such a route. This can also be configured on your router.
        
        The calling process must be run as root (sudo).

    Args:
        operation (RouteOperation): RouteOperation.ADD or RouteOperation.DELETE, corresponding to desired operation for network route.
        destination (str): The network or IP address in IPv4 CIDR notation (e.g., "192.168.1.0/24")
        gateway (str): The IP address of the Tesla Gateway/Powerwall (e.g., "192.168.1.250")
        interface (str, optional): The optional network interface (e.g., "eth0"). If not provided, the route is managed without specifying an interface. Defaults to None.
        interactive (bool, optional): Whether messages should be printed. Defaults to False.

    Example usage:
        manage_ip_route_pyroute(RouteOperation.ADD, "192.168.1.0/24", "192.168.1.1")
        manage_ip_route_pyroute(RouteOperation.DELETE, "192.168.1.0/24", "192.168.1.1", "eth0")
    """

    route_params = {
        "family": socket.AF_INET6 if ":" in destination else socket.AF_INET,
        "dst": destination,
        "gateway": gateway
    }

    if operation == RouteOperation.ADD:
        route_params["flags"] = ["onlink"]

    with IPRoute() as ip:
        try:
            # Lookup interface index if interface is specified
            idxs = ip.link_lookup(ifname=interface) if interface else None
            if not idxs:
                print(f"Interface '{interface}' not found.")
                return
            route_params["oif"] = idxs[0]
            # Perform the route operation
            ip.route(operation.get_action(Tense.BASE), **route_params)
            if interactive:
                print(f"Route {operation.get_action(Tense.PAST)}: {destination} via {gateway}" + (f" dev {interface}" if interface else "") + (f" {','.join(route_params['flags'])}" if 'flags' in route_params else ""))
        except NetlinkError as e:
            print(f"Network specific error occurred {operation.get_action(Tense.PRESENT)} route: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")


def manage_ip_route_subprocess(operation: RouteOperation, destination: str, gateway: str, interface: Optional[str] = None, interactive: bool = False) -> None:
    """ Manages an IP route using the 'ip' command, utilizing onlink to ensure the route works.
        For instance, if you want to map all requests that go from a CIDR range of 192.168.91.0/24 => 192.168.1.250,
        use this to add/delete such a route. This can also be configured on your router.

    Args:
        operation (RouteOperation): RouteOperation.ADD or RouteOperation.DELETE, corresponding to desired operation for network route.
        destination (str): The network or IP address in IPv4 CIDR notation (e.g., "192.168.1.0/24")
        gateway (str): The IP address of the Tesla Gateway/Powerwall (e.g., "192.168.1.250")
        interface (str, optional): The optional network interface (e.g., "eth0"). If not provided, the route is managed without specifying an interface. Defaults to None.
        interactive (bool, optional): Whether messages should be printed. Defaults to False.

    Example usage:
        manage_ip_route_subprocess(RouteOperation.ADD, "192.168.1.0/24", "192.168.1.1")
        manage_ip_route_subprocess(RouteOperation.DELETE, "192.168.1.0/24", "192.168.1.1", "eth0")
    """
    command = ["sudo", "ip", "route", operation.get_action(Tense.BASE), destination, "via", gateway]

    if interface:
        command.extend(["dev", interface])

    if operation == RouteOperation.ADD:
        command.append("onlink")

    try:
        subprocess.run(command, check=True)
        if interactive:
            print(f"Route {operation.get_action(Tense.PAST)}: {destination} via {gateway}" + (f" dev {interface}" if interface else "") + (f" onlink" if 'onlink' in command else ""))
    except subprocess.CalledProcessError as e:
        print(f"Error adding route: {e}")
