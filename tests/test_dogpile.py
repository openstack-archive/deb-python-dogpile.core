from unittest import TestCase
import time
import threading
from dogpile import Dogpile, SyncReaderDogpile

import logging
log = logging.getLogger(__name__)

class DogpileTest(TestCase):
    def test_multithreaded_slow(self):
        self._test_multi(10, 5, 1, 10, 1, 1)

    def test_multithreaded_fast(self):
        self._test_multi(10, 1, 1, 100, .05, .05)

    def test_multithreaded_fast_slow_write(self):
        self._test_multi(10, 1, 1, 100, .05, .05, 2)

    def test_multithreaded_slow_w_fast_expiry(self):
        self._test_multi(10, .5, 1, 10, .1, 1)

    def test_multithreaded_fast_w_slow_expiry(self):
        self._test_multi(10, 5, 1, 100, .05, .05)

    def test_multithreaded_fast_w_slow_expiry_slow_write(self):
        self._test_multi(10, 5, 1, 100, .05, .05, 2)

    def _test_multi(self, num_threads, 
                            expiretime, 
                            creation_time,
                            num_usages, 
                            usage_time, delay_time,
                            slow_write_time=None):
        # expire every "expiretime" seconds

        if slow_write_time:
            dogpile = SyncReaderDogpile(expiretime)
        else:
            dogpile = Dogpile(expiretime)

        the_resource = []
        def create_resource():
            log.debug("creating resource...")
            time.sleep(creation_time)
            if slow_write_time:
                with dogpile.acquire_write_lock():
                    saved = list(the_resource)
                    the_resource[:] = []
                    time.sleep(slow_write_time)
                    the_resource[:] = saved
                    the_resource.append(time.time())
            else:
                the_resource.append(time.time())

        def use_dogpile():
            # "num_usages" usages
            # each usage takes "usage_time" seconds, 
            # "delay_time" seconds in between
            # total of "num_usages * (usage_time + delay_time)" 
            # seconds per thread
            for i in range(num_usages):
                with dogpile.acquire(create_resource):
                    # check resource is initialized
                    assert the_resource

                    # time since the current resource was
                    # created
                    time_since_create = time.time() - the_resource[-1]

                    # establish "max stale" as, object expired + time 
                    # to create a new one + 10%
                    max_stale = (expiretime + creation_time) * 1.1

                    assert time_since_create < max_stale
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

        # total of X seconds, expiry time of Y,
        # means X / Y generations should occur
        expected_generations = (num_usages * 
                                (usage_time + delay_time)) / expiretime
        log.info("Total generations %s Max generations expected %s" % (
            len(the_resource), expected_generations
        ))
        assert len(the_resource) <= expected_generations,\
            "Number of resource generations %d exceeded "\
            "expected %d" % (len(the_resource), 
                expected_generations)

    def test_single_create(self):
        dogpile = Dogpile(2)
        the_resource = [0]

        def create_resource():
            the_resource[0] += 1

        with dogpile.acquire(create_resource):
            assert the_resource[0] == 1

        with dogpile.acquire(create_resource):
            assert the_resource[0] == 1

        time.sleep(2)
        with dogpile.acquire(create_resource):
            assert the_resource[0] == 2

        with dogpile.acquire(create_resource):
            assert the_resource[0] == 2
