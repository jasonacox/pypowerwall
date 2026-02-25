# pyPowerWall - Tesla TEDAPI Class
# -*- coding: utf-8 -*-
"""
 Tesla TEADAPI Class

 This module allows you to access the Tesla Powerwall Gateway
 TEDAPI on 192.168.91.1 as used by the Tesla One app.

 Class:
    TEDAPI(gw_pwd: str, debug: bool = False, pwcacheexpire: int = 5, timeout: int = 5,
              pwconfigexpire: int = 5, host: str = GW_IP) - Initialize TEDAPI

 Parameters:
    gw_pwd - Powerwall Gateway Password
    debug - Enable Debug Output
    pwcacheexpire - Cache Expiration in seconds
    timeout - API Timeout in seconds
    pwconfigexpire - Configuration Cache Expiration in seconds
    host - Powerwall Gateway IP Address (default: 192.168.91.1)

 Functions:
    get_din() - Get the DIN from the Powerwall Gateway
    get_config() - Get the Powerwall Gateway Configuration
    get_status() - Get the Powerwall Gateway Status
    connect() - Connect to the Powerwall Gateway
    backup_time_remaining() - Get the time remaining in hours
    battery_level() - Get the battery level as a percentage
    vitals() - Use tedapi data to create a vitals dictionary
    get_firmware_version() - Get the Powerwall Firmware Version
    get_battery_blocks() - Get list of Powerwall Battery Blocks
    get_components() - Get the Powerwall 3 Device Information
    get_battery_block(din) - Get the Powerwall 3 Battery Block Information
    get_pw3_vitals() - Get the Powerwall 3 Vitals Information
    get_device_controller() - Get the Powerwall Device Controller Status

 Note:
    This module requires access to the Powerwall Gateway. You can add a route to
    using the command: sudo route add -host 192.168.91.1 <Powerwall_IP>
    The Powerwall Gateway password is required to access the TEDAPI.

 Author: Jason A. Cox
 Date: 1 Jun 2024
 For more information see https://github.com/jasonacox/pypowerwall
"""

import gzip
import json
import logging
import math
import sys
import threading
import time
from functools import wraps
from http import HTTPStatus
from typing import Dict, Final, List, Optional, Tuple

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning

from pypowerwall import __version__
from pypowerwall.api_lock import acquire_lock_with_backoff

from . import tedapi_pb2

urllib3.disable_warnings(InsecureRequestWarning)

# TEDAPI Fixed Gateway IP Address
GW_IP = "192.168.91.1"

# Rate Limit Codes
BUSY_CODES: Final[List[HTTPStatus]] = [HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE]
RETRY_FORCE_CODES: Final[List[int]] = [int(i) for i in [
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.GATEWAY_TIMEOUT,
    HTTPStatus.INTERNAL_SERVER_ERROR,
    HTTPStatus.SERVICE_UNAVAILABLE,
    HTTPStatus.TOO_MANY_REQUESTS
]]

# Setup Logging
log = logging.getLogger(__name__)
log.debug('%s version %s', __name__, __version__)
log.debug('Python %s on %s', sys.version, sys.platform)

def _build_signed_query(query_text: str) -> bytes:
    """Build serialized SignedGraphQLQuery bytes from query text.

    The gateway expects field 2 (query) of GraphQLAPIQueryRequest to contain
    serialized SignedGraphQLQuery{version:2, query:queryText} bytes. The ECDSA
    signature is computed over these exact bytes.
    """
    sq = tedapi_pb2.SignedGraphQLQuery()
    sq.version = 2
    sq.query = query_text.encode('utf-8')
    return sq.SerializeToString()

# ECDSA-SHA256 signature for DEVICE_CONTROLLER query
SEND_CODE_DEVICE_CONTROLLER = bytes.fromhex(
    '308187024159f83efaa7736c038110b06dbb125618'
    'ca4e0c6c3dbbd78a32aaeb6b8c11c848f10a0d0478'
    'b1a5f66fe9a565a20637dcf0bc97a93c7eb5790c27'
    '42db663ee74393024201685dd07b85b0f888bc284e'
    'dd3614cb6fdb969b52c622d11b1014207994d52b58'
    '5e0cf9b110d581780b16106db6234d577e809119fc'
    '62577ea62bf82c6459ec2733'
)

# GraphQL query for get_status() and get_device_controller()
# NOTE: This query MUST remain byte-exact (minified) - the signature above is an
# ECDSA-SHA256 signature of this exact byte sequence. Any change invalidates it.
QUERY_DEVICE_CONTROLLER = (
    'query DeviceControllerQuery{control{systemStatus{nominalFullPackEnergyWh nominalEnergyRemainingWh}is'
    'landing{customerIslandMode contactorClosed microGridOK gridOK disableReasons}meterAggregates{locatio'
    'n realPowerW}alerts{active}siteShutdown{isShutDown reasons}batteryBlocks{din disableReasons}pvInvert'
    'ers{din disableReasons}protectionTripTests{isRunning}}system{time supportMode{remoteService{isEnable'
    'd expiryTime sessionId}}sitemanagerStatus{isRunning}}neurio{isDetectingWiredMeters readings{firmware'
    'Version serial dataRead{voltageV realPowerW reactivePowerVAR currentA}timestamp}pairings{serial shor'
    'tId status errors macAddress hostname isWired modbusPort modbusId lastUpdateTimestamp}}teslaRemoteMe'
    'ter{meters{din reading{timestamp firmwareVersion rssiDb ctReadings{voltageV realPowerW reactivePower'
    'VAR energyExportedWs energyImportedWs currentA}}firmwareUpdate{updating numSteps currentStep current'
    'StepProgress progress}}detectedWired{din serialPort}}pw3Can{firmwareUpdate{isUpdating progress{updat'
    'ing numSteps currentStep currentStepProgress progress}}enumeration{inProgress}}esCan{bus{PVAC{packag'
    'ePartNumber packageSerialNumber subPackagePartNumber subPackageSerialNumber PVAC_Status{isMIA PVAC_P'
    'out PVAC_State PVAC_Vout PVAC_Fout}PVAC_ControlMeasurements{PVAC_FanSelfTestState}PVAC_InfoMsg{PVAC_'
    'appGitHash}PVAC_Logging{isMIA PVAC_PVCurrent_A PVAC_PVCurrent_B PVAC_PVCurrent_C PVAC_PVCurrent_D PV'
    'AC_PVMeasuredVoltage_A PVAC_PVMeasuredVoltage_B PVAC_PVMeasuredVoltage_C PVAC_PVMeasuredVoltage_D PV'
    'AC_VL1Ground PVAC_VL2Ground PVAC_Fan_Speed_Actual_RPM PVAC_Fan_Speed_Target_RPM}alerts{isComplete is'
    'MIA active}}PINV{PINV_Status{isMIA PINV_Fout PINV_Pout PINV_Vout PINV_State PINV_GridState}PINV_AcMe'
    'asurements{isMIA PINV_VSplit1 PINV_VSplit2}PINV_PowerCapability{isComplete isMIA PINV_Pnom}alerts{is'
    'Complete isMIA active}}PVS{PVS_Status{isMIA PVS_State PVS_vLL PVS_StringA_Connected PVS_StringB_Conn'
    'ected PVS_StringC_Connected PVS_StringD_Connected PVS_SelfTestState}PVS_Logging{PVS_numStringsLockou'
    'tBits PVS_sbsComplete}alerts{isComplete isMIA active}}THC{packagePartNumber packageSerialNumber THC_'
    'InfoMsg{isComplete isMIA THC_appGitHash}THC_Logging{THC_LOG_PW_2_0_EnableLineState}alerts{isComplete'
    ' isMIA active}}POD{POD_EnergyStatus{isMIA POD_nom_energy_remaining POD_nom_full_pack_energy}POD_Info'
    'Msg{POD_appGitHash}alerts{isComplete isMIA active}}SYNC{packagePartNumber packageSerialNumber subPac'
    'kagePartNumber subPackageSerialNumber SYNC_InfoMsg{isMIA SYNC_appGitHash SYNC_assemblyId}METER_X_AcM'
    'easurements{isMIA isComplete METER_X_CTA_InstRealPower METER_X_CTA_InstReactivePower METER_X_CTA_I M'
    'ETER_X_VL1N METER_X_CTB_InstRealPower METER_X_CTB_InstReactivePower METER_X_CTB_I METER_X_VL2N METER'
    '_X_CTC_InstRealPower METER_X_CTC_InstReactivePower METER_X_CTC_I METER_X_VL3N}METER_Y_AcMeasurements'
    '{isMIA isComplete METER_Y_CTA_InstRealPower METER_Y_CTA_InstReactivePower METER_Y_CTA_I METER_Y_VL1N'
    ' METER_Y_CTB_InstRealPower METER_Y_CTB_InstReactivePower METER_Y_CTB_I METER_Y_VL2N METER_Y_CTC_Inst'
    'RealPower METER_Y_CTC_InstReactivePower METER_Y_CTC_I METER_Y_VL3N}alerts{isComplete isMIA active}}I'
    'SLANDER{ISLAND_GridConnection{ISLAND_GridConnected isComplete}ISLAND_AcMeasurements{ISLAND_VL1N_Main'
    ' ISLAND_FreqL1_Main ISLAND_VL2N_Main ISLAND_FreqL2_Main ISLAND_VL3N_Main ISLAND_FreqL3_Main ISLAND_V'
    'L1N_Load ISLAND_FreqL1_Load ISLAND_VL2N_Load ISLAND_FreqL2_Load ISLAND_VL3N_Load ISLAND_FreqL3_Load '
    'ISLAND_GridState isComplete isMIA}}}enumeration{inProgress numACPW numPVI}firmwareUpdate{isUpdating '
    'powerwalls{updating numSteps currentStep currentStepProgress progress}msa{updating numSteps currentS'
    'tep currentStepProgress progress}msa1{updating numSteps currentStep currentStepProgress progress}syn'
    'c{updating numSteps currentStep currentStepProgress progress}pvInverters{updating numSteps currentSt'
    'ep currentStepProgress progress}}phaseDetection{inProgress lastUpdateTimestamp powerwalls{din progre'
    'ss phase}}}components{msa:components(filter:{types:[TEMSA]}){partNumber serialNumber signals(names:['
    '"MSA_pcbaId" "MSA_usageId" "MSA_appGitHash" "MSA_HeatingRateOccurred" "METER_Z_CTA_InstRealPower" "M'
    'ETER_Z_CTA_InstReactivePower" "METER_Z_CTA_I" "METER_Z_VL1G" "METER_Z_CTB_InstRealPower" "METER_Z_CT'
    'B_InstReactivePower" "METER_Z_CTB_I" "METER_Z_VL2G"]){name value textValue boolValue}activeAlerts{na'
    'me}}}}'
)

# ECDSA-SHA256 signature for COMPONENTS query
SEND_CODE_COMPONENTS = bytes.fromhex(
    '3081870241786800ad176df8c4ab2835d2f0d31efc'
    '901cda3c6bb26a0dcb0fa9d7bc7e11e31981c1867b'
    '2e8d770c69f9a7d796cb2668570400a71d0f0802b1'
    'b1e2aa5a46406f024200f2c014dcb5585c73cb90c5'
    'e49944033f7ab3255b0b68b74e68719bb1fc192246'
    'a6dd8d71a0f138ab698357ba5c05bd1460c680a844'
    'd5870e458629c657b032f0a3'
)

