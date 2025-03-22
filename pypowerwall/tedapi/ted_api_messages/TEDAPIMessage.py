import logging
log = logging.getLogger(__name__)


class TEDAPIMessage:
    def __init__(self, din):
        self.din = din

    def SerializeToString(self):
        return self.getMessage().SerializeToString()
