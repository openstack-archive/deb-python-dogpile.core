from unittest import TestCase
import time
import threading
from dogpile.core import Dogpile, SyncReaderDogpile, NeedRegenerationException
from dogpile.core.nameregistry import NameRegistry
import contextlib
import math
import logging
log = logging.getLogger(__name__)

class ConcurrencyTest(TestCase):
    # expiretime, time to create, num usages, time spend using, delay btw usage
    timings = [
        # quick one
        (2, .5, 50, .05, .1),

        # slow creation time
        (5, 2, 50, .1, .1),

    ]

    _assertion_lock = threading.Lock()

    def test_rudimental(self):
        for exp, crt, nu, ut, dt in self.timings:
            self._test_multi(
                10, exp, crt, nu, ut, dt,
            )

    def test_rudimental_slow_write(self):
        self._test_multi(
            10, 2, .5, 50, .05, .1,
            slow_write_time=2
        )

    def test_return_while_in_progress(self):
        self._test_multi(
            10, 5, 2, 50, 1, .1,
            inline_create='get_value'
        )

    def test_rudimental_long_create(self):
        self._test_multi(
            10, 2, 2.5, 50, .05, .1,
        )

    def test_get_value_plus_created_slow_write(self):
        self._test_multi(
            10, 2, .5, 50, .05, .1,
            inline_create='get_value_plus_created',
            slow_write_time=2
        )

    def test_get_value_plus_created_long_create(self):
        self._test_multi(
            10, 2, 2.5, 50, .05, .1,
            inline_create='get_value_plus_created',
        )

    def test_get_value_plus_created_registry_unsafe_cache(self):
        self._test_multi(
            10, 1, .6, 100, .05, .1,
            inline_create='get_value_plus_created',
            cache_expire_time='unsafe'
        )

    def test_get_value_plus_created_registry_safe_cache(self):
        for exp, crt, nu, ut, dt in self.timings:
            self._test_multi(
                10, exp, crt, nu, ut, dt,
                inline_create='get_value_plus_created',
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
                            cache_expire_time=None,
                            slow_write_time=None,
                            inline_create='rudimental'):

        if slow_write_time:
            dogpile_cls = SyncReaderDogpile
        else:
            dogpile_cls = Dogpile

        # the registry feature should not be used
        # unless the value + created time func is used.
        use_registry = inline_create == 'get_value_plus_created'

        if use_registry:
            reg = NameRegistry(dogpile_cls)
            get_dogpile = lambda: reg.get(expiretime)
        else:
            dogpile = dogpile_cls(expiretime)
            get_dogpile = lambda: dogpile

        unsafe_cache = False
        if cache_expire_time:
            if cache_expire_time == 'unsafe':
                unsafe_cache = True
                cache_expire_time = expiretime *.8
            elif cache_expire_time == 'safe':
                cache_expire_time = (expiretime + creation_time) * 1.1
            else:
                assert False, cache_expire_time

            log.info("Cache expire time: %s", cache_expire_time)

            effective_expiretime = min(cache_expire_time, expiretime)
        else:
            effective_expiretime = expiretime

        effective_creation_time= creation_time
        if slow_write_time:
            effective_creation_time += slow_write_time

        max_stale = (effective_expiretime + effective_creation_time + 
                        usage_time + delay_time) * 1.1

        the_resource = []
        slow_waiters = [0]
        failures = [0]

        def create_impl(dogpile):
            log.debug("creating resource...")
            time.sleep(creation_time)

            if slow_write_time:
                with dogpile.acquire_write_lock():
                    saved = list(the_resource)
                    # clear out the resource dict so that
                    # usage threads hitting it will
                    # raise
                    the_resource[:] = []
                    time.sleep(slow_write_time)
                    the_resource[:] = saved
            the_resource.append(time.time())
            return the_resource[-1]

        if inline_create == 'get_value_plus_created':
            def create_resource(dogpile):
                with self._assert_synchronized():
                    value = create_impl(dogpile)
                    return value, time.time()
        else:
            def create_resource(dogpile):
                with self._assert_synchronized():
                    return create_impl(dogpile)

        if cache_expire_time:
            def get_value():
                if not the_resource:
                    raise NeedRegenerationException()
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

                if inline_create == 'get_value_plus_created':
                    return the_resource[-1], the_resource[-1]
                else:
                    return the_resource[-1]
        else:
            def get_value():
                if not the_resource:
                    raise NeedRegenerationException()
                if inline_create == 'get_value_plus_created':
                    return the_resource[-1], the_resource[-1]
                else:
                    return the_resource[-1]

        if inline_create == 'rudimental':
            assert not cache_expire_time

            @contextlib.contextmanager
            def enter_dogpile_block(dogpile):
                with dogpile.acquire(lambda: create_resource(dogpile)) as x:
                    yield the_resource[-1]
        elif inline_create == 'get_value':
            @contextlib.contextmanager
            def enter_dogpile_block(dogpile):
                with dogpile.acquire(
                        lambda: create_resource(dogpile), 
                        get_value
                    ) as rec:
                    yield rec
        elif inline_create == 'get_value_plus_created':
            @contextlib.contextmanager
            def enter_dogpile_block(dogpile):
                with dogpile.acquire(
                        lambda: create_resource(dogpile), 
                        value_and_created_fn=get_value
                    ) as rec:
                    yield rec
        else:
            assert False, inline_create


        def use_dogpile():
            try:
                for i in range(num_usages):
                    dogpile = get_dogpile()
                    now = time.time()
                    with enter_dogpile_block(dogpile) as value:
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

        if slow_write_time:
            expected_slow_waiters = num_threads * expected_generations

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
        log.info("cache expire time: %s; unsafe cache: %s slow "
                "write time: %s; inline: %s; registry: %s", 
            cache_expire_time, unsafe_cache, slow_write_time, 
            inline_create, use_registry)
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

class DogpileTest(TestCase):
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

    def test_no_expiration(self):
        dogpile = Dogpile(None)
        the_resource = [0]

        def create_resource():
            the_resource[0] += 1

        with dogpile.acquire(create_resource):
            assert the_resource[0] == 1

        with dogpile.acquire(create_resource):
            assert the_resource[0] == 1

