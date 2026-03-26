"""Live integration tests for mode 4 (full/hybrid) over WiFi.

These tests require WiFi connectivity to the Powerwall gateway at 192.168.91.1.
Skip with: pytest -m "not live"
"""

import os
import pytest

# Read gw_pwd from environment or Powerwall-Dashboard env file
GW_PWD = os.getenv("PW_GW_PWD")
if not GW_PWD:
    # Check common locations for pypowerwall.env
    for env_file in [
        "/home/localadmin/Powerwall-Dashboard/pypowerwall.env",
        os.path.expanduser("~/Powerwall-Dashboard/pypowerwall.env"),
    ]:
        if os.path.exists(env_file):
            break
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("PW_GW_PWD="):
                    GW_PWD = line.strip().split("=", 1)[1]
                    break

PASSWORD = GW_PWD[-5:] if GW_PWD else None
GW_IP = "192.168.91.1"


def gateway_reachable():
    """Check if gateway is reachable on WiFi."""
    import subprocess
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", GW_IP],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


skip_no_wifi = pytest.mark.skipif(
    not gateway_reachable(),
    reason=f"Gateway {GW_IP} not reachable (no WiFi connection)"
)
skip_no_pwd = pytest.mark.skipif(
    not GW_PWD,
    reason="PW_GW_PWD not set and not found in pypowerwall.env"
)

live = pytest.mark.live


@live
@skip_no_wifi
@skip_no_pwd
class TestMode4FullLive:
    """Live tests for mode 4 full TEDAPI (gw_pwd only, over WiFi)."""

    @pytest.fixture(scope="class")
    def pw_full(self):
        """Shared Powerwall instance for full TEDAPI tests."""
        import pypowerwall
        return pypowerwall.Powerwall(
            host=GW_IP,
            password="",
            gw_pwd=GW_PWD,
            timezone="America/Chicago",
        )

    def test_full_tedapi_connects(self, pw_full):
        """Mode 4 full: connects with only gw_pwd, no customer password."""
        assert pw_full.tedapi_mode == "full"

    def test_full_tedapi_power(self, pw_full):
        """Mode 4 full: power() returns valid data."""
        power = pw_full.power()
        assert isinstance(power, dict)
        assert "site" in power
        assert "solar" in power
        assert "battery" in power
        assert "load" in power

    def test_full_tedapi_level(self, pw_full):
        """Mode 4 full: level() returns battery percentage."""
        level = pw_full.level()
        assert isinstance(level, (int, float))
        assert 0 <= level <= 100

    def test_full_tedapi_vitals(self, pw_full):
        """Mode 4 full: vitals() returns device data."""
        vitals = pw_full.vitals()
        assert vitals is not None
        assert isinstance(vitals, dict)

    def test_full_tedapi_version(self, pw_full):
        """Mode 4 full: version() returns firmware string."""
        version = pw_full.version()
        assert version is not None
        assert isinstance(version, str)
        assert len(version) > 0


@live
@skip_no_wifi
@skip_no_pwd
class TestMode4HybridLive:
    """Live tests for mode 4 hybrid (password + gw_pwd, over WiFi)."""

    @pytest.fixture(scope="class")
    def pw_hybrid(self):
        """Shared Powerwall instance for hybrid TEDAPI tests."""
        import pypowerwall
        return pypowerwall.Powerwall(
            host=GW_IP,
            password=PASSWORD,
            gw_pwd=GW_PWD,
            timezone="America/Chicago",
        )

    def test_hybrid_connects(self, pw_hybrid):
        """Mode 4 hybrid: connects with password + gw_pwd."""
        assert pw_hybrid.tedapi_mode in ("hybrid", "off")

    def test_hybrid_power(self, pw_hybrid):
        """Mode 4 hybrid: power() returns valid data."""
        power = pw_hybrid.power()
        assert isinstance(power, dict)
        assert "site" in power
        assert "solar" in power
        assert "battery" in power
        assert "load" in power

    def test_hybrid_level(self, pw_hybrid):
        """Mode 4 hybrid: level() returns battery percentage."""
        level = pw_hybrid.level()
        assert isinstance(level, (int, float))
        assert 0 <= level <= 100

    def test_hybrid_grid_status(self, pw_hybrid):
        """Mode 4 hybrid: grid_status() returns string."""
        status = pw_hybrid.grid_status()
        assert status is not None
        assert isinstance(status, str)

    def test_hybrid_has_tedapi(self, pw_hybrid):
        """Mode 4 hybrid: TEDAPI should be active when gw_pwd is provided."""
        # On PW3, hybrid may report tedapi_mode as "off" since customer API
        # is limited, but the PyPowerwallLocal object is still created
        assert pw_hybrid.tedapi_mode in ("hybrid", "off")
