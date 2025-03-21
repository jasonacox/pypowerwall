import logging
import json
import os
from .. import tedapi_pb2
from .TEDAPIMessage import TEDAPIMessage

log = logging.getLogger(__name__)

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
 
    def ParseFromString(self, data):
        self.getMessage().ParseFromString(data)
        payload = self.pb.message.payload.recv.text

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            log.error(f"Error decoding JSON: {e}")
            data = {}
        return data