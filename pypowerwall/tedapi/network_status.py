# pyPowerwall - TEDAPI gateway networking status model
# -*- coding: utf-8 -*-
"""
 Tesla TEDAPI Gateway Networking Status

 Normalized model for the gateway's networking status: one entry per gateway
 network interface (Wi-Fi, Ethernet, cellular) with its enabled / active-route
 flags, link / internet / Tesla connectivity and signal strength.

 The data comes from the read-only ``common.get_networking_status_request``
 TEDAPI message (see ``protobuf/V2024_06/tedapi_combined.proto``). The request
 changes nothing on the gateway.

 Validated on a Powerwall 3, firmware 26.34.3, over the signed v1r LAN transport
 and Gateway Wi-Fi basic auth (2026-11-14), and on a Powerwall 2, firmware
 26.42.0, over Gateway Wi-Fi basic auth. Observed on the Powerwall 3:
    * all three interfaces are reported, including ones that are not in use;
    * signal strength arrives as a percentage; the dBm ``rssi`` value and the
      ``snr`` wrapper are left unset;
    * ``device_state`` / ``device_state_reason`` are only populated for Wi-Fi
      (Ethernet and cellular report the INVALID zero value), and the Wi-Fi
      ``security_type`` is left at its INVALID zero value.
 Over signed v1r the request goes out in the signed-command envelope the
 other v1r commands use; a Powerwall 2 did not route the local installer
 envelope over v1r, and the signed-command envelope is not yet confirmed there.
 Not validated on the bearer transport or on Powerwall+.

 Privacy:
    The gateway's reply also carries the Wi-Fi password. The protobuf definition
    does not model that field, so it is never parsed, logged or returned. The
    SSID, MAC addresses and IPv4 settings are only returned when the caller asks
    for ``details=True`` and are kept out of the model's ``repr`` (and therefore
    out of debug logs).

 Classes:
    NetworkInterfaceStatus - Status of one gateway network interface
    NetworkStatus - Status of all gateway network interfaces

 Functions:
    enum_name(enum_type, value) - Protobuf enum value name, or "UNKNOWN (<n>)"
    format_ipv4(value) - Dotted-quad string for a fixed32 IPv4 value
    format_mac(value) - Colon-separated string for a MAC address

 Author: Jason A. Cox
 For more information see https://github.com/jasonacox/pypowerwall
"""
from dataclasses import dataclass, field
from ipaddress import IPv4Address
from typing import Any, Dict, List, Optional

from .protobuf.V2024_06 import tedapi_combined_pb2 as combined_pb2

# Interface keys, in the order they are reported. These are the proto field
# names of CommonAPIGetNetworkingStatusResponse and the keys of the output dict.
INTERFACES = ('wifi', 'eth', 'gsm')


def enum_name(enum_type, value: int) -> str:
    """Return the protobuf enum value name for ``value`` (e.g.
    ``NETWORK_DEVICE_STATE_READY``), or ``"UNKNOWN (<value>)"`` for a value this
    schema does not define, so newer firmware can't break the output."""
    try:
        return enum_type.Name(value)
    except ValueError:
        return f'UNKNOWN ({value})'


def format_ipv4(value: int) -> Optional[str]:
    """Render a fixed32 IPv4 value as a dotted quad, or None when unset (0).

    The gateway packs the address with the first octet in the most significant
    byte (192.168.1.2 == 0xC0A80102) -- confirmed on PW3 firmware 26.34.3."""
    if not value:
        return None
    return str(IPv4Address(value))


def format_mac(value: bytes) -> Optional[str]:
    """Render MAC address bytes as ``aa:bb:cc:dd:ee:ff``, or None when the
    interface reports none (the cellular interface has no MAC)."""
    if not value:
        return None
    return ':'.join(f'{octet:02x}' for octet in value)


