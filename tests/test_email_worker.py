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


class TestWorkerPriorities:
    def test_high_priority_runs_before_low(self):
        gate = threading.Event()
        worker = EmailWorker(dispatch=sync_dispatch)
        results: list[str] = []
        worker.submit(make_command(lambda: gate.wait(5) and "gate", results))
        worker.submit(make_command(lambda: "prefetch", results), low_priority=True)
        worker.submit(make_command(lambda: "user", results))
        gate.set()
        assert worker.wait_idle()
        assert results == ["gate", "user", "prefetch"]
        worker.stop()


class TestWorkerFetchDedup:
    def test_second_fetch_for_same_uid_attaches_to_first(self):
        gate = threading.Event()
        calls: list[int] = []
        worker = EmailWorker(dispatch=sync_dispatch)
        results_a: list = []
        results_b: list = []

        def blocking_first():
            gate.wait(5)
            return "x"

        worker.submit(make_command(blocking_first, results_a))  # blockiert den Worker

        def fetch_fn():
            calls.append(1)
            return "mail-7"

        worker.submit(
            Command(
                kind="fetch",
                uid=7,
                fn=fetch_fn,
                on_done=results_a.append,
                on_error=results_a.append,
            ),
            low_priority=True,
        )
        worker.submit(
            Command(
                kind="fetch",
                uid=7,
                fn=fetch_fn,
                on_done=results_b.append,
                on_error=results_b.append,
            ),
        )
        gate.set()
        assert worker.wait_idle()
        assert calls == [1]  # nur EIN echter Fetch
        assert "mail-7" in results_a
        assert results_b == ["mail-7"]  # Warter bekommt dasselbe Ergebnis
        worker.stop()

    def test_user_interest_promotes_prefetch_priority(self):
        gate = threading.Event()
        worker = EmailWorker(dispatch=sync_dispatch)
        order: list[str] = []
        worker.submit(make_command(lambda: gate.wait(5) and order.append("gate"), []))
        worker.submit(
            Command(
                kind="fetch",
                uid=7,
                fn=lambda: order.append("fetch7"),
                on_done=lambda r: None,
                on_error=lambda e: None,
            ),
            low_priority=True,
        )
        worker.submit(make_command(lambda: order.append("other-low"), []), low_priority=True)
        # User waehlt UID 7 -> Prefetch wird hochgestuft
        worker.submit(
            Command(
                kind="fetch",
                uid=7,
                fn=lambda: order.append("nie"),
                on_done=lambda r: None,
                on_error=lambda e: None,
            ),
        )
        gate.set()
        assert worker.wait_idle()
        assert order.index("fetch7") < order.index("other-low")
        assert "nie" not in order
        worker.stop()

    def test_fetch_error_reaches_all_waiters(self):
        gate = threading.Event()
        worker = EmailWorker(dispatch=sync_dispatch)
        errors_a: list = []
        errors_b: list = []

        def failing_fetch():
            raise ConnectionError("weg")

        worker.submit(make_command(lambda: gate.wait(5), []))
        worker.submit(
            Command(
                kind="fetch",
                uid=9,
                fn=failing_fetch,
                on_done=lambda r: None,
                on_error=errors_a.append,
            ),
            low_priority=True,
        )
        worker.submit(
            Command(
                kind="fetch",
                uid=9,
                fn=failing_fetch,
                on_done=lambda r: None,
                on_error=errors_b.append,
            ),
        )
        gate.set()
        assert worker.wait_idle()
        assert len(errors_a) == 1 and len(errors_b) == 1
        worker.stop()


class TestWorkerBusySignal:
    def test_busy_true_then_false_around_batch(self):
        transitions: list[bool] = []
        worker = EmailWorker(dispatch=sync_dispatch, on_busy_changed=transitions.append)
        worker.submit(make_command(lambda: 1, []))
        worker.submit(make_command(lambda: 2, []))
        assert worker.wait_idle()
        worker.stop()
        assert transitions[0] is True
        assert transitions[-1] is False
        # Innerhalb eines Batches kein Flackern:
        assert transitions.count(True) == transitions.count(False)