# GraphQL query for get_components/get_pw3_vitals/get_battery_block
# NOTE: This query MUST remain byte-exact (minified) - the signature above is an
# ECDSA-SHA256 signature of this exact byte sequence. Any change invalidates it.
QUERY_COMPONENTS = (
    'query ComponentsQuery{pw3Can{firmwareUpdate{isUpdating progress{updating numSteps currentStep curren'
    'tStepProgress progress}}}components{pws:components(filter:{types:[PW3SAF]}){signals(names:["PWS_asse'
    'mblyId" "PWS_SelfTest" "PWS_PeImpTestState" "PWS_PvIsoTestState" "PWS_RelaySelfTest_State" "PWS_MciT'
    'estState" "PWS_ProdSwitch_State" "PWS_RSD_State" "PWS_RSDSelfTest_State" "PWS_RSDSelfTest_Result" "P'
    'WS_ExtSwitch_State" "PWS_reversePolarityStrings"]){name value textValue boolValue}activeAlerts{name}'
    '}pch:components(filter:{types:[PCH]}){signals(names:["PCH_appGitHash" "PCH_State" "PCH_AcFrequency" '
    '"PCH_AcMode" "PCH_AcRealPowerAB" "PCH_AcVoltageAB" "PCH_AcVoltageAN" "PCH_AcVoltageBN" "PCH_BatteryP'
    'ower" "PCH_DcdcState_A" "PCH_DcdcState_B" "PCH_PvState_A" "PCH_PvState_B" "PCH_PvState_C" "PCH_PvSta'
    'te_D" "PCH_PvState_E" "PCH_PvState_F" "PCH_PvVoltageA" "PCH_PvVoltageB" "PCH_PvVoltageC" "PCH_PvVolt'
    'ageD" "PCH_PvVoltageE" "PCH_PvVoltageF" "PCH_PvCurrentA" "PCH_PvCurrentB" "PCH_PvCurrentC" "PCH_PvCu'
    'rrentD" "PCH_PvCurrentE" "PCH_PvCurrentF" "PCH_SlowPvPowerSum"]){name value textValue boolValue}acti'
    'veAlerts{name}}bms:components(filter:{types:[PW3BMS]}){signals(names:["BMS_nominalEnergyRemaining" "'
    'BMS_nominalFullPackEnergy"]){name value textValue boolValue}activeAlerts{name}}hvp:components(filter'
    ':{types:[PW3HVP]}){partNumber serialNumber signals(names:["HVP_State" "HVP_SafetyBiDisconnectState"]'
    '){name value textValue boolValue}activeAlerts{name}}baggr:components(filter:{types:[BAGGR]}){signals'
    '(names:["BAGGR_State" "BAGGR_OperationRequest" "BAGGR_NumBatteriesConnected" "BAGGR_NumBatteriesPres'
    'ent" "BAGGR_NumBatteriesExpected" "BAGGR_LOG_BattConnectionStatus0" "BAGGR_LOG_BattConnectionStatus1'
    '" "BAGGR_LOG_BattConnectionStatus2" "BAGGR_LOG_BattConnectionStatus3" "BAGGR_ExpectedEnergyRemaining'
    '" "BAGGR_ExpectedFullPackEnergy"]){name value textValue boolValue}activeAlerts{name}}}}'
)

# ECDSA-SHA256 signature for IEEE20305 query
SEND_CODE_IEEE20305 = bytes.fromhex(
    '308188024201ed8814348e8f9df393fc149659358b'
    '12aa30fead0460745e0ce1ce7d9e4a6251b6b1c977'
    'dbfe50a86542e67434b6425fb6046038cf5b065ed3'
    '07698da6fb9990d1024200c94d155840700889e4f5'
    'bec765b0d37cbba18fa5d33361e85e11d1d0965d0a'
    '6825684dfe72ee754ec64278aeeefe240cf8ab89e1'
    '1906182e6353042e9e14a789d8'
)

# GraphQL query for IEEE 2030.5 data
# NOTE: Byte-exact, ECDSA-SHA256 signed.
QUERY_IEEE20305 = (
    'query IEEE20305Query{ieee20305{longFormDeviceID polledResources{url name pollRateSeconds lastPolledT'
    'imestamp}controls{defaultControl{mRID setGradW opModEnergize opModMaxLimW opModImpLimW opModExpLimW '
    'opModGenLimW opModLoadLimW}activeControls{opModEnergize opModMaxLimW opModImpLimW opModExpLimW opMod'
    'GenLimW opModLoadLimW}}registration{dateTimeRegistered pin}}}'
)

# ECDSA-SHA256 signature for GRID_CODE_DETAILS query
SEND_CODE_GRID_CODE_DETAILS = bytes.fromhex(
    '3081880242015e85521f3ac12f9f63b82e1777c149'
    'cdf384ec0edce4b5d8a8553d94dd9d581937cf5fea'
    '21a65edbddbff82090844f0531929b556903d39aca'
    'ea531667e9a50e0602420132e94ffabbd8c0091058'
    '0ed2575b7276c21052c0d92b31058fba80f610f2ff'
    '9dffb094a94e2d51ad9a0991585e663f6dacf642ac'
    'b9ccbbfbaf1cbe7372db514579'
)

# GraphQL query for grid code details (uses variables: $gridCode, $pointNames)
# NOTE: Byte-exact, ECDSA-SHA256 signed.
QUERY_GRID_CODE_DETAILS = (
    'query GridCodeDetailsQuery($gridCode:String!$pointNames:[String!]){system{gridCodeSettings(gridCode:'
    '$gridCode){gridCode gridVoltageSetting gridFrequencySetting gridPhaseSetting gridPerPhaseNetMeterEna'
    'bled gridCodePoints(names:$pointNames){name units min max fileValue}}}}'
)

# ECDSA-SHA256 signature for GRID_CODES query
SEND_CODE_GRID_CODES = bytes.fromhex(
    '308186024135da0bb771a881feb151227b92e5cdbf'
    '60c035f36f79517962c5c7f8138087322d2ba958ee'
    'eeb7a47bbbae595f56e1e49f93ad1c49f4514e4aec'
    '43946955ca76b8024131064c2913404dd80a9f4d0e'
    '71cd42738463e49a50f62f9783028c6549013eb580'
    '1544edc88dd7e53757b28f354fcf295ca2fd19ba49'
    '7f7aeea7548dc65c35e9d7'
)

# GraphQL query for available grid codes
# NOTE: Byte-exact, ECDSA-SHA256 signed.
QUERY_GRID_CODES = (
    'query GridCodesQuery{system{gridCodes}}'
)

# ECDSA-SHA256 signature for EATON_SBII query
SEND_CODE_EATON_SBII = bytes.fromhex(
    '30818802420110b3ff5de5c1e64fbda251170b1c85'
    'f5c892dde1e5225eccdb6a4be555a2e7ff1e8326c1'
    'c3b69eec23800ce9c94fe63ba94147f19a1628f7ab'
    'b1c5599f5394ab5c0242012f3133187f4000022826'
    'c028d4799b4579750a7c29afd2c80609b5ba2ee2d5'
    '91d0e06d2a59ad21bcb752b8efc266592892739f74'
    '643729206cc82543d60557c25d'
)

# GraphQL query for Eaton SBII transfer switch data
# NOTE: Byte-exact, ECDSA-SHA256 signed.
QUERY_EATON_SBII = (
    'query EatonSBIIQuery{components{nodes(filter:{nodes:["EATON_SBII"]}){serialNumber subPackagePartNumb'
    'er signals(names:["EATON_SBII_realPower" "EATON_SBII_primaryHandleState" "EATON_SBII_secondaryHandle'
    'State"]){name value textValue boolValue}}}}'
)

# ECDSA-SHA256 signature for PINV_SELF_TEST query
SEND_CODE_PINV_SELF_TEST = bytes.fromhex(
    '308188024200a9d1a9cee2cf7e50d23c6b95cabaac'
    '394e039f28613141d1c0c947d50613c417a9d08534'
    'b26556349e8bdc5df89362c16ee8108e6da4c0669b'
    '812d1eda48f25ecf02420143cb418c2d665bd4ca1a'
    '58f02be0d431c0aceb125c1664ed7d6b5362c22ba3'
    '47f95ae4eb81438960f303aad38ab35b0ed38bff8c'
    '36c0f711a729eae2f8393c22e6'
)

# GraphQL query for inverter self-test results
# NOTE: Byte-exact, ECDSA-SHA256 signed.
QUERY_PINV_SELF_TEST = (
    'query PinvSelfTestQuery{esCan{inverterSelfTests{isRunning isCanceled pinvSelfTestsResults{din overal'
    'l{status test summary setMagnitude setTime tripMagnitude tripTime accuracyMagnitude accuracyTime cur'
    'rentMagnitude timestamp lastError}testResults{status test summary setMagnitude setTime tripMagnitude'
    ' tripTime accuracyMagnitude accuracyTime currentMagnitude timestamp lastError}}}}}'
)

# ECDSA-SHA256 signature for PROTECTION_TRIP_TEST query
SEND_CODE_PROTECTION_TRIP_TEST = bytes.fromhex(
    '3081880242008eb1e3ceaf5ad65ad3ff75a6fa3eeb'
    'ccf80eaf528ada3fa7fef51a234044599cad4671fe'
    '6f2d0bf24677b6756e2f5f52673439cca90accad56'
    '118dad1e8bdb7988024200cc72dee1c8abd9c9d341'
    '4ae85b4e06a0ecf12425d190d4f32a53356150d208'
    '59a4666557364c43fe30de5cd665800bc7d184d6ac'
    'e76364a3551532045e9e7aae96'
)

# GraphQL query for protection trip test results
# NOTE: Byte-exact, ECDSA-SHA256 signed.
QUERY_PROTECTION_TRIP_TEST = (
    'query ProtectionTripTestQuery{control{protectionTripTests{isRunning results{testType status timestam'
    'p mandatedTripThreshold{value unit}mandatedTripTime{value unit}rampStepSize{value unit}rampInterval{'
    'value unit}tripThresholdDeviationMax{value unit}tripTimeDeviationMax{value unit}observedTripThreshol'
    'd{value unit}observedTripTime{value unit}observedMeasurementAtTrip{value unit}observedTripThresholdD'
    'eviation{value unit}observedTripTimeDeviation{value unit}tripThresholdAccuracy{value unit}tripTimeAc'
    'curacy{value unit}measurementAccuracy{value unit}measurementTimeAccuracy{value unit}}}}}'
)

# Utility Functions
def lookup(data, keylist):
    """
    Lookup a value in a nested dictionary or return None if not found.
    data - nested dictionary
    keylist - list of keys to traverse
    """
    for key in keylist:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return None
    return data

def decompress_response(content: bytes) -> bytes:
    """
    Decompress gzip-compressed response content if needed.

    Firmware 25.42.2+ returns gzip-compressed responses from TEDAPI endpoints.
    This function checks for the gzip magic bytes (0x1f 0x8b) and decompresses
    if necessary.

    Args:
        content: Raw response content bytes

    Returns:
        Decompressed bytes if gzip-compressed, otherwise original content
    """
    if len(content) > 2 and content[0:2] == b'\x1f\x8b':
        try:
            return gzip.decompress(content)
        except Exception as e:
            log.debug(f"Gzip decompression failed: {e}")
    return content

def uses_api_lock(func):
    # If the attribute doesn't exist or isn't a valid threading.Lock, overwrite it.
    if not hasattr(func, 'api_lock') or not isinstance(func.api_lock, type(threading.Lock)):
        func.api_lock = threading.Lock()
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Inject the function object itself into kwargs.
        kwargs['self_function'] = func
        return func(*args, **kwargs)
    return wrapper

def _pb_extract(data: bytes, *field_path: int) -> Optional[bytes]:
    """Extract a length-delimited field from raw protobuf bytes by field number path.

    Navigates nested protobuf messages by following the given field numbers.
    Returns the raw bytes of the final field, or None if not found.
    Only supports length-delimited (wire type 2) fields in the path.
    """
    for target in field_path:
        pos = 0
        found = False
        while pos < len(data):
            # Decode varint tag
            tag = 0
            shift = 0
            while pos < len(data):
                b = data[pos]
                pos += 1
                tag |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            wire_type = tag & 0x07
            field_number = tag >> 3
            if wire_type == 0:  # varint
                while pos < len(data) and data[pos] & 0x80:
                    pos += 1
                pos += 1
            elif wire_type == 2:  # length-delimited
                length = 0
                shift = 0
                while pos < len(data):
                    b = data[pos]
                    pos += 1
                    length |= (b & 0x7F) << shift
                    if not (b & 0x80):
                        break
                    shift += 7
                if field_number == target:
                    data = data[pos:pos + length]
                    found = True
                    break
                pos += length
            elif wire_type == 1:  # 64-bit
                pos += 8
            elif wire_type == 5:  # 32-bit
                pos += 4
            else:
                break
        if not found:
            return None
    return data

