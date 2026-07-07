# Back-compat shim. This protobuf module moved to
# pypowerwall.tedapi.protobuf.V2024_06.tedapi_pb2 when the V2024_06/V2026_06
# query sets were split out. Re-exported here so deep imports that predate the
# move (e.g. `import pypowerwall.tedapi.tedapi_pb2`) keep resolving for external
# scripts. New code should import from the protobuf.V2024_06 path directly.
from .protobuf.V2024_06.tedapi_pb2 import *  # noqa: F401,F403
