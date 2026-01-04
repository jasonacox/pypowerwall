import unittest

from proxy.server import Handler


class TestDispatchHandlers(unittest.TestCase):
    def test_freq_handler_registered(self):
        self.assertIn('/freq', Handler.GET_PATH_HANDLERS)
        self.assertTrue(callable(Handler.GET_PATH_HANDLERS['/freq']))


if __name__ == '__main__':
    unittest.main()
