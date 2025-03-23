from pypowerwall import __version__
import time

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

def calculate_dc_power(V, I):
    power = V * I
    return power

class Vitals:
    def __init__(self, config, status, gw_ip):
        self.config = config
        self.gw_ip = gw_ip
        self.status = status

    def get_vitals(self):
        return {
            **self.__get_header(),
            **self.__get_neurio(),
            **self.__get_pvac(),
            **self.__get_pvs(),
            **self.__get_ststsm(),
            **self.__get_tepinv(),
            **self.__get_tepod(),
            **self.__get_tesla(),
            **self.__get_tesync(),
            **self.__get_tethc(),
        }

    def __get_header(self):
        header = {}
        header["VITALS"] = {
            "text": "Device vitals generated from Tesla Powerwall Gateway TEDAPI",
            "timestamp": time.time(),
            "gateway": self.gw_ip,
            "pyPowerwall": __version__,
        }
        return header

    def __get_meters(self):
        meter_config = {}
        if "meters" in self.config:
            # Loop through each meter and use device_serial as the key
            for meter in self.config['meters']:
                if meter.get('type') == "neurio_w2_tcp":
                    device_serial = lookup(meter, ['connection', 'device_serial'])
                    if device_serial:
                        # Check to see if we already have this meter in meter_config
                        if device_serial in meter_config:
                            cts = meter.get('cts', [False] * 4)
                            if not isinstance(cts, list):
                                cts = [False] * 4
                            for i, ct in enumerate(cts):
                                if ct:
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

    def __get_neurio(self):
        # Build meter Lookup if available
        meter_config = self.__get_meters()
        neurio = {}
        c = 1000
        # Loop through each Neurio device serial number
        for n in lookup(self.status, ['neurio', 'readings']) or {}:
            # Loop through each CT on the Neurio device
            sn = n.get('serial', str(c))
            cts = {}
            c = c + 1
            for i, ct in enumerate(n['dataRead'] or {}):
                # Only show if we have a meter configuration and cts[i] is true
                cts_bool = lookup(meter_config, [sn, 'cts'])
                if isinstance(cts_bool, list) and i < len(cts_bool):
                    if not cts_bool[i]:
                        # Skip this CT
                        continue
                factor = lookup(meter_config, [sn, 'real_power_scale_factor']) or 1
                device = f"NEURIO_CT{i}_"
                cts[device + "InstRealPower"] = lookup(ct, ['realPowerW']) * factor
                cts[device + "InstReactivePower"] = lookup(ct, ['reactivePowerVAR'])
                cts[device + "InstVoltage"] = lookup(ct, ['voltageV'])
                cts[device + "InstCurrent"] = lookup(ct, ['currentA'])
                location = lookup(meter_config, [sn, 'location'])
                cts[device + "Location"] = location[i] if len(location) > i else None
            meter_manufacturer = None
            if lookup(meter_config, [sn, 'type']) == "neurio_w2_tcp":
                meter_manufacturer = "NEURIO"
            rest = {
                "componentParentDin": lookup(self.config, ['vin']),
                "firmwareVersion": None,
                "lastCommunicationTime": lookup(n, ['timestamp']),
                "manufacturer": meter_manufacturer,
                "meterAttributes": {
                    "meterLocation": []
                },
                "serialNumber": sn
            }
            neurio[f"NEURIO--{sn}"] = {**cts, **rest}
        return neurio

    def __get_pvac(self):
        pvac = {}
        pvac_strings = self.__get_pvac_strings()

        # Loop through each device serial number
        for i, p in enumerate(lookup(self.status, ['esCan', 'bus', 'PVAC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            pvac_name = f"PVAC--{packagePartNumber}--{packageSerialNumber}"
            V_A = p['PVAC_Logging']['PVAC_PVMeasuredVoltage_A']
            V_B = p['PVAC_Logging']['PVAC_PVMeasuredVoltage_B']
            V_C = p['PVAC_Logging']['PVAC_PVMeasuredVoltage_C']
            V_D = p['PVAC_Logging']['PVAC_PVMeasuredVoltage_D']
            I_A = p['PVAC_Logging']['PVAC_PVCurrent_A']
            I_B = p['PVAC_Logging']['PVAC_PVCurrent_B']
            I_C = p['PVAC_Logging']['PVAC_PVCurrent_C']
            I_D = p['PVAC_Logging']['PVAC_PVCurrent_D']
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
                "PVAC_PvState_A": pvac_strings[pvac_name]["PVAC_PvState_A"], # These are computed from PVS below
                "PVAC_PvState_B": pvac_strings[pvac_name]["PVAC_PvState_B"], #
                "PVAC_PvState_C": pvac_strings[pvac_name]["PVAC_PvState_C"], # PV_Disabled, PV_Active, PV_Active_Parallel
                "PVAC_PvState_D": pvac_strings[pvac_name]["PVAC_PvState_D"], # Not available in TEDAPI
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
        return pvac

    def __get_pvs(self):
        data = self.__get_pvs_and_pvac_strings()
        return data["pvs"]

    def __get_pvac_strings(self):
        data = self.__get_pvs_and_pvac_strings()
        return data["pvac_strings"]

    def __get_pvs_and_pvac_strings(self):
        pvs = {}
        pvac_strings = {}
        # Loop through each device serial number
        for i, p in enumerate(lookup(self.status, ['esCan', 'bus', 'PVAC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            pvac_name = f"PVAC--{packagePartNumber}--{packageSerialNumber}"
            pvs_name = f"PVS--{packagePartNumber}--{packageSerialNumber}"
            pvs_data = lookup(self.status, ['esCan', 'bus', 'PVS'])
            if i < len(pvs_data):
                pvs_data = pvs_data[i]
                # Set String Connected states
                string_a = lookup(pvs_data, ['PVS_Status', 'PVS_StringA_Connected'])
                string_b = lookup(pvs_data, ['PVS_Status', 'PVS_StringB_Connected'])
                string_c = lookup(pvs_data, ['PVS_Status', 'PVS_StringC_Connected'])
                string_d = lookup(pvs_data, ['PVS_Status', 'PVS_StringD_Connected'])
                # Set PVAC PvState based on PVS String Connected states
                pvac_strings[pvac_name] = {
                    "PVAC_PvState_A": None,
                    "PVAC_PvState_B": None,
                    "PVAC_PvState_C": None,
                    "PVAC_PvState_D": None
                }
                pvac_strings[pvac_name]["PVAC_PvState_A"] = "PV_Active" if string_a else "PV_Disabled"
                pvac_strings[pvac_name]["PVAC_PvState_B"] = "PV_Active" if string_b else "PV_Disabled"
                pvac_strings[pvac_name]["PVAC_PvState_C"] = "PV_Active" if string_c else "PV_Disabled"
                pvac_strings[pvac_name]["PVAC_PvState_D"] = "PV_Active" if string_d else "PV_Disabled"
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

        return {
            "pvs": pvs,
            "pvac_strings": pvac_strings
        }

    def __get_tesla(self):
        tesla = {}
        # Loop through each device serial number
        for i, p in enumerate(lookup(self.status, ['esCan', 'bus', 'PVAC']) or {}):
            if not p['packageSerialNumber']:
                continue
            print(p)
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            tesla_name = f"TESLA--{packagePartNumber}--{packageSerialNumber}"
            if "solars" in self.config and i < len(self.config.get('solars', [{}])):
                tesla_nameplate = self.config['solars'][i].get('power_rating_watts', None)
                brand = self.config['solars'][i].get('brand', None)
            else:
                tesla_nameplate = None
                brand = None
            tesla[tesla_name] = {
                "componentParentDin": f"STSTSM--{lookup(self.config, ['vin'])}",
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": brand.upper() if brand else "TESLA",
                "pvInverterAttributes": {
                    "nameplateRealPowerW": tesla_nameplate,
                },
                "serialNumber": f"{packagePartNumber}--{packageSerialNumber}",
            }

        # Create TESLA block - tied to TESYNC
        sync = lookup(self.status, ['esCan', 'bus', 'SYNC']) or {}
        packagePartNumber = sync.get('packagePartNumber', None)
        packageSerialNumber = sync.get('packageSerialNumber', None)
        name = f"TESLA--{packageSerialNumber}"
        tesla[name] = {
                "componentParentDin": f"STSTSM--{lookup(self.config, ['vin'])}",
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "meterAttributes": {
                    "meterLocation": [
                        1
                    ]
                },
                "serialNumber": packageSerialNumber
            }
        return tesla
    
    def __get_temp_sensors(self):
        temp_sensors = {}
        for i in lookup(self.status, ['components', 'msa']) or []:
            if "signals" in i and "serialNumber" in i and i["serialNumber"]:
                for s in i["signals"]:
                    if "name" in s and s["name"] == "THC_AmbientTemp" and "value" in s:
                        temp_sensors[i["serialNumber"]] = s["value"]
        return temp_sensors

    def __get_ststsm(self):
        name = f"STSTSM--{lookup(self.config, ['vin'])}"
        ststsm = {}
        ststsm[name] =  {
            "STSTSM-Location": "Gateway",
            "alerts": lookup(self.status, ['control', 'alerts', 'active']) or [],
            "firmwareVersion": None,
            "lastCommunicationTime": None,
            "manufacturer": "TESLA",
            "partNumber": lookup(self.config, ['vin']).split('--')[0],
            "serialNumber": lookup(self.config, ['vin']).split('--')[-1],
            "teslaEnergyEcuAttributes": {
                "ecuType": 207
            }
        }
        return ststsm

    def __get_tethc(self):
        tethc = {}
        temp_sensors = self.__get_temp_sensors()

        # Loop through each THC device serial number
        for i, p in enumerate(lookup(self.status, ['esCan', 'bus', 'THC']) or {}):
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
                "componentParentDin": f"STSTSM--{lookup(self.config, ['vin'])}",
                "firmwareVersion": None,
                "lastCommunicationTime": None,
                "manufacturer": "TESLA",
                "partNumber": packagePartNumber,
                "serialNumber": packageSerialNumber,
                "teslaEnergyEcuAttributes": {
                    "ecuType": 224
                }
            }
        return tethc

    def __get_tepod(self):
        tepod = {}
        # Loop through each THC device serial number
        for i, p in enumerate(lookup(self.status, ['esCan', 'bus', 'THC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            # TETHC block
            parent_name = f"TETHC--{packagePartNumber}--{packageSerialNumber}"

            # TEPOD block
            name = f"TEPOD--{packagePartNumber}--{packageSerialNumber}"
            pod = lookup(self.status, ['esCan', 'bus', 'POD'])[i]
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
        return tepod

    def __get_tepinv(self):
        tepinv = {}
        # Loop through each THC device serial number
        for i, p in enumerate(lookup(self.status, ['esCan', 'bus', 'THC']) or {}):
            if not p['packageSerialNumber']:
                continue
            packagePartNumber = p.get('packagePartNumber', str(i))
            packageSerialNumber = p.get('packageSerialNumber', str(i))
            # TETHC block
            parent_name = f"TETHC--{packagePartNumber}--{packageSerialNumber}"

            # TEPINV block
            name = f"TEPINV--{packagePartNumber}--{packageSerialNumber}"
            pinv = lookup(self.status, ['esCan', 'bus', 'PINV'])[i]
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
        return tepinv

    def __get_tesync(self):
        tesync = {}
        status = self.status
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
            "componentParentDin": f"STSTSM--{lookup(self.config, ['vin'])}",
            "firmwareVersion": None,
            "manufacturer": "TESLA",
            "partNumber": packagePartNumber,
            "serialNumber": packageSerialNumber,
            "teslaEnergyEcuAttributes": {
                "ecuType": 259
            }
        }
        return tesync
