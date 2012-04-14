try:
    import threading
    import thread
except ImportError:
    import dummy_threading as threading
    import dummy_thread as thread

