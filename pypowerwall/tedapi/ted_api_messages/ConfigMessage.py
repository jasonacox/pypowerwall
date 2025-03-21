import logging
import json
from .. import tedapi_pb2
from .TEDAPIMessage import TEDAPIMessage

log = logging.getLogger(__name__)

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
    
    def ParseFromString(self, data):
        self.pb.ParseFromString(data)
        payload = self.pb.message.config.recv.file.text
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            log.error(f"Error decoding JSON: {e}")
            data = {}
        return data