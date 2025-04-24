class PyPowerwallTEDAPINoTeslaAuthFile(Exception):
    pass


class PyPowerwallTEDAPITeslaNotConnected(Exception):
    pass


class PyPowerwallTEDAPINotImplemented(Exception):
    pass


class PyPowerwallTEDAPIInvalidPayload(Exception):
    pass


class PyPowerwallTEDAPIThrottleException(Exception):
    pass


class PyPowerwallTEDAPIException(Exception):
    pass