import logging
import json
import os
from .. import tedapi_pb2
from .TEDAPIMessage import TEDAPIMessage

log = logging.getLogger(__name__)


class GatewayStatusMessage(TEDAPIMessage):
    """Protobuf message for requesting gateway status data from the Powerwall."""

    def __init__(self, din):
        super().__init__(din)

    def get_message(self): 
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

    def ParseFromString(self, data):
        self.get_message().ParseFromString(data)
        payload = self.pb.message.payload.recv.text

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            log.error(f"Error decoding JSON: {e}")
            data = {}
        return data
