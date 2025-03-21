import logging
from .. import tedapi_pb2
from .TEDAPIMessage import TEDAPIMessage

log = logging.getLogger(__name__)

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