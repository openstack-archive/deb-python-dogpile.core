import unittest
import threading
import dogpile.core


class TestAsyncRunner(unittest.TestCase):
    def test_async_release(self):
        self.called = False

        def runner(mutex):
            self.called = True
            mutex.release()

        mutex = threading.Lock()
        create = lambda: ("value", 1)
        get = lambda: ("value", 1)
        expiretime = 1

        assert not self.called

        with dogpile.core.Lock(mutex, create, get, expiretime, runner) as l:
            assert self.called

        assert self.called

if __name__ == '__main__':
    unittest.main()
