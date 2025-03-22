import logging
import json
from .. import tedapi_pb2
from .TEDAPIMessage import TEDAPIMessage

log = logging.getLogger(__name__)


class ComponentsMessage(TEDAPIMessage):
    def __init__(self, din):
        super().__init__(din)

    def getMessage(self):
        pb = tedapi_pb2.Message()
        pb.message.deliveryChannel = 1
        pb.message.sender.local = 1
        pb.message.recipient.din = self.din  # DIN of Powerwall
        pb.message.payload.send.num = 2
        pb.message.payload.send.payload.value = 1
        pb.message.payload.send.payload.text = " query ComponentsQuery (\n  $pchComponentsFilter: ComponentFilter,\n  $pchSignalNames: [String!],\n  $pwsComponentsFilter: ComponentFilter,\n  $pwsSignalNames: [String!],\n  $bmsComponentsFilter: ComponentFilter,\n  $bmsSignalNames: [String!],\n  $hvpComponentsFilter: ComponentFilter,\n  $hvpSignalNames: [String!],\n  $baggrComponentsFilter: ComponentFilter,\n  $baggrSignalNames: [String!],\n  ) {\n  # TODO STST-57686: Introduce GraphQL fragments to shorten\n  pw3Can {\n    firmwareUpdate {\n      isUpdating\n      progress {\n         updating\n         numSteps\n         currentStep\n         currentStepProgress\n         progress\n      }\n    }\n  }\n  components {\n    pws: components(filter: $pwsComponentsFilter) {\n      signals(names: $pwsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    pch: components(filter: $pchComponentsFilter) {\n      signals(names: $pchSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    bms: components(filter: $bmsComponentsFilter) {\n      signals(names: $bmsSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    hvp: components(filter: $hvpComponentsFilter) {\n      partNumber\n      serialNumber\n      signals(names: $hvpSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n    baggr: components(filter: $baggrComponentsFilter) {\n      signals(names: $baggrSignalNames) {\n        name\n        value\n        textValue\n        boolValue\n        timestamp\n      }\n      activeAlerts {\n        name\n      }\n    }\n  }\n}\n"
        pb.message.payload.send.code = b'0\201\210\002B\000\270q\354>\243m\325p\371S\253\231\346~:\032\216~\242\263\207\017L\273O\203u\241\270\333w\233\354\276\246h\262\243\255\261\007\202D\277\353x\023O\022\303\216\264\010-\'i6\360>B\237\236\304\244m\002B\001\023Pk\033)\277\236\342R\264\247g\260u\036\023\3662\354\242\353\035\221\234\027\245\321J\342\345\037q\262O\3446-\353\315m1\237zai0\341\207C4\307\300Z\177@h\335\327\0239\252f\n\206W'
        pb.message.payload.send.b.value = "{\"pwsComponentsFilter\":{\"types\":[\"PW3SAF\"]},\"pwsSignalNames\":[\"PWS_SelfTest\",\"PWS_PeImpTestState\",\"PWS_PvIsoTestState\",\"PWS_RelaySelfTest_State\",\"PWS_MciTestState\",\"PWS_appGitHash\",\"PWS_ProdSwitch_State\"],\"pchComponentsFilter\":{\"types\":[\"PCH\"]},\"pchSignalNames\":[\"PCH_State\",\"PCH_PvState_A\",\"PCH_PvState_B\",\"PCH_PvState_C\",\"PCH_PvState_D\",\"PCH_PvState_E\",\"PCH_PvState_F\",\"PCH_AcFrequency\",\"PCH_AcVoltageAB\",\"PCH_AcVoltageAN\",\"PCH_AcVoltageBN\",\"PCH_packagePartNumber_1_7\",\"PCH_packagePartNumber_8_14\",\"PCH_packagePartNumber_15_20\",\"PCH_packageSerialNumber_1_7\",\"PCH_packageSerialNumber_8_14\",\"PCH_PvVoltageA\",\"PCH_PvVoltageB\",\"PCH_PvVoltageC\",\"PCH_PvVoltageD\",\"PCH_PvVoltageE\",\"PCH_PvVoltageF\",\"PCH_PvCurrentA\",\"PCH_PvCurrentB\",\"PCH_PvCurrentC\",\"PCH_PvCurrentD\",\"PCH_PvCurrentE\",\"PCH_PvCurrentF\",\"PCH_BatteryPower\",\"PCH_AcRealPowerAB\",\"PCH_SlowPvPowerSum\",\"PCH_AcMode\",\"PCH_AcFrequency\",\"PCH_DcdcState_A\",\"PCH_DcdcState_B\",\"PCH_appGitHash\"],\"bmsComponentsFilter\":{\"types\":[\"PW3BMS\"]},\"bmsSignalNames\":[\"BMS_nominalEnergyRemaining\",\"BMS_nominalFullPackEnergy\",\"BMS_appGitHash\"],\"hvpComponentsFilter\":{\"types\":[\"PW3HVP\"]},\"hvpSignalNames\":[\"HVP_State\",\"HVP_appGitHash\"],\"baggrComponentsFilter\":{\"types\":[\"BAGGR\"]},\"baggrSignalNames\":[\"BAGGR_State\",\"BAGGR_OperationRequest\",\"BAGGR_NumBatteriesConnected\",\"BAGGR_NumBatteriesPresent\",\"BAGGR_NumBatteriesExpected\",\"BAGGR_LOG_BattConnectionStatus0\",\"BAGGR_LOG_BattConnectionStatus1\",\"BAGGR_LOG_BattConnectionStatus2\",\"BAGGR_LOG_BattConnectionStatus3\"]}"
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
