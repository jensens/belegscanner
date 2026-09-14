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
        # WICHTIG: "other-low" wird VOR dem uid-7-Prefetch eingereiht. Ohne echte
        # Promotion liefe die Low-Queue FIFO als [other-low, fetch7] und wuerde die
        # Assertion unten verletzen -- der Test erzwingt damit tatsaechlich die
        # Hochstufung, statt nur zufaellig durch Einreihungsreihenfolge zu bestehen.
        gate = threading.Event()
        worker = EmailWorker(dispatch=sync_dispatch)
        order: list[str] = []
        worker.submit(make_command(lambda: gate.wait(5) and order.append("gate"), []))
        worker.submit(make_command(lambda: order.append("other-low"), []), low_priority=True)
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
        # User waehlt UID 7 -> Prefetch wird hochgestuft (vor "other-low", obwohl
        # dieses zuerst gequeued wurde)
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

    def test_dedup_attaches_to_active_fetch_while_it_is_still_running(self):
        """Deckt den `_active`-Zweig von `_find_pending_fetch` ab (nicht nur den
        Queue-Zweig, den test_second_fetch_for_same_uid_attaches_to_first prueft):
        das Duplikat trifft ein, WAEHREND der erste Fetch noch blockierend laeuft."""
        started = threading.Event()
        gate = threading.Event()
        calls: list[int] = []
        worker = EmailWorker(dispatch=sync_dispatch)
        results_a: list = []
        results_b: list = []

        def blocking_fetch():
            calls.append(1)
            started.set()
            gate.wait(5)
            return "mail-11"

        worker.submit(
            Command(
                kind="fetch",
                uid=11,
                fn=blocking_fetch,
                on_done=results_a.append,
                on_error=results_a.append,
            )
        )
        assert started.wait(5)  # Fetch ist jetzt _active und blockiert in gate.wait
        worker.submit(
            Command(
                kind="fetch",
                uid=11,
                fn=blocking_fetch,
                on_done=results_b.append,
                on_error=results_b.append,
            )
        )
        gate.set()
        assert worker.wait_idle()
        assert calls == [1]  # nur EIN echter Fetch, obwohl das Duplikat waehrend
        # des laufenden aktiven Fetches kam
        assert results_a == ["mail-11"]
        assert results_b == ["mail-11"]
        worker.stop()

    def test_duplicate_submitted_during_delivery_window_is_not_orphaned(self):
        """Regression (Critical 1): Ein Duplikat-Fetch, der waehrend der Zustellung
        des ersten Fetches eintrifft -- nachdem dessen Waiter bereits ausgeliefert
        wurden, aber bevor `_active` zurueckgesetzt ist -- darf nicht verloren gehen.
        Der synchrone Dispatcher macht dieses Zeitfenster deterministisch testbar:
        `on_done_first` laeuft synchron INNERHALB von `_deliver`."""
        worker = EmailWorker(dispatch=sync_dispatch)
        calls: list[int] = []
        waiter_results: list = []

        def fetch_fn():
            calls.append(1)
            return "mail-3"

        def on_done_first(_result):
            worker.submit(
                Command(
                    kind="fetch",
                    uid=3,
                    fn=fetch_fn,
                    on_done=waiter_results.append,
                    on_error=waiter_results.append,
                )
            )

        worker.submit(
            Command(
                kind="fetch", uid=3, fn=fetch_fn, on_done=on_done_first, on_error=lambda e: None
            )
        )
        assert worker.wait_idle()
        assert waiter_results == ["mail-3"]
        worker.stop()

    def test_deliver_does_not_leak_waiters_to_unrelated_command_with_same_uid(self):
        """Regression (Important 2): `_deliver` darf Waiter nur fuer fetch-Kommandos
        ausliefern (Symmetrie zu `_find_pending_fetch`); sonst bekaeme ein zufaellig
        gleich-uid'ter Nicht-Fetch (z. B. ein move/delete) die Waiter eines noch
        laufenden Fetches untergejubelt."""
        gate = threading.Event()
        worker = EmailWorker(dispatch=sync_dispatch)

        worker.submit(make_command(lambda: gate.wait(5), []))  # blockiert den Worker

        fetch_results: list = []
        worker.submit(
            Command(
                kind="fetch",
                uid=5,
                fn=lambda: "mail-5",
                on_done=fetch_results.append,
                on_error=fetch_results.append,
            ),
            low_priority=True,
        )
        waiter_results: list = []
        worker.submit(
            Command(
                kind="fetch",
                uid=5,
                fn=lambda: "mail-5",
                on_done=waiter_results.append,
                on_error=waiter_results.append,
            ),
            low_priority=True,  # kein Promote, der Fetch selbst bleibt in _low
        )
        op_results: list = []
        worker.submit(
            Command(
                kind="op",
                uid=5,
                fn=lambda: "op-result",
                on_done=op_results.append,
                on_error=op_results.append,
            )
        )  # hohe Prioritaet, uid=5 nur zufaellig identisch -> laeuft VOR dem Fetch

        gate.set()
        assert worker.wait_idle()
        assert op_results == ["op-result"]
        assert fetch_results == ["mail-5"]
        assert waiter_results == ["mail-5"]  # Waiter bekommt Fetch-Ergebnis, nie das des op
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
        # Das erste Kommando blockiert per Gate, bis BEIDE Kommandos gequeued sind --
        # das garantiert einen zusammenhaengenden Batch statt einer zufaelligen
        # Verschachtelung. `done` wird erst gesetzt, wenn busy(False) tatsaechlich
        # dispatcht wurde, sodass wir nicht vorzeitig pruefen. Die exakte Sequenz
        # [True, False] laesst -- anders als ein reines count(True)==count(False) --
        # kein Flackern innerhalb des Batches durch.
        gate = threading.Event()
        done = threading.Event()
        transitions: list[bool] = []

        def on_busy_changed(value):
            transitions.append(value)
            if value is False:
                done.set()

        worker = EmailWorker(dispatch=sync_dispatch, on_busy_changed=on_busy_changed)
        worker.submit(make_command(lambda: gate.wait(5), []))
        worker.submit(make_command(lambda: 2, []))
        gate.set()
        assert done.wait(5)
        assert worker.wait_idle()
        worker.stop()
        assert transitions == [True, False]


class TestWorkerDispatchSafety:
    def test_exception_in_on_done_does_not_kill_worker(self):
        """Regression (Important 3): Eine Exception im Callback (z. B. im View)
        darf den Worker-Thread nicht toeten -- sonst haengt jedes danach
        eingereihte Kommando fuer immer in der Queue."""
        worker = EmailWorker(dispatch=sync_dispatch)
        results: list = []

        def bad_on_done(_result):
            raise RuntimeError("callback kaputt")

        worker.submit(
            Command(kind="op", fn=lambda: 1, on_done=bad_on_done, on_error=lambda e: None)
        )
        worker.submit(make_command(lambda: 42, results))
        assert worker.wait_idle()
        assert results == [42]
        worker.stop()

    def test_exception_in_busy_callback_does_not_kill_worker(self):
        """Wie oben, aber fuer den on_busy_changed-Dispatch in `_run`."""

        def bad_on_busy_changed(_value):
            raise RuntimeError("busy-callback kaputt")

        worker = EmailWorker(dispatch=sync_dispatch, on_busy_changed=bad_on_busy_changed)
        results: list = []
        worker.submit(make_command(lambda: 42, results))
        assert worker.wait_idle()
        assert results == [42]
        worker.stop()
