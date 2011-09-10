from unittest import TestCase
import time
import threading
from dogpile import Dogpile, NeedRegenerationException


import logging
log = logging.getLogger(__name__)

class InlineGetFnTest(TestCase):
    def test_multithreaded_slow(self):
        self._test_multi(10, 5, 4, 1, 10, 1, 1)

    def test_multithreaded_fast(self):
        self._test_multi(10, 1, .8, 1, 100, .05, .05)

    def test_multithreaded_slow_w_fast_expiry(self):
        self._test_multi(10, .5, 1, 1, 10, .1, 1)

    def test_multithreaded_fast_w_slow_expiry(self):
        self._test_multi(10, 5, 4, 1, 100, .05, .05)

    def _test_multi(self, num_threads, 
                            expiretime, 
                            cache_expire_time,
                            creation_time,
                            num_usages, 
                            usage_time, delay_time):

        dogpile = Dogpile(expiretime)

        the_resource = []
        def cache():
            if the_resource:
                if time.time() - the_resource[0] > cache_expire_time:
                    log.debug("cache expiring resource")
                    the_resource[:] = []

            if the_resource:
                return the_resource[0]
            else:
                return None

        def create_resource():
            log.debug("creating resource...")
            time.sleep(creation_time)
            value = time.time()
            the_resource[:] = [value]
            return value

        def get_resource():
            value = cache()
            if value is None:
                raise NeedRegenerationException()
            else:
                return value

        def use_dogpile():
            # "num_usages" usages
            # each usage takes "usage_time" seconds, 
            # "delay_time" seconds in between
            # total of "num_usages * (usage_time + delay_time)" 
            # seconds per thread
            for i in range(num_usages):
                with dogpile.acquire(create_resource, get_resource) as value:
                    # check resource is initialized
                    assert value

                    # time since the current resource was
                    # created
                    time_since_create = time.time() - value

                    # establish "max stale" as, object expired + time 
                    # to create a new one + 10%
                    max_stale = (expiretime + creation_time) * 1.1
                    assert time_since_create < max_stale, \
                        "Value is %f seconds old, expiretime %f, time to create %f" % (
                            time_since_create, expiretime, creation_time
                        )
                    log.debug("time since create %s max stale time %s" % (
                        time_since_create,
                        max_stale
                    ))
                    time.sleep(usage_time)
                time.sleep(delay_time)

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=use_dogpile)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