@dataclass
class NetworkInterfaceStatus:
    """Status of one gateway network interface.

    ``signal_strength_percent``, ``rssi`` and ``snr`` are None when the gateway
    does not report them. The identifying fields (MAC address, IPv4 settings)
    are excluded from ``repr`` so they do not end up in debug logs.
    """
    enabled: bool = False
    active_route: bool = False                     # carries the default route
    connected_physical: bool = False               # link / association is up
    connected_internet: bool = False
    connected_tesla: bool = False                  # can reach Tesla's servers
    signal_strength_percent: Optional[int] = None  # 0-100
    rssi: Optional[int] = None                     # dBm
    snr: Optional[int] = None                      # dB
    device_state: int = 0                          # NetworkDeviceState
    device_state_reason: int = 0                   # NetworkDeviceStateReason
    mac_address: Optional[str] = field(default=None, repr=False)
    ipv4: Optional[Dict[str, Any]] = field(default=None, repr=False)

    @classmethod
    def from_proto(cls, interface) -> 'NetworkInterfaceStatus':
        """Build from a parsed ``NetworkInterface`` protobuf message."""
        status = interface.connectivity_status
        rssi = status.rssi
        ipv4 = None
        if interface.HasField('ipv4_config'):
            config = interface.ipv4_config
            ipv4 = {
                'dhcp_enabled': config.dhcp_enabled,
                'address': format_ipv4(config.address),
                'subnet_mask': format_ipv4(config.subnet_mask),
                'gateway': format_ipv4(config.gateway),
                'dns': [format_ipv4(dns) for dns in config.dns if dns],
            }
        return cls(
            enabled=interface.enabled,
            active_route=interface.active_route,
            connected_physical=status.connected_physical,
            connected_internet=status.connected_internet,
            connected_tesla=status.connected_tesla,
            # Wrapper type: presence is explicit, so a real 0 % is kept.
            signal_strength_percent=(rssi.signal_strength_percent.value
                                     if rssi.HasField('signal_strength_percent') else None),
            # Plain sint32: proto3 can't tell "unset" from 0, and 0 dBm is not
            # a reading a radio reports, so 0 means "not reported" (PW3
            # firmware 26.34.3 leaves it unset and sends only the percentage).
            rssi=rssi.value or None,
            snr=status.snr.value if status.HasField('snr') else None,
            device_state=interface.device_state,
            device_state_reason=interface.device_state_reason,
            mac_address=format_mac(interface.mac_address),
            ipv4=ipv4,
        )

    @property
    def device_state_name(self) -> str:
        """The NetworkDeviceState name for :attr:`device_state`."""
        return enum_name(combined_pb2.NetworkDeviceState, self.device_state)

    @property
    def device_state_reason_name(self) -> str:
        """The NetworkDeviceStateReason name for :attr:`device_state_reason`."""
        return enum_name(combined_pb2.NetworkDeviceStateReason, self.device_state_reason)

    def to_dict(self, details: bool = False) -> Dict[str, Any]:
        """Render the JSON-safe payload for this interface. ``details`` adds the
        identifying fields (``mac_address`` and ``ipv4``)."""
        data: Dict[str, Any] = {
            'enabled': self.enabled,
            'active_route': self.active_route,
            'connected_physical': self.connected_physical,
            'connected_internet': self.connected_internet,
            'connected_tesla': self.connected_tesla,
            'signal_strength_percent': self.signal_strength_percent,
            'rssi': self.rssi,
            'snr': self.snr,
            'device_state': self.device_state_name,
            'device_state_reason': self.device_state_reason_name,
        }
        if details:
            data['mac_address'] = self.mac_address
            # Copy, so a caller mutating the result can't alter the cached model.
            data['ipv4'] = None if self.ipv4 is None else {**self.ipv4, 'dns': list(self.ipv4['dns'])}
        return data


@dataclass
class NetworkStatus:
    """Gateway networking status: one :class:`NetworkInterfaceStatus` per
    interface (None for an interface the gateway left out of its reply), plus
    the configured Wi-Fi network (SSID and security type -- never the password).
    """
    wifi: Optional[NetworkInterfaceStatus] = None
    eth: Optional[NetworkInterfaceStatus] = None
    gsm: Optional[NetworkInterfaceStatus] = None
    wifi_ssid: Optional[str] = field(default=None, repr=False)
    wifi_security_type: Optional[int] = None       # WifiNetworkSecurityType

    @classmethod
    def from_proto(cls, response) -> 'NetworkStatus':
        """Build from a parsed ``CommonAPIGetNetworkingStatusResponse``."""
        interfaces = {
            name: (NetworkInterfaceStatus.from_proto(getattr(response, name))
                   if response.HasField(name) else None)
            for name in INTERFACES
        }
        has_config = response.HasField('wifi_config')
        return cls(
            wifi_ssid=(response.wifi_config.ssid or None) if has_config else None,
            wifi_security_type=response.wifi_config.security_type if has_config else None,
            **interfaces,
        )

    @property
    def interfaces(self) -> List[str]:
        """Names of the interfaces the gateway reported."""
        return [name for name in INTERFACES if getattr(self, name) is not None]

    def to_dict(self, details: bool = False) -> Dict[str, Any]:
        """Render the ``get_network_status()`` payload: a dict keyed by interface
        (``wifi``, ``eth``, ``gsm``). ``details`` adds each interface's MAC
        address and IPv4 settings, and a ``wifi_config`` entry with the SSID and
        security type of the configured Wi-Fi network."""
        data: Dict[str, Any] = {}
        for name in INTERFACES:
            interface = getattr(self, name)
            data[name] = None if interface is None else interface.to_dict(details=details)
        if details:
            data['wifi_config'] = None if self.wifi_security_type is None else {
                'ssid': self.wifi_ssid,
                'security_type': enum_name(combined_pb2.WifiNetworkSecurityType,
                                           self.wifi_security_type),
            }
        return data
