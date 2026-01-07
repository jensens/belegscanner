# Plan: Email-Prefetching und Caching

## Problem

Nach "Verarbeiten & Ablegen" dauert es 3-10 Sekunden bis die nächste Email angezeigt wird.

**Ursache**: Drei serielle IMAP-Operationen:
```
[move_email: ~1-2s] -> [list_emails: ~1-2s] -> [fetch_email: ~1-3s]
```

## Lösung: Prefetching + Caching kombinieren

### Optimierter Ablauf

```
User klickt "Verarbeiten"
        |
        v
+------------------+     +-------------------+
| Main Thread      |     | Prefetch Thread   |
+------------------+     +-------------------+
| [PDF erstellen]  |     |                   |
|        |         |     |                   |
| start_prefetch() |---->| fetch_email()     |
|        |         |     |     |             |
| [move_email]     |     |     v             |
|        |         |     | cache_email()     |
|        v         |     +-------------------+
| [list_emails]    |
|        v         |
| select_row()     |
|        v         |
| Cache HIT!       |  <-- Keine fetch_email mehr!
+------------------+
```

**Erwartete Zeitersparnis**: ~3-10s → ~1-3s

---

## Implementierung

### Phase 1: EmailCache Klasse (TDD)

**Neue Datei**: `src/belegscanner/services/email_cache.py`

```python
class EmailCache:
    """LRU-Cache für EmailMessage Objekte."""

    def __init__(self, max_size: int = 20): ...
    def get(self, folder: str, uid: int) -> EmailMessage | None: ...
    def put(self, folder: str, uid: int, email: EmailMessage) -> None: ...
    def remove(self, folder: str, uid: int) -> None: ...
    def clear(self) -> None: ...
    def contains(self, folder: str, uid: int) -> bool: ...
```

**Tests**: `tests/test_email_cache.py`
- test_get_returns_none_for_missing
- test_put_and_get
- test_remove_deletes_entry
- test_clear_empties_cache
- test_max_size_evicts_oldest

### Phase 2: ImapService Prefetch-Connection

**Änderung**: `src/belegscanner/services/imap.py`

```python
class ImapService:
    def __init__(self, ...):
        self._connection = None
        self._prefetch_connection = None  # NEU
        self._prefetch_lock = threading.Lock()  # NEU

    def connect_prefetch(self, username: str, password: str) -> bool: ...
    def fetch_email_prefetch(self, uid: int, folder: str) -> EmailMessage | None: ...
    def disconnect(self) -> None:  # Beide Connections schließen
```

**Tests erweitern**: `tests/test_imap.py`
- test_connect_prefetch_establishes_second_connection
- test_fetch_email_prefetch_uses_separate_connection
- test_disconnect_closes_both_connections

### Phase 3: EmailViewModel Cache-Integration

**Änderung**: `src/belegscanner/email_viewmodel.py`

```python
class EmailViewModel:
    def __init__(self):
        self._cache = EmailCache(max_size=20)  # NEU

    def get_cached_email(self, uid: int) -> EmailMessage | None: ...
    def cache_email(self, email: EmailMessage) -> None: ...
    def invalidate_cached_email(self, uid: int) -> None: ...
    def get_next_email_uid(self, current_index: int) -> int | None: ...
```

**Tests erweitern**: `tests/test_email_viewmodel.py`

### Phase 4: EmailView Prefetch-Orchestrierung

**Änderung**: `src/belegscanner/email_view.py`

1. `_connect()`: Auch Prefetch-Connection aufbauen
2. `_on_email_selected()`: Erst Cache prüfen, dann fetchen
3. `_on_email_fetched()`: Email in Cache speichern
4. `_on_process_clicked()`: Prefetch starten vor move_email
5. `_on_process_success()` / `_on_archive_success()`: Cache invalidieren

---

## Kritische Dateien

| Datei | Änderung |
|-------|----------|
| `src/belegscanner/services/email_cache.py` | NEU |
| `src/belegscanner/services/imap.py` | Prefetch-Connection |
| `src/belegscanner/email_viewmodel.py` | Cache-Integration |
| `src/belegscanner/email_view.py` | Orchestrierung |
| `tests/test_email_cache.py` | NEU |
| `tests/test_imap.py` | Erweitern |
| `tests/test_email_viewmodel.py` | Erweitern |

---

## Risiken

| Risiko | Mitigation |
|--------|------------|
| IMAP-Server erlaubt keine 2 Connections | Fallback ohne Prefetch, nur Caching |
| Race Condition bei Cache | threading.Lock |
| Memory bei vielen Emails | max_size=20, LRU-Eviction |
