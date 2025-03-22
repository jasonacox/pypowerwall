import logging
log = logging.getLogger(__name__)


class TEDAPIMessage:
    """Base class for all TED API protobuf messages."""

    def __init__(self, din):
        self.din = din
        self.pb = None

    def SerializeToString(self):
        return self.get_message().SerializeToString()
