"""Tests for the serial email worker."""

import threading

from belegscanner.services.email_worker import Command, EmailWorker


def sync_dispatch(fn, *args):
    fn(*args)


def make_command(fn, results, errors=None, **kwargs):
    errors = errors if errors is not None else []
    return Command(
        kind=kwargs.pop("kind", "op"),
        fn=fn,
        on_done=results.append,
        on_error=errors.append,
        **kwargs,
    )


class TestWorkerSerialExecution:
    def test_executes_commands_in_submit_order(self):
        worker = EmailWorker(dispatch=sync_dispatch)
        results: list[int] = []
        for i in range(5):
            worker.submit(make_command(lambda i=i: i, results))
        assert worker.wait_idle()
        assert results == [0, 1, 2, 3, 4]
        worker.stop()

    def test_commands_never_overlap(self):
        worker = EmailWorker(dispatch=sync_dispatch)
        lock = threading.Lock()
        results: list[bool] = []

        def exclusive():
            acquired = lock.acquire(blocking=False)
            try:
                return acquired
            finally:
                if acquired:
                    lock.release()

        for _ in range(10):
            worker.submit(make_command(exclusive, results))
        assert worker.wait_idle()
        assert results == [True] * 10
        worker.stop()

    def test_error_reaches_on_error_callback(self):
        worker = EmailWorker(dispatch=sync_dispatch)
        results: list = []
        errors: list = []

        def boom():
            raise RuntimeError("kaputt")

        worker.submit(make_command(boom, results, errors))
        assert worker.wait_idle()
        assert results == []
        assert len(errors) == 1
        assert isinstance(errors[0], RuntimeError)
        worker.stop()

    def test_error_does_not_kill_worker(self):
        worker = EmailWorker(dispatch=sync_dispatch)
        results: list = []
        errors: list = []
        worker.submit(make_command(lambda: 1 / 0, results, errors))
        worker.submit(make_command(lambda: 42, results, errors))
        assert worker.wait_idle()
        assert results == [42]
        assert len(errors) == 1
        worker.stop()

    def test_stop_discards_pending_commands(self):
        gate = threading.Event()
        worker = EmailWorker(dispatch=sync_dispatch)
        results: list = []
        worker.submit(make_command(lambda: gate.wait(5), results))
        worker.submit(make_command(lambda: "nie", results))
        worker.stop()
        gate.set()
        assert worker.wait_idle()
        assert "nie" not in results
