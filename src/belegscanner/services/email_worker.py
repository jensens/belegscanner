"""Serieller Worker-Thread fuer alle IMAP-Operationen.

Alle Kommandos laufen nacheinander auf einem dedizierten Thread; Ergebnisse
und Fehler werden ueber einen injizierbaren Dispatcher (GLib.idle_add in der
App, direkter Aufruf in Tests) an den Main-Thread uebergeben. User-Kommandos
haben Vorrang vor Prefetch-Kommandos; Fetches auf dieselbe UID werden
dedupliziert.
"""

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from belegscanner.log import get_logger

logger = get_logger(__name__)


@dataclass
class Command:
    """Ein Kommando fuer den EmailWorker.

    fn laeuft im Worker-Thread; on_done bzw. on_error werden mit dem
    Ergebnis bzw. der Exception ueber den Dispatcher aufgerufen.
    uid dient der Fetch-Deduplizierung, generation dem Verwerfen
    veralteter Ergebnisse im View.
    """

    kind: str
    fn: Callable[[], Any]
    on_done: Callable[[Any], None]
    on_error: Callable[[Exception], None]
    uid: int | None = None
    generation: int = 0


class EmailWorker:
    """Arbeitet Kommandos seriell ab; User-Kommandos vor Prefetch."""

    def __init__(
        self,
        dispatch: Callable[..., Any],
        on_busy_changed: Callable[[bool], None] | None = None,
    ):
        self._dispatch = dispatch
        self._on_busy_changed = on_busy_changed
        self._high: deque[Command] = deque()
        self._low: deque[Command] = deque()
        self._waiters: dict[int, list[Command]] = {}
        self._active: Command | None = None
        # Wird in _deliver() gesetzt, sobald dessen Waiter bereits ausgeliefert
        # wurden, aber bevor _run() _active auf None zuruecksetzt. Verhindert,
        # dass ein Duplikat-Fetch in genau diesem Fenster als Waiter an ein
        # bereits abgeschlossenes _active-Kommando gehaengt wird und dort nie
        # wieder abgeholt wird (siehe _find_pending_fetch).
        self._active_closed = False
        self._cv = threading.Condition()
        self._stopped = False
        self._thread = threading.Thread(target=self._run, name="email-worker", daemon=True)
        self._thread.start()

    def submit(self, command: Command, low_priority: bool = False) -> None:
        """Kommando einreihen; Fetch auf bereits laufende/queued UID dedupliziert."""
        with self._cv:
            if self._stopped:
                return
            if command.kind == "fetch" and command.uid is not None:
                pending = self._find_pending_fetch(command.uid)
                if pending is not None:
                    self._waiters.setdefault(command.uid, []).append(command)
                    if not low_priority and pending in self._low:
                        self._low.remove(pending)
                        self._high.append(pending)
                    return
            (self._low if low_priority else self._high).append(command)
            self._cv.notify_all()

    def stop(self) -> None:
        """Worker beenden; wartende Kommandos verfallen ohne Callback."""
        with self._cv:
            self._stopped = True
            self._high.clear()
            self._low.clear()
            self._waiters.clear()
            self._cv.notify_all()

    def wait_idle(self, timeout: float = 5.0) -> bool:
        """Nur fuer Tests: warten, bis Queue leer und kein Kommando aktiv ist."""
        with self._cv:
            return self._cv.wait_for(
                lambda: self._active is None and not self._high and not self._low,
                timeout,
            )

    def _find_pending_fetch(self, uid: int) -> Command | None:
        if (
            self._active is not None
            and not self._active_closed
            and self._active.kind == "fetch"
            and self._active.uid == uid
        ):
            return self._active
        for cmd in [*self._high, *self._low]:
            if cmd.kind == "fetch" and cmd.uid == uid:
                return cmd
        return None

    def _run(self) -> None:
        busy = False
        while True:
            with self._cv:
                self._cv.wait_for(lambda: self._stopped or self._high or self._low)
                if self._stopped:
                    break
                command = self._high.popleft() if self._high else self._low.popleft()
                self._active = command
                self._active_closed = False
            if not busy and self._on_busy_changed:
                busy = True
                self._safe_dispatch(self._on_busy_changed, True)
            try:
                result = command.fn()
            except Exception as e:
                logger.debug("Kommando %s fehlgeschlagen: %s", command.kind, e)
                self._deliver(command, error=e)
            else:
                self._deliver(command, result=result)
            with self._cv:
                self._active = None
                idle = not self._high and not self._low
                self._cv.notify_all()
            if idle and busy and self._on_busy_changed:
                busy = False
                self._safe_dispatch(self._on_busy_changed, False)
        if busy and self._on_busy_changed:
            self._safe_dispatch(self._on_busy_changed, False)

    def _deliver(
        self, command: Command, result: Any = None, error: Exception | None = None
    ) -> None:
        with self._cv:
            if command.kind == "fetch" and command.uid is not None:
                extra = self._waiters.pop(command.uid, [])
            else:
                extra = []
            # Ab hier gilt das aktive Kommando als "geschlossen": seine Waiter
            # wurden bereits ausgeliefert (bzw. es hatte keine), also darf sich ab
            # jetzt kein neues Duplikat mehr an _active anhaengen (Critical-1-Fix).
            self._active_closed = True
        for cmd in (command, *extra):
            if error is not None:
                self._safe_dispatch(cmd.on_error, error)
            else:
                self._safe_dispatch(cmd.on_done, result)

    def _safe_dispatch(self, fn: Callable[..., Any], *args: Any) -> None:
        """Dispatch aufrufen; eine Exception im Callback darf den Worker nicht toeten."""
        try:
            self._dispatch(fn, *args)
        except Exception:
            logger.exception("Dispatch-Callback fehlgeschlagen")
