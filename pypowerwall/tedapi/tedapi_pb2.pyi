"""Type stubs for tedapi_pb2 (generated from tedapi.proto)."""

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message

DESCRIPTOR: _descriptor.FileDescriptor

class AuthEnvelope(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    payload: bytes
    externalAuth: ExternalAuth
    def __init__(self, *, payload: bytes = ..., externalAuth: ExternalAuth | None = ...) -> None: ...

class ExternalAuth(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    type: int
    def __init__(self, *, type: int = ...) -> None: ...

class Message(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    message: MessageEnvelope
    tail: Tail
    def __init__(self, *, message: MessageEnvelope | None = ..., tail: Tail | None = ...) -> None: ...

class MessageEnvelope(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    deliveryChannel: int
    sender: Participant
    recipient: Participant
    firmware: FirmwareType
    config: ConfigType
    payload: QueryType
    def __init__(
        self,
        *,
        deliveryChannel: int = ...,
        sender: Participant | None = ...,
        recipient: Participant | None = ...,
        firmware: FirmwareType | None = ...,
        config: ConfigType | None = ...,
        payload: QueryType | None = ...,
    ) -> None: ...

class Participant(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    din: str
    teslaService: int
    local: int
    authorizedClient: int
    def __init__(self, *, din: str = ..., teslaService: int = ..., local: int = ..., authorizedClient: int = ...) -> None: ...

class Tail(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    value: int
    def __init__(self, *, value: int = ...) -> None: ...

class FirmwareType(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    request: str
    system: FirmwarePayload
    def __init__(self, *, request: str = ..., system: FirmwarePayload | None = ...) -> None: ...

class FirmwarePayload(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    gateway: EcuId
    din: str
    version: FirmwareVersion
    five: FirmwareFive
    six: int
    wireless: DeviceArray
    field8: bytes
    field9: bytes
    def __init__(
        self,
        *,
        gateway: EcuId | None = ...,
        din: str = ...,
        version: FirmwareVersion | None = ...,
        five: FirmwareFive | None = ...,
        six: int = ...,
        wireless: DeviceArray | None = ...,
        field8: bytes = ...,
        field9: bytes = ...,
    ) -> None: ...

class EcuId(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    partNumber: str
    serialNumber: str
    def __init__(self, *, partNumber: str = ..., serialNumber: str = ...) -> None: ...

class FirmwareVersion(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    text: str
    githash: bytes
    def __init__(self, *, text: str = ..., githash: bytes = ...) -> None: ...

class FirmwareFive(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    d: int
    def __init__(self, *, d: int = ...) -> None: ...

class DeviceArray(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    device: list[DeviceInfo]
    def __init__(self, *, device: list[DeviceInfo] | None = ...) -> None: ...

class DeviceInfo(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    company: StringValue
    model: StringValue
    fcc_id: StringValue
    ic: StringValue
    def __init__(self, *, company: StringValue | None = ..., model: StringValue | None = ..., fcc_id: StringValue | None = ..., ic: StringValue | None = ...) -> None: ...

class QueryType(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    send: PayloadQuerySend
    recv: PayloadString
    def __init__(self, *, send: PayloadQuerySend | None = ..., recv: PayloadString | None = ...) -> None: ...

class PayloadQuerySend(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    num: int
    payload: PayloadString
    code: bytes
    b: StringValue
    def __init__(self, *, num: int = ..., payload: PayloadString | None = ..., code: bytes = ..., b: StringValue | None = ...) -> None: ...

class ConfigType(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    send: PayloadConfigSend
    recv: PayloadConfigRecv
    def __init__(self, *, send: PayloadConfigSend | None = ..., recv: PayloadConfigRecv | None = ...) -> None: ...

class PayloadConfigSend(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    num: int
    file: str
    def __init__(self, *, num: int = ..., file: str = ...) -> None: ...

class PayloadConfigRecv(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    file: ConfigString
    code: bytes
    def __init__(self, *, file: ConfigString | None = ..., code: bytes = ...) -> None: ...

class ConfigString(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    name: str
    text: str
    def __init__(self, *, name: str = ..., text: str = ...) -> None: ...

class PayloadString(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    value: int
    text: str
    def __init__(self, *, value: int = ..., text: str = ...) -> None: ...

class StringValue(_message.Message):
    DESCRIPTOR: _descriptor.Descriptor
    value: str
    def __init__(self, *, value: str = ...) -> None: ...
