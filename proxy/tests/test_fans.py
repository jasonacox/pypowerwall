"""Tests for /fans and /fans/pw: Powerwall 2/+ PVAC fans (unchanged shapes) and
Powerwall 3 inverter fans (TEPINV blocks, two fans per inverter).

Hardware basis (2026-09-26, two PW3s on firmware 26.18.1): each PW3 inverter
reports PCH_FanSpeed_A/B (measured RPM) and PCH_FanDuty_A/B (duty cycle, %);
there is no target-RPM signal.
"""
import json
from http import HTTPStatus
from unittest.mock import patch

from proxy.tests.test_csv_endpoints import BaseDoGetTest, common_patches

PW2_FANS = {
    "PVAC--1538000-45-C--TG2": {"PVAC_Fan_Speed_Actual_RPM": 1175, "PVAC_Fan_Speed_Target_RPM": 1200},
    "PVAC--1538000-45-C--TG1": {"PVAC_Fan_Speed_Actual_RPM": 1180, "PVAC_Fan_Speed_Target_RPM": 1200},
}

# get_fan_speeds() order: leader first (get_pw3_vitals order), not sorted - the
# follower's serial sorts before the leader's here, as on the validation hardware
PW3_FANS = {
    "TEPINV--1707000-11-M--TG1253370033TB": {
        "PCH_FanSpeed_A": 1395, "PCH_FanSpeed_B": 1397, "PCH_FanDuty_A": 19.1, "PCH_FanDuty_B": 19.1},
    "TEPINV--1707000-11-M--TG125337002LNY": {
        "PCH_FanSpeed_A": 1000, "PCH_FanSpeed_B": 991, "PCH_FanDuty_A": 5.1, "PCH_FanDuty_B": 6.6},
}


class FanTestBase(BaseDoGetTest):

    def get_fans(self, path, fan_speeds, mock_safe_pw_call, mock_pw):
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = path
            mock_safe_pw_call.side_effect = lambda func, *a, **k: (
                fan_speeds if func == mock_pw.tedapi.get_fan_speeds else None)
            self.handler.do_GET()
            self.handler.send_response.assert_called_with(HTTPStatus.OK)
            return json.loads(self.get_written_text())


class TestFansPw(FanTestBase):
    """/fans/pw simplified keys"""

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_pw2_unchanged(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        """PW2: FANn_actual/FANn_target per PVAC, numbered in sorted key order, no duty key"""
        data = self.get_fans("/fans/pw", dict(PW2_FANS), mock_safe_pw_call, mock_pw)
        self.assertEqual(list(data.items()), [
            ("FAN1_actual", 1180), ("FAN1_target", 1200),
            ("FAN2_actual", 1175), ("FAN2_target", 1200),
        ])

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_pw3_two_fans_per_inverter_leader_first(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        data = self.get_fans("/fans/pw", dict(PW3_FANS), mock_safe_pw_call, mock_pw)
        self.assertEqual(data, {
            "FAN1_actual": 1395, "FAN1_target": None, "FAN1_duty": 19.1,
            "FAN2_actual": 1397, "FAN2_target": None, "FAN2_duty": 19.1,
            "FAN3_actual": 1000, "FAN3_target": None, "FAN3_duty": 5.1,
            "FAN4_actual": 991, "FAN4_target": None, "FAN4_duty": 6.6,
        })
        self.assertEqual(list(data)[:3], ["FAN1_actual", "FAN1_target", "FAN1_duty"])

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_pw3_missing_fan_keeps_numbering(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        """A fan signal the gateway didn't deliver stays in its FANn slot as null"""
        fans = {"TEPINV--1707000-11-M--TG1": {
            "PCH_FanSpeed_A": None, "PCH_FanSpeed_B": 1397, "PCH_FanDuty_A": None, "PCH_FanDuty_B": 19.1}}
        data = self.get_fans("/fans/pw", fans, mock_safe_pw_call, mock_pw)
        self.assertEqual(data, {
            "FAN1_actual": None, "FAN1_target": None, "FAN1_duty": None,
            "FAN2_actual": 1397, "FAN2_target": None, "FAN2_duty": 19.1,
        })

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_pw3_numbered_after_pvac_fans(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        fans = {**PW3_FANS, **PW2_FANS}
        data = self.get_fans("/fans/pw", fans, mock_safe_pw_call, mock_pw)
        self.assertEqual((data["FAN1_actual"], data["FAN2_actual"]), (1180, 1175))
        self.assertEqual((data["FAN3_actual"], data["FAN6_actual"]), (1395, 991))
        self.assertNotIn("FAN1_duty", data)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_no_fans_is_empty_object(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        self.assertEqual(self.get_fans("/fans/pw", {}, mock_safe_pw_call, mock_pw), {})

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_failure_is_empty_object(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        self.assertEqual(self.get_fans("/fans/pw", None, mock_safe_pw_call, mock_pw), {})


class TestFansRaw(FanTestBase):
    """/fans raw passthrough"""

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_pw3_raw_passthrough(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        data = self.get_fans("/fans", dict(PW3_FANS), mock_safe_pw_call, mock_pw)
        self.assertEqual(data, PW3_FANS)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_pw2_raw_passthrough(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        self.assertEqual(self.get_fans("/fans", dict(PW2_FANS), mock_safe_pw_call, mock_pw), PW2_FANS)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_failure_is_null(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        """Documented quirk (DESIGN.md): /fans is null on failure, /fans/pw is {}"""
        self.assertIsNone(self.get_fans("/fans", None, mock_safe_pw_call, mock_pw))
