# Plan: RC5 - IMAP-Connection-Guard implementieren

## Problem

`self.imap` kann zwischen Thread-Start und Thread-Ausführung auf `None` gesetzt werden (z.B. wenn der Benutzer "Trennen" klickt während ein Fetch läuft). Dies führt zu `AttributeError: 'NoneType' has no attribute 'fetch_email'`.

**Betroffene Stellen in `src/belegscanner/email_view.py`:**
- Zeile 573: `self.imap.fetch_email(...)` im `fetch_thread`
- Zeile 850: `self.imap.move_email(...)` im `archive_thread`
- Zeile 981: `self.imap.move_email(...)` im `process_thread`

## Lösung

IMAP-Referenz am Thread-Start capturen und im Thread nur die gecapturte Referenz verwenden.

## Implementierungsplan (TDD)

### 1. Tests schreiben

Neue Testklasse `TestImapConnectionGuard` in `tests/test_race_conditions.py`:

- `test_captured_reference_survives_disconnect` - Gecapturte Referenz überlebt wenn `self.imap` None wird
- `test_guard_returns_none_when_disconnected_before_capture` - Guard gibt None zurück wenn vor Capture disconnected

### 2. Code ändern

**`fetch_thread` in `_on_email_selected()` (Zeilen 569-576):**
- IMAP-Referenz am Anfang capturen: `imap = self.imap`
- None-Check: `if imap is None: return None`
- Alle IMAP-Aufrufe über die gecapturte Referenz

**`archive_thread` in `_on_archive_clicked()` (Zeilen 846-864):**
- IMAP-Referenz capturen am Anfang
- None-Check mit Fehlermeldung
- `archived_uid` statt `email.uid` verwenden (RC6 Fix mit einschließen)

**`process_thread` in `_on_process_clicked()` (Zeilen 948-993):**
- IMAP-Referenz und `email.uid` am Anfang capturen
- None-Check vor move_email mit Fehlermeldung

### 3. Tests ausführen und Lint prüfen

```bash
cd /home/jensens/ws/kup/belegscanner/.worktrees/belegscanner-8 && uv run pytest tests/test_race_conditions.py -v
cd /home/jensens/ws/kup/belegscanner/.worktrees/belegscanner-8 && uv run ruff check .
```
