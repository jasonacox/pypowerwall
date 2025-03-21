import json
import os
import logging
from . import tedapi_pb2

# Setup Logging
log = logging.getLogger(__name__)

class TEDAPIMessage:
    def __init__(self, din):
        self.din = din

class ConfigMessage(TEDAPIMessage):
    def __init__(self, din):
        self.din = din

    def getMessage(self):
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.config.send.num = 1
        pb.message.config.send.file = "config.json"
        pb.tail.value = 1
        self.pb = pb
        return self.pb
    
    def SerializeToString(self):
        return self.getMessage().SerializeToString()
    
    def ParseFromString(self, data):
        self.pb.ParseFromString(data)
        payload = self.pb.message.config.recv.file.text
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            log.error(f"Error decoding JSON: {e}")
            data = {}
        return data

class GatewayStatusMessage(TEDAPIMessage):
    def __init__(self, din):
        self.din = din

    def getMessage(self): 
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        with open(os.path.join(os.path.dirname(__file__), "graphql/status_query.graphql"), "r") as file:
            pb.message.payload.send.payload.text = file.read()
        with open(os.path.join(os.path.dirname(__file__), "graphql/status_query.sig"), "rb") as sig_file:
            pb.message.payload.send.code = sig_file.read()
        
        pb.message.payload.send.b.value = "{}"
        pb.tail.value = 1
        self.pb = pb
        return self.pb
    
    def SerializeToString(self):
        return self.getMessage().SerializeToString()
    
    def ParseFromString(self, data):
        self.getMessage().ParseFromString(data)
        payload = self.pb.message.payload.recv.text

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            log.error(f"Error decoding JSON: {e}")
            data = {}
        return data
    
class DeviceControllerMessage(TEDAPIMessage):
    def __init__(self, din):
        self.din = din

    def getMessage(self): 
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        pb.message.payload.send.b.value = '{"msaComp":{"types" :["PVS","PVAC", "TESYNC", "TEPINV", "TETHC", "STSTSM",  "TEMSA", "TEPINV" ]},\n\t"msaSignals":[\n\t"MSA_pcbaId",\n\t"MSA_usageId",\n\t"MSA_appGitHash",\n\t"MSA_HeatingRateOccurred",\n\t"THC_AmbientTemp",\n\t"METER_Z_CTA_InstRealPower",\n\t"METER_Z_CTA_InstReactivePower",\n\t"METER_Z_CTA_I",\n\t"METER_Z_VL1G",\n\t"METER_Z_CTB_InstRealPower",\n\t"METER_Z_CTB_InstReactivePower",\n\t"METER_Z_CTB_I",\n\t"METER_Z_VL2G"]}'
        with open(os.path.join(os.path.dirname(__file__), "graphql/device_controller_query.graphql"), "r") as file:
            pb.message.payload.send.payload.text = file.read()
        with open(os.path.join(os.path.dirname(__file__), "graphql/device_controller_query.sig"), "rb") as sig_file:
            pb.message.payload.send.code = sig_file.read()
        pb.tail.value = 1
        
        pb.message.payload.send.b.value = "{}"
        pb.tail.value = 1
        self.pb = pb
        return self.pb
    
    def SerializeToString(self):
        return self.getMessage().SerializeToString()
    
    def ParseFromString(self, data):
        self.getMessage().ParseFromString(data)
        payload = self.pb.message.payload.recv.text

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            log.error(f"Error decoding JSON: {e}")
            data = {}
        return data

class FirmwareMessage(TEDAPIMessage):
    def __init__(self, din):
        self.din = din
    
    def getMessage(self):
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.firmware.request = ""
        pb.tail.value = 1
        self.pb = pb
        return self.pb
    
    def SerializeToString(self):
        return self.getMessage().SerializeToString()
    
    def ParseFromString(self, data):
        self.pb.ParseFromString(data)
        data = self.pb.message.firmware.system

        payload = {
            "system": {
                "gateway": {
                    "partNumber": data.gateway.partNumber,
                    "serialNumber": data.gateway.serialNumber
                },
                "din": data.din,
                "version": {
                    "text": data.version.text,
                    "githash": data.version.githash
                },
                "five": data.five,
                "six": data.six,
                "wireless": {
                    "device": []
                }
            }
        }
        try:
            for device in data.wireless.device:
                payload["system"]["wireless"]["device"].append({
                    "company": device.company.value,
                    "model": device.model.value,
                    "fcc_id": device.fcc_id.value,
                    "ic": device.ic.value
                })
        except Exception as e:
            log.debug(f"Error parsing wireless devices: {e}")

        return payload