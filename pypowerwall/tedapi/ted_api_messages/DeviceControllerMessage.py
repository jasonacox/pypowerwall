import logging
import json
import os
from .. import tedapi_pb2
from .TEDAPIMessage import TEDAPIMessage

log = logging.getLogger(__name__)


class DeviceControllerMessage(TEDAPIMessage):
    """Protobuf message for requesting controller data from the Powerwall."""

    def __init__(self, din):
        super().__init__(din)

    def get_message(self): 
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        pb.message.payload.send.payload.text = " query ComponentsQuery (\n  $pchComponentsFilter: ComponentFilter,\n  $pchSignalNames: [String!],\n  $pwsComponentsFilter: ComponentFilter,\n  $pwsSignalNames: [String!],\n  $bmsComponentsFilter: ComponentFilter,\n  $bmsSignalNames: [String!],\n  $hvpComponentsFilter: ComponentFilter,\n  $hvpSignalNames: [String!],\n  $baggrComponentsFilter: ComponentFilter,\n  $baggrSignalNames: [String!],\n  ) {\n  # TODO STST-57686: Introduce GraphQL fragments to shorten\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  components {\n    pws: components(filter: $pwsComponentsFilter) {\n      signals(names: $pwsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    pch: components(filter: $pchComponentsFilter) {\n      signals(names: $pchSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    bms: components(filter: $bmsComponentsFilter) {\n      signals(names: $bmsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    hvp: components(filter: $hvpComponentsFilter) {\n      partNumber\n      serialNumber\n      signals(names: $hvpSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    baggr: components(filter: $baggrComponentsFilter) {\n      signals(names: $baggrSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n  }\n}\n"
        pb.message.payload.send.code = b'0\201\210\002B\000\270q\354>\243m\325p\371S\253\231\346~:\032\216~\242\263\207\017L\273O\203u\241\270\333w\233\354\276\246h\262\243\255\261\007\202D\277\353x\023O\022\303\216\264\010-\'i6\360>B\237\236\304\244m\002B\001\023Pk\033)\277\236\342R\264\247g\260u\036\023\3662\354\242\353\035\221\234\027\245\321J\342\345\037q\262O\3446-\353\315m1\237zai0\341\207C4\307\300Z\177@h\335\327\0239\252f\n\206W'

        pb.message.payload.send.code = b'0\x81\x87\x02B\x01A\x95\x12\xe3B\xd1\xca\x1a\xd3\x00\xf6}\x0bE@/\x9a\x9f\xc0\r\x06%\xac,\x0ej!)\nd\xef\xe67\x8b\xafb\xd7\xf8&\x0b.\xc1\xac\xd9!\x1f\xd6\x83\xffkIm\xf3\\J\xd8\xeeiTY\xde\x7f\xc5xR\x02A\x1dC\x03H\xfb8"\xb0\xe4\xd6\x18\xde\x11\xc45\xb2\xa9VB\xa6J\x8f\x08\x9d\xba\x86\xf1 W\xcdJ\x8c\x02*\x05\x12\xcb{<\x9b\xc8g\xc9\x9d9\x8bR\xb3\x89\xb8\xf1\xf1\x0f\x0e\x16E\xed\xd7\xbf\xd5&)\x92.\x12'
        pb.tail.value = 1

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