# TEDAPI Class
class TEDAPI:
    def __init__(self, gw_pwd: str, debug: bool = False, pwcacheexpire: int = 5, poolmaxsize: int = 10,
                 timeout: int = 5, pwconfigexpire: int = 5, host: str = GW_IP, auth_mode: str = "basic") -> None:
        self.debug = debug
        self.pwcachetime = {}  # holds the cached data timestamps for api
        self.pwcacheexpire = pwcacheexpire  # seconds to expire status cache
        self.pwconfigexpire = pwconfigexpire  # seconds to expire config cache
        self.poolmaxsize = poolmaxsize # maximum size of the connection
        self.pwcache = {}  # holds the cached data for api
        self.timeout = timeout
        self.pwcooldown = 0
        self.gw_ip = host
        self.din = None
        self.pw3 = False # Powerwall 3 Gateway only supports TEDAPI
        self.auth_mode = auth_mode.lower()
        self.token = None  # Bearer token (only used in bearer mode)
        if self.auth_mode not in ("basic", "bearer"):
            raise ValueError(f"Invalid auth_mode '{auth_mode}': must be 'basic' or 'bearer'")
        if not gw_pwd:
            raise ValueError("Missing gw_pwd")
        if self.debug:
            self.set_debug(True)
        self.gw_pwd = gw_pwd
        log.debug(f"TEDAPI initialized with auth_mode={self.auth_mode}, pwcacheexpire={self.pwcacheexpire}s, pwconfigexpire={self.pwconfigexpire}s")
        # Connect to Powerwall Gateway
        if not self.connect():
            log.error("Failed to connect to Powerwall Gateway")

    # TEDAPI Functions
    def set_debug(self, toggle=True, color=True):
        """Enable verbose logging"""
        if toggle:
            if color:
                logging.basicConfig(format='\x1b[31;1m%(levelname)s:%(message)s\x1b[0m', level=logging.DEBUG)
            else:
                logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
            log.setLevel(logging.DEBUG)
            log.debug("%s [%s]\n" % (__name__, __version__))
        else:
            log.setLevel(logging.NOTSET)

    def get_din(self, force=False):
        """Get the Device Identification Number (DIN) from the Powerwall Gateway."""
        # Check Cache
        if not force and "din" in self.pwcachetime:
            if time.time() - self.pwcachetime["din"] < self.pwcacheexpire:
                log.debug("Using Cached DIN")
                return self.pwcache["din"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        # Fetch DIN from Powerwall
        log.debug("Fetching DIN from Powerwall...")
        url = f'https://{self.gw_ip}/tedapi/din'
        r = self.session.get(url, timeout=self.timeout)
        if r.status_code in BUSY_CODES:
            # Rate limited - Switch to cooldown mode for 5 minutes
            self.pwcooldown = time.perf_counter() + 300
            log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
            return None
        if r.status_code == HTTPStatus.FORBIDDEN:
            log.error("Access Denied: Check your Gateway Password")
            return None
        if r.status_code != HTTPStatus.OK:
            log.error(f"Error fetching DIN: {r.status_code}")
            return None
        # Firmware 25.42.2+ returns gzip-compressed DIN response
        content = decompress_response(r.content)
        try:
            din = content.decode('utf-8').strip()
        except UnicodeDecodeError as e:
            log.error(f"Error decoding DIN response: {e}")
            return None
        log.debug(f"Connected: Powerwall Gateway DIN: {din}")
        self.pwcachetime["din"] = time.time()
        self.pwcache["din"] = din
        
        return din


    @uses_api_lock
    def get_config(self, self_function, force=False):
        """
        Get the Powerwall Gateway Configuration

        Payload:
        {
            "auto_meter_update": true,
            "battery_blocks": [],
            "bridge_inverter": {},
            "client_protocols": {},
            "credentials": [],
            "customer": {},
            "default_real_mode": "self_consumption",
            "dio": {},
            "enable_inverter_meter_readings": true,
            "freq_shift_load_shed": {},
            "freq_support_parameters": {},
            "industrial_networks": {},
            "installer": {},
            "island_config": {},
            "island_contactor_controller": {},
            "logging": {},
            "meters": [],
            "site_info": {},
            "solar": {},
            "solars": [],
            "strategy": {},
            "test_timers": {},
            "vin": "1232100-00-E--TG11234567890"
        }
        """
        # Check for lock and wait if api request already sent
        data = None
        with acquire_lock_with_backoff(self_function, self.timeout):
            # Check Cache
            if not force and "config" in self.pwcachetime:
                if time.time() - self.pwcachetime["config"] < self.pwconfigexpire:
                    log.debug("Using Cached Payload")
                    return self.pwcache["config"]
            if not force and self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
                return None
            # Check Connection
            if not self.din:
                if not self.connect():
                    log.error("Not Connected - Unable to get configuration")
                    return None
            # Fetch Configuration from Powerwall
            log.debug("Get Configuration from Powerwall")
            # Build Protobuf to fetch config
            pb = tedapi_pb2.Message()
            pb.message.deliveryChannel = tedapi_pb2.DELIVERY_CHANNEL_LOCAL_HTTPS
            pb.message.sender.local = tedapi_pb2.LOCAL_PARTICIPANT_INSTALLER
            pb.message.recipient.din = self.din  # DIN of Powerwall
            pb.message.filestore.readFileRequest.domain = 1  # CONFIG_JSON
            pb.message.filestore.readFileRequest.name = "config.json"
            pb.tail.value = 1
            try:
                r = self._send_cmd(pb)
                log.debug(f"Response Code: {r.status_code}")
                if r.status_code in BUSY_CODES:
                    # Rate limited - Switch to cooldown mode for 5 minutes
                    self.pwcooldown = time.perf_counter() + 300
                    log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                    return None
                if r.status_code != HTTPStatus.OK:
                    log.error(f"Error fetching config: {r.status_code}")
                    return None
                tedapi = self._parse_response(r.content)
                payload = tedapi.message.filestore.readFileResponse.file.blob.decode('utf-8')
                if payload:
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError as e:
                        log.error(f"Error Decoding JSON: {e}")
                        data = {}
                else:
                    log.warning("Empty config payload from gateway")
                    data = {}
                log.debug(f"Configuration: {data}")
                self.pwcachetime["config"] = time.time()
                self.pwcache["config"] = data
            except Exception as e:
                log.error(f"Error fetching config: {e}")
                data = None
        return data


    @uses_api_lock
    def get_status(self, self_function, force=False):
        """
        Get the Powerwall Gateway Status

        Payload:
        {
            "control": {
                "alerts": {},
                "batteryBlocks": [],
                "islanding": {},
                "meterAggregates": [],
                "pvInverters": [],
                "siteShutdown": {},
                "systemStatus": {}
                },
            "esCan": {
                "bus": {
                    "ISLANDER": {},
                    "MSA": {},
                    "PINV": [],
                    "POD": [],
                    "PVAC": [],
                    "PVS": [],
                    "SYNC": {},
                    "THC": []
                    },
                "enumeration": null,
                "firmwareUpdate": {},
                "inverterSelfTests": null,
                "phaseDetection": null
                },
            "neurio": {
                "isDetectingWiredMeters": false,
                "pairings": [],
                "readings": []
                },
            "pw3Can": {},
            "system": {}
        }
        """
        
        # Check Cache BEFORE acquiring lock
        if not force and "status" in self.pwcachetime:
            age = time.time() - self.pwcachetime["status"]
            if age < self.pwcacheexpire:
                log.debug(f"Using Cached Payload (age: {age:.2f}s, expire: {self.pwcacheexpire}s)")
                return self.pwcache["status"]
            else:
                log.debug(f"Cache expired for status (age: {age:.2f}s, expire: {self.pwcacheexpire}s)")
                
        # Check cooldown BEFORE acquiring lock
        if not force and self.pwcooldown > time.perf_counter():
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        
        # Check for lock and wait if api request already sent
        data = None
        with acquire_lock_with_backoff(self_function, self.timeout):
            # Check Cache
            if not force and "status" in self.pwcachetime:
                if time.time() - self.pwcachetime["status"] < self.pwcacheexpire:
                    log.debug("Using Cached Payload")
                    return self.pwcache["status"]
            if not force and self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
                return None
            # Check Connection
            if not self.din:
                if not self.connect():
                    log.error("Not Connected - Unable to get status")
                    return None
            # Fetch Current Status from Powerwall
            log.debug("Get Status from Powerwall")
            # Build Protobuf to fetch status
            pb = tedapi_pb2.Message()
            pb.message.deliveryChannel = tedapi_pb2.DELIVERY_CHANNEL_LOCAL_HTTPS
            pb.message.sender.local = tedapi_pb2.LOCAL_PARTICIPANT_INSTALLER
            pb.message.recipient.din = self.din  # DIN of Powerwall
            pb.message.graphql.send.format = tedapi_pb2.GRAPH_QL_QUERY_FORMAT_SIGNED_SHA256_ECDSA_ASN1
            pb.message.graphql.send.query = _build_signed_query(QUERY_DEVICE_CONTROLLER)
            pb.message.graphql.send.signature = SEND_CODE_DEVICE_CONTROLLER
            pb.message.graphql.send.variablesJson.value = "{}"
            pb.tail.value = 1
            try:
                r = self._send_cmd(pb)
                log.debug(f"Response Code: {r.status_code}")
                if r.status_code in BUSY_CODES:
                    # Rate limited - Switch to cooldown mode for 5 minutes
                    self.pwcooldown = time.perf_counter() + 300
                    log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                    return None
                if r.status_code != HTTPStatus.OK:
                    log.error(f"Error fetching status: {r.status_code}")
                    return None
                # Decode response
                tedapi = self._parse_response(r.content)
                payload = tedapi.message.graphql.recv.data
                if payload:
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError as e:
                        log.error(f"Error Decoding JSON: {e}")
                        data = {}
                else:
                    log.warning("Empty status payload from gateway")
                    data = {}
                log.debug(f"Status: {data}")
                self.pwcachetime["status"] = time.time()
                self.pwcache["status"] = data
            except Exception as e:
                log.error(f"Error fetching status: {e}")
                data = None
        return data


    @uses_api_lock
    def get_device_controller(self, self_function, force=False):
        """
        Get the Powerwall Device Controller Status

        Similar to get_status but with additional data:
        {
            "components": {}, // Additional data
            "control": {},
            "esCan": {},
            "ieee20305": {}, // Additional data
            "neurio": {},
            "pw3Can": {},
            "system": {},
            "teslaRemoteMeter": {} // Additional data
        }

        TODO: Refactor to combine tedapi queries
        """
        # Check for lock and wait if api request already sent
        data = None
        with acquire_lock_with_backoff(self_function, self.timeout):
            # Check Cache
            if not force and "controller" in self.pwcachetime:
                if time.time() - self.pwcachetime["controller"] < self.pwcacheexpire:
                    log.debug("Using Cached Payload")
                    return self.pwcache["controller"]
            if not force and self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
                return None
            # Check Connection
            if not self.din:
                if not self.connect():
                    log.error("Not Connected - Unable to get controller data")
                    return None
            # Fetch Current Status from Powerwall
            log.debug("Get controller data from Powerwall")
            # Build Protobuf to fetch controller data
            pb = tedapi_pb2.Message()
            pb.message.deliveryChannel = tedapi_pb2.DELIVERY_CHANNEL_LOCAL_HTTPS
            pb.message.sender.local = tedapi_pb2.LOCAL_PARTICIPANT_INSTALLER
            pb.message.recipient.din = self.din  # DIN of Powerwall
            pb.message.graphql.send.format = tedapi_pb2.GRAPH_QL_QUERY_FORMAT_SIGNED_SHA256_ECDSA_ASN1
            pb.message.graphql.send.query = _build_signed_query(QUERY_DEVICE_CONTROLLER)
            pb.message.graphql.send.signature = SEND_CODE_DEVICE_CONTROLLER
            pb.message.graphql.send.variablesJson.value = "{}"
            pb.tail.value = 1
            try:
                r = self._send_cmd(pb)
                log.debug(f"Response Code: {r.status_code}")
                if r.status_code in BUSY_CODES:
                    # Rate limited - Switch to cooldown mode for 5 minutes
                    self.pwcooldown = time.perf_counter() + 300
                    log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                    return None
                if r.status_code != HTTPStatus.OK:
                    log.error(f"Error fetching controller data: {r.status_code}")
                    return None
                # Decode response
                tedapi = self._parse_response(r.content)
                payload = tedapi.message.graphql.recv.data
                log.debug(f"Payload: {payload}")
                if payload:
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError as e:
                        log.error(f"Error Decoding JSON: {e}")
                        data = {}
                else:
                    log.warning("Empty controller payload from gateway")
                    data = {}
                log.debug(f"Status: {data}")
                self.pwcachetime["controller"] = time.time()
                self.pwcache["controller"] = data
            except Exception as e:
                log.error(f"Error fetching controller data: {e}")
                data = None
        return data


    @uses_api_lock
    def get_firmware_version(self, self_function, force=False, details=False):
        """
        Get the Powerwall Firmware Version

        Args:
            force (bool): Force a refresh of the firmware version
            details (bool): Return additional system information including
                            gateway part number, serial number, and wireless devices
        """
        payload = None
        with acquire_lock_with_backoff(self_function, self.timeout):
            # Check Connection
            if not self.din:
                if not self.connect():
                    log.error("Not Connected - Unable to get firmware version")
                    return None
            # Check Cache
            if not force and "firmware" in self.pwcachetime:
                if time.time() - self.pwcachetime["firmware"] < self.pwcacheexpire:
                    log.debug("Using Cached Firmware")
                    return self.pwcache["firmware"]
            if not force and self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
                return None
            # Fetch Current Status from Powerwall
            log.debug("Get Firmware Version from Powerwall")
            # Build Protobuf to fetch system info (wire-compatible with old firmware request)
            # Old: field 4 (firmware) → field 2 (request="")
            # New: field 4 (common) → field 2 (getSystemInfoRequest={})
            pb = tedapi_pb2.Message()
            pb.message.deliveryChannel = tedapi_pb2.DELIVERY_CHANNEL_LOCAL_HTTPS
            pb.message.sender.local = tedapi_pb2.LOCAL_PARTICIPANT_INSTALLER
            pb.message.recipient.din = self.din  # DIN of Powerwall
            pb.message.common.getSystemInfoRequest.CopyFrom(
                tedapi_pb2.CommonAPIGetSystemInfoRequest()
            )
            pb.tail.value = 1
            try:
                r = self._send_cmd(pb)
                log.debug(f"Response Code: {r.status_code}")
                if r.status_code in BUSY_CODES:
                    # Rate limited - Switch to cooldown mode for 5 minutes
                    self.pwcooldown = time.perf_counter() + 300
                    log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                    return None
                if r.status_code != HTTPStatus.OK:
                    log.error(f"Error fetching firmware version: {r.status_code}")
                    return None
                # Decode response - the gateway returns firmware data inside
                # getSystemInfoResponse (field 3 of CommonMessages). Since the
                # proto defines it as empty, firmware fields are preserved as
                # raw bytes. Use _pb_extract to navigate the wire format:
                #   FirmwarePayload.version (field 3) → FirmwareVersion.text (field 1)
                #   FirmwarePayload.gateway (field 1) → EcuId
                #   FirmwarePayload.din (field 2)
                tedapi = self._parse_response(r.content)
                sys_info = tedapi.message.common.getSystemInfoResponse
                raw = sys_info.SerializeToString()
                version_text = _pb_extract(raw, 3, 1)  # version.text
                firmware_version = version_text.decode('utf-8') if version_text else None
                if details:
                    din_bytes = _pb_extract(raw, 2)  # din
                    gw_part = _pb_extract(raw, 1, 1)  # gateway.partNumber
                    gw_serial = _pb_extract(raw, 1, 2)  # gateway.serialNumber
                    githash = _pb_extract(raw, 3, 2)  # version.githash
                    payload = {
                        "system": {
                            "gateway": {
                                "partNumber": gw_part.decode('utf-8') if gw_part else "",
                                "serialNumber": gw_serial.decode('utf-8') if gw_serial else ""
                            },
                            "din": din_bytes.decode('utf-8') if din_bytes else "",
                            "version": {
                                "text": firmware_version or "",
                                "githash": githash or b""
                            }
                        }
                    }
                    log.debug(f"Firmware Version: {payload}")
                else:
                    payload = firmware_version
                log.debug(f"Firmware Version: {firmware_version}")
                self.pwcachetime["firmware"] = time.time()
                self.pwcache["firmware"] = firmware_version
            except Exception as e:
                log.error(f"Error fetching firmware version: {e}")
                payload = None
        return payload


    @uses_api_lock
    def get_components(self, self_function, force=False):
        """
        Get the Powerwall 3 Device Information

        Note: Provides empty response for previous Powerwall versions
        """
        components = None
        with acquire_lock_with_backoff(self_function, self.timeout):
            # Check Connection
            if not self.din:
                if not self.connect():
                    log.error("Not Connected - Unable to get configuration")
                    return None
            # Check Cache
            if not force and "components" in self.pwcachetime:
                if time.time() - self.pwcachetime["components"] < self.pwconfigexpire:
                    log.debug("Using Cached Components")
                    return self.pwcache["components"]
            if not force and self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
                return None
            # Fetch Configuration from Powerwall
            log.debug("Get PW3 Components from Powerwall")
            # Build Protobuf to fetch config
            pb = tedapi_pb2.Message()
            pb.message.deliveryChannel = tedapi_pb2.DELIVERY_CHANNEL_LOCAL_HTTPS
            pb.message.sender.local = tedapi_pb2.LOCAL_PARTICIPANT_INSTALLER
            pb.message.recipient.din = self.din  # DIN of Powerwall
            pb.message.graphql.send.format = tedapi_pb2.GRAPH_QL_QUERY_FORMAT_SIGNED_SHA256_ECDSA_ASN1
            pb.message.graphql.send.query = _build_signed_query(" query ComponentsQuery (\n  $pchComponentsFilter: ComponentFilter,\n  $pchSignalNames: [String!],\n  $pwsComponentsFilter: ComponentFilter,\n  $pwsSignalNames: [String!],\n  $bmsComponentsFilter: ComponentFilter,\n  $bmsSignalNames: [String!],\n  $hvpComponentsFilter: ComponentFilter,\n  $hvpSignalNames: [String!],\n  $baggrComponentsFilter: ComponentFilter,\n  $baggrSignalNames: [String!],\n  ) {\n  # TODO STST-57686: Introduce GraphQL fragments to shorten\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  components {\n    pws: components(filter: $pwsComponentsFilter) {\n      signals(names: $pwsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    pch: components(filter: $pchComponentsFilter) {\n      signals(names: $pchSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    bms: components(filter: $bmsComponentsFilter) {\n      signals(names: $bmsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    hvp: components(filter: $hvpComponentsFilter) {\n      partNumber\n      serialNumber\n      signals(names: $hvpSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    baggr: components(filter: $baggrComponentsFilter) {\n      signals(names: $baggrSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n  }\n}\n")
            pb.message.graphql.send.signature = b'0\201\210\002B\000\270q\354>\243m\325p\371S\253\231\346~:\032\216~\242\263\207\017L\273O\203u\241\270\333w\233\354\276\246h\262\243\255\261\007\202D\277\353x\023O\022\303\216\264\010-\'i6\360>B\237\236\304\244m\002B\001\023Pk\033)\277\236\342R\264\247g\260u\036\023\3662\354\242\353\035\221\234\027\245\321J\342\345\037q\262O\3446-\353\315m1\237zai0\341\207C4\307\300Z\177@h\335\327\0239\252f\n\206W'
            pb.message.graphql.send.variablesJson.value = "{\"pwsComponentsFilter\":{\"types\":[\"PW3SAF\"]},\"pwsSignalNames\":[\"PWS_SelfTest\",\"PWS_PeImpTestState\",\"PWS_PvIsoTestState\",\"PWS_RelaySelfTest_State\",\"PWS_MciTestState\",\"PWS_appGitHash\",\"PWS_ProdSwitch_State\"],\"pchComponentsFilter\":{\"types\":[\"PCH\"]},\"pchSignalNames\":[\"PCH_State\",\"PCH_PvState_A\",\"PCH_PvState_B\",\"PCH_PvState_C\",\"PCH_PvState_D\",\"PCH_PvState_E\",\"PCH_PvState_F\",\"PCH_AcFrequency\",\"PCH_AcVoltageAB\",\"PCH_AcVoltageAN\",\"PCH_AcVoltageBN\",\"PCH_packagePartNumber_1_7\",\"PCH_packagePartNumber_8_14\",\"PCH_packagePartNumber_15_20\",\"PCH_packageSerialNumber_1_7\",\"PCH_packageSerialNumber_8_14\",\"PCH_PvVoltageA\",\"PCH_PvVoltageB\",\"PCH_PvVoltageC\",\"PCH_PvVoltageD\",\"PCH_PvVoltageE\",\"PCH_PvVoltageF\",\"PCH_PvCurrentA\",\"PCH_PvCurrentB\",\"PCH_PvCurrentC\",\"PCH_PvCurrentD\",\"PCH_PvCurrentE\",\"PCH_PvCurrentF\",\"PCH_BatteryPower\",\"PCH_AcRealPowerAB\",\"PCH_SlowPvPowerSum\",\"PCH_AcMode\",\"PCH_AcFrequency\",\"PCH_DcdcState_A\",\"PCH_DcdcState_B\",\"PCH_appGitHash\"],\"bmsComponentsFilter\":{\"types\":[\"PW3BMS\"]},\"bmsSignalNames\":[\"BMS_nominalEnergyRemaining\",\"BMS_nominalFullPackEnergy\",\"BMS_appGitHash\"],\"hvpComponentsFilter\":{\"types\":[\"PW3HVP\"]},\"hvpSignalNames\":[\"HVP_State\",\"HVP_appGitHash\"],\"baggrComponentsFilter\":{\"types\":[\"BAGGR\"]},\"baggrSignalNames\":[\"BAGGR_State\",\"BAGGR_OperationRequest\",\"BAGGR_NumBatteriesConnected\",\"BAGGR_NumBatteriesPresent\",\"BAGGR_NumBatteriesExpected\",\"BAGGR_LOG_BattConnectionStatus0\",\"BAGGR_LOG_BattConnectionStatus1\",\"BAGGR_LOG_BattConnectionStatus2\",\"BAGGR_LOG_BattConnectionStatus3\"]}"
            pb.tail.value = 1
            try:
                r = self._send_cmd(pb)
                log.debug(f"Response Code: {r.status_code}")
                if r.status_code in BUSY_CODES:
                    # Rate limited - Switch to cooldown mode for 5 minutes
                    self.pwcooldown = time.perf_counter() + 300
                    log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                    return None
                if r.status_code != HTTPStatus.OK:
                    log.error(f"Error fetching components: {r.status_code}")
                    return None
                tedapi = self._parse_response(r.content)
                payload = tedapi.message.graphql.recv.data
                log.debug(f"Payload (len={len(payload)}): {payload}")
                # Append payload to components
                components = json.loads(payload)
                log.debug(f"Components: {components}")
                self.pwcachetime["components"] = time.time()
                self.pwcache["components"] = components
            except Exception as e:
                log.error(f"Error fetching components: {e}")
                components = None
        return components


    def get_pw3_vitals(self, force=False):
        """
        Get Powerwall 3 Battery Vitals Data

        Returns:
        {
            "PVAC--{part}--{sn}" {
                "PVAC_PvState_A": "PV_Active",
                "PVAC_PVCurrent_A": 0.0,
                ...
                "PVAC_PVMeasuredVoltage_A": 0.0,
                ...
                "PVAC_PVMeasuredPower_A": 0.0,
                ...
                "PVAC_Fout": 60.0,
                "PVAC_Pout": 0.0,
                "PVAC_State": X,
                "PVAC_VL1Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL1Ground']),
                "PVAC_VL2Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL2Ground']),
                "PVAC_Vout": lookup(p, ['PVAC_Status', 'PVAC_Vout']),
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
            }.
            "PVS--{part}--{sn}" {
                "PVS_StringA_Connected": true,
                ...
            },
            "TEPOD--{part}--{sn}" {
                "alerts": [],
                "POD_nom_energy_remaining": 0.0,
                "POD_nom_full_pack_energy": 0.0,
                "POD_nom_energy_to_be_charged": 0.0,
            }
        }
        """
        # Check Connection
        if not self.din:
            if not self.connect():
                log.error("Not Connected - Unable to get configuration")
                return None
        # Check Cache
        if not force and "pw3_vitals" in self.pwcachetime:
            if time.time() - self.pwcachetime["pw3_vitals"] < self.pwconfigexpire:
                log.debug("Using Cached Components")
                return self.pwcache["pw3_vitals"]
        if not force and self.pwcooldown > time.perf_counter():
            # Rate limited - return None
            log.debug('Rate limit cooldown period - Pausing API calls')
            return None
        components = self.get_components(force=force)
        din = self.din
        if not components:
            log.error("Unable to get Powerwall 3 Components")
            return None

        response = {}
        config = self.get_config(force=force)
        battery_blocks = config.get('battery_blocks', {}) or {}
        # Check to see if there is only one Powerwall
        single_pw = False
        if battery_blocks and len(battery_blocks) == 1:
            single_pw = True
        # Loop through all the battery blocks (Powerwalls)
        for battery in battery_blocks:
            pw_din = battery['vin'] # 1707000-11-J--TG12xxxxxx3A8Z
            pw_part, pw_serial = pw_din.split('--')
            battery_type = battery['type']
            if "Powerwall3" not in battery_type:
                continue
            # Fetch Device ComponentsQuery from each Powerwall
            pb = tedapi_pb2.Message()
            pb.message.deliveryChannel = tedapi_pb2.DELIVERY_CHANNEL_LOCAL_HTTPS
            pb.message.sender.local = tedapi_pb2.LOCAL_PARTICIPANT_INSTALLER
            pb.message.sender.din = din  # DIN of Primary Powerwall 3 / System
            pb.message.recipient.din = pw_din  # DIN of Powerwall of Interest
            pb.message.graphql.send.format = tedapi_pb2.GRAPH_QL_QUERY_FORMAT_SIGNED_SHA256_ECDSA_ASN1
            pb.message.graphql.send.query = _build_signed_query(" query ComponentsQuery (\n  $pchComponentsFilter: ComponentFilter,\n  $pchSignalNames: [String!],\n  $pwsComponentsFilter: ComponentFilter,\n  $pwsSignalNames: [String!],\n  $bmsComponentsFilter: ComponentFilter,\n  $bmsSignalNames: [String!],\n  $hvpComponentsFilter: ComponentFilter,\n  $hvpSignalNames: [String!],\n  $baggrComponentsFilter: ComponentFilter,\n  $baggrSignalNames: [String!],\n  ) {\n  # TODO STST-57686: Introduce GraphQL fragments to shorten\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  components {\n    pws: components(filter: $pwsComponentsFilter) {\n      signals(names: $pwsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    pch: components(filter: $pchComponentsFilter) {\n      signals(names: $pchSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    bms: components(filter: $bmsComponentsFilter) {\n      signals(names: $bmsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    hvp: components(filter: $hvpComponentsFilter) {\n      partNumber\n      serialNumber\n      signals(names: $hvpSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    baggr: components(filter: $baggrComponentsFilter) {\n      signals(names: $baggrSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n  }\n}\n")
            pb.message.graphql.send.signature = b'0\201\210\002B\000\270q\354>\243m\325p\371S\253\231\346~:\032\216~\242\263\207\017L\273O\203u\241\270\333w\233\354\276\246h\262\243\255\261\007\202D\277\353x\023O\022\303\216\264\010-\'i6\360>B\237\236\304\244m\002B\001\023Pk\033)\277\236\342R\264\247g\260u\036\023\3662\354\242\353\035\221\234\027\245\321J\342\345\037q\262O\3446-\353\315m1\237zai0\341\207C4\307\300Z\177@h\335\327\0239\252f\n\206W'
            pb.message.graphql.send.variablesJson.value = "{\"pwsComponentsFilter\":{\"types\":[\"PW3SAF\"]},\"pwsSignalNames\":[\"PWS_SelfTest\",\"PWS_PeImpTestState\",\"PWS_PvIsoTestState\",\"PWS_RelaySelfTest_State\",\"PWS_MciTestState\",\"PWS_appGitHash\",\"PWS_ProdSwitch_State\"],\"pchComponentsFilter\":{\"types\":[\"PCH\"]},\"pchSignalNames\":[\"PCH_State\",\"PCH_PvState_A\",\"PCH_PvState_B\",\"PCH_PvState_C\",\"PCH_PvState_D\",\"PCH_PvState_E\",\"PCH_PvState_F\",\"PCH_AcFrequency\",\"PCH_AcVoltageAB\",\"PCH_AcVoltageAN\",\"PCH_AcVoltageBN\",\"PCH_packagePartNumber_1_7\",\"PCH_packagePartNumber_8_14\",\"PCH_packagePartNumber_15_20\",\"PCH_packageSerialNumber_1_7\",\"PCH_packageSerialNumber_8_14\",\"PCH_PvVoltageA\",\"PCH_PvVoltageB\",\"PCH_PvVoltageC\",\"PCH_PvVoltageD\",\"PCH_PvVoltageE\",\"PCH_PvVoltageF\",\"PCH_PvCurrentA\",\"PCH_PvCurrentB\",\"PCH_PvCurrentC\",\"PCH_PvCurrentD\",\"PCH_PvCurrentE\",\"PCH_PvCurrentF\",\"PCH_BatteryPower\",\"PCH_AcRealPowerAB\",\"PCH_SlowPvPowerSum\",\"PCH_AcMode\",\"PCH_AcFrequency\",\"PCH_DcdcState_A\",\"PCH_DcdcState_B\",\"PCH_appGitHash\"],\"bmsComponentsFilter\":{\"types\":[\"PW3BMS\"]},\"bmsSignalNames\":[\"BMS_nominalEnergyRemaining\",\"BMS_nominalFullPackEnergy\",\"BMS_appGitHash\"],\"hvpComponentsFilter\":{\"types\":[\"PW3HVP\"]},\"hvpSignalNames\":[\"HVP_State\",\"HVP_appGitHash\"],\"baggrComponentsFilter\":{\"types\":[\"BAGGR\"]},\"baggrSignalNames\":[\"BAGGR_State\",\"BAGGR_OperationRequest\",\"BAGGR_NumBatteriesConnected\",\"BAGGR_NumBatteriesPresent\",\"BAGGR_NumBatteriesExpected\",\"BAGGR_LOG_BattConnectionStatus0\",\"BAGGR_LOG_BattConnectionStatus1\",\"BAGGR_LOG_BattConnectionStatus2\",\"BAGGR_LOG_BattConnectionStatus3\"]}"
            if single_pw:
                # If only one Powerwall, use basic tedapi URL
                pb.tail.value = 1
                url = f'https://{self.gw_ip}/tedapi/v1'
            else:
                # If multiple Powerwalls, use tedapi/device/{pw_din}/v1
                pb.tail.value = 2
                pb.message.sender.din = din  # DIN of Primary Powerwall 3 / System
                url = f'https://{self.gw_ip}/tedapi/device/{pw_din}/v1'
            url = f'https://{self.gw_ip}/tedapi/device/{pw_din}/v1'
            r = self._send_cmd(pb, url=url)
            if r.status_code == HTTPStatus.OK:
                tedapi = self._parse_response(r.content)
                payload = tedapi.message.payload.recv.text
                if payload:
                    data = json.loads(payload)
                    # TEDPOD
                    alerts = []
                    components = data['components']
                    for component in components:
                        if components[component]:
                            for alert in components[component][0]['activeAlerts']:
                                if alert['name'] not in alerts:
                                    alerts.append(alert['name'])
                    bms_component = data['components']['bms'][0] # TODO: Process all BMS components
                    signals = bms_component['signals']
                    nom_energy_remaining = 0
                    nom_full_pack_energy = 0
                    for signal in signals:
                        if "BMS_nominalEnergyRemaining" == signal['name']:
                            nom_energy_remaining = int(signal['value'] * 1000) # Convert to Wh
                        elif "BMS_nominalFullPackEnergy" == signal['name']:
                            nom_full_pack_energy = int(signal['value'] * 1000) # Convert to Wh
                    response[f"TEPOD--{pw_din}"] = {
                        "alerts": alerts,
                        "POD_nom_energy_remaining": nom_energy_remaining,
                        "POD_nom_energy_to_be_charged": nom_full_pack_energy - nom_energy_remaining,
                        "POD_nom_full_pack_energy": nom_full_pack_energy,
                    }
                    # PVAC, PVS and TEPINV
                    response[f"PVAC--{pw_din}"] = {}
                    response[f"PVS--{pw_din}"] = {}
                    response[f"TEPINV--{pw_din}"] = {}
                    pch_components = data['components']['pch']
                    # pch_components contain:
                    #   PCH_PvState_A through F - textValue in [Pv_Active, Pv_Active_Parallel, Pv_Standby]
                    #   PCH_PvVoltageA through F - value
                    #   PCH_PvCurrentA through F - value
                    # Loop through and find all the strings - PW3 has 6 strings A-F
                    for n in ["A", "B", "C", "D", "E", "F"]:
                        pv_state = "Unknown"
                        pv_voltage = 0
                        pv_current = 0
                        for component in pch_components: # TODO: Probably better way to do this
                            signals = component['signals']
                            for signal in signals:
                                if f'PCH_PvState_{n}' == signal['name']:
                                    pv_state = signal['textValue']
                                elif f'PCH_PvVoltage{n}' == signal['name']:
                                    pv_voltage = signal['value'] if signal['value'] > 0 else 0
                                elif f'PCH_PvCurrent{n}' == signal['name']:
                                    pv_current = signal['value'] if signal['value'] > 0 else 0
                                elif 'PCH_AcFrequency' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_Fout"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_Fout"] = signal['value']
                                elif 'PCH_AcVoltageAN' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_VL1Ground"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_VSplit1"] = signal['value']
                                elif 'PCH_AcVoltageBN' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_VL2Ground"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_VSplit2"] = signal['value']
                                elif 'PCH_AcVoltageAB' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_Vout"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_Vout"] = signal['value']
                                elif 'PCH_AcRealPowerAB' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_Pout"] = signal['value']
                                    response[f"TEPINV--{pw_din}"]["PINV_Pout"] = (signal['value'] or 0) / 1000
                                elif 'PCH_AcMode' == signal['name']:
                                    response[f"PVAC--{pw_din}"]["PVAC_State"] = signal['textValue']
                                    response[f"TEPINV--{pw_din}"]["PINV_State"] = signal['textValue']
                        pv_power = pv_voltage * pv_current # Calculate power
                        response[f"PVAC--{pw_din}"][f"PVAC_PvState_{n}"] = pv_state
                        response[f"PVAC--{pw_din}"][f"PVAC_PVMeasuredVoltage_{n}"] = pv_voltage
                        response[f"PVAC--{pw_din}"][f"PVAC_PVCurrent_{n}"] = pv_current
                        response[f"PVAC--{pw_din}"][f"PVAC_PVMeasuredPower_{n}"] = pv_power
                        response[f"PVAC--{pw_din}"]["manufacturer"] = "TESLA"
                        response[f"PVAC--{pw_din}"]["partNumber"] = pw_part
                        response[f"PVAC--{pw_din}"]["serialNumber"] = pw_serial
                        response[f"PVS--{pw_din}"][f"PVS_String{n}_Connected"] = ("Pv_Active" in pv_state)
                else:
                    log.debug(f"No payload for {pw_din}")
            else:
                log.debug(f"Error fetching components: {r.status_code}")
        return response


    def get_battery_blocks(self, force=False):
        """
        Return Powerwall Battery Blocks
        """
        config = self.get_config(force=force)
        battery_blocks = config.get('battery_blocks') or []
        return battery_blocks


    @uses_api_lock
    def get_battery_block(self, self_function, din=None, force=False):
        """
        Get the Powerwall 3 Battery Block Information

        Args:
            din (str): DIN of Powerwall 3 to query
            force (bool): Force a refresh of the battery block

        Note: Provides 404 response for previous Powerwall versions
        """
        # Make sure we have a DIN
        if not din:
            log.error("No DIN specified - Unable to get battery block")
            return None
        data = None
        with acquire_lock_with_backoff(self_function, self.timeout):
            # Check Cache
            if not force and din in self.pwcachetime:
                if time.time() - self.pwcachetime[din] < self.pwcacheexpire:
                    log.debug("Using Cached Battery Block")
                    return self.pwcache[din]
            if not force and self.pwcooldown > time.perf_counter():
                # Rate limited - return None
                log.debug('Rate limit cooldown period - Pausing API calls')
                return None
            # Fetch Battery Block from Powerwall
            log.debug(f"Get Battery Block from Powerwall ({din})")
            # Build Protobuf to fetch config
            pb = tedapi_pb2.Message()
            pb.message.deliveryChannel = tedapi_pb2.DELIVERY_CHANNEL_LOCAL_HTTPS
            pb.message.sender.local = tedapi_pb2.LOCAL_PARTICIPANT_INSTALLER
            pb.message.sender.din = self.din  # DIN of Primary Powerwall 3 / System
            pb.message.recipient.din = din  # DIN of Powerwall of Interest
            pb.message.graphql.send.format = tedapi_pb2.GRAPH_QL_QUERY_FORMAT_SIGNED_SHA256_ECDSA_ASN1
            pb.message.graphql.send.query = _build_signed_query(" query ComponentsQuery (\n  $pchComponentsFilter: ComponentFilter,\n  $pchSignalNames: [String!],\n  $pwsComponentsFilter: ComponentFilter,\n  $pwsSignalNames: [String!],\n  $bmsComponentsFilter: ComponentFilter,\n  $bmsSignalNames: [String!],\n  $hvpComponentsFilter: ComponentFilter,\n  $hvpSignalNames: [String!],\n  $baggrComponentsFilter: ComponentFilter,\n  $baggrSignalNames: [String!],\n  ) {\n  # TODO STST-57686: Introduce GraphQL fragments to shorten\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  components {\n    pws: components(filter: $pwsComponentsFilter) {\n      signals(names: $pwsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    pch: components(filter: $pchComponentsFilter) {\n      signals(names: $pchSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    bms: components(filter: $bmsComponentsFilter) {\n      signals(names: $bmsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    hvp: components(filter: $hvpComponentsFilter) {\n      partNumber\n      serialNumber\n      signals(names: $hvpSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    baggr: components(filter: $baggrComponentsFilter) {\n      signals(names: $baggrSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n  }\n}\n")
            pb.message.graphql.send.signature = b'0\201\210\002B\000\270q\354>\243m\325p\371S\253\231\346~:\032\216~\242\263\207\017L\273O\203u\241\270\333w\233\354\276\246h\262\243\255\261\007\202D\277\353x\023O\022\303\216\264\010-\'i6\360>B\237\236\304\244m\002B\001\023Pk\033)\277\236\342R\264\247g\260u\036\023\3662\354\242\353\035\221\234\027\245\321J\342\345\037q\262O\3446-\353\315m1\237zai0\341\207C4\307\300Z\177@h\335\327\0239\252f\n\206W'
            pb.message.payload.send.variablesJson.value = "{\"pwsComponentsFilter\":{\"types\":[\"PW3SAF\"]},\"pwsSignalNames\":[\"PWS_SelfTest\",\"PWS_PeImpTestState\",\"PWS_PvIsoTestState\",\"PWS_RelaySelfTest_State\",\"PWS_MciTestState\",\"PWS_appGitHash\",\"PWS_ProdSwitch_State\"],\"pchComponentsFilter\":{\"types\":[\"PCH\"]},\"pchSignalNames\":[\"PCH_State\",\"PCH_PvState_A\",\"PCH_PvState_B\",\"PCH_PvState_C\",\"PCH_PvState_D\",\"PCH_PvState_E\",\"PCH_PvState_F\",\"PCH_AcFrequency\",\"PCH_AcVoltageAB\",\"PCH_AcVoltageAN\",\"PCH_AcVoltageBN\",\"PCH_packagePartNumber_1_7\",\"PCH_packagePartNumber_8_14\",\"PCH_packagePartNumber_15_20\",\"PCH_packageSerialNumber_1_7\",\"PCH_packageSerialNumber_8_14\",\"PCH_PvVoltageA\",\"PCH_PvVoltageB\",\"PCH_PvVoltageC\",\"PCH_PvVoltageD\",\"PCH_PvVoltageE\",\"PCH_PvVoltageF\",\"PCH_PvCurrentA\",\"PCH_PvCurrentB\",\"PCH_PvCurrentC\",\"PCH_PvCurrentD\",\"PCH_PvCurrentE\",\"PCH_PvCurrentF\",\"PCH_BatteryPower\",\"PCH_AcRealPowerAB\",\"PCH_SlowPvPowerSum\",\"PCH_AcMode\",\"PCH_AcFrequency\",\"PCH_DcdcState_A\",\"PCH_DcdcState_B\",\"PCH_appGitHash\"],\"bmsComponentsFilter\":{\"types\":[\"PW3BMS\"]},\"bmsSignalNames\":[\"BMS_nominalEnergyRemaining\",\"BMS_nominalFullPackEnergy\",\"BMS_appGitHash\"],\"hvpComponentsFilter\":{\"types\":[\"PW3HVP\"]},\"hvpSignalNames\":[\"HVP_State\",\"HVP_appGitHash\"],\"baggrComponentsFilter\":{\"types\":[\"BAGGR\"]},\"baggrSignalNames\":[\"BAGGR_State\",\"BAGGR_OperationRequest\",\"BAGGR_NumBatteriesConnected\",\"BAGGR_NumBatteriesPresent\",\"BAGGR_NumBatteriesExpected\",\"BAGGR_LOG_BattConnectionStatus0\",\"BAGGR_LOG_BattConnectionStatus1\",\"BAGGR_LOG_BattConnectionStatus2\",\"BAGGR_LOG_BattConnectionStatus3\"]}"
            pb.tail.value = 2
            url = f'https://{self.gw_ip}/tedapi/device/{din}/v1'
            try:
                r = self._send_cmd(pb, url=url)
                log.debug(f"Response Code: {r.status_code}")
                if r.status_code in BUSY_CODES:
                    # Rate limited - Switch to cooldown mode for 5 minutes
                    self.pwcooldown = time.perf_counter() + 300
                    log.error('Possible Rate limited by Powerwall at - Activating 5 minute cooldown')
                    return None
                if r.status_code == 404:
                    log.debug(f"Device not found: {din}")
                    return None
                if r.status_code != 200:
                    log.error(f"Error fetching config: {r.status_code}")
                    return None
                tedapi = self._parse_response(r.content)
                payload = tedapi.message.filestore.readFileResponse.file.blob.decode('utf-8')
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError as e:
                    log.error(f"Error Decoding JSON: {e}")
                    data = {}
                log.debug(f"Configuration: {data}")
                self.pwcachetime[din] = time.time()
                self.pwcache[din] = data
            except Exception as e:
                log.error(f"Error fetching device: {e}")
                data = None
        return data

    def _init_session(self):
        session = requests.Session()
        if self.poolmaxsize > 0:
            retries = urllib3.Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=RETRY_FORCE_CODES,
                raise_on_status=False
            )
            adapter = HTTPAdapter(max_retries=retries, pool_connections=self.poolmaxsize, pool_maxsize=self.poolmaxsize, pool_block=True)
            session.mount("https://", adapter)
        else:
            session.headers.update({'Connection': 'close'})  # This disables keep-alive
        session.verify = False
        if self.auth_mode == "bearer":
            session.headers.update({'Content-type': 'application/octet-stream'})
        else:
            session.auth = ('Tesla_Energy_Device', self.gw_pwd)
            session.headers.update({'Content-type': 'application/octet-string'})
        return session

    def _bearer_login(self):
        """Authenticate via /api/login/Basic and store Bearer token on session."""
        url = f'https://{self.gw_ip}/api/login/Basic'
        payload = {
            "username": "installer",
            "password": self.gw_pwd,
            "email": "installer@tesla.com",
            "clientInfo": {"timezone": "America/Los_Angeles"},
        }
        log.debug(f"Bearer login to {url}")
        r = self.session.post(url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if "token" not in data:
            raise ValueError("Login response missing 'token' field")
        self.token = data["token"]
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        log.debug(f"Bearer token acquired ({len(self.token)} chars)")

    def _bearer_logout(self):
        """Invalidate the Bearer token session."""
        if not self.token:
            return
        try:
            self.session.get(
                f'https://{self.gw_ip}/api/logout',
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
        except Exception:
            pass
        self.token = None
        self.session.headers.pop("Authorization", None)

    def _send_cmd(self, pb, url=None):
        """Send a protobuf command to a TEDAPI endpoint.

        In basic mode, sends the raw serialized Message.
        In bearer mode, wraps the inner MessageEnvelope in an AuthEnvelope
        with EXTERNAL_AUTH_TYPE_PRESENCE.

        Args:
            pb: The tedapi_pb2.Message to send
            url: Override URL (default: https://{gw_ip}/tedapi/v1)

        Returns the requests.Response object.
        """
        if self.auth_mode == "bearer":
            auth_env = tedapi_pb2.AuthEnvelope()
            auth_env.payload = pb.message.SerializeToString()
            auth_env.externalAuth.type = 1  # EXTERNAL_AUTH_TYPE_PRESENCE
            data = auth_env.SerializeToString()
        else:
            data = pb.SerializeToString()

        if url is None:
            url = f'https://{self.gw_ip}/tedapi/v1'
        r = self.session.post(url, data=data, timeout=self.timeout)

        # Bearer mode: auto-relogin on 401/403
        if self.auth_mode == "bearer" and r.status_code in (
            HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN
        ):
            log.debug("Bearer token expired or rejected, re-authenticating...")
            try:
                self._bearer_login()
                # Re-wrap with fresh session state
                if self.auth_mode == "bearer":
                    auth_env = tedapi_pb2.AuthEnvelope()
                    auth_env.payload = pb.message.SerializeToString()
                    auth_env.externalAuth.type = 1
                    data = auth_env.SerializeToString()
                r = self.session.post(url, data=data, timeout=self.timeout)
            except Exception as e:
                log.error(f"Bearer re-authentication failed: {e}")

        return r

    def _parse_response(self, content):
        """Parse a TEDAPI protobuf response.

        In basic mode, parses raw content as a Message.
        In bearer mode, unwraps the AuthEnvelope first, then parses the
        inner payload as a MessageEnvelope.

        Returns a tedapi_pb2.Message object.
        """
        content = decompress_response(content)
        if self.auth_mode == "bearer":
            auth_resp = tedapi_pb2.AuthEnvelope()
            auth_resp.ParseFromString(content)
            tedapi = tedapi_pb2.Message()
            tedapi.message.ParseFromString(auth_resp.payload)
        else:
            tedapi = tedapi_pb2.Message()
            tedapi.ParseFromString(content)
        return tedapi

    def connect(self):
        """
        Connect to the Powerwall Gateway
        """
        # Test IP Connection to Powerwall Gateway
        log.debug(f"Testing Connection to Powerwall Gateway: {self.gw_ip}")
        url = f'https://{self.gw_ip}'
        self.din = None
        self.session = self._init_session()
        try:
            resp = self.session.get(url, timeout=5)
            if self.auth_mode == "bearer":
                # Bearer mode: login first to get token
                self._bearer_login()
            else:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code != HTTPStatus.OK:
                    # Connected but appears to be Powerwall 3
                    log.debug("Detected Powerwall 3 Gateway")
                    self.pw3 = True
            self.din = self.get_din()
        except Exception as e:
            log.error(f"Unable to connect to Powerwall Gateway {self.gw_ip}")
            if self.auth_mode == "basic":
                log.error("Please verify your host has a route to the Gateway.")
            else:
                log.error("Please verify the gateway password and that the host is reachable.")
            log.error(f"Error Details: {e}")
        return self.din

    # Handy Function to access Powerwall Status
    def current_power(self, location=None, force=False):
        """
        Get the current power in watts for a location:
            BATTERY, SITE, LOAD, SOLAR, SOLAR_RGM, GENERATOR, CONDUCTOR
        """
        status = self.get_status(force=force)
        power = lookup(status, ['control', 'meterAggregates'])
        if not isinstance(power, list):
            return None
        if location:
            for p in power:
                if p.get('location') == location.upper():
                    return p.get('realPowerW')
        else:
            # Build a dictionary of all locations
            power = {}
            for p in power:
                power[p.get('location')] = p.get('realPowerW')
        return power


    def backup_time_remaining(self, force=False):
        """
        Get the time remaining in hours
        """
        status = self.get_status(force=force)
        nominalEnergyRemainingWh = lookup(status, ['control', 'systemStatus', 'nominalEnergyRemainingWh'])
        load = self.current_power('LOAD', force)
        if not nominalEnergyRemainingWh or not load:
            return None
        time_remaining = nominalEnergyRemainingWh / load
        return time_remaining


    def battery_level(self, force=False):
        """
        Get the battery level as a percentage
        """
        status = self.get_status(force=force)
        nominalEnergyRemainingWh = lookup(status, ['control', 'systemStatus', 'nominalEnergyRemainingWh'])
        nominalFullPackEnergyWh = lookup(status, ['control', 'systemStatus', 'nominalFullPackEnergyWh'])
        if not nominalEnergyRemainingWh or not nominalFullPackEnergyWh:
            return None
        battery_level = nominalEnergyRemainingWh / nominalFullPackEnergyWh * 100
        return battery_level


    # Helper Function
    def extract_fan_speeds(self, data) -> Dict[str, Dict[str, str]]:
        """Extract fan speed signals from device controller data.

        Primary path: esCan.bus.PVAC[].PVAC_Logging (new APK query location).
        Fallback: components.msa[].signals[] (older firmware compatibility).
        """
        if not isinstance(data, dict):
            return {}

        fan_speed_signal_names = {"PVAC_Fan_Speed_Actual_RPM", "PVAC_Fan_Speed_Target_RPM"}
        result = {}

        # Primary: fan speeds are now in esCan.bus.PVAC[].PVAC_Logging
        pvac_list = lookup(data, ['esCan', 'bus', 'PVAC']) or []
        for pvac in pvac_list:
            logging_data = pvac.get("PVAC_Logging", {}) or {}
            fan_speeds = {
                name: logging_data[name]
                for name in fan_speed_signal_names
                if name in logging_data and logging_data[name] is not None
            }
            if not fan_speeds:
                continue
            part = pvac.get("packagePartNumber")
            serial = pvac.get("packageSerialNumber")
            result[f"PVAC--{part}--{serial}"] = fan_speeds

        # Fallback: older firmware may still have fan speeds in components.msa signals
        if not result:
            components = data.get("components", {})
            if isinstance(components, dict):
                for component in components.get("msa", []):
                    signals = component.get("signals", [])
                    fan_speeds = {
                        signal["name"]: signal["value"]
                        for signal in signals
                        if signal.get("name") in fan_speed_signal_names and signal.get("value") is not None
                    }
                    if not fan_speeds:
                        continue
                    part = component.get("partNumber")
                    serial = component.get("serialNumber")
                    result[f"PVAC--{part}--{serial}"] = fan_speeds

        return result

    def get_fan_speeds(self, force=False):
        """Get the fan speeds for the Powerwall or inverter."""
        return self.extract_fan_speeds(self.get_device_controller(force=force))

    def derive_meter_config(self, config) -> dict:
        # Build meter Lookup if available
        meter_config = {}
        if not "meters" in config:
            return meter_config
        # Loop through each meter and use device_serial as the key
        for meter in config['meters']:
            if meter.get('type') != "neurio_w2_tcp":
                continue
            device_serial = lookup(meter, ['connection', 'device_serial'])
            if not device_serial:
                continue
            # Check to see if we already have this meter in meter_config
            if device_serial in meter_config:
                cts = meter.get('cts', [False] * 4)
                if not isinstance(cts, list):
                    cts = [False] * 4
                for i, ct in enumerate(cts):
                    if not ct:
                        continue
                    meter_config[device_serial]['cts'][i] = True
                    meter_config[device_serial]['location'][i] = meter.get('location', "")
            else:
                # New meter, add to meter_config
                cts = meter.get('cts', [False] * 4)
                if not isinstance(cts, list):
                    cts = [False] * 4
                location = meter.get('location', "")
                meter_config[device_serial] = {
                    "type": meter.get('type'),
                    "location": [location] * 4,
                    "cts": cts,
                    "inverted": meter.get('inverted'),
                    "connection": meter.get('connection'),
                    "real_power_scale_factor": meter.get('real_power_scale_factor', 1)
                }
        return meter_config


    def aggregate_neurio_data(self, config_data, status_data, meter_config_data) -> Tuple[dict, dict]:
        # Create NEURIO block
        neurio_flat = {}
        neurio_hierarchy = {}
        # Loop through each Neurio device serial number
        for c, n in enumerate(lookup(status_data, ['neurio', 'readings']) or {}, start=1000):
            # Loop through each CT on the Neurio device
            sn = n.get('serial', str(c))
            cts_flat = {}
            for i, ct in enumerate(n['dataRead'] or {}):
                # Only show if we have a meter configuration and cts[i] is true
                cts_bool = lookup(meter_config_data, [sn, 'cts'])
                if isinstance(cts_bool, list) and i < len(cts_bool):
                    if not cts_bool[i]:
                        # Skip this CT
                        continue
                factor = lookup(meter_config_data, [sn, 'real_power_scale_factor']) or 1
                location = lookup(meter_config_data, [sn, 'location'])
                ct_hierarchy = {
                    "Index": i,
                    "InstRealPower": ct.get('realPowerW', 0) * factor,
                    "InstReactivePower": ct.get('reactivePowerVAR'),
                    "InstVoltage": ct.get('voltageV'),
                    "InstCurrent": ct.get('currentA'),
                    "Location": location[i] if location and len(location) > i else None
                }
                neurio_hierarchy[f"CT{i}"] = ct_hierarchy
                cts_flat.update({f"NEURIO_CT{i}_" + key: value for key, value in ct_hierarchy.items() if key != "Index"})
            meter_manufacturer = "NEURIO" if lookup(meter_config_data, [sn, "type"]) == "neurio_w2_tcp" else None
            rest = {
                "componentParentDin": lookup(config_data, ['vin']),
                "firmwareVersion": None,
                "lastCommunicationTime": lookup(n, ['timestamp']),
                "manufacturer": meter_manufacturer,
                "meterAttributes": {
                    "meterLocation": []
                },
                "serialNumber": sn
            }
            neurio_flat[f"NEURIO--{sn}"] = {**cts_flat, **rest}
        return (neurio_flat, neurio_hierarchy)


    # Vitals API Mapping Function
    def vitals(self, force=False):
        """
        Use tedapi data to create a vitals API dictionary
        """
        def calculate_ac_power(Vpeak, Ipeak):
            Vrms = Vpeak / math.sqrt(2)
            Irms = Ipeak / math.sqrt(2)
            power = Vrms * Irms
            return power

        def calculate_dc_power(V, I):
            power = V * I
            return power

        # status = self.get_status(force)
        config = self.get_config(force=force)
        status = self.get_device_controller(force=force)

        if not isinstance(status, dict) or not isinstance(config, dict):
            return None

        # Create Header
        tesla = {}
        header = {}
        header["VITALS"] = {
            "text": "Device vitals generated from Tesla Powerwall Gateway TEDAPI",
            "timestamp": time.time(),
            "gateway": self.gw_ip,
            "pyPowerwall": __version__,
        }
        neurio = self.aggregate_neurio_data(
            config_data=config,
            status_data=status,
            meter_config_data=self.derive_meter_config(config)
        )[0]

        # Create PVAC, PVS, and TESLA blocks - Assume the are aligned
        pvac = {}
        pvs = {}
        tesla = {}
        num = len(lookup(status, ['esCan', 'bus', 'PVAC']) or {})
        if num != len(lookup(status, ['esCan', 'bus', 'PVS']) or {}):
            log.debug("PVAC and PVS device count mismatch in TEDAPI")
        # Loop through each device serial number

        fan_speeds = self.extract_fan_speeds(status)

        for i, p in enumerate(lookup(status, ['esCan', 'bus', 'PVAC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            pvac_name = f"PVAC--{packagePartNumber}--{packageSerialNumber}"
            pvac_logging = p['PVAC_Logging']
            V_A = pvac_logging['PVAC_PVMeasuredVoltage_A']
            V_B = pvac_logging['PVAC_PVMeasuredVoltage_B']
            V_C = pvac_logging['PVAC_PVMeasuredVoltage_C']
            V_D = pvac_logging['PVAC_PVMeasuredVoltage_D']
            I_A = pvac_logging['PVAC_PVCurrent_A']
            I_B = pvac_logging['PVAC_PVCurrent_B']
            I_C = pvac_logging['PVAC_PVCurrent_C']
            I_D = pvac_logging['PVAC_PVCurrent_D']
            P_A = calculate_dc_power(V_A, I_A)
            P_B = calculate_dc_power(V_B, I_B)
            P_C = calculate_dc_power(V_C, I_C)
            P_D = calculate_dc_power(V_D, I_D)
            pvac[pvac_name] = {
                "PVAC_Fout": lookup(p, ['PVAC_Status', 'PVAC_Fout']),
                "PVAC_GridState": None,
                "PVAC_InvState": None,
                "PVAC_Iout": None,
                "PVAC_LifetimeEnergyPV_Total": None,
                "PVAC_PVCurrent_A": I_A,
                "PVAC_PVCurrent_B": I_B,
                "PVAC_PVCurrent_C": I_C,
                "PVAC_PVCurrent_D": I_D,
                "PVAC_PVMeasuredPower_A": P_A, # computed
                "PVAC_PVMeasuredPower_B": P_B, # computed
                "PVAC_PVMeasuredPower_C": P_C, # computed
                "PVAC_PVMeasuredPower_D": P_D, # computed
                "PVAC_PVMeasuredVoltage_A": V_A,
                "PVAC_PVMeasuredVoltage_B": V_B,
                "PVAC_PVMeasuredVoltage_C": V_C,
                "PVAC_PVMeasuredVoltage_D": V_D,
                "PVAC_Pout": lookup(p, ['PVAC_Status', 'PVAC_Pout']),
                "PVAC_PvState_A": None, # These are placeholders
                "PVAC_PvState_B": None, # Compute from PVS below
                "PVAC_PvState_C": None, # PV_Disabled, PV_Active, PV_Active_Parallel
                "PVAC_PvState_D": None, # Not available in TEDAPI
                "PVAC_Qout": None,
                "PVAC_State": lookup(p, ['PVAC_Status', 'PVAC_State']),
                "PVAC_VHvMinusChassisDC": None,
                "PVAC_VL1Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL1Ground']),
                "PVAC_VL2Ground": lookup(p, ['PVAC_Logging', 'PVAC_VL2Ground']),
                "PVAC_Vout": lookup(p, ['PVAC_Status', 'PVAC_Vout']),
                "alerts": lookup(p, ['alerts', 'active']) or [],
                "PVI-PowerStatusSetpoint": None,
                "componentParentDin": None, # TODO: map to TETHC
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 296
                }
            }
            pvac_fans = fan_speeds.get(pvac_name, {})
            if pvac_fans:
                pvac[pvac_name].update({
                    "PVAC_Fan_Speed_Actual_RPM": pvac_fans["PVAC_Fan_Speed_Actual_RPM"],
                    "PVAC_Fan_Speed_Target_RPM": pvac_fans["PVAC_Fan_Speed_Target_RPM"]
                })

            pvs_name = f"PVS--{packagePartNumber}--{packageSerialNumber}"
            pvs_data = lookup(status, ['esCan', 'bus', 'PVS'])
            if i < len(pvs_data):
                pvs_data = pvs_data[i]
                # Set String Connected states
                string_a = lookup(pvs_data, ['PVS_Status', 'PVS_StringA_Connected'])
                string_b = lookup(pvs_data, ['PVS_Status', 'PVS_StringB_Connected'])
                string_c = lookup(pvs_data, ['PVS_Status', 'PVS_StringC_Connected'])
                string_d = lookup(pvs_data, ['PVS_Status', 'PVS_StringD_Connected'])
                # Set PVAC PvState based on PVS String Connected states
                pvac[pvac_name]["PVAC_PvState_A"] = "PV_Active" if string_a else "PV_Disabled"
                pvac[pvac_name]["PVAC_PvState_B"] = "PV_Active" if string_b else "PV_Disabled"
                pvac[pvac_name]["PVAC_PvState_C"] = "PV_Active" if string_c else "PV_Disabled"
                pvac[pvac_name]["PVAC_PvState_D"] = "PV_Active" if string_d else "PV_Disabled"
                pvs[pvs_name] = {
                    "PVS_EnableOutput": None,
                    "PVS_SelfTestState": lookup(pvs_data, ['PVS_Status', 'PVS_SelfTestState']),
                    "PVS_State": lookup(pvs_data, ['PVS_Status', 'PVS_State']),
                    "PVS_StringA_Connected": string_a,
                    "PVS_StringB_Connected": string_b,
                    "PVS_StringC_Connected": string_c,
                    "PVS_StringD_Connected": string_d,
                    "PVS_vLL": lookup(pvs_data, ['PVS_Status', 'PVS_vLL']),
                    "alerts": lookup(pvs_data, ['alerts', 'active']) or [],
                    "componentParentDin": pvac_name,
                    "firmwareVersion": None,
                    "lastCommunicationTime": None,
                    "manufacturer": "TESLA",
                    "partNumber": packagePartNumber,
                    "serialNumber": packageSerialNumber,
                    "teslaEnergyEcuAttributes": {
                        "ecuType": 297
                    }
                }
            tesla_name = f"TESLA--{packagePartNumber}--{packageSerialNumber}"
            if "solars" in config and i < len(config.get('solars', [{}])):
                tesla_nameplate = config['solars'][i].get('power_rating_watts', None)
                brand = config['solars'][i].get('brand', None)
            else:
                tesla_nameplate = None
                brand = None
            tesla[tesla_name] = {
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": brand.upper() if brand else "TESLA",
                "pvInverterAttributes": {
                    "nameplateRealPowerW": tesla_nameplate,
                },
                "serialNumber": f"{packagePartNumber}--{packageSerialNumber}",
            }

        # Create STSTSM block
        name = f"STSTSM--{lookup(config, ['vin'])}"
        ststsm = {}
        ststsm[name] =  {
            "STSTSM-Location": "Gateway",
            "alerts": lookup(status, ['control', 'alerts', 'active']) or [],
            "firmwareVersion": None,
            "lastCommunicationTime": None,
            "manufacturer": "TESLA",
            "partNumber": lookup(config, ['vin']).split('--')[0],
            "serialNumber": lookup(config, ['vin']).split('--')[-1],
            "teslaEnergyEcuAttributes": {
                "ecuType": 207
            }
        }

        # Get Dictionary of Powerwall Temperatures
        temp_sensors = {}
        for component in lookup(status, ['components', 'msa']) or []:
            serial = component.get("serialNumber")
            if not serial:
                continue
            for signal in component.get("signals", []):
                if signal.get("name") == "THC_AmbientTemp" and "value" in signal:
                    temp_sensors[serial] = signal["value"]

        # Create TETHC, TEPINV and TEPOD blocks
        tethc = {} # parent
        tepinv = {}
        tepod = {}
        # Loop through each THC device serial number
        for i, p in enumerate(lookup(status, ['esCan', 'bus', 'THC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            # TETHC block
            parent_name = f"TETHC--{packagePartNumber}--{packageSerialNumber}"
            tethc[parent_name] = {
                "THC_AmbientTemp": temp_sensors.get(packageSerialNumber, None),
                "THC_State": None,
                "alerts": lookup(p, ['alerts', 'active']) or [],
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 224
                }
            }
            # TEPOD block
            name = f"TEPOD--{packagePartNumber}--{packageSerialNumber}"
            pod = lookup(status, ['esCan', 'bus', 'POD'])[i]
            energy_remaining = lookup(pod, ['POD_EnergyStatus', 'POD_nom_energy_remaining'])
            full_pack_energy = lookup(pod, ['POD_EnergyStatus', 'POD_nom_full_pack_energy'])
            if energy_remaining and full_pack_energy:
                energy_to_be_charged = full_pack_energy - energy_remaining
            else:
                energy_to_be_charged = None
            tepod[name] = {
                "POD_ActiveHeating": None,
                "POD_CCVhold": None,
                "POD_ChargeComplete": None,
                "POD_ChargeRequest": None,
                "POD_DischargeComplete": None,
                "POD_PermanentlyFaulted": None,
                "POD_PersistentlyFaulted": None,
                "POD_available_charge_power": None,
                "POD_available_dischg_power": None,
                "POD_enable_line": None,
                "POD_nom_energy_remaining": energy_remaining,
                "POD_nom_energy_to_be_charged": energy_to_be_charged, #computed
                "POD_nom_full_pack_energy": full_pack_energy,
                "POD_state": None,
                "alerts": lookup(p, ['alerts', 'active']) or [],
                "componentParentDin": parent_name,
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 226
                }
            }
            # TEPINV block
            name = f"TEPINV--{packagePartNumber}--{packageSerialNumber}"
            pinv = lookup(status, ['esCan', 'bus', 'PINV'])[i]
            tepinv[name] = {
                "PINV_EnergyCharged": None,
                "PINV_EnergyDischarged": None,
                "PINV_Fout": lookup(pinv, ['PINV_Status', 'PINV_Fout']),
                "PINV_GridState": lookup(p, ['PINV_Status', 'PINV_GridState']),
                "PINV_HardwareEnableLine": None,
                "PINV_PllFrequency": None,
                "PINV_PllLocked": None,
                "PINV_Pnom": lookup(pinv, ['PINV_PowerCapability', 'PINV_Pnom']),
                "PINV_Pout": lookup(pinv, ['PINV_Status', 'PINV_Pout']),
                "PINV_PowerLimiter": None,
                "PINV_Qout": None,
                "PINV_ReadyForGridForming": None,
                "PINV_State": lookup(pinv, ['PINV_Status', 'PINV_State']),
                "PINV_VSplit1": lookup(pinv, ['PINV_AcMeasurements', 'PINV_VSplit1']),
                "PINV_VSplit2": lookup(pinv, ['PINV_AcMeasurements', 'PINV_VSplit2']),
                "PINV_Vout": lookup(pinv, ['PINV_Status', 'PINV_Vout']),
                "alerts": lookup(pinv, ['alerts', 'active']) or [],
                "componentParentDin": parent_name,
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 253
                }
            }

        # Create TESYNC block
        tesync = {}
        sync = lookup(status, ['esCan', 'bus', 'SYNC']) or {}
        islander = lookup(status, ['esCan', 'bus', 'ISLANDER']) or {}
        packagePartNumber = sync.get('packagePartNumber', None)
        packageSerialNumber = sync.get('packageSerialNumber', None)
        name = f"TESYNC--{packagePartNumber}--{packageSerialNumber}"
        tesync[name] = {
            "ISLAND_FreqL1_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL1_Load']),
            "ISLAND_FreqL1_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL1_Main']),
            "ISLAND_FreqL2_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL2_Load']),
            "ISLAND_FreqL2_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL2_Main']),
            "ISLAND_FreqL3_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL3_Load']),
            "ISLAND_FreqL3_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_FreqL3_Main']),
            "ISLAND_GridConnected": lookup(islander, ['ISLAND_GridConnection', 'ISLAND_GridConnected']),
            "ISLAND_GridState": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_GridState']),
            "ISLAND_L1L2PhaseDelta":lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L1L2PhaseDelta']),
            "ISLAND_L1L3PhaseDelta": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L1L3PhaseDelta']),
            "ISLAND_L1MicrogridOk": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L1MicrogridOk']),
            "ISLAND_L2L3PhaseDelta": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L2L3PhaseDelta']),
            "ISLAND_L2MicrogridOk": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L2MicrogridOk']),
            "ISLAND_L3MicrogridOk": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_L3MicrogridOk']),
            "ISLAND_PhaseL1_Main_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_PhaseL1_Main_Load']),
            "ISLAND_PhaseL2_Main_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_PhaseL2_Main_Load']),
            "ISLAND_PhaseL3_Main_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_PhaseL3_Main_Load']),
            "ISLAND_ReadyForSynchronization": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_ReadyForSynchronization']),
            "ISLAND_VL1N_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL1N_Load']),
            "ISLAND_VL1N_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL1N_Main']),
            "ISLAND_VL2N_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL2N_Load']),
            "ISLAND_VL2N_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL2N_Main']),
            "ISLAND_VL3N_Load": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL3N_Load']),
            "ISLAND_VL3N_Main": lookup(islander, ['ISLAND_AcMeasurements', 'ISLAND_VL3N_Main']),
            "METER_X_CTA_I": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTA_I']),
            "METER_X_CTA_InstReactivePower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTA_InstReactivePower']),
            "METER_X_CTA_InstRealPower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTA_InstRealPower']),
            "METER_X_CTB_I": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTB_I']),
            "METER_X_CTB_InstReactivePower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTB_InstReactivePower']),
            "METER_X_CTB_InstRealPower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTB_InstRealPower']),
            "METER_X_CTC_I": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTC_I']),
            "METER_X_CTC_InstReactivePower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTC_InstReactivePower']),
            "METER_X_CTC_InstRealPower": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_CTC_InstRealPower']),
            "METER_X_LifetimeEnergyExport": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_LifetimeEnergyExport']),
            "METER_X_LifetimeEnergyImport": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_LifetimeEnergyImport']),
            "METER_X_VL1N": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_VL1N']),
            "METER_X_VL2N": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_VL2N']),
            "METER_X_VL3N": lookup(sync, ['METER_X_AcMeasurements', 'METER_X_VL3N']),
            "METER_Y_CTA_I": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTA_I']),
            "METER_Y_CTA_InstReactivePower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTA_InstReactivePower']),
            "METER_Y_CTA_InstRealPower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTA_InstRealPower']),
            "METER_Y_CTB_I": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTB_I']),
            "METER_Y_CTB_InstReactivePower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTB_InstReactivePower']),
            "METER_Y_CTB_InstRealPower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTB_InstRealPower']),
            "METER_Y_CTC_I": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTC_I']),
            "METER_Y_CTC_InstReactivePower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTC_InstReactivePower']),
            "METER_Y_CTC_InstRealPower": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_CTC_InstRealPower']),
            "METER_Y_LifetimeEnergyExport": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_LifetimeEnergyExport']),
            "METER_Y_LifetimeEnergyImport": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_LifetimeEnergyImport']),
            "METER_Y_VL1N": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_VL1N']),
            "METER_Y_VL2N": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_VL2N']),
            "METER_Y_VL3N": lookup(sync, ['METER_Y_AcMeasurements', 'METER_Y_VL3N']),
            "SYNC_ExternallyPowered": None,
            "SYNC_SiteSwitchEnabled": None,
            "alerts": lookup(sync, ['alerts', 'active']) or [],
            "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
            "firmwareVersion": None,
            "manufacturer": "TESLA",
            "partNumber": packagePartNumber,
            "serialNumber": packageSerialNumber,
            "teslaEnergyEcuAttributes": {
                "ecuType": 259
            }
        }

        # Create TESLA block - tied to TESYNC
        name = f"TESLA--{packageSerialNumber}"
        tesla[name] = {
                "componentParentDin": f"STSTSM--{lookup(config, ['vin'])}",
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "meterAttributes": {
                    "meterLocation": [
                        1
                    ]
                },
                "serialNumber": packageSerialNumber
            }

        # Create Vitals Dictionary
        vitals = {
            **header,
            **neurio,
            **pvac,
            **pvs,
            **ststsm,
            **tepinv,
            **tepod,
            **tesla,
            **tesync,
            **tethc,
        }
        # Merge in the Powerwall 3 data if available
        if self.pw3:
            pw3_data = self.get_pw3_vitals(force) or {}
            vitals.update(pw3_data)

        return vitals


    def get_blocks(self, force=False):
        """
        Get the list of battery blocks from the Powerwall Gateway
        """
        status = self.get_status(force=force)
        config = self.get_config(force=force)

        if not isinstance(status, dict) or not isinstance(config, dict):
            return None
        block = {}
        # Loop through each THC device serial number
        for i, p in enumerate(lookup(status, ['esCan', 'bus', 'THC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            # THC block
            name = f"{packagePartNumber}--{packageSerialNumber}"
            block[name] = {
                "Type": "",
                "PackagePartNumber": packagePartNumber,
                "PackageSerialNumber": packageSerialNumber,
                "disabled_reasons": [],
                "pinv_state": None,
                "pinv_grid_state": None,
                "nominal_energy_remaining": None,
                "nominal_full_pack_energy": None,
                "p_out": None,
                "q_out": None,
                "v_out": None,
                "f_out": None,
                "i_out": None,
                "energy_charged": None,
                "energy_discharged": None,
                "off_grid": None,
                "vf_mode": None,
                "wobble_detected": None,
                "charge_power_clamped": None,
                "backup_ready": None,
                "OpSeqState": None,
                "version": None
            }
            # POD block
            pod = lookup(status, ['esCan', 'bus', 'POD'])[i]
            energy_remaining = lookup(pod, ['POD_EnergyStatus', 'POD_nom_energy_remaining'])
            full_pack_energy = lookup(pod, ['POD_EnergyStatus', 'POD_nom_full_pack_energy'])
            block[name].update({
                "nominal_energy_remaining": energy_remaining,
                "nominal_full_pack_energy": full_pack_energy,
            })
            # INV block
            pinv = lookup(status, ['esCan', 'bus', 'PINV'])[i]
            block[name].update({
                "f_out": lookup(pinv, ['PINV_Status', 'PINV_Fout']),
                "pinv_state": lookup(p, ['PINV_Status', 'PINV_State']),
                "pinv_grid_state": lookup(p, ['PINV_Status', 'PINV_GridState']),
                "p_out": lookup(pinv, ['PINV_Status', 'PINV_Pout']),
                "v_out": lookup(pinv, ['PINV_Status', 'PINV_Vout']),
            })
        return block

    # End of TEDAPI Class
