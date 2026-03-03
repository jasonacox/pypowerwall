from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExternalAuthType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXTERNAL_AUTH_TYPE_INVALID: _ClassVar[ExternalAuthType]
    EXTERNAL_AUTH_TYPE_PRESENCE: _ClassVar[ExternalAuthType]
    EXTERNAL_AUTH_TYPE_MTLS: _ClassVar[ExternalAuthType]
    EXTERNAL_AUTH_TYPE_HERMES_COMMAND: _ClassVar[ExternalAuthType]

class DeliveryChannel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DELIVERY_CHANNEL_INVALID: _ClassVar[DeliveryChannel]
    DELIVERY_CHANNEL_LOCAL_HTTPS: _ClassVar[DeliveryChannel]
    DELIVERY_CHANNEL_HERMES_COMMAND: _ClassVar[DeliveryChannel]
    DELIVERY_CHANNEL_BLE: _ClassVar[DeliveryChannel]

class LocalParticipant(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LOCAL_PARTICIPANT_INVALID: _ClassVar[LocalParticipant]
    LOCAL_PARTICIPANT_INSTALLER: _ClassVar[LocalParticipant]
    LOCAL_PARTICIPANT_CUSTOMER: _ClassVar[LocalParticipant]

class TeslaService(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TESLA_SERVICE_INVALID: _ClassVar[TeslaService]
    TESLA_SERVICE_COMMAND: _ClassVar[TeslaService]

class AuthorizedClientType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUTHORIZED_CLIENT_TYPE_INVALID: _ClassVar[AuthorizedClientType]
    AUTHORIZED_CLIENT_TYPE_CUSTOMER_MOBILE_APP: _ClassVar[AuthorizedClientType]
    AUTHORIZED_CLIENT_TYPE_VEHICLE: _ClassVar[AuthorizedClientType]

class WifiNetworkSecurityType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WIFI_NETWORK_SECURITY_TYPE_INVALID: _ClassVar[WifiNetworkSecurityType]
    WIFI_NETWORK_SECURITY_TYPE_NONE: _ClassVar[WifiNetworkSecurityType]
    WIFI_NETWORK_SECURITY_TYPE_DYNAMIC_WEP: _ClassVar[WifiNetworkSecurityType]
    WIFI_NETWORK_SECURITY_TYPE_WPA2_PERSONAL: _ClassVar[WifiNetworkSecurityType]
    WIFI_NETWORK_SECURITY_TYPE_WPA2_ENTERPRISE: _ClassVar[WifiNetworkSecurityType]

class WifiConfigureResult(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WIFI_CONFIGURE_RESULT_INVALID: _ClassVar[WifiConfigureResult]
    WIFI_CONFIGURE_RESULT_SUCCESS: _ClassVar[WifiConfigureResult]
    WIFI_CONFIGURE_RESULT_FAILURE_GENERIC: _ClassVar[WifiConfigureResult]
    WIFI_CONFIGURE_RESULT_FAILED_WITH_INVALID_CONFIG: _ClassVar[WifiConfigureResult]
    WIFI_CONFIGURE_RESULT_FAILED_TO_CONNECT: _ClassVar[WifiConfigureResult]

class NeurioConnectionStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NEURIO_CONNECTION_STATUS_INVALID: _ClassVar[NeurioConnectionStatus]
    NEURIO_CONNECTION_STATUS_NO_COMMS: _ClassVar[NeurioConnectionStatus]
    NEURIO_CONNECTION_STATUS_PAIRING: _ClassVar[NeurioConnectionStatus]
    NEURIO_CONNECTION_STATUS_CONNECTED: _ClassVar[NeurioConnectionStatus]
    NEURIO_CONNECTION_STATUS_CONFIG_CHANGE_UNDERWAY: _ClassVar[NeurioConnectionStatus]

class NeurioConnectionError(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NEURIO_CONNECTION_ERROR_INVALID: _ClassVar[NeurioConnectionError]
    NEURIO_CONNECTION_ERROR_NONE: _ClassVar[NeurioConnectionError]
    NEURIO_CONNECTION_ERROR_UNKNOWN: _ClassVar[NeurioConnectionError]
    NEURIO_CONNECTION_ERROR_WIFI_AP: _ClassVar[NeurioConnectionError]
    NEURIO_CONNECTION_ERROR_PAIRING_COMMAND: _ClassVar[NeurioConnectionError]
    NEURIO_CONNECTION_ERROR_REBOOT_COMMAND: _ClassVar[NeurioConnectionError]

class AuthorizationRole(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUTHORIZATION_ROLE_INVALID: _ClassVar[AuthorizationRole]
    AUTHORIZATION_ROLE_CUSTOMER: _ClassVar[AuthorizationRole]
    AUTHORIZATION_ROLE_VEHICLE: _ClassVar[AuthorizationRole]

class AuthorizedState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUTHORIZED_STATE_INVALID: _ClassVar[AuthorizedState]
    AUTHORIZED_STATE_PENDING_VERIFICATION: _ClassVar[AuthorizedState]
    AUTHORIZED_STATE_PENDING_VERIFICATION_TIMEOUT: _ClassVar[AuthorizedState]
    AUTHORIZED_STATE_VERIFIED: _ClassVar[AuthorizedState]
    AUTHORIZED_STATE_REMOVED: _ClassVar[AuthorizedState]

class AuthorizedVerificationType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUTHORIZED_VERIFICATION_TYPE_INVALID: _ClassVar[AuthorizedVerificationType]
    AUTHORIZED_VERIFICATION_TYPE_PRESENCE_PROOF: _ClassVar[AuthorizedVerificationType]
    AUTHORIZED_VERIFICATION_TYPE_HERMES_COMMAND: _ClassVar[AuthorizedVerificationType]

class AuthorizedKeyType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUTHORIZED_KEY_TYPE_INVALID: _ClassVar[AuthorizedKeyType]
    AUTHORIZED_KEY_TYPE_RSA: _ClassVar[AuthorizedKeyType]
    AUTHORIZED_KEY_TYPE_ECC: _ClassVar[AuthorizedKeyType]

class GraphQLQueryFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GRAPH_QL_QUERY_FORMAT_INVALID: _ClassVar[GraphQLQueryFormat]
    GRAPH_QL_QUERY_FORMAT_RAW: _ClassVar[GraphQLQueryFormat]
    GRAPH_QL_QUERY_FORMAT_SIGNED_SHA256_ECDSA_ASN1: _ClassVar[GraphQLQueryFormat]

class FileStoreAPIDomain(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FILE_STORE_API_DOMAIN_INVALID: _ClassVar[FileStoreAPIDomain]
    FILE_STORE_API_DOMAIN_CONFIG_JSON: _ClassVar[FileStoreAPIDomain]
    FILE_STORE_API_DOMAIN_GRID_CODE_REGIONS_CSV: _ClassVar[FileStoreAPIDomain]
    FILE_STORE_API_DOMAIN_CERTIFIED_INSTALLERS_CSV: _ClassVar[FileStoreAPIDomain]
    FILE_STORE_API_DOMAIN_SUPERCHARGER_FILES: _ClassVar[FileStoreAPIDomain]
    FILE_STORE_API_DOMAIN_OPTICASTER_FILES: _ClassVar[FileStoreAPIDomain]
    FILE_STORE_API_DOMAIN_WALLBOX_CONFIG: _ClassVar[FileStoreAPIDomain]
    FILE_STORE_API_DOMAIN_OCPP_CSMS_ROOT_CA: _ClassVar[FileStoreAPIDomain]
EXTERNAL_AUTH_TYPE_INVALID: ExternalAuthType
EXTERNAL_AUTH_TYPE_PRESENCE: ExternalAuthType
EXTERNAL_AUTH_TYPE_MTLS: ExternalAuthType
EXTERNAL_AUTH_TYPE_HERMES_COMMAND: ExternalAuthType
DELIVERY_CHANNEL_INVALID: DeliveryChannel
DELIVERY_CHANNEL_LOCAL_HTTPS: DeliveryChannel
DELIVERY_CHANNEL_HERMES_COMMAND: DeliveryChannel
DELIVERY_CHANNEL_BLE: DeliveryChannel
LOCAL_PARTICIPANT_INVALID: LocalParticipant
LOCAL_PARTICIPANT_INSTALLER: LocalParticipant
LOCAL_PARTICIPANT_CUSTOMER: LocalParticipant
TESLA_SERVICE_INVALID: TeslaService
TESLA_SERVICE_COMMAND: TeslaService
AUTHORIZED_CLIENT_TYPE_INVALID: AuthorizedClientType
AUTHORIZED_CLIENT_TYPE_CUSTOMER_MOBILE_APP: AuthorizedClientType
AUTHORIZED_CLIENT_TYPE_VEHICLE: AuthorizedClientType
WIFI_NETWORK_SECURITY_TYPE_INVALID: WifiNetworkSecurityType
WIFI_NETWORK_SECURITY_TYPE_NONE: WifiNetworkSecurityType
WIFI_NETWORK_SECURITY_TYPE_DYNAMIC_WEP: WifiNetworkSecurityType
WIFI_NETWORK_SECURITY_TYPE_WPA2_PERSONAL: WifiNetworkSecurityType
WIFI_NETWORK_SECURITY_TYPE_WPA2_ENTERPRISE: WifiNetworkSecurityType
WIFI_CONFIGURE_RESULT_INVALID: WifiConfigureResult
WIFI_CONFIGURE_RESULT_SUCCESS: WifiConfigureResult
WIFI_CONFIGURE_RESULT_FAILURE_GENERIC: WifiConfigureResult
WIFI_CONFIGURE_RESULT_FAILED_WITH_INVALID_CONFIG: WifiConfigureResult
WIFI_CONFIGURE_RESULT_FAILED_TO_CONNECT: WifiConfigureResult
NEURIO_CONNECTION_STATUS_INVALID: NeurioConnectionStatus
NEURIO_CONNECTION_STATUS_NO_COMMS: NeurioConnectionStatus
NEURIO_CONNECTION_STATUS_PAIRING: NeurioConnectionStatus
NEURIO_CONNECTION_STATUS_CONNECTED: NeurioConnectionStatus
NEURIO_CONNECTION_STATUS_CONFIG_CHANGE_UNDERWAY: NeurioConnectionStatus
NEURIO_CONNECTION_ERROR_INVALID: NeurioConnectionError
NEURIO_CONNECTION_ERROR_NONE: NeurioConnectionError
NEURIO_CONNECTION_ERROR_UNKNOWN: NeurioConnectionError
NEURIO_CONNECTION_ERROR_WIFI_AP: NeurioConnectionError
NEURIO_CONNECTION_ERROR_PAIRING_COMMAND: NeurioConnectionError
NEURIO_CONNECTION_ERROR_REBOOT_COMMAND: NeurioConnectionError
AUTHORIZATION_ROLE_INVALID: AuthorizationRole
AUTHORIZATION_ROLE_CUSTOMER: AuthorizationRole
AUTHORIZATION_ROLE_VEHICLE: AuthorizationRole
AUTHORIZED_STATE_INVALID: AuthorizedState
AUTHORIZED_STATE_PENDING_VERIFICATION: AuthorizedState
AUTHORIZED_STATE_PENDING_VERIFICATION_TIMEOUT: AuthorizedState
AUTHORIZED_STATE_VERIFIED: AuthorizedState
AUTHORIZED_STATE_REMOVED: AuthorizedState
AUTHORIZED_VERIFICATION_TYPE_INVALID: AuthorizedVerificationType
AUTHORIZED_VERIFICATION_TYPE_PRESENCE_PROOF: AuthorizedVerificationType
AUTHORIZED_VERIFICATION_TYPE_HERMES_COMMAND: AuthorizedVerificationType
AUTHORIZED_KEY_TYPE_INVALID: AuthorizedKeyType
AUTHORIZED_KEY_TYPE_RSA: AuthorizedKeyType
AUTHORIZED_KEY_TYPE_ECC: AuthorizedKeyType
GRAPH_QL_QUERY_FORMAT_INVALID: GraphQLQueryFormat
GRAPH_QL_QUERY_FORMAT_RAW: GraphQLQueryFormat
GRAPH_QL_QUERY_FORMAT_SIGNED_SHA256_ECDSA_ASN1: GraphQLQueryFormat
FILE_STORE_API_DOMAIN_INVALID: FileStoreAPIDomain
FILE_STORE_API_DOMAIN_CONFIG_JSON: FileStoreAPIDomain
FILE_STORE_API_DOMAIN_GRID_CODE_REGIONS_CSV: FileStoreAPIDomain
FILE_STORE_API_DOMAIN_CERTIFIED_INSTALLERS_CSV: FileStoreAPIDomain
FILE_STORE_API_DOMAIN_SUPERCHARGER_FILES: FileStoreAPIDomain
FILE_STORE_API_DOMAIN_OPTICASTER_FILES: FileStoreAPIDomain
FILE_STORE_API_DOMAIN_WALLBOX_CONFIG: FileStoreAPIDomain
FILE_STORE_API_DOMAIN_OCPP_CSMS_ROOT_CA: FileStoreAPIDomain

class AuthEnvelope(_message.Message):
    __slots__ = ("payload", "externalAuth")
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    EXTERNALAUTH_FIELD_NUMBER: _ClassVar[int]
    payload: bytes
    externalAuth: ExternalAuth
    def __init__(self, payload: _Optional[bytes] = ..., externalAuth: _Optional[_Union[ExternalAuth, _Mapping]] = ...) -> None: ...

class ExternalAuth(_message.Message):
    __slots__ = ("type",)
    TYPE_FIELD_NUMBER: _ClassVar[int]
    type: ExternalAuthType
    def __init__(self, type: _Optional[_Union[ExternalAuthType, str]] = ...) -> None: ...

class Message(_message.Message):
    __slots__ = ("message", "tail")
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TAIL_FIELD_NUMBER: _ClassVar[int]
    message: MessageEnvelope
    tail: Tail
    def __init__(self, message: _Optional[_Union[MessageEnvelope, _Mapping]] = ..., tail: _Optional[_Union[Tail, _Mapping]] = ...) -> None: ...

class MessageEnvelope(_message.Message):
    __slots__ = ("deliveryChannel", "sender", "recipient", "common", "teg", "wc", "neuriometer", "energysitenet", "authorization", "filestore", "graphql")
    DELIVERYCHANNEL_FIELD_NUMBER: _ClassVar[int]
    SENDER_FIELD_NUMBER: _ClassVar[int]
    RECIPIENT_FIELD_NUMBER: _ClassVar[int]
    COMMON_FIELD_NUMBER: _ClassVar[int]
    TEG_FIELD_NUMBER: _ClassVar[int]
    WC_FIELD_NUMBER: _ClassVar[int]
    NEURIOMETER_FIELD_NUMBER: _ClassVar[int]
    ENERGYSITENET_FIELD_NUMBER: _ClassVar[int]
    AUTHORIZATION_FIELD_NUMBER: _ClassVar[int]
    FILESTORE_FIELD_NUMBER: _ClassVar[int]
    GRAPHQL_FIELD_NUMBER: _ClassVar[int]
    deliveryChannel: DeliveryChannel
    sender: Participant
    recipient: Participant
    common: CommonMessages
    teg: TEGMessages
    wc: WCMessages
    neuriometer: NeurioMeterMessages
    energysitenet: EnergySiteNetMessages
    authorization: AuthorizationMessages
    filestore: FileStoreMessages
    graphql: GraphQLMessages
    def __init__(self, deliveryChannel: _Optional[_Union[DeliveryChannel, str]] = ..., sender: _Optional[_Union[Participant, _Mapping]] = ..., recipient: _Optional[_Union[Participant, _Mapping]] = ..., common: _Optional[_Union[CommonMessages, _Mapping]] = ..., teg: _Optional[_Union[TEGMessages, _Mapping]] = ..., wc: _Optional[_Union[WCMessages, _Mapping]] = ..., neuriometer: _Optional[_Union[NeurioMeterMessages, _Mapping]] = ..., energysitenet: _Optional[_Union[EnergySiteNetMessages, _Mapping]] = ..., authorization: _Optional[_Union[AuthorizationMessages, _Mapping]] = ..., filestore: _Optional[_Union[FileStoreMessages, _Mapping]] = ..., graphql: _Optional[_Union[GraphQLMessages, _Mapping]] = ...) -> None: ...

class Participant(_message.Message):
    __slots__ = ("din", "teslaService", "local", "authorizedClient")
    DIN_FIELD_NUMBER: _ClassVar[int]
    TESLASERVICE_FIELD_NUMBER: _ClassVar[int]
    LOCAL_FIELD_NUMBER: _ClassVar[int]
    AUTHORIZEDCLIENT_FIELD_NUMBER: _ClassVar[int]
    din: str
    teslaService: int
    local: int
    authorizedClient: int
    def __init__(self, din: _Optional[str] = ..., teslaService: _Optional[int] = ..., local: _Optional[int] = ..., authorizedClient: _Optional[int] = ...) -> None: ...

class Tail(_message.Message):
    __slots__ = ("value",)
    VALUE_FIELD_NUMBER: _ClassVar[int]
    value: int
    def __init__(self, value: _Optional[int] = ...) -> None: ...

class CommonMessages(_message.Message):
    __slots__ = ("errorResponse", "getSystemInfoRequest", "getSystemInfoResponse", "setLocalSiteConfigRequest", "setLocalSiteConfigResponse", "performUpdateRequest", "performUpdateResponse", "factoryResetRequest", "factoryResetResponse", "wifiScanRequest", "wifiScanResponse", "configureWifiRequest", "configureWifiResponse", "checkForUpdateRequest", "checkForUpdateResponse", "clearUpdateRequest", "clearUpdateResponse", "deviceCertRequest", "deviceCertResponse", "configureWifiEncryptedRequest", "configureWifiEncryptedResponse", "getNetworkingStatusRequest", "getNetworkingStatusResponse", "getCellularInfoRequest", "getCellularInfoResponse", "configureEthernetRequest", "configureEthernetResponse", "forgetWifiNetworkRequest", "forgetWifiNetworkResponse", "checkInternetRequest", "checkInternetResponse")
    ERRORRESPONSE_FIELD_NUMBER: _ClassVar[int]
    GETSYSTEMINFOREQUEST_FIELD_NUMBER: _ClassVar[int]
    GETSYSTEMINFORESPONSE_FIELD_NUMBER: _ClassVar[int]
    SETLOCALSITECONFIGREQUEST_FIELD_NUMBER: _ClassVar[int]
    SETLOCALSITECONFIGRESPONSE_FIELD_NUMBER: _ClassVar[int]
    PERFORMUPDATEREQUEST_FIELD_NUMBER: _ClassVar[int]
    PERFORMUPDATERESPONSE_FIELD_NUMBER: _ClassVar[int]
    FACTORYRESETREQUEST_FIELD_NUMBER: _ClassVar[int]
    FACTORYRESETRESPONSE_FIELD_NUMBER: _ClassVar[int]
    WIFISCANREQUEST_FIELD_NUMBER: _ClassVar[int]
    WIFISCANRESPONSE_FIELD_NUMBER: _ClassVar[int]
    CONFIGUREWIFIREQUEST_FIELD_NUMBER: _ClassVar[int]
    CONFIGUREWIFIRESPONSE_FIELD_NUMBER: _ClassVar[int]
    CHECKFORUPDATEREQUEST_FIELD_NUMBER: _ClassVar[int]
    CHECKFORUPDATERESPONSE_FIELD_NUMBER: _ClassVar[int]
    CLEARUPDATEREQUEST_FIELD_NUMBER: _ClassVar[int]
    CLEARUPDATERESPONSE_FIELD_NUMBER: _ClassVar[int]
    DEVICECERTREQUEST_FIELD_NUMBER: _ClassVar[int]
    DEVICECERTRESPONSE_FIELD_NUMBER: _ClassVar[int]
    CONFIGUREWIFIENCRYPTEDREQUEST_FIELD_NUMBER: _ClassVar[int]
    CONFIGUREWIFIENCRYPTEDRESPONSE_FIELD_NUMBER: _ClassVar[int]
    GETNETWORKINGSTATUSREQUEST_FIELD_NUMBER: _ClassVar[int]
    GETNETWORKINGSTATUSRESPONSE_FIELD_NUMBER: _ClassVar[int]
    GETCELLULARINFOREQUEST_FIELD_NUMBER: _ClassVar[int]
    GETCELLULARINFORESPONSE_FIELD_NUMBER: _ClassVar[int]
    CONFIGUREETHERNETREQUEST_FIELD_NUMBER: _ClassVar[int]
    CONFIGUREETHERNETRESPONSE_FIELD_NUMBER: _ClassVar[int]
    FORGETWIFINETWORKREQUEST_FIELD_NUMBER: _ClassVar[int]
    FORGETWIFINETWORKRESPONSE_FIELD_NUMBER: _ClassVar[int]
    CHECKINTERNETREQUEST_FIELD_NUMBER: _ClassVar[int]
    CHECKINTERNETRESPONSE_FIELD_NUMBER: _ClassVar[int]
    errorResponse: ErrorResponse
    getSystemInfoRequest: CommonAPIGetSystemInfoRequest
    getSystemInfoResponse: CommonAPIGetSystemInfoResponse
    setLocalSiteConfigRequest: CommonAPISetLocalSiteConfigRequest
    setLocalSiteConfigResponse: CommonAPISetLocalSiteConfigResponse
    performUpdateRequest: CommonAPIPerformUpdateRequest
    performUpdateResponse: CommonAPIPerformUpdateResponse
    factoryResetRequest: CommonAPIFactoryResetRequest
    factoryResetResponse: CommonAPIFactoryResetResponse
    wifiScanRequest: CommonAPIWifiScanRequest
    wifiScanResponse: CommonAPIWifiScanResponse
    configureWifiRequest: CommonAPIConfigureWifiRequest
    configureWifiResponse: CommonAPIConfigureWifiResponse
    checkForUpdateRequest: CommonAPICheckForUpdateRequest
    checkForUpdateResponse: CommonAPICheckForUpdateResponse
    clearUpdateRequest: CommonAPIClearUpdateRequest
    clearUpdateResponse: CommonAPIClearUpdateResponse
    deviceCertRequest: CommonAPIDeviceCertRequest
    deviceCertResponse: CommonAPIDeviceCertResponse
    configureWifiEncryptedRequest: CommonAPIConfigureWifiEncryptedRequest
    configureWifiEncryptedResponse: CommonAPIConfigureWifiEncryptedResponse
    getNetworkingStatusRequest: CommonAPIGetNetworkingStatusRequest
    getNetworkingStatusResponse: CommonAPIGetNetworkingStatusResponse
    getCellularInfoRequest: CommonAPIGetCellularInfoRequest
    getCellularInfoResponse: CommonAPIGetCellularInfoResponse
    configureEthernetRequest: CommonAPIConfigureEthernetRequest
    configureEthernetResponse: CommonAPIConfigureEthernetResponse
    forgetWifiNetworkRequest: CommonAPIForgetWifiNetworkRequest
    forgetWifiNetworkResponse: CommonAPIForgetWifiNetworkResponse
    checkInternetRequest: CommonAPICheckInternetRequest
    checkInternetResponse: CommonAPICheckInternetResponse
    def __init__(self, errorResponse: _Optional[_Union[ErrorResponse, _Mapping]] = ..., getSystemInfoRequest: _Optional[_Union[CommonAPIGetSystemInfoRequest, _Mapping]] = ..., getSystemInfoResponse: _Optional[_Union[CommonAPIGetSystemInfoResponse, _Mapping]] = ..., setLocalSiteConfigRequest: _Optional[_Union[CommonAPISetLocalSiteConfigRequest, _Mapping]] = ..., setLocalSiteConfigResponse: _Optional[_Union[CommonAPISetLocalSiteConfigResponse, _Mapping]] = ..., performUpdateRequest: _Optional[_Union[CommonAPIPerformUpdateRequest, _Mapping]] = ..., performUpdateResponse: _Optional[_Union[CommonAPIPerformUpdateResponse, _Mapping]] = ..., factoryResetRequest: _Optional[_Union[CommonAPIFactoryResetRequest, _Mapping]] = ..., factoryResetResponse: _Optional[_Union[CommonAPIFactoryResetResponse, _Mapping]] = ..., wifiScanRequest: _Optional[_Union[CommonAPIWifiScanRequest, _Mapping]] = ..., wifiScanResponse: _Optional[_Union[CommonAPIWifiScanResponse, _Mapping]] = ..., configureWifiRequest: _Optional[_Union[CommonAPIConfigureWifiRequest, _Mapping]] = ..., configureWifiResponse: _Optional[_Union[CommonAPIConfigureWifiResponse, _Mapping]] = ..., checkForUpdateRequest: _Optional[_Union[CommonAPICheckForUpdateRequest, _Mapping]] = ..., checkForUpdateResponse: _Optional[_Union[CommonAPICheckForUpdateResponse, _Mapping]] = ..., clearUpdateRequest: _Optional[_Union[CommonAPIClearUpdateRequest, _Mapping]] = ..., clearUpdateResponse: _Optional[_Union[CommonAPIClearUpdateResponse, _Mapping]] = ..., deviceCertRequest: _Optional[_Union[CommonAPIDeviceCertRequest, _Mapping]] = ..., deviceCertResponse: _Optional[_Union[CommonAPIDeviceCertResponse, _Mapping]] = ..., configureWifiEncryptedRequest: _Optional[_Union[CommonAPIConfigureWifiEncryptedRequest, _Mapping]] = ..., configureWifiEncryptedResponse: _Optional[_Union[CommonAPIConfigureWifiEncryptedResponse, _Mapping]] = ..., getNetworkingStatusRequest: _Optional[_Union[CommonAPIGetNetworkingStatusRequest, _Mapping]] = ..., getNetworkingStatusResponse: _Optional[_Union[CommonAPIGetNetworkingStatusResponse, _Mapping]] = ..., getCellularInfoRequest: _Optional[_Union[CommonAPIGetCellularInfoRequest, _Mapping]] = ..., getCellularInfoResponse: _Optional[_Union[CommonAPIGetCellularInfoResponse, _Mapping]] = ..., configureEthernetRequest: _Optional[_Union[CommonAPIConfigureEthernetRequest, _Mapping]] = ..., configureEthernetResponse: _Optional[_Union[CommonAPIConfigureEthernetResponse, _Mapping]] = ..., forgetWifiNetworkRequest: _Optional[_Union[CommonAPIForgetWifiNetworkRequest, _Mapping]] = ..., forgetWifiNetworkResponse: _Optional[_Union[CommonAPIForgetWifiNetworkResponse, _Mapping]] = ..., checkInternetRequest: _Optional[_Union[CommonAPICheckInternetRequest, _Mapping]] = ..., checkInternetResponse: _Optional[_Union[CommonAPICheckInternetResponse, _Mapping]] = ...) -> None: ...

class ErrorResponse(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: Status
    def __init__(self, status: _Optional[_Union[Status, _Mapping]] = ...) -> None: ...

class Status(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: int
    message: str
    def __init__(self, code: _Optional[int] = ..., message: _Optional[str] = ...) -> None: ...

class CommonAPIGetSystemInfoRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIGetSystemInfoResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPISetLocalSiteConfigRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPISetLocalSiteConfigResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIPerformUpdateRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIPerformUpdateResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIFactoryResetRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIFactoryResetResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPICheckForUpdateRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPICheckForUpdateResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIClearUpdateRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIClearUpdateResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPICheckInternetRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIForgetWifiNetworkResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIWifiScanRequest(_message.Message):
    __slots__ = ("maxScanDurationS", "desiredSecurityTypes", "maximumTotalAps")
    MAXSCANDURATIONS_FIELD_NUMBER: _ClassVar[int]
    DESIREDSECURITYTYPES_FIELD_NUMBER: _ClassVar[int]
    MAXIMUMTOTALAPS_FIELD_NUMBER: _ClassVar[int]
    maxScanDurationS: int
    desiredSecurityTypes: _containers.RepeatedScalarFieldContainer[int]
    maximumTotalAps: int
    def __init__(self, maxScanDurationS: _Optional[int] = ..., desiredSecurityTypes: _Optional[_Iterable[int]] = ..., maximumTotalAps: _Optional[int] = ...) -> None: ...

class CommonAPIWifiScanResponse(_message.Message):
    __slots__ = ("wifiNetworks",)
    WIFINETWORKS_FIELD_NUMBER: _ClassVar[int]
    wifiNetworks: _containers.RepeatedCompositeFieldContainer[WifiNetwork]
    def __init__(self, wifiNetworks: _Optional[_Iterable[_Union[WifiNetwork, _Mapping]]] = ...) -> None: ...

class WifiNetwork(_message.Message):
    __slots__ = ("placeholder",)
    PLACEHOLDER_FIELD_NUMBER: _ClassVar[int]
    placeholder: bytes
    def __init__(self, placeholder: _Optional[bytes] = ...) -> None: ...

class CommonAPIConfigureWifiRequest(_message.Message):
    __slots__ = ("enabled", "wifiConfig")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    WIFICONFIG_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    wifiConfig: WifiConfig
    def __init__(self, enabled: bool = ..., wifiConfig: _Optional[_Union[WifiConfig, _Mapping]] = ...) -> None: ...

class CommonAPIConfigureWifiResponse(_message.Message):
    __slots__ = ("wifiConfig", "wifi")
    WIFICONFIG_FIELD_NUMBER: _ClassVar[int]
    WIFI_FIELD_NUMBER: _ClassVar[int]
    wifiConfig: WifiConfig
    wifi: NetworkInterface
    def __init__(self, wifiConfig: _Optional[_Union[WifiConfig, _Mapping]] = ..., wifi: _Optional[_Union[NetworkInterface, _Mapping]] = ...) -> None: ...

class CommonAPIConfigureWifiEncryptedRequest(_message.Message):
    __slots__ = ("enabled", "wifiConfig", "encryptedPassword")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    WIFICONFIG_FIELD_NUMBER: _ClassVar[int]
    ENCRYPTEDPASSWORD_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    wifiConfig: WifiConfig
    encryptedPassword: bytes
    def __init__(self, enabled: bool = ..., wifiConfig: _Optional[_Union[WifiConfig, _Mapping]] = ..., encryptedPassword: _Optional[bytes] = ...) -> None: ...

class CommonAPIConfigureWifiEncryptedResponse(_message.Message):
    __slots__ = ("wifiConfig", "wifi", "result")
    WIFICONFIG_FIELD_NUMBER: _ClassVar[int]
    WIFI_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    wifiConfig: WifiConfig
    wifi: NetworkInterface
    result: WifiConfigureResult
    def __init__(self, wifiConfig: _Optional[_Union[WifiConfig, _Mapping]] = ..., wifi: _Optional[_Union[NetworkInterface, _Mapping]] = ..., result: _Optional[_Union[WifiConfigureResult, str]] = ...) -> None: ...

class CommonAPIDeviceCertRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIDeviceCertResponse(_message.Message):
    __slots__ = ("format", "deviceCert")
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    DEVICECERT_FIELD_NUMBER: _ClassVar[int]
    format: int
    deviceCert: bytes
    def __init__(self, format: _Optional[int] = ..., deviceCert: _Optional[bytes] = ...) -> None: ...

class CommonAPIGetCellularInfoRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIGetCellularInfoResponse(_message.Message):
    __slots__ = ("eid",)
    EID_FIELD_NUMBER: _ClassVar[int]
    eid: CellularEID
    def __init__(self, eid: _Optional[_Union[CellularEID, _Mapping]] = ...) -> None: ...

class CommonAPIForgetWifiNetworkRequest(_message.Message):
    __slots__ = ("ssid",)
    SSID_FIELD_NUMBER: _ClassVar[int]
    ssid: str
    def __init__(self, ssid: _Optional[str] = ...) -> None: ...

class CommonAPIGetNetworkingStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CommonAPIGetNetworkingStatusResponse(_message.Message):
    __slots__ = ("wifiConfig", "wifi", "eth", "gsm")
    WIFICONFIG_FIELD_NUMBER: _ClassVar[int]
    WIFI_FIELD_NUMBER: _ClassVar[int]
    ETH_FIELD_NUMBER: _ClassVar[int]
    GSM_FIELD_NUMBER: _ClassVar[int]
    wifiConfig: WifiConfig
    wifi: NetworkInterface
    eth: NetworkInterface
    gsm: NetworkInterface
    def __init__(self, wifiConfig: _Optional[_Union[WifiConfig, _Mapping]] = ..., wifi: _Optional[_Union[NetworkInterface, _Mapping]] = ..., eth: _Optional[_Union[NetworkInterface, _Mapping]] = ..., gsm: _Optional[_Union[NetworkInterface, _Mapping]] = ...) -> None: ...

class CommonAPIConfigureEthernetRequest(_message.Message):
    __slots__ = ("ipv4Config",)
    IPV4CONFIG_FIELD_NUMBER: _ClassVar[int]
    ipv4Config: NetworkInterfaceIPv4Config
    def __init__(self, ipv4Config: _Optional[_Union[NetworkInterfaceIPv4Config, _Mapping]] = ...) -> None: ...

class CommonAPIConfigureEthernetResponse(_message.Message):
    __slots__ = ("eth",)
    ETH_FIELD_NUMBER: _ClassVar[int]
    eth: NetworkInterface
    def __init__(self, eth: _Optional[_Union[NetworkInterface, _Mapping]] = ...) -> None: ...

class CommonAPICheckInternetResponse(_message.Message):
    __slots__ = ("wifi", "eth", "gsm")
    WIFI_FIELD_NUMBER: _ClassVar[int]
    ETH_FIELD_NUMBER: _ClassVar[int]
    GSM_FIELD_NUMBER: _ClassVar[int]
    wifi: NetworkInterface
    eth: NetworkInterface
    gsm: NetworkInterface
    def __init__(self, wifi: _Optional[_Union[NetworkInterface, _Mapping]] = ..., eth: _Optional[_Union[NetworkInterface, _Mapping]] = ..., gsm: _Optional[_Union[NetworkInterface, _Mapping]] = ...) -> None: ...

class NetworkInterfaceIPv4Config(_message.Message):
    __slots__ = ("dhcpEnabled", "address", "subnetMask", "gateway", "dns")
    DHCPENABLED_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_FIELD_NUMBER: _ClassVar[int]
    SUBNETMASK_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_FIELD_NUMBER: _ClassVar[int]
    DNS_FIELD_NUMBER: _ClassVar[int]
    dhcpEnabled: bool
    address: int
    subnetMask: int
    gateway: int
    dns: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, dhcpEnabled: bool = ..., address: _Optional[int] = ..., subnetMask: _Optional[int] = ..., gateway: _Optional[int] = ..., dns: _Optional[_Iterable[int]] = ...) -> None: ...

class NetworkInterface(_message.Message):
    __slots__ = ("macAddress", "enabled", "activeRoute", "ipv4Config", "connectivityStatus")
    MACADDRESS_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    ACTIVEROUTE_FIELD_NUMBER: _ClassVar[int]
    IPV4CONFIG_FIELD_NUMBER: _ClassVar[int]
    CONNECTIVITYSTATUS_FIELD_NUMBER: _ClassVar[int]
    macAddress: bytes
    enabled: bool
    activeRoute: bool
    ipv4Config: NetworkInterfaceIPv4Config
    connectivityStatus: NetworkConnectivityStatus
    def __init__(self, macAddress: _Optional[bytes] = ..., enabled: bool = ..., activeRoute: bool = ..., ipv4Config: _Optional[_Union[NetworkInterfaceIPv4Config, _Mapping]] = ..., connectivityStatus: _Optional[_Union[NetworkConnectivityStatus, _Mapping]] = ...) -> None: ...

class NetworkConnectivityStatus(_message.Message):
    __slots__ = ("connectedPhysical", "connectedInternet", "connectedTesla")
    CONNECTEDPHYSICAL_FIELD_NUMBER: _ClassVar[int]
    CONNECTEDINTERNET_FIELD_NUMBER: _ClassVar[int]
    CONNECTEDTESLA_FIELD_NUMBER: _ClassVar[int]
    connectedPhysical: bool
    connectedInternet: bool
    connectedTesla: bool
    def __init__(self, connectedPhysical: bool = ..., connectedInternet: bool = ..., connectedTesla: bool = ...) -> None: ...

class WifiConfig(_message.Message):
    __slots__ = ("ssid", "password", "securityType")
    SSID_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    SECURITYTYPE_FIELD_NUMBER: _ClassVar[int]
    ssid: str
    password: WifiPassword
    securityType: WifiNetworkSecurityType
    def __init__(self, ssid: _Optional[str] = ..., password: _Optional[_Union[WifiPassword, _Mapping]] = ..., securityType: _Optional[_Union[WifiNetworkSecurityType, str]] = ...) -> None: ...

class WifiPassword(_message.Message):
    __slots__ = ("value",)
    VALUE_FIELD_NUMBER: _ClassVar[int]
    value: str
    def __init__(self, value: _Optional[str] = ...) -> None: ...

class CellularEID(_message.Message):
    __slots__ = ("value",)
    VALUE_FIELD_NUMBER: _ClassVar[int]
    value: str
    def __init__(self, value: _Optional[str] = ...) -> None: ...

class TEGMessages(_message.Message):
    __slots__ = ("placeholder",)
    PLACEHOLDER_FIELD_NUMBER: _ClassVar[int]
    placeholder: bytes
    def __init__(self, placeholder: _Optional[bytes] = ...) -> None: ...

class WCMessages(_message.Message):
    __slots__ = ("placeholder",)
    PLACEHOLDER_FIELD_NUMBER: _ClassVar[int]
    placeholder: bytes
    def __init__(self, placeholder: _Optional[bytes] = ...) -> None: ...

class NeurioCTConfig(_message.Message):
    __slots__ = ("location", "realPowerScaleFactor")
    LOCATION_FIELD_NUMBER: _ClassVar[int]
    REALPOWERSCALEFACTOR_FIELD_NUMBER: _ClassVar[int]
    location: int
    realPowerScaleFactor: float
    def __init__(self, location: _Optional[int] = ..., realPowerScaleFactor: _Optional[float] = ...) -> None: ...

class NeurioMeterConfig(_message.Message):
    __slots__ = ("shortId", "serial", "ctConfig")
    SHORTID_FIELD_NUMBER: _ClassVar[int]
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    CTCONFIG_FIELD_NUMBER: _ClassVar[int]
    shortId: str
    serial: str
    ctConfig: _containers.RepeatedCompositeFieldContainer[NeurioCTConfig]
    def __init__(self, shortId: _Optional[str] = ..., serial: _Optional[str] = ..., ctConfig: _Optional[_Iterable[_Union[NeurioCTConfig, _Mapping]]] = ...) -> None: ...

class NeurioMeterConnection(_message.Message):
    __slots__ = ("connectionStatus", "connectionError", "rssi", "firmwareVersion", "meterReadings")
    CONNECTIONSTATUS_FIELD_NUMBER: _ClassVar[int]
    CONNECTIONERROR_FIELD_NUMBER: _ClassVar[int]
    RSSI_FIELD_NUMBER: _ClassVar[int]
    FIRMWAREVERSION_FIELD_NUMBER: _ClassVar[int]
    METERREADINGS_FIELD_NUMBER: _ClassVar[int]
    connectionStatus: NeurioConnectionStatus
    connectionError: NeurioConnectionError
    rssi: Rssi
    firmwareVersion: str
    meterReadings: NeurioMeterReadings
    def __init__(self, connectionStatus: _Optional[_Union[NeurioConnectionStatus, str]] = ..., connectionError: _Optional[_Union[NeurioConnectionError, str]] = ..., rssi: _Optional[_Union[Rssi, _Mapping]] = ..., firmwareVersion: _Optional[str] = ..., meterReadings: _Optional[_Union[NeurioMeterReadings, _Mapping]] = ...) -> None: ...

class Rssi(_message.Message):
    __slots__ = ("value", "signalStrengthPercent")
    VALUE_FIELD_NUMBER: _ClassVar[int]
    SIGNALSTRENGTHPERCENT_FIELD_NUMBER: _ClassVar[int]
    value: int
    signalStrengthPercent: int
    def __init__(self, value: _Optional[int] = ..., signalStrengthPercent: _Optional[int] = ...) -> None: ...

class NeurioCTReading(_message.Message):
    __slots__ = ("realPowerW", "scaledRealPowerW", "currentAmps")
    REALPOWERW_FIELD_NUMBER: _ClassVar[int]
    SCALEDREALPOWERW_FIELD_NUMBER: _ClassVar[int]
    CURRENTAMPS_FIELD_NUMBER: _ClassVar[int]
    realPowerW: float
    scaledRealPowerW: float
    currentAmps: float
    def __init__(self, realPowerW: _Optional[float] = ..., scaledRealPowerW: _Optional[float] = ..., currentAmps: _Optional[float] = ...) -> None: ...

class NeurioMeterReadings(_message.Message):
    __slots__ = ("ctReadings",)
    CTREADINGS_FIELD_NUMBER: _ClassVar[int]
    ctReadings: _containers.RepeatedCompositeFieldContainer[NeurioCTReading]
    def __init__(self, ctReadings: _Optional[_Iterable[_Union[NeurioCTReading, _Mapping]]] = ...) -> None: ...

class NeurioMeterInterface(_message.Message):
    __slots__ = ("config", "connection")
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    CONNECTION_FIELD_NUMBER: _ClassVar[int]
    config: NeurioMeterConfig
    connection: NeurioMeterConnection
    def __init__(self, config: _Optional[_Union[NeurioMeterConfig, _Mapping]] = ..., connection: _Optional[_Union[NeurioMeterConnection, _Mapping]] = ...) -> None: ...

class NeurioMeterAPIAddMeterRequest(_message.Message):
    __slots__ = ("config",)
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    config: NeurioMeterConfig
    def __init__(self, config: _Optional[_Union[NeurioMeterConfig, _Mapping]] = ...) -> None: ...

class NeurioMeterAPIAddMeterResponse(_message.Message):
    __slots__ = ("config",)
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    config: NeurioMeterConfig
    def __init__(self, config: _Optional[_Union[NeurioMeterConfig, _Mapping]] = ...) -> None: ...

class NeurioMeterAPIRemoveMeterRequest(_message.Message):
    __slots__ = ("serial",)
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    serial: str
    def __init__(self, serial: _Optional[str] = ...) -> None: ...

class NeurioMeterAPIRemoveMeterResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class NeurioMeterAPIConfigureCtsRequest(_message.Message):
    __slots__ = ("serial", "ctConfig")
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    CTCONFIG_FIELD_NUMBER: _ClassVar[int]
    serial: str
    ctConfig: _containers.RepeatedCompositeFieldContainer[NeurioCTConfig]
    def __init__(self, serial: _Optional[str] = ..., ctConfig: _Optional[_Iterable[_Union[NeurioCTConfig, _Mapping]]] = ...) -> None: ...

class NeurioMeterAPIConfigureCtsResponse(_message.Message):
    __slots__ = ("ctConfig",)
    CTCONFIG_FIELD_NUMBER: _ClassVar[int]
    ctConfig: _containers.RepeatedCompositeFieldContainer[NeurioCTConfig]
    def __init__(self, ctConfig: _Optional[_Iterable[_Union[NeurioCTConfig, _Mapping]]] = ...) -> None: ...

class NeurioMeterMessages(_message.Message):
    __slots__ = ("addMeterRequest", "addMeterResponse", "removeMeterRequest", "removeMeterResponse", "configureCtsRequest", "configureCtsResponse")
    ADDMETERREQUEST_FIELD_NUMBER: _ClassVar[int]
    ADDMETERRESPONSE_FIELD_NUMBER: _ClassVar[int]
    REMOVEMETERREQUEST_FIELD_NUMBER: _ClassVar[int]
    REMOVEMETERRESPONSE_FIELD_NUMBER: _ClassVar[int]
    CONFIGURECTSREQUEST_FIELD_NUMBER: _ClassVar[int]
    CONFIGURECTSRESPONSE_FIELD_NUMBER: _ClassVar[int]
    addMeterRequest: NeurioMeterAPIAddMeterRequest
    addMeterResponse: NeurioMeterAPIAddMeterResponse
    removeMeterRequest: NeurioMeterAPIRemoveMeterRequest
    removeMeterResponse: NeurioMeterAPIRemoveMeterResponse
    configureCtsRequest: NeurioMeterAPIConfigureCtsRequest
    configureCtsResponse: NeurioMeterAPIConfigureCtsResponse
    def __init__(self, addMeterRequest: _Optional[_Union[NeurioMeterAPIAddMeterRequest, _Mapping]] = ..., addMeterResponse: _Optional[_Union[NeurioMeterAPIAddMeterResponse, _Mapping]] = ..., removeMeterRequest: _Optional[_Union[NeurioMeterAPIRemoveMeterRequest, _Mapping]] = ..., removeMeterResponse: _Optional[_Union[NeurioMeterAPIRemoveMeterResponse, _Mapping]] = ..., configureCtsRequest: _Optional[_Union[NeurioMeterAPIConfigureCtsRequest, _Mapping]] = ..., configureCtsResponse: _Optional[_Union[NeurioMeterAPIConfigureCtsResponse, _Mapping]] = ...) -> None: ...

class EnergySiteNetMessages(_message.Message):
    __slots__ = ("placeholder",)
    PLACEHOLDER_FIELD_NUMBER: _ClassVar[int]
    placeholder: bytes
    def __init__(self, placeholder: _Optional[bytes] = ...) -> None: ...

class AuthorizationRecord(_message.Message):
    __slots__ = ("type", "description", "keyType", "publicKey", "roles", "state", "verification", "identifier", "authorizedByPublicKey")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    KEYTYPE_FIELD_NUMBER: _ClassVar[int]
    PUBLICKEY_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    VERIFICATION_FIELD_NUMBER: _ClassVar[int]
    IDENTIFIER_FIELD_NUMBER: _ClassVar[int]
    AUTHORIZEDBYPUBLICKEY_FIELD_NUMBER: _ClassVar[int]
    type: AuthorizedClientType
    description: str
    keyType: AuthorizedKeyType
    publicKey: bytes
    roles: _containers.RepeatedScalarFieldContainer[AuthorizationRole]
    state: AuthorizedState
    verification: AuthorizedVerificationType
    identifier: str
    authorizedByPublicKey: bytes
    def __init__(self, type: _Optional[_Union[AuthorizedClientType, str]] = ..., description: _Optional[str] = ..., keyType: _Optional[_Union[AuthorizedKeyType, str]] = ..., publicKey: _Optional[bytes] = ..., roles: _Optional[_Iterable[_Union[AuthorizationRole, str]]] = ..., state: _Optional[_Union[AuthorizedState, str]] = ..., verification: _Optional[_Union[AuthorizedVerificationType, str]] = ..., identifier: _Optional[str] = ..., authorizedByPublicKey: _Optional[bytes] = ...) -> None: ...

class AuthorizationMessages(_message.Message):
    __slots__ = ("addAuthorizedClientRequest", "addAuthorizedClientResponse", "removeAuthorizedClientRequest", "removeAuthorizedClientResponse", "listAuthorizedClientsRequest", "listAuthorizedClientsResponse", "getSignedCommandsPublicKeyRequest", "getSignedCommandsPublicKeyResponse", "addAuthorizedClientByTrustedSignatureRequest", "addAuthorizedClientByTrustedSignatureResponse", "configureRemoteServiceRequest", "configureRemoteServiceResponse")
    ADDAUTHORIZEDCLIENTREQUEST_FIELD_NUMBER: _ClassVar[int]
    ADDAUTHORIZEDCLIENTRESPONSE_FIELD_NUMBER: _ClassVar[int]
    REMOVEAUTHORIZEDCLIENTREQUEST_FIELD_NUMBER: _ClassVar[int]
    REMOVEAUTHORIZEDCLIENTRESPONSE_FIELD_NUMBER: _ClassVar[int]
    LISTAUTHORIZEDCLIENTSREQUEST_FIELD_NUMBER: _ClassVar[int]
    LISTAUTHORIZEDCLIENTSRESPONSE_FIELD_NUMBER: _ClassVar[int]
    GETSIGNEDCOMMANDSPUBLICKEYREQUEST_FIELD_NUMBER: _ClassVar[int]
    GETSIGNEDCOMMANDSPUBLICKEYRESPONSE_FIELD_NUMBER: _ClassVar[int]
    ADDAUTHORIZEDCLIENTBYTRUSTEDSIGNATUREREQUEST_FIELD_NUMBER: _ClassVar[int]
    ADDAUTHORIZEDCLIENTBYTRUSTEDSIGNATURERESPONSE_FIELD_NUMBER: _ClassVar[int]
    CONFIGUREREMOTESERVICEREQUEST_FIELD_NUMBER: _ClassVar[int]
    CONFIGUREREMOTESERVICERESPONSE_FIELD_NUMBER: _ClassVar[int]
    addAuthorizedClientRequest: AuthorizationAPIAddAuthorizedClientRequest
    addAuthorizedClientResponse: AuthorizationAPIAddAuthorizedClientResponse
    removeAuthorizedClientRequest: AuthorizationAPIRemoveAuthorizedClientRequest
    removeAuthorizedClientResponse: AuthorizationAPIRemoveAuthorizedClientResponse
    listAuthorizedClientsRequest: AuthorizationAPIListAuthorizedClientsRequest
    listAuthorizedClientsResponse: AuthorizationAPIListAuthorizedClientsResponse
    getSignedCommandsPublicKeyRequest: AuthorizationAPIGetSignedCommandsPublicKeyRequest
    getSignedCommandsPublicKeyResponse: AuthorizationAPIGetSignedCommandsPublicKeyResponse
    addAuthorizedClientByTrustedSignatureRequest: AuthorizationAPIAddAuthorizedClientByTrustedSignatureRequest
    addAuthorizedClientByTrustedSignatureResponse: AuthorizationAPIAddAuthorizedClientByTrustedSignatureResponse
    configureRemoteServiceRequest: AuthorizationAPIConfigureRemoteServiceRequest
    configureRemoteServiceResponse: AuthorizationAPIConfigureRemoteServiceResponse
    def __init__(self, addAuthorizedClientRequest: _Optional[_Union[AuthorizationAPIAddAuthorizedClientRequest, _Mapping]] = ..., addAuthorizedClientResponse: _Optional[_Union[AuthorizationAPIAddAuthorizedClientResponse, _Mapping]] = ..., removeAuthorizedClientRequest: _Optional[_Union[AuthorizationAPIRemoveAuthorizedClientRequest, _Mapping]] = ..., removeAuthorizedClientResponse: _Optional[_Union[AuthorizationAPIRemoveAuthorizedClientResponse, _Mapping]] = ..., listAuthorizedClientsRequest: _Optional[_Union[AuthorizationAPIListAuthorizedClientsRequest, _Mapping]] = ..., listAuthorizedClientsResponse: _Optional[_Union[AuthorizationAPIListAuthorizedClientsResponse, _Mapping]] = ..., getSignedCommandsPublicKeyRequest: _Optional[_Union[AuthorizationAPIGetSignedCommandsPublicKeyRequest, _Mapping]] = ..., getSignedCommandsPublicKeyResponse: _Optional[_Union[AuthorizationAPIGetSignedCommandsPublicKeyResponse, _Mapping]] = ..., addAuthorizedClientByTrustedSignatureRequest: _Optional[_Union[AuthorizationAPIAddAuthorizedClientByTrustedSignatureRequest, _Mapping]] = ..., addAuthorizedClientByTrustedSignatureResponse: _Optional[_Union[AuthorizationAPIAddAuthorizedClientByTrustedSignatureResponse, _Mapping]] = ..., configureRemoteServiceRequest: _Optional[_Union[AuthorizationAPIConfigureRemoteServiceRequest, _Mapping]] = ..., configureRemoteServiceResponse: _Optional[_Union[AuthorizationAPIConfigureRemoteServiceResponse, _Mapping]] = ...) -> None: ...

class AuthorizationAPIAddAuthorizedClientRequest(_message.Message):
    __slots__ = ("type", "description", "keyType", "publicKey")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    KEYTYPE_FIELD_NUMBER: _ClassVar[int]
    PUBLICKEY_FIELD_NUMBER: _ClassVar[int]
    type: AuthorizedClientType
    description: str
    keyType: AuthorizedKeyType
    publicKey: bytes
    def __init__(self, type: _Optional[_Union[AuthorizedClientType, str]] = ..., description: _Optional[str] = ..., keyType: _Optional[_Union[AuthorizedKeyType, str]] = ..., publicKey: _Optional[bytes] = ...) -> None: ...

class AuthorizationAPIAddAuthorizedClientResponse(_message.Message):
    __slots__ = ("client",)
    CLIENT_FIELD_NUMBER: _ClassVar[int]
    client: AuthorizationRecord
    def __init__(self, client: _Optional[_Union[AuthorizationRecord, _Mapping]] = ...) -> None: ...

class AuthorizationAPIRemoveAuthorizedClientRequest(_message.Message):
    __slots__ = ("publicKey",)
    PUBLICKEY_FIELD_NUMBER: _ClassVar[int]
    publicKey: bytes
    def __init__(self, publicKey: _Optional[bytes] = ...) -> None: ...

class AuthorizationAPIRemoveAuthorizedClientResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AuthorizationAPIListAuthorizedClientsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AuthorizationAPIListAuthorizedClientsResponse(_message.Message):
    __slots__ = ("clients", "enableLineSwitchOff")
    CLIENTS_FIELD_NUMBER: _ClassVar[int]
    ENABLELINESWITCHOFF_FIELD_NUMBER: _ClassVar[int]
    clients: _containers.RepeatedCompositeFieldContainer[AuthorizationRecord]
    enableLineSwitchOff: bool
    def __init__(self, clients: _Optional[_Iterable[_Union[AuthorizationRecord, _Mapping]]] = ..., enableLineSwitchOff: bool = ...) -> None: ...

class AuthorizationAPIGetSignedCommandsPublicKeyRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AuthorizationAPIGetSignedCommandsPublicKeyResponse(_message.Message):
    __slots__ = ("pubKeyEcc",)
    PUBKEYECC_FIELD_NUMBER: _ClassVar[int]
    pubKeyEcc: bytes
    def __init__(self, pubKeyEcc: _Optional[bytes] = ...) -> None: ...

class AuthorizationAPIAddAuthorizedClientByTrustedSignatureRequest(_message.Message):
    __slots__ = ("type", "description", "keyType", "publicKey", "roles", "identifier")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    KEYTYPE_FIELD_NUMBER: _ClassVar[int]
    PUBLICKEY_FIELD_NUMBER: _ClassVar[int]
    ROLES_FIELD_NUMBER: _ClassVar[int]
    IDENTIFIER_FIELD_NUMBER: _ClassVar[int]
    type: AuthorizedClientType
    description: str
    keyType: AuthorizedKeyType
    publicKey: bytes
    roles: _containers.RepeatedScalarFieldContainer[AuthorizationRole]
    identifier: str
    def __init__(self, type: _Optional[_Union[AuthorizedClientType, str]] = ..., description: _Optional[str] = ..., keyType: _Optional[_Union[AuthorizedKeyType, str]] = ..., publicKey: _Optional[bytes] = ..., roles: _Optional[_Iterable[_Union[AuthorizationRole, str]]] = ..., identifier: _Optional[str] = ...) -> None: ...

class AuthorizationAPIAddAuthorizedClientByTrustedSignatureResponse(_message.Message):
    __slots__ = ("client",)
    CLIENT_FIELD_NUMBER: _ClassVar[int]
    client: AuthorizationRecord
    def __init__(self, client: _Optional[_Union[AuthorizationRecord, _Mapping]] = ...) -> None: ...

class AuthorizationAPIConfigureRemoteServiceRequest(_message.Message):
    __slots__ = ("durationSeconds", "sessionId", "requesterEmail")
    DURATIONSECONDS_FIELD_NUMBER: _ClassVar[int]
    SESSIONID_FIELD_NUMBER: _ClassVar[int]
    REQUESTEREMAIL_FIELD_NUMBER: _ClassVar[int]
    durationSeconds: int
    sessionId: str
    requesterEmail: str
    def __init__(self, durationSeconds: _Optional[int] = ..., sessionId: _Optional[str] = ..., requesterEmail: _Optional[str] = ...) -> None: ...

class AuthorizationAPIConfigureRemoteServiceResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GraphQLMessages(_message.Message):
    __slots__ = ("send", "recv")
    SEND_FIELD_NUMBER: _ClassVar[int]
    RECV_FIELD_NUMBER: _ClassVar[int]
    send: GraphQLAPIQueryRequest
    recv: GraphQLAPIQueryResponse
    def __init__(self, send: _Optional[_Union[GraphQLAPIQueryRequest, _Mapping]] = ..., recv: _Optional[_Union[GraphQLAPIQueryResponse, _Mapping]] = ...) -> None: ...

class SignedGraphQLQuery(_message.Message):
    __slots__ = ("version", "query")
    VERSION_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    version: int
    query: bytes
    def __init__(self, version: _Optional[int] = ..., query: _Optional[bytes] = ...) -> None: ...

class GraphQLAPIQueryRequest(_message.Message):
    __slots__ = ("format", "query", "signature", "variablesJson")
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    VARIABLESJSON_FIELD_NUMBER: _ClassVar[int]
    format: GraphQLQueryFormat
    query: bytes
    signature: bytes
    variablesJson: GraphQLStringValue
    def __init__(self, format: _Optional[_Union[GraphQLQueryFormat, str]] = ..., query: _Optional[bytes] = ..., signature: _Optional[bytes] = ..., variablesJson: _Optional[_Union[GraphQLStringValue, _Mapping]] = ...) -> None: ...

class GraphQLAPIQueryResponse(_message.Message):
    __slots__ = ("status", "data", "errors")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    status: int
    data: str
    errors: _containers.RepeatedCompositeFieldContainer[GraphQLError]
    def __init__(self, status: _Optional[int] = ..., data: _Optional[str] = ..., errors: _Optional[_Iterable[_Union[GraphQLError, _Mapping]]] = ...) -> None: ...

class GraphQLError(_message.Message):
    __slots__ = ("path", "code", "message")
    PATH_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    path: _containers.RepeatedScalarFieldContainer[str]
    code: int
    message: str
    def __init__(self, path: _Optional[_Iterable[str]] = ..., code: _Optional[int] = ..., message: _Optional[str] = ...) -> None: ...

class GraphQLStringValue(_message.Message):
    __slots__ = ("value",)
    VALUE_FIELD_NUMBER: _ClassVar[int]
    value: str
    def __init__(self, value: _Optional[str] = ...) -> None: ...

class FileStoreMessages(_message.Message):
    __slots__ = ("readFileRequest", "readFileResponse", "forceWriteFileRequest", "forceWriteFileResponse", "updateFileRequest", "updateFileResponse")
    READFILEREQUEST_FIELD_NUMBER: _ClassVar[int]
    READFILERESPONSE_FIELD_NUMBER: _ClassVar[int]
    FORCEWRITEFILEREQUEST_FIELD_NUMBER: _ClassVar[int]
    FORCEWRITEFILERESPONSE_FIELD_NUMBER: _ClassVar[int]
    UPDATEFILEREQUEST_FIELD_NUMBER: _ClassVar[int]
    UPDATEFILERESPONSE_FIELD_NUMBER: _ClassVar[int]
    readFileRequest: FileStoreAPIReadFileRequest
    readFileResponse: FileStoreAPIReadFileResponse
    forceWriteFileRequest: FileStoreAPIForceWriteFileRequest
    forceWriteFileResponse: FileStoreAPIForceWriteFileResponse
    updateFileRequest: FileStoreAPIUpdateFileRequest
    updateFileResponse: FileStoreAPIUpdateFileResponse
    def __init__(self, readFileRequest: _Optional[_Union[FileStoreAPIReadFileRequest, _Mapping]] = ..., readFileResponse: _Optional[_Union[FileStoreAPIReadFileResponse, _Mapping]] = ..., forceWriteFileRequest: _Optional[_Union[FileStoreAPIForceWriteFileRequest, _Mapping]] = ..., forceWriteFileResponse: _Optional[_Union[FileStoreAPIForceWriteFileResponse, _Mapping]] = ..., updateFileRequest: _Optional[_Union[FileStoreAPIUpdateFileRequest, _Mapping]] = ..., updateFileResponse: _Optional[_Union[FileStoreAPIUpdateFileResponse, _Mapping]] = ...) -> None: ...

class FileStoreAPIFile(_message.Message):
    __slots__ = ("name", "blob")
    NAME_FIELD_NUMBER: _ClassVar[int]
    BLOB_FIELD_NUMBER: _ClassVar[int]
    name: str
    blob: bytes
    def __init__(self, name: _Optional[str] = ..., blob: _Optional[bytes] = ...) -> None: ...

class FileStoreAPIReadFileRequest(_message.Message):
    __slots__ = ("domain", "name", "ifDifferentHash")
    DOMAIN_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    IFDIFFERENTHASH_FIELD_NUMBER: _ClassVar[int]
    domain: FileStoreAPIDomain
    name: str
    ifDifferentHash: bytes
    def __init__(self, domain: _Optional[_Union[FileStoreAPIDomain, str]] = ..., name: _Optional[str] = ..., ifDifferentHash: _Optional[bytes] = ...) -> None: ...

class FileStoreAPIReadFileResponse(_message.Message):
    __slots__ = ("file", "hash")
    FILE_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    file: FileStoreAPIFile
    hash: bytes
    def __init__(self, file: _Optional[_Union[FileStoreAPIFile, _Mapping]] = ..., hash: _Optional[bytes] = ...) -> None: ...

class FileStoreAPIUpdateFileRequest(_message.Message):
    __slots__ = ("domain", "file", "hash")
    DOMAIN_FIELD_NUMBER: _ClassVar[int]
    FILE_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    domain: FileStoreAPIDomain
    file: FileStoreAPIFile
    hash: bytes
    def __init__(self, domain: _Optional[_Union[FileStoreAPIDomain, str]] = ..., file: _Optional[_Union[FileStoreAPIFile, _Mapping]] = ..., hash: _Optional[bytes] = ...) -> None: ...

class FileStoreAPIUpdateFileResponse(_message.Message):
    __slots__ = ("file", "hash")
    FILE_FIELD_NUMBER: _ClassVar[int]
    HASH_FIELD_NUMBER: _ClassVar[int]
    file: FileStoreAPIFile
    hash: bytes
    def __init__(self, file: _Optional[_Union[FileStoreAPIFile, _Mapping]] = ..., hash: _Optional[bytes] = ...) -> None: ...

class FileStoreAPIForceWriteFileRequest(_message.Message):
    __slots__ = ("domain", "file")
    DOMAIN_FIELD_NUMBER: _ClassVar[int]
    FILE_FIELD_NUMBER: _ClassVar[int]
    domain: FileStoreAPIDomain
    file: FileStoreAPIFile
    def __init__(self, domain: _Optional[_Union[FileStoreAPIDomain, str]] = ..., file: _Optional[_Union[FileStoreAPIFile, _Mapping]] = ...) -> None: ...

class FileStoreAPIForceWriteFileResponse(_message.Message):
    __slots__ = ("hash",)
    HASH_FIELD_NUMBER: _ClassVar[int]
    hash: bytes
    def __init__(self, hash: _Optional[bytes] = ...) -> None: ...
