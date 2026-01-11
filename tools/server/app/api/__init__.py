"""API router initialization."""
from . import legacy, gateways, aggregates, websockets

__all__ = ["legacy", "gateways", "aggregates", "websockets"]
