from unittest import TestCase
import time
import threading
from dogpile.core import Lock, NeedRegenerationException
from dogpile.core.nameregistry import NameRegistry
import contextlib
import math
import logging
log = logging.getLogger(__name__)

class ConcurrencyTest(TestCase):
    # expiretime, time to create, num usages, time spend using, delay btw usage

    _assertion_lock = threading.Lock()


    def test_quick(self):
        self._test_multi(
            10, 2, .5, 50, .05, .1,
        )

    def test_slow(self):
        self._test_multi(
            10, 5, 2, 50, .1, .1,
        )


    def test_return_while_in_progress(self):
        self._test_multi(
            10, 5, 2, 50, 1, .1
        )


    def test_get_value_plus_created_long_create(self):
        self._test_multi(
            10, 2, 2.5, 50, .05, .1,
        )

    def test_get_value_plus_created_registry_unsafe_cache(self):
        self._test_multi(
            10, 1, .6, 100, .05, .1,
            cache_expire_time='unsafe'
        )

    def test_get_value_plus_created_registry_safe_cache_quick(self):
        self._test_multi(
            10, 2, .5, 50, .05, .1,
            cache_expire_time='safe'
        )

    def test_get_value_plus_created_registry_safe_cache_slow(self):
        self._test_multi(
            10, 5, 2, 50, .1, .1,
            cache_expire_time='safe'
        )

    def _assert_synchronized(self):
        acq = self._assertion_lock.acquire(False)
        assert acq, "Could not acquire"

        @contextlib.contextmanager
        def go():
            try:
                yield {}
            except:
                raise
            finally:
                self._assertion_lock.release()
        return go()

    def _assert_log(self, cond, msg, *args):
        if cond:
            log.debug(msg, *args)
        else:
            log.error("Assertion failed: " + msg, *args)
            assert False, msg % args

    def _test_multi(self, num_threads,
                            expiretime,
                            creation_time,
                            num_usages,
                            usage_time,
                            delay_time,
                            cache_expire_time=None):

        mutex = threading.Lock()

        unsafe_cache = False
        if cache_expire_time:
            if cache_expire_time == 'unsafe':
                unsafe_cache = True
                cache_expire_time = expiretime * .8
            elif cache_expire_time == 'safe':
                cache_expire_time = (expiretime + creation_time) * 1.1
            else:
                assert False, cache_expire_time

            log.info("Cache expire time: %s", cache_expire_time)

            effective_expiretime = min(cache_expire_time, expiretime)
        else:
            effective_expiretime = expiretime

        effective_creation_time = creation_time

        max_stale = (effective_expiretime + effective_creation_time +
                        usage_time + delay_time) * 1.1

        the_resource = []
        slow_waiters = [0]
        failures = [0]

        def create_resource():
            with self._assert_synchronized():
                log.debug("creating resource, will take %f sec" % creation_time)
                time.sleep(creation_time)

                the_resource.append(time.time())
                value = the_resource[-1]
                log.debug("finished creating resource")
                return value, time.time()

        def get_value():
            if not the_resource:
                raise NeedRegenerationException()
            if cache_expire_time:
                if time.time() - the_resource[-1] > cache_expire_time:
                    # should never hit a cache invalidation
                    # if we've set expiretime below the cache
                    # expire time (assuming a cache which
                    # honors this).
                    self._assert_log(
                        cache_expire_time < expiretime,
                        "Cache expiration hit, cache "
                        "expire time %s, expiretime %s",
                        cache_expire_time,
                        expiretime,
                    )

                    raise NeedRegenerationException()

            return the_resource[-1], the_resource[-1]

        def use_dogpile():
            try:
                for i in range(num_usages):
                    now = time.time()
                    with Lock(mutex, create_resource, get_value, expiretime) as value:
                        waited = time.time() - now
                        if waited > .01:
                            slow_waiters[0] += 1
                        check_value(value, waited)
                        time.sleep(usage_time)
                    time.sleep(delay_time)
            except:
                log.error("thread failed", exc_info=True)
                failures[0] += 1

        def check_value(value, waited):
            assert value

            # time since the current resource was
            # created
            time_since_create = time.time() - value

            self._assert_log(
                time_since_create < max_stale,
                "Time since create %.4f max stale time %s, "
                    "total waited %s",
                time_since_create, max_stale,
                slow_waiters[0]
            )

        started_at = time.time()
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=use_dogpile)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        actual_run_time = time.time() - started_at

        # time spent starts with num usages * time per usage, with a 10% fudge
        expected_run_time = (num_usages * (usage_time + delay_time)) * 1.1

        expected_generations = math.ceil(expected_run_time / effective_expiretime)

        if unsafe_cache:
            expected_slow_waiters = expected_generations * num_threads
        else:
            expected_slow_waiters = expected_generations + num_threads - 1


        # time spent also increments by one wait period in the beginning...
        expected_run_time += effective_creation_time

        # and a fudged version of the periodic waiting time anticipated
        # for a single thread...
        expected_run_time += (expected_slow_waiters * effective_creation_time) / num_threads
        expected_run_time *= 1.1

        log.info("Test Summary")
        log.info("num threads: %s; expiretime: %s; creation_time: %s; "
                "num_usages: %s; "
                "usage_time: %s; delay_time: %s",
            num_threads, expiretime, creation_time, num_usages,
            usage_time, delay_time
        )
        log.info("cache expire time: %s; unsafe cache: %s",
            cache_expire_time, unsafe_cache)
        log.info("Estimated run time %.2f actual run time %.2f",
                    expected_run_time, actual_run_time)
        log.info("Effective expiretime (min(cache_exp_time, exptime)) %s",
                    effective_expiretime)
        log.info("Expected slow waits %s, Total slow waits %s",
                    expected_slow_waiters, slow_waiters[0])
        log.info("Total generations %s Max generations expected %s" % (
            len(the_resource), expected_generations
        ))

        assert not failures[0], "%s failures occurred" % failures[0]
        assert actual_run_time <= expected_run_time

        assert slow_waiters[0] <= expected_slow_waiters, \
            "Number of slow waiters %s exceeds expected slow waiters %s" % (
                slow_waiters[0],
                expected_slow_waiters
            )
        assert len(the_resource) <= expected_generations,\
            "Number of resource generations %d exceeded "\
            "expected %d" % (len(the_resource),
                expected_generations)

