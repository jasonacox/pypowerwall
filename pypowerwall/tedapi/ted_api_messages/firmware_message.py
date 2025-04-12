import logging
from .. import tedapi_pb2
from .tedapi_message import TEDAPIMessage

log = logging.getLogger(__name__)


class FirmwareMessage(TEDAPIMessage):
    """Protobuf message for requesting firmware details from the Powerwall."""

    def __init__(self, din):
        super().__init__(din)

    def get_message(self):
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
                    "githash": data.version.githash # Whatever this is, it isn't JSON-serializable
                },
                "five": data.five, # Whatever this is, it isn't JSON-serializable
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
