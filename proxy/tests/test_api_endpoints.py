import json
import unittest
from http import HTTPStatus
from io import BytesIO
from unittest.mock import Mock, patch

from proxy.server import Handler
from proxy.tests.test_csv_endpoints import BaseDoGetTest, common_patches


class TestFreqEndpoint(BaseDoGetTest):
    """Test cases for /freq endpoint"""

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_freq_basic_output(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        """Test /freq endpoint basic output with battery_blocks and vitals"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/freq"
            
            # Mock system_status call with battery_blocks
            def safe_pw_call_side_effect(*args, **kwargs):
                if args[0] == mock_pw.system_status:
                    return {
                        'battery_blocks': [
                            {
                                'PackagePartNumber': 'PW123',
                                'PackageSerialNumber': 'SN001',
                                'f_out': 60.0,
                                'p_out': 1000,
                                'q_out': 50,
                                'v_out': 240.0,
                                'i_out': 4.2
                            }
                        ]
                    }
                elif args[0] == mock_pw.vitals:
                    return {
                        'TEPINV1': {
                            'PINV_Fout': 59.98,
                            'PINV_VSplit1': 120.5,
                            'PINV_VSplit2': 119.8
                        }
                    }
                elif args[0] == mock_pw.grid_status:
                    return 1  # UP
                return None
            
            mock_safe_pw_call.side_effect = safe_pw_call_side_effect
            
            self.handler.do_GET()
            
            self.handler.send_response.assert_called_with(HTTPStatus.OK)
            result = self.get_written_text()
            data = json.loads(result)
            
            # Verify battery_blocks data
            self.assertEqual(data['PW1_PackagePartNumber'], 'PW123')
            self.assertEqual(data['PW1_f_out'], 60.0)
            self.assertEqual(data['PW1_v_out'], 240.0)
            
            # Verify vitals data
            self.assertEqual(data['PW1_name'], 'TEPINV1')
            self.assertEqual(data['PW1_PINV_Fout'], 59.98)
            self.assertEqual(data['PW1_PINV_VSplit1'], 120.5)
            
            # Verify grid status
            self.assertEqual(data['grid_status'], 1)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_freq_with_meter_data(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        """Test /freq endpoint with TESYNC/TEMSA meter data"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/freq"
            
            def safe_pw_call_side_effect(*args, **kwargs):
                if args[0] == mock_pw.system_status:
                    return {'battery_blocks': []}
                elif args[0] == mock_pw.vitals:
                    return {
                        'TESYNC1': {
                            'ISLAND_FreqL1_Load': 60.01,
                            'METER_X_CTA_InstRealPower': 5000
                        }
                    }
                elif args[0] == mock_pw.grid_status:
                    return 1
                return None
            
            mock_safe_pw_call.side_effect = safe_pw_call_side_effect
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            data = json.loads(result)
            
            # Verify meter/island metrics are included
            self.assertEqual(data['ISLAND_FreqL1_Load'], 60.01)
            self.assertEqual(data['METER_X_CTA_InstRealPower'], 5000)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_freq_cache_behavior(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        """Test /freq endpoint caching"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/freq"
            
            call_count = 0
            def safe_pw_call_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if args[0] == mock_pw.system_status:
                    return {'battery_blocks': []}
                elif args[0] == mock_pw.vitals:
                    return {}
                elif args[0] == mock_pw.grid_status:
                    return 1
                return None
            
            mock_safe_pw_call.side_effect = safe_pw_call_side_effect
            
            # First call - should hit the API
            self.handler.do_GET()
            first_call_count = call_count
            
            # Second call - should use cache
            self.handler.wfile = BytesIO()
            self.handler.do_GET()
            second_call_count = call_count
            
            # Verify cache was used (no new API calls)
            self.assertEqual(first_call_count, second_call_count)


class TestPodEndpoint(BaseDoGetTest):
    """Test cases for /pod endpoint"""

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_pod_basic_output(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        """Test /pod endpoint basic output"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/pod"
            
            def safe_pw_call_side_effect(*args, **kwargs):
                if args[0] == mock_pw.system_status:
                    return {
                        'battery_blocks': [
                            {
                                'PackagePartNumber': 'PW2-123',
                                'PackageSerialNumber': 'TG123456',
                                'nominal_energy_remaining': 13500,
                                'nominal_full_pack_energy': 14000,
                                'pinv_state': 'PV_Active',
                                'p_out': 1500,
                                'v_out': 240.5,
                                'f_out': 60.0
                            }
                        ],
                        'nominal_full_pack_energy': 14000,
                        'nominal_energy_remaining': 13500
                    }
                elif args[0] == mock_pw.vitals:
                    return {
                        'TEPOD1': {
                            'POD_ActiveHeating': 0,
                            'POD_ChargeComplete': 0,
                            'POD_available_charge_power': 5000,
                            'POD_nom_energy_remaining': 13500,
                            'POD_nom_full_pack_energy': 14000
                        }
                    }
                elif args[0] == mock_pw.get_time_remaining:
                    return 18.5
                elif args[0] == mock_pw.get_reserve:
                    return 20.0
                return None
            
            mock_safe_pw_call.side_effect = safe_pw_call_side_effect
            
            self.handler.do_GET()
            
            self.handler.send_response.assert_called_with(HTTPStatus.OK)
            result = self.get_written_text()
            data = json.loads(result)
            
            # Verify battery block data
            self.assertEqual(data['PW1_PackagePartNumber'], 'PW2-123')
            self.assertEqual(data['PW1_POD_nom_energy_remaining'], 13500)
            self.assertEqual(data['PW1_pinv_state'], 'PV_Active')
            
            # Verify vitals overlay
            self.assertEqual(data['PW1_name'], 'TEPOD1')
            self.assertEqual(data['PW1_POD_available_charge_power'], 5000)
            
            # Verify aggregates
            self.assertEqual(data['nominal_full_pack_energy'], 14000)
            self.assertEqual(data['time_remaining_hours'], 18.5)
            self.assertEqual(data['backup_reserve_percent'], 20.0)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_pod_multiple_batteries(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        """Test /pod endpoint with multiple Powerwalls"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/pod"
            
            def safe_pw_call_side_effect(*args, **kwargs):
                if args[0] == mock_pw.system_status:
                    return {
                        'battery_blocks': [
                            {'PackageSerialNumber': 'SN001', 'p_out': 1000},
                            {'PackageSerialNumber': 'SN002', 'p_out': 1200}
                        ],
                        'nominal_full_pack_energy': 28000,
                        'nominal_energy_remaining': 25000
                    }
                elif args[0] == mock_pw.vitals:
                    return {
                        'TEPOD1': {'POD_nom_energy_remaining': 12500},
                        'TEPOD2': {'POD_nom_energy_remaining': 12500}
                    }
                elif args[0] == mock_pw.get_time_remaining:
                    return 20.0
                elif args[0] == mock_pw.get_reserve:
                    return 15.0
                return None
            
            mock_safe_pw_call.side_effect = safe_pw_call_side_effect
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            data = json.loads(result)
            
            # Verify both batteries are present
            self.assertEqual(data['PW1_PackageSerialNumber'], 'SN001')
            self.assertEqual(data['PW2_PackageSerialNumber'], 'SN002')
            self.assertEqual(data['PW1_name'], 'TEPOD1')
            self.assertEqual(data['PW2_name'], 'TEPOD2')

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.safe_pw_call')
    def test_pod_null_handling(self, proxystats_lock, mock_safe_pw_call, mock_pw):
        """Test /pod endpoint with null values"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/pod"
            
            # All calls return None
            mock_safe_pw_call.return_value = None
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            data = json.loads(result)
            
            # Should return empty/null aggregates
            self.assertIsNone(data.get('nominal_full_pack_energy'))
            self.assertIsNone(data.get('time_remaining_hours'))


class TestJsonEndpoint(BaseDoGetTest):
    """Test cases for /json endpoint"""

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_json_basic_output(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /json endpoint basic output"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/json"
            
            # Mock aggregates call
            mock_safe_endpoint_call.return_value = {
                'site': {'instant_power': 100},
                'solar': {'instant_power': 5000},
                'battery': {'instant_power': -2000},
                'load': {'instant_power': 3100}
            }
            
            # Mock other calls
            def safe_pw_call_side_effect(*args, **kwargs):
                if args[0] == mock_pw.level:
                    return 75.5
                elif args[0] == mock_pw.grid_status:
                    return "UP"
                elif args[0] == mock_pw.get_reserve:
                    return 20.0
                elif args[0] == mock_pw.get_time_remaining:
                    return 15.5
                elif args[0] == mock_pw.system_status:
                    return {
                        'nominal_full_pack_energy': 14000,
                        'nominal_energy_remaining': 10570
                    }
                elif args[0] == mock_pw.strings:
                    return {'A': {'Connected': True, 'Current': 5.5}}
                return None
            
            mock_safe_pw_call.side_effect = safe_pw_call_side_effect
            
            self.handler.do_GET()
            
            self.handler.send_response.assert_called_with(HTTPStatus.OK)
            result = self.get_written_text()
            data = json.loads(result)
            
            # Verify all fields
            self.assertEqual(data['grid'], 100)
            self.assertEqual(data['home'], 3100)
            self.assertEqual(data['solar'], 5000)
            self.assertEqual(data['battery'], -2000)
            self.assertEqual(data['soe'], 75.5)
            self.assertEqual(data['grid_status'], 1)  # UP = 1
            self.assertEqual(data['reserve'], 20.0)
            self.assertEqual(data['time_remaining_hours'], 15.5)
            self.assertEqual(data['full_pack_energy'], 14000)
            self.assertEqual(data['energy_remaining'], 10570)
            self.assertIn('A', data['strings'])

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_json_negative_solar_correction(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /json endpoint with negative solar correction"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/json"
            
            # Mock aggregates with negative solar
            mock_safe_endpoint_call.return_value = {
                'site': {'instant_power': 100},
                'solar': {'instant_power': -50},
                'battery': {'instant_power': 200},
                'load': {'instant_power': 250}
            }
            
            mock_safe_pw_call.side_effect = lambda *args, **kwargs: (
                50.0 if args[0] == mock_pw.level else
                "UP" if args[0] == mock_pw.grid_status else
                20.0 if args[0] == mock_pw.get_reserve else
                10.0 if args[0] == mock_pw.get_time_remaining else
                {} if args[0] == mock_pw.system_status else
                {} if args[0] == mock_pw.strings else None
            )
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            data = json.loads(result)
            
            # Verify solar clamped to 0 and home adjusted
            self.assertEqual(data['solar'], 0)
            self.assertEqual(data['home'], 300)  # 250 - (-50)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_json_aggregates_optimization(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /json endpoint uses single aggregates call"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/json"
            
            mock_safe_endpoint_call.return_value = {
                'site': {'instant_power': 100},
                'solar': {'instant_power': 200},
                'battery': {'instant_power': -50},
                'load': {'instant_power': 250}
            }
            
            # Mock safe_pw_call with appropriate return values
            mock_safe_pw_call.side_effect = lambda *args, **kwargs: (
                50.0 if args[0] == mock_pw.level else
                "UP" if args[0] == mock_pw.grid_status else
                20.0 if args[0] == mock_pw.get_reserve else
                10.0 if args[0] == mock_pw.get_time_remaining else
                {} if args[0] == mock_pw.system_status else
                {} if args[0] == mock_pw.strings else None
            )
            
            self.handler.do_GET()
            
            # Verify aggregates was called once
            mock_safe_endpoint_call.assert_called_once_with(
                "/aggregates", mock_pw.poll, "/api/meters/aggregates", jsonformat=False
            )
            
            # Verify individual power methods were NOT called
            for call in mock_safe_pw_call.call_args_list:
                method = call[0][0]
                # None of these should be called since we use aggregates
                self.assertNotEqual(method, mock_pw.grid)
                self.assertNotEqual(method, mock_pw.solar)
                self.assertNotEqual(method, mock_pw.battery)
                self.assertNotEqual(method, mock_pw.home)

    @common_patches
    @patch('proxy.server.pw')
    @patch('proxy.server.neg_solar', False)
    @patch('proxy.server.safe_endpoint_call')
    @patch('proxy.server.safe_pw_call')
    def test_json_null_aggregates(self, proxystats_lock, mock_safe_pw_call, mock_safe_endpoint_call, mock_pw):
        """Test /json endpoint with null aggregates"""
        with patch.dict('proxy.server._performance_cache', {}, clear=True):
            self.handler.path = "/json"
            
            # Aggregates returns None (timeout/error)
            mock_safe_endpoint_call.return_value = None
            mock_safe_pw_call.return_value = 0
            
            self.handler.do_GET()
            
            result = self.get_written_text()
            data = json.loads(result)
            
            # All power values should be 0
            self.assertEqual(data['grid'], 0)
            self.assertEqual(data['home'], 0)
            self.assertEqual(data['solar'], 0)
            self.assertEqual(data['battery'], 0)
