from unittest import TestCase
import time
import threading
from dogpile.nameregistry import NameRegistry
import random

import logging
log = logging.getLogger(__name__)

class NameRegistryTest(TestCase):

    def test_name_registry(self):
        success = [True]
        num_operations = [0]

        def create(identifier):
            log.debug("Creator running for id: " + identifier)
            return threading.Lock()

        registry = NameRegistry(create)

        baton = {
            "beans":False,
            "means":False,
            "please":False
        }

        def do_something(name):
            for iteration in xrange(20):
                name = baton.keys()[random.randint(0, 2)]
                lock = registry.get(name)
                lock.acquire()
                try:
                    if baton[name]:
                        success[0] = False
                        log.debug("Baton is already populated")
                        break
                    baton[name] = True
                    try:
                        time.sleep(random.random() * .01)
                    finally:
                        num_operations[0] += 1
                        baton[name] = False
                finally:
                    lock.release()
            log.debug("thread completed operations")

        threads = []
        for id_ in range(1, 20):
            t = threading.Thread(target=do_something, args=("somename",))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        assert success[0]

