# E-Mail-Worker, IMAP-Modernisierung und Review-Härtung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die im Review gefundenen Bugs, Test- und Infrastrukturprobleme beseitigen und die RC-Bug-Klasse strukturell unmöglich machen: serieller IMAP-Worker mit Prioritäts-Queue + Selektions-Generation, IMAP-Layer auf `imapclient`, funktionierendes Logging, Security-Härtung.

**Architecture:** Ein Worker-Thread (`services/email_worker.py`) arbeitet alle IMAP-Kommandos seriell ab; Ergebnisse laufen über einen injizierbaren Dispatcher zurück. Das ViewModel führt eine Selektions-Generation, veraltete Ergebnisse werden verworfen. `ImapService` behält seine API, nutzt intern `imapclient` statt Regex über Roh-Antworten.

**Tech Stack:** Python 3.12+, GTK4/libadwaita/WebKitGTK 6.0, imapclient, weasyprint, pytest, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-09-14-email-worker-imap-redesign-design.md`

## Global Constraints

- Python `>=3.12`; Paketverwaltung ausschließlich `uv`.
- Tests laufen mit `uv sync --all-extras && uv run pytest` (im Worktree zwingend so).
- IMMER TDD: erst Test schreiben/ändern, fehlschlagen sehen, dann Implementierung.
- Vor jedem Commit: `uv run ruff check .` und `uv run ruff format .` müssen sauber sein.
- Commit-Messages: Deutsch, ASCII (keine Umlaute: "fuer", "ergaenzen"), Prefixe `feat:`/`fix:`/`refactor:`/`test:`/`docs:`/`chore:`/`security:`/`ci:`.
- Einzige neue Runtime-Dependency: `imapclient>=3.0`. Keine weiteren Pakete.
- UI-Strings bleiben Deutsch.
- Zeilenlänge 100 (ruff); ruff-Select `E,F,I,N,W,B,S,T,UP,RUF` bleibt unangetastet.

---

## Phase 0 — Merge und Branch

### Task 1: feature/modernisierung mergen, Arbeitsbranch anlegen

**WICHTIG:** Dieser Task läuft im Haupt-Checkout (`/home/jensens/ws/kup/belegscanner`), NICHT in einem Worktree. Erst danach wird für die restlichen Tasks per `superpowers:using-git-worktrees` ein Worktree vom neuen Branch erstellt.

**Files:** keine Quellcode-Änderung.

- [ ] **Step 1: Sicherstellen, dass der Stand sauber ist**

```bash
git -C /home/jensens/ws/kup/belegscanner status --short
```

Erwartet: keine Änderungen an `src/`, `tests/`, `docs/` oder `pyproject.toml` (Spec und Pläne sind bereits committet). Lokale Editor-/Agent-Konfigurationsdateien (`.claude/`, `.mcp.json`) dürfen geändert sein — nicht anfassen, nicht committen. Bei anderen offenen Änderungen: abbrechen und nachfragen.

- [ ] **Step 2: Mergen und Branch anlegen**

```bash
git checkout main
git merge --no-ff feature/modernisierung -m "Merge feature/modernisierung: Ruff, Logging, Security-Fixes, Tests"
git checkout -b feature/email-worker-imap
```

- [ ] **Step 3: Testsuite auf dem neuen Branch verifizieren**

```bash
uv sync --all-extras && uv run pytest -q
```

Erwartet: 369 passed, 3 skipped (Stand vor diesem Plan).

---

## Phase 1 — Fundament

### Task 2: Logging-Umbau: `setup_logging` + schlankes `get_logger`

**Files:**
- Modify: `src/belegscanner/log.py`
- Test: `tests/test_log.py`

**Interfaces:**
- Produces: `setup_logging(level: int = logging.WARNING) -> None` (idempotent, konfiguriert Paket-Logger `belegscanner`); `get_logger(name: str) -> logging.Logger` (reines `logging.getLogger`). Alle späteren Tasks benutzen genau diese zwei Funktionen.

- [ ] **Step 1: Tests ersetzen**

`tests/test_log.py` komplett ersetzen durch:

```python
"""Tests for logging setup."""

import logging

from belegscanner.log import get_logger, setup_logging


class TestSetupLogging:
    def test_configures_package_logger_once(self):
        setup_logging()
        setup_logging()
        pkg = logging.getLogger("belegscanner")
        assert len(pkg.handlers) == 1
        assert pkg.propagate is False

    def test_default_level_is_warning(self):
        setup_logging()
        assert logging.getLogger("belegscanner").level == logging.WARNING

    def test_level_applies_to_child_loggers(self):
        setup_logging(logging.DEBUG)
        child = get_logger("belegscanner.services.imap")
        assert child.getEffectiveLevel() == logging.DEBUG
        assert child.handlers == []
        setup_logging()  # zuruecksetzen fuer andere Tests


class TestGetLogger:
    def test_returns_plain_logger_without_handlers(self):
        logger = get_logger("belegscanner.services.ocr")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "belegscanner.services.ocr"
        assert logger.handlers == []
```

- [ ] **Step 2: Fehlschlag verifizieren**

Run: `uv run pytest tests/test_log.py -v` — Erwartet: FAIL (`setup_logging` existiert nicht).

- [ ] **Step 3: Implementieren**

`src/belegscanner/log.py` komplett ersetzen:

```python
"""Logging setup for belegscanner."""

import logging
import sys

_PACKAGE = "belegscanner"


def setup_logging(level: int = logging.WARNING) -> None:
    """Configure the package logger (idempotent; call once per entry point).

    Args:
        level: Log level for the whole belegscanner package.
    """
    pkg_logger = logging.getLogger(_PACKAGE)
    if not pkg_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(name)s [%(levelname)s] %(message)s"))
        pkg_logger.addHandler(handler)
        pkg_logger.propagate = False
    pkg_logger.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return the logger for a module; configuration happens via setup_logging()."""
    return logging.getLogger(name)
```

- [ ] **Step 4: Tests grün, Gesamtsuite grün** — `uv run pytest -q`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "refactor: Logging zentral ueber setup_logging konfigurieren"`

### Task 3: Entry-Points verkabeln (`-v`/`-vv`, `BELEGSCANNER_DEBUG`), noqa-Flut in cli.py beseitigen

**Files:**
- Modify: `src/belegscanner/cli.py`, `src/belegscanner/app.py`, `pyproject.toml`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `setup_logging` aus Task 2.

- [ ] **Step 1: Test schreiben** — in `tests/test_cli.py`, neue Klasse am Ende:

```python
class TestCliVerbosity:
    @pytest.mark.parametrize(
        "extra_args, expected_level",
        [([], logging.WARNING), (["-v"], logging.INFO), (["-vv"], logging.DEBUG)],
        ids=["default", "verbose", "debug"],
    )
    def test_verbose_flags_configure_logging(self, extra_args, expected_level):
        with (
            patch("sys.argv", ["scan-beleg", "-k", "1", *extra_args]),
            patch("belegscanner.cli.setup_logging") as mock_setup,
            patch("belegscanner.cli.ConfigManager") as mock_config,
        ):
            mock_config.return_value.archive_path = None
            main()
            mock_setup.assert_called_once_with(expected_level)
```

Oben in der Datei `import logging` ergänzen.

- [ ] **Step 2: Fehlschlag verifizieren** — `uv run pytest tests/test_cli.py -v` → FAIL (kein `setup_logging` in cli).
- [ ] **Step 3: Implementieren**

In `src/belegscanner/cli.py`: oben `import logging` und `from belegscanner.log import setup_logging` ergänzen. Argument hinzufügen (nach `--gui`):

```python
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Ausfuehrliche Ausgabe (-v: Info, -vv: Debug)",
    )
```

Direkt nach `args = parser.parse_args()`:

```python
    level = {0: logging.WARNING, 1: logging.INFO}.get(args.verbose, logging.DEBUG)
    setup_logging(level)
```

In `src/belegscanner/app.py`, in `main()` vor `app = BelegscannerApp()`:

```python
    level = logging.DEBUG if os.environ.get("BELEGSCANNER_DEBUG") else logging.WARNING
    setup_logging(level)
```

mit `import logging`, `import os`, `from belegscanner.log import setup_logging` oben.

- [ ] **Step 4: noqa-Kommentare entfernen, per-file-ignore setzen**

```bash
sed -i 's/  # noqa: T201//' src/belegscanner/cli.py
```

In `pyproject.toml` unter `[tool.ruff.lint.per-file-ignores]` ergänzen:

```toml
"src/belegscanner/cli.py" = ["T201"]  # print ist die CLI-UI
```

- [ ] **Step 5: Verifizieren + Commit** — `uv run pytest -q && uv run ruff check .`, dann `git add -A && git commit -m "feat: Verbositaet per -v/-vv und BELEGSCANNER_DEBUG steuerbar"`

### Task 4: Debug-Prints in email_view.py entfernen, T201-Ausnahme löschen

**Files:**
- Modify: `src/belegscanner/email_view.py`, `pyproject.toml`

Regeln (kein Test nötig — Verhalten unverändert, Lint erzwingt Vollständigkeit):

- [ ] **Step 1: Logger einführen** — oben nach den Service-Imports:

```python
from belegscanner.log import get_logger

logger = get_logger(__name__)
```

- [ ] **Step 2: Prints umstellen**

Alle 27 `print(...)`-Aufrufe und die zugehörigen funktionslokalen `import time`-Zeilen entfernen, nach dieser Regel:

- Reine `[TIMING] ...: {time.time()}`-Zeilen: **ersatzlos löschen** (Zeitstempel liefert bei Bedarf der Logging-Formatter).
- Informationstragende Zeilen ersetzen:
  - `print(f"[DEBUG] Verfügbare IMAP-Ordner: {folders}")` → `logger.debug("Verfuegbare IMAP-Ordner: %s", folders)`
  - `print(f"[DEBUG] Konfigurierter Inbox-Ordner: {self.config.imap_inbox}")` → `logger.debug("Konfigurierter Inbox-Ordner: %s", self.config.imap_inbox)`
  - `print("[DEBUG] Prefetch-Connection konnte nicht hergestellt werden")` → `logger.warning("Prefetch-Verbindung konnte nicht hergestellt werden")`
  - `print(f"[TIMING] Cache HIT for UID {uid}: ...")` → `logger.debug("Cache-Treffer fuer UID %d", uid)`
  - `print(f"[TIMING] Stale request {request_id} rejected")` → `logger.debug("Veraltetes Fetch-Ergebnis verworfen (Request %d)", request_id)`
  - `print(f"[TIMING] _start_prefetch for UID {uid}: ...")` → `logger.debug("Prefetch gestartet fuer UID %d", uid)`
  - `print(f"[TIMING] _on_prefetch_complete for UID {email.uid}: ...")` → `logger.debug("Prefetch abgeschlossen fuer UID %d", email.uid)`

- [ ] **Step 3: Ausnahme entfernen** — in `pyproject.toml` die Zeile `"src/belegscanner/email_view.py" = ["T201"]  ...` löschen.
- [ ] **Step 4: Verifizieren** — `grep -c "print(" src/belegscanner/email_view.py` → `0`; `uv run ruff check . && uv run pytest -q` grün.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "refactor: Debug-Prints in email_view durch Logging ersetzen"`

### Task 5: Log-Höhen-Konvention in credential.py und ollama.py

**Files:**
- Modify: `src/belegscanner/services/credential.py`, `src/belegscanner/services/ollama.py`
- Test: `tests/test_credential.py`, `tests/test_ollama.py`

Konvention (Spec §3.6): erwartbare Umgebungsausfälle → `debug`; fehlgeschlagene User-Aktionen → `warning`; `logger.exception` nur für Unerwartetes.

- [ ] **Step 1: Test schreiben** — in `tests/test_credential.py` ergänzen:

```python
import logging
from unittest.mock import MagicMock, patch

from belegscanner.services.credential import CredentialService


class TestKeyringFailureLogging:
    def test_get_password_failure_logs_debug_not_error(self, caplog):
        """Fehlender Keyring ist erwartbar: debug, kein ERROR/Traceback."""
        service = CredentialService()
        fake_secret = MagicMock()
        fake_secret.password_lookup_sync.side_effect = RuntimeError("kein Daemon")
        # setup_logging setzt propagate=False; fuer caplog (Handler am Root) aufheben
        logging.getLogger("belegscanner").propagate = True
        with patch.object(CredentialService, "_get_secret_module", return_value=fake_secret):
            with caplog.at_level(logging.DEBUG, logger="belegscanner"):
                assert service.get_password("user@example.com") is None
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("Keyring" in r.message for r in caplog.records)
```

(Vorhandene Imports der Datei beachten, nicht doppeln.)

- [ ] **Step 2: Fehlschlag verifizieren** — FAIL: aktuell loggt `logger.exception` einen ERROR-Record.
- [ ] **Step 3: Implementieren**

In `credential.py` alle drei Blöcke

```python
        except Exception:
            logger.exception("Keyring-Operation fehlgeschlagen fuer %s", username)
```

ersetzen durch

```python
        except Exception as e:
            logger.debug("Keyring nicht verfuegbar fuer %s: %s", username, e)
```

(Rückgabewerte `False`/`None` bleiben wie sie sind.)

In `ollama.py` oben `from belegscanner.log import get_logger` + `logger = get_logger(__name__)` ergänzen; in `is_available` und `extract` die stummen `except`-Blöcke um eine Zeile ergänzen:

```python
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            logger.debug("Ollama nicht erreichbar: %s", e)
            return False
```

bzw. in `extract`:

```python
        except (TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.debug("Ollama-Extraktion fehlgeschlagen: %s", e)
            return ExtractionResult(vendor=None, amount=None, currency=None, date=None)
```

- [ ] **Step 4: Tests grün** — `uv run pytest tests/test_credential.py tests/test_ollama.py -q`
- [ ] **Step 5: Commit** — `git commit -am "fix: Log-Hoehen fuer erwartbare Ausfaelle vereinheitlichen"`

### Task 6: `sanitize_filename` + `strip_html` mit `html.unescape` in text.py

**Files:**
- Modify: `src/belegscanner/services/text.py`, `src/belegscanner/email_view.py`
- Test: `tests/test_text.py`
- Delete: `tests/test_email_view_attachment_safety.py`

**Interfaces:**
- Produces: `sanitize_filename(filename: str | None) -> str` — wird ab Task 13 auch von `imap.py` beim Parsen benutzt.

- [ ] **Step 1: Tests schreiben** — in `tests/test_text.py` ergänzen (Import oben erweitern auf `from belegscanner.services.text import sanitize_filename, strip_html`):

```python
class TestSanitizeFilename:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("invoice.pdf", "invoice.pdf"),
            ("../../etc/passwd", "passwd"),
            ("/etc/passwd", "passwd"),
            ("C:\\Users\\file.pdf", "file.pdf"),
            ("", "attachment"),
            (None, "attachment"),
            ("..", "attachment"),
            ("....", "attachment"),
            ("inv\x00oice.pdf", "invoice.pdf"),
            ("re\x1bport\t.pdf", "report.pdf"),
        ],
        ids=["plain", "traversal", "absolute", "windows", "empty", "none",
             "dotdot", "dots", "nul", "control"],
    )
    def test_sanitize(self, raw, expected):
        assert sanitize_filename(raw) == expected


class TestStripHtmlEntities:
    def test_decodes_euro_and_nbsp(self):
        assert strip_html("Gesamt: 47,99&nbsp;&euro;") == "Gesamt: 47,99 €"

    def test_decodes_umlaut_entities(self):
        assert strip_html("B&uuml;ro") == "Büro"

    def test_no_double_unescape(self):
        # "&amp;lt;" ist die Escapung des literalen Texts "&lt;"
        assert strip_html("&amp;lt;b&amp;gt;") == "&lt;b&gt;"
```

Dazu oben `import pytest` falls noch nicht vorhanden.

- [ ] **Step 2: Fehlschlag verifizieren** — `uv run pytest tests/test_text.py -v` → FAILs.
- [ ] **Step 3: Implementieren** — `src/belegscanner/services/text.py` komplett ersetzen:

```python
"""Text utility functions."""

import re
from html import unescape
from pathlib import Path

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def strip_html(html: str | None) -> str:
    """Strip HTML tags and return plain text.

    Simple regex-based HTML stripping for extraction purposes.

    Args:
        html: HTML string or None.

    Returns:
        Plain text with HTML tags removed and entities decoded.
    """
    if not html:
        return ""
    text = _SCRIPT_STYLE_RE.sub("", html)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def sanitize_filename(filename: str | None) -> str:
    """Reduce an untrusted (e.g. MIME) filename to a safe basename.

    Strips directory components (also Windows-style), control characters
    and NUL bytes; dot-only or empty names become "attachment".

    Args:
        filename: Untrusted filename or None.

    Returns:
        Safe basename, never empty.
    """
    if not filename:
        return "attachment"
    name = _CONTROL_RE.sub("", filename.replace("\\", "/"))
    name = Path(name).name
    if not name or set(name) == {"."}:
        return "attachment"
    return name
```

Hinweis: `unescape` läuft NACH der Tag-Entfernung — escaptes Markup (`&lt;b&gt;`) bleibt dadurch als sichtbarer Text erhalten.

- [ ] **Step 4: email_view.py umstellen** — in `_on_open_attachment_clicked` den Block

```python
        _raw = att.filename.replace("\\", "/")
        _name = Path(_raw).name
        safe_filename = _name if (_name and set(_name) != {"."}) else "attachment"
```

ersetzen durch

```python
        safe_filename = sanitize_filename(att.filename)
```

und den Import `from belegscanner.services.text import strip_html` erweitern zu `from belegscanner.services.text import sanitize_filename, strip_html`.

- [ ] **Step 5: Kopie-Testdatei löschen** — `git rm tests/test_email_view_attachment_safety.py` (die Fälle leben jetzt gegen den echten Code in `tests/test_text.py`).
- [ ] **Step 6: Verifizieren + Commit** — `uv run pytest -q && uv run ruff check .`; `git add -A && git commit -m "refactor: sanitize_filename als echte Utility, strip_html mit html.unescape"`

### Task 7: Währungs-Konstanten konsolidieren

**Files:**
- Modify: `src/belegscanner/constants.py`, `src/belegscanner/services/ocr.py`, `src/belegscanner/services/ollama.py`, `src/belegscanner/window.py`, `src/belegscanner/email_view.py`
- Test: `tests/test_constants.py`, `tests/test_ollama.py`

**Interfaces:**
- Produces: `constants.DEFAULT_CURRENCY: str`, `constants.KNOWN_CURRENCIES: frozenset[str]`, `OllamaService.build_prompt(ocr_text: str) -> str`.

- [ ] **Step 1: Tests ersetzen/ergänzen**

`tests/test_constants.py` komplett ersetzen:

```python
"""Tests for shared constants."""

from belegscanner.constants import CURRENCIES, DEFAULT_CURRENCY, KNOWN_CURRENCIES


class TestCurrencyConstants:
    def test_ui_currencies(self):
        assert CURRENCIES == ("EUR", "USD", "CHF", "GBP")

    def test_default_is_a_ui_currency(self):
        assert DEFAULT_CURRENCY in CURRENCIES

    def test_known_currencies_superset_of_ui(self):
        assert frozenset(CURRENCIES) <= KNOWN_CURRENCIES
```

In `tests/test_ollama.py` ergänzen:

```python
from belegscanner.constants import CURRENCIES


class TestBuildPrompt:
    def test_prompt_lists_all_ui_currencies(self):
        service = OllamaService()
        prompt = service.build_prompt("Rechnungstext")
        for currency in CURRENCIES:
            assert currency in prompt
        assert "Rechnungstext" in prompt
```

- [ ] **Step 2: Fehlschlag verifizieren** — beide Testdateien → FAIL.
- [ ] **Step 3: Implementieren**

`constants.py`: nach `CURRENCIES` ergänzen:

```python
# Default currency for dropdowns and fallbacks
DEFAULT_CURRENCY = "EUR"

# Codes, die OCR/KI-Extraktion erkennen: UI-Waehrungen plus gaengige weitere
KNOWN_CURRENCIES = frozenset(CURRENCIES) | {
    "JPY", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF",
    "RON", "BGN", "HRK", "RUB", "TRY", "BRL", "MXN", "INR", "CNY", "KRW",
}
```

`ocr.py`: das Klassenattribut `KNOWN_CURRENCIES = frozenset([...])` (Zeilen 69–97) ersetzen durch `KNOWN_CURRENCIES = KNOWN_CURRENCIES` mit Import `from belegscanner.constants import KNOWN_CURRENCIES, OCR_LANGUAGE, OCR_THRESHOLDS` — konkret:

```python
from belegscanner.constants import KNOWN_CURRENCIES, OCR_LANGUAGE, OCR_THRESHOLDS
```

und in der Klasse:

```python
    # Known currency codes (only these are recognized, not arbitrary 3-letter codes)
    KNOWN_CURRENCIES = KNOWN_CURRENCIES
```

`ollama.py`: `from belegscanner.constants import CURRENCIES, OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT`; im Template `EUR/USD/CHF` durch `{currencies}` ersetzen und neue Methode:

```python
    def build_prompt(self, ocr_text: str) -> str:
        """Render the extraction prompt for the given OCR text."""
        return self.PROMPT_TEMPLATE.format(
            ocr_text=ocr_text, currencies="/".join(CURRENCIES)
        )
```

`_call_ollama`: `prompt = self.build_prompt(ocr_text)`.

Dropdown-Resets: in `email_view.py` (zwei Stellen: `_update_details`-else-Zweig, `_clear_details`) und `window.py` (`_on_save_complete`) jeweils

```python
self.currency_dropdown.set_selected(0)  # ...EUR...
```

ersetzen durch

```python
self.currency_dropdown.set_selected(CURRENCIES.index(DEFAULT_CURRENCY))
```

und die `"EUR"`-Fallback-Literale in `window.py` (`currency = CURRENCIES[currency_idx] if ... else "EUR"`) und `email_view.py` (gleiche Zeile in `_on_process_clicked`) durch `DEFAULT_CURRENCY` ersetzen; Importe entsprechend erweitern (`from belegscanner.constants import CATEGORIES, CURRENCIES, DEFAULT_CURRENCY`).

- [ ] **Step 4: Verifizieren + Commit** — `uv run pytest -q`; `git add -A && git commit -m "refactor: Waehrungskonstanten zusammenfuehren, Ollama-Prompt aus CURRENCIES"`

### Task 8: CI-Matrix reparieren, README-URL, ConfigManager-Legacy-API entfernen

**Files:**
- Modify: `.github/workflows/ci.yml`, `README.md`, `src/belegscanner/services/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Tests umstellen** — in `tests/test_config.py` alle sieben Aufrufe ersetzen: `manager.load()` → `manager.archive_path`, `manager.save(X)` → `manager.archive_path = X`. Semantik der Tests bleibt identisch.
- [ ] **Step 2: Fehlschlag verifizieren** — noch kein FAIL (Properties existieren schon); danach Legacy-API entfernen: in `config.py` die Methoden `load()` und `save()` ersatzlos löschen.
- [ ] **Step 3: Suche nach Restnutzern** — `grep -rn "config.load()\|config.save(" src/` → keine Treffer erwartet.
- [ ] **Step 4: CI fixen** — in `ci.yml` im `test`-Job:

```yaml
      - name: Install dependencies
        run: uv sync --all-extras --python ${{ matrix.python-version }}
```

- [ ] **Step 5: README-URL angleichen** — `https://github.com/jensens/belegscanner.git` → `https://github.com/kup-org/belegscanner.git`.
- [ ] **Step 6: Verifizieren + Commit** — `uv run pytest -q`; `git add -A && git commit -m "chore: CI-Python-Matrix real machen, README-URL, Config-Legacy-API entfernen"`

### Task 9: Wertlose bzw. doppelte Tests reparieren

**Files:**
- Modify: `tests/test_cli.py`, `tests/test_email_view_auto_connect.py`, `tests/test_ocr.py`

- [ ] **Step 1: CLI-Duplikat löschen** — in `tests/test_cli.py` die Methode `TestCliArgumentParsing.test_accepts_valid_kategorie` ersatzlos löschen (identisch mit `TestCliNoScanner.test_returns_error_when_no_scanner`).
- [ ] **Step 2: Tote raise unter @skip** — in `tests/test_email_view_auto_connect.py` die drei Methodenkörper `raise AssertionError(...)` unter `@pytest.mark.skip` durch reine Docstrings ersetzen (`"""Benoetigt GTK-Display."""` als einziger Body).
- [ ] **Step 3: OCR-Cleanup-Test echt machen** — in `tests/test_ocr.py` `test_cleans_up_temporary_files` ersetzen durch:

```python
    @patch("belegscanner.services.ocr.subprocess.run")
    def test_cleans_up_temporary_files(self, mock_run: MagicMock, tmp_path: Path):
        """Remove temporary threshold images after processing."""
        service = OcrService()
        image_path = tmp_path / "test.png"
        image_path.touch()

        def fake_run(cmd, **kwargs):
            if cmd[0] == "convert":
                Path(cmd[-1]).touch()  # convert legt die BW-Datei real an
            return MagicMock(returncode=0, stdout="Text")

        mock_run.side_effect = fake_run
        service.find_best_threshold(image_path)

        leftovers = [p.name for p in tmp_path.iterdir() if "_bw" in p.name]
        assert leftovers == []
```

Zusätzlich in `TestFindBestThresholdErrors.test_returns_empty_string_on_convert_failure` die lokale Zeile `from unittest.mock import patch` löschen (Modul-Import existiert).

- [ ] **Step 4: Verifizieren + Commit** — `uv run pytest -q`; `git add -A && git commit -m "test: Kopien- und Leerlauftests durch echte Pruefungen ersetzen"`

---

## Phase 2 — IMAP-Layer auf IMAPClient

Hinweis für alle Tasks dieser Phase: `tests/test_imap.py` mockt bisher `imaplib`-Interna; die Klassen werden pro Task auf `imapclient`-Mocks umgestellt. Die Roh-E-Mail-Fixtures (RFC822-Bytes) bleiben erhalten. Muster für alle Tests:

```python
from unittest.mock import MagicMock, patch

@patch("belegscanner.services.imap.IMAPClient")
def test_xyz(self, mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    ...
```

### Task 10: Dependency imapclient

**Files:**
- Modify: `pyproject.toml`, `uv.lock`

- [ ] **Step 1:** `uv add "imapclient>=3.0"`
- [ ] **Step 2:** `uv run python -c "import imapclient; print(imapclient.__version__)"` → Version ≥ 3.0.
- [ ] **Step 3:** `git add pyproject.toml uv.lock && git commit -m "chore: imapclient als Dependency aufnehmen"`

### Task 11: connect/disconnect/list_folders auf IMAPClient

**Files:**
- Modify: `src/belegscanner/services/imap.py`
- Test: `tests/test_imap.py` (Klassen `TestImapServiceConnection`, `TestImapServiceListFolders`)

**Interfaces:**
- Produces (API bleibt): `ImapService(server, port=993, use_ssl=True)`, `connect(user, pw) -> tuple[bool, str]`, `disconnect() -> None`, `list_folders() -> list[str]`, `is_connected: bool`. Neu: Modulkonstante `SOCKET_TIMEOUT = 15`.

- [ ] **Step 1: Tests umstellen** — `TestImapServiceConnection` und `TestImapServiceListFolders` auf das Mock-Muster oben umschreiben. Kernfälle:

```python
    @patch("belegscanner.services.imap.IMAPClient")
    def test_connect_establishes_connection(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        success, error = service.connect("user@example.com", "secret")
        assert success is True
        assert error == ""
        mock_client_cls.assert_called_once_with(
            "imap.example.com", port=993, ssl=True, timeout=SOCKET_TIMEOUT
        )
        mock_client.login.assert_called_once_with("user@example.com", "secret")
        assert service.is_connected

    @patch("belegscanner.services.imap.IMAPClient")
    def test_connect_returns_false_on_auth_failure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.login.side_effect = Exception("AUTHENTICATIONFAILED")
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        success, error = service.connect("user@example.com", "wrong")
        assert success is False
        assert "AUTHENTICATIONFAILED" in error
        assert not service.is_connected

    @patch("belegscanner.services.imap.IMAPClient")
    def test_list_folders_returns_folder_names(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.list_folders.return_value = [
            ((b"\\HasNoChildren",), b"/", "INBOX"),
            ((b"\\HasNoChildren",), b"/", "Rechnungseingang"),
        ]
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.list_folders() == ["INBOX", "Rechnungseingang"]
```

`SOCKET_TIMEOUT` importieren: `from belegscanner.services.imap import SOCKET_TIMEOUT`. Disconnect-Fälle: `logout` wird auf beiden Verbindungen gerufen, Fehler beim Logout werden geschluckt (bestehende Testfälle sinngemäß portieren).

- [ ] **Step 2: Fehlschlag verifizieren** — `uv run pytest tests/test_imap.py -k "Connection or ListFolders" -v` → FAIL.
- [ ] **Step 3: Implementieren** — in `imap.py`: Imports oben ersetzen/ergänzen:

```python
import email
import email.header
import threading
from dataclasses import dataclass
from datetime import datetime

from imapclient import IMAPClient

from belegscanner.log import get_logger
from belegscanner.services.text import sanitize_filename

logger = get_logger(__name__)

SOCKET_TIMEOUT = 15  # Sekunden; verhindert Minuten-Haenger bei toter Verbindung
```

`connect`/`disconnect`/`list_folders`/`connect_prefetch` ersetzen:

```python
    def connect(self, username: str, password: str) -> tuple[bool, str]:
        try:
            self._connection = IMAPClient(
                self.server, port=self.port, ssl=self.use_ssl, timeout=SOCKET_TIMEOUT
            )
            self._connection.login(username, password)
            return True, ""
        except Exception as e:
            logger.warning("IMAP-Verbindung fehlgeschlagen: %s", e)
            self._connection = None
            return False, str(e)

    def disconnect(self) -> None:
        for attr in ("_connection", "_prefetch_connection"):
            conn = getattr(self, attr)
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    logger.debug("Fehler beim IMAP-Logout (ignoriert)")
                setattr(self, attr, None)

    def connect_prefetch(self, username: str, password: str) -> bool:
        try:
            self._prefetch_connection = IMAPClient(
                self.server, port=self.port, ssl=self.use_ssl, timeout=SOCKET_TIMEOUT
            )
            self._prefetch_connection.login(username, password)
            return True
        except Exception:
            logger.warning("Prefetch-Verbindung fehlgeschlagen")
            self._prefetch_connection = None
            return False

    def list_folders(self) -> list[str]:
        if not self._connection:
            return []
        try:
            return [
                name if isinstance(name, str) else name.decode("utf-8", errors="replace")
                for _flags, _delim, name in self._connection.list_folders()
            ]
        except Exception:
            logger.warning("Ordnerliste konnte nicht abgerufen werden", exc_info=True)
            return []
```

Typannotation der Attribute anpassen: `self._connection: IMAPClient | None = None` (und analog `_prefetch_connection`). Docstring der Klasse ergänzen: *"Instanzen sind nicht thread-safe; ab Phase 3 ist der EmailWorker der einzige Nutzer."*

- [ ] **Step 4: Suite** — die noch nicht portierten Testklassen (`ListEmails`, `FetchEmail`, `MoveEmail`, `HasAttachments`, `Prefetch`) schlagen jetzt fehl; sie werden in Tasks 12–14 portiert. Bis dahin: `uv run pytest tests/test_imap.py -k "Connection or ListFolders or DataClasses" -q` muss grün sein. KEIN Commit mit rot laufender Gesamtsuite: Tasks 11–14 werden als EIN Commit am Ende von Task 14 abgeschlossen, ODER die alten Klassen werden hier vorübergehend mit `@pytest.mark.skip(reason="Portierung auf IMAPClient in Folge-Tasks")` markiert und der Task einzeln committet. Empfehlung: skip-Marker setzen und committen:

```bash
git add -A && git commit -m "refactor: IMAP-Verbindungsaufbau auf IMAPClient umstellen"
```

### Task 12: list_emails mit echtem ENVELOPE/BODYSTRUCTURE-Parsing

**Files:**
- Modify: `src/belegscanner/services/imap.py`
- Test: `tests/test_imap.py` (Klassen `TestImapServiceListEmails`, `TestHasAttachmentsDetection`)

**Interfaces:**
- Produces: `list_emails(folder) -> list[EmailSummary]`; intern `_decode_mime_words(value) -> str`, `_format_address(addresses) -> str`, `_structure_has_attachments(structure) -> bool`.

- [ ] **Step 1: Tests umstellen** — `TestImapServiceListEmails` neu, mit echten imapclient-Typen:

```python
from datetime import datetime

from imapclient.response_types import Address, Envelope


def make_envelope(subject=b"Rechnung", name=b"Amazon", mailbox=b"billing", host=b"amazon.de"):
    return Envelope(
        date=datetime(2024, 11, 15, 10, 0),
        subject=subject,
        from_=(Address(name, None, mailbox, host),),
        sender=None, reply_to=None, to=None, cc=None, bcc=None,
        in_reply_to=None, message_id=b"<x@y>",
    )


class TestImapServiceListEmails:
    @patch("belegscanner.services.imap.IMAPClient")
    def test_list_emails_returns_email_summaries(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.search.return_value = [7]
        mock_client.fetch.return_value = {
            7: {b"ENVELOPE": make_envelope(), b"BODYSTRUCTURE": None}
        }
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        result = service.list_emails("INBOX")
        assert len(result) == 1
        assert result[0].uid == 7
        assert result[0].subject == "Rechnung"
        assert "billing@amazon.de" in result[0].sender
        mock_client.select_folder.assert_called_with("INBOX")

    @patch("belegscanner.services.imap.IMAPClient")
    def test_subject_is_rfc2047_decoded(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.search.return_value = [1]
        mock_client.fetch.return_value = {
            1: {
                b"ENVELOPE": make_envelope(subject=b"=?utf-8?q?Rechnung_M=C3=A4rz?="),
                b"BODYSTRUCTURE": None,
            }
        }
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.list_emails("INBOX")[0].subject == "Rechnung März"

    @patch("belegscanner.services.imap.IMAPClient")
    def test_list_emails_empty_folder(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.list_emails("INBOX") == []

    def test_list_emails_returns_empty_when_not_connected(self):
        assert ImapService("imap.example.com").list_emails("INBOX") == []
```

`TestHasAttachmentsDetection` neu, gegen die Struktur-Heuristik mit Fake-Parts:

```python
class FakePart(tuple):
    is_multipart = False


class FakeMultipart(tuple):
    is_multipart = True


class TestHasAttachmentsDetection:
    def _service(self):
        return ImapService("imap.example.com")

    def test_none_structure(self):
        assert self._service()._structure_has_attachments(None) is False

    def test_plain_text_part(self):
        part = FakePart((b"text", b"plain", (b"charset", b"utf-8"), None, None, b"7bit", 42))
        assert self._service()._structure_has_attachments(part) is False

    def test_attachment_disposition(self):
        part = FakePart((
            b"application", b"pdf", None, None, None, b"base64", 1000,
            None, (b"attachment", (b"filename", b"invoice.pdf")),
        ))
        assert self._service()._structure_has_attachments(part) is True

    def test_pdf_by_param_name(self):
        part = FakePart((
            b"application", b"octet-stream",
            (b"name", b"rechnung.PDF"), None, None, b"base64", 1000,
        ))
        assert self._service()._structure_has_attachments(part) is True

    def test_multipart_with_nested_attachment(self):
        text = FakePart((b"text", b"plain", None, None, None, b"7bit", 10))
        pdf = FakePart((
            b"application", b"pdf", None, None, None, b"base64", 99,
            None, (b"attachment", (b"filename", b"a.pdf")),
        ))
        multi = FakeMultipart(([text, pdf], b"mixed"))
        assert self._service()._structure_has_attachments(multi) is True

    def test_broken_structure_returns_false(self):
        assert self._service()._structure_has_attachments(FakePart(())) is False
```

- [ ] **Step 2: Fehlschlag verifizieren.**
- [ ] **Step 3: Implementieren** — `list_emails`, `_parse_envelope` löschen und ersetzen durch:

```python
    def list_emails(self, folder: str) -> list[EmailSummary]:
        if not self._connection:
            return []
        try:
            self._connection.select_folder(folder)
            uids = self._connection.search("ALL")
            if not uids:
                return []
            summaries = []
            response = self._connection.fetch(uids, [b"ENVELOPE", b"BODYSTRUCTURE"])
            for uid, data in response.items():
                envelope = data.get(b"ENVELOPE")
                if envelope is None:
                    continue
                summaries.append(
                    EmailSummary(
                        uid=uid,
                        sender=self._format_address(envelope.from_),
                        subject=self._decode_mime_words(envelope.subject) or "(Kein Betreff)",
                        date=envelope.date or datetime.now(),
                        has_attachments=self._structure_has_attachments(
                            data.get(b"BODYSTRUCTURE")
                        ),
                    )
                )
            return summaries
        except Exception:
            logger.warning("E-Mail-Liste konnte nicht abgerufen werden", exc_info=True)
            return []

    @staticmethod
    def _decode_mime_words(value: bytes | str | None) -> str:
        """RFC-2047-dekodierter Header-Wert (z. B. '=?utf-8?q?...?=')."""
        if not value:
            return ""
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        try:
            parts = email.header.decode_header(value)
        except Exception:
            logger.debug("Header-Dekodierung fehlgeschlagen: %s", value)
            return value
        return "".join(
            part.decode(charset or "utf-8", errors="replace")
            if isinstance(part, bytes)
            else part
            for part, charset in parts
        )

    def _format_address(self, addresses) -> str:
        """Erste Adresse als 'Name <mailbox@host>' formatieren."""
        if not addresses:
            return "(Unbekannt)"
        addr = addresses[0]
        mailbox = (addr.mailbox or b"").decode("utf-8", errors="replace")
        host = (addr.host or b"").decode("utf-8", errors="replace")
        name = self._decode_mime_words(addr.name)
        email_str = f"{mailbox}@{host}" if mailbox and host else ""
        if name and email_str:
            return f"{name} <{email_str}>"
        return email_str or name or "(Unbekannt)"

    _ATTACHMENT_EXTENSIONS = (b".pdf", b".zip", b".doc", b".docx", b".xls", b".xlsx")

    def _structure_has_attachments(self, structure) -> bool:
        """Heuristik auf der geparsten BODYSTRUCTURE (imapclient BodyData)."""
        if structure is None:
            return False
        try:
            return self._part_has_attachment(structure)
        except (IndexError, TypeError, AttributeError):
            logger.debug("BODYSTRUCTURE nicht auswertbar", exc_info=True)
            return False

    def _part_has_attachment(self, part) -> bool:
        if getattr(part, "is_multipart", False):
            return any(self._part_has_attachment(sub) for sub in part[0])
        for item in part:
            if not isinstance(item, tuple):
                continue
            flat = [x for x in item if isinstance(x, bytes)]
            if flat and flat[0].lower() == b"attachment":
                return True
            for i, token in enumerate(flat):
                if token.lower() in (b"name", b"filename") and i + 1 < len(flat):
                    if flat[i + 1].lower().endswith(self._ATTACHMENT_EXTENSIONS):
                        return True
        return False
```

Hinweis: `_format_address` liefert jetzt „Name <adresse>" statt nur „mailbox@host" — bewusste Verbesserung, `VendorExtractor` priorisiert den Display-Namen.

- [ ] **Step 4: Verifizieren + Commit** — betroffene Klassen grün, restliche noch geskippt; `git add -A && git commit -m "refactor: list_emails auf IMAPClient mit RFC-2047-Dekodierung"`

### Task 13: fetch_email und _parse_email (Sanitizing beim Parsen)

**Files:**
- Modify: `src/belegscanner/services/imap.py`
- Test: `tests/test_imap.py` (Klassen `TestImapServiceFetchEmail`, `TestImapServicePrefetch`)

**Interfaces:**
- Produces: `fetch_email(uid, folder) -> EmailMessage | None`, `fetch_email_prefetch(uid, folder) -> EmailMessage | None`. `EmailAttachment.filename` ist ab jetzt garantiert sanitisiert.

- [ ] **Step 1: Tests umstellen** — die bestehenden Roh-RFC822-Fixtures wiederverwenden; Fetch-Mock:

```python
        mock_client.fetch.return_value = {42: {b"RFC822": raw_email_bytes}}
```

Skip-Marker der Klassen entfernen. Neuer Fall (feindlicher Dateiname):

```python
    @patch("belegscanner.services.imap.IMAPClient")
    def test_attachment_filename_is_sanitized_on_parse(self, mock_client_cls):
        raw = (
            b"From: a@b.de\r\nSubject: x\r\nDate: Mon, 4 Nov 2024 10:00:00 +0100\r\n"
            b"Message-ID: <1@b>\r\nMIME-Version: 1.0\r\n"
            b'Content-Type: multipart/mixed; boundary="B"\r\n\r\n'
            b"--B\r\nContent-Type: text/plain\r\n\r\nText\r\n"
            b"--B\r\nContent-Type: application/pdf\r\n"
            b'Content-Disposition: attachment; filename="../../etc/passwd.pdf"\r\n'
            b"Content-Transfer-Encoding: base64\r\n\r\nJVBERg==\r\n--B--\r\n"
        )
        mock_client = MagicMock()
        mock_client.fetch.return_value = {42: {b"RFC822": raw}}
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        message = service.fetch_email(42, "INBOX")
        assert message.attachments[0].filename == "passwd.pdf"
```

Prefetch-Tests: analog, `fetch_email_prefetch` nutzt die zweite Connection (Mock über zweiten `IMAPClient`-Konstruktoraufruf: `mock_client_cls.side_effect = [main_mock, prefetch_mock]`).

- [ ] **Step 2: Fehlschlag verifizieren.**
- [ ] **Step 3: Implementieren** — `fetch_email` und `fetch_email_prefetch` ersetzen:

```python
    def fetch_email(self, uid: int, folder: str) -> EmailMessage | None:
        if not self._connection:
            return None
        try:
            self._connection.select_folder(folder)
            data = self._connection.fetch([uid], [b"RFC822"]).get(uid)
            raw = data.get(b"RFC822") if data else None
            if not raw:
                return None
            return self._parse_email(uid, raw)
        except Exception:
            logger.warning("E-Mail-Fetch fehlgeschlagen fuer UID %d", uid, exc_info=True)
            return None

    def fetch_email_prefetch(self, uid: int, folder: str) -> EmailMessage | None:
        if not self._prefetch_connection:
            return None
        with self._prefetch_lock:
            try:
                self._prefetch_connection.select_folder(folder)
                data = self._prefetch_connection.fetch([uid], [b"RFC822"]).get(uid)
                raw = data.get(b"RFC822") if data else None
                if not raw:
                    return None
                return self._parse_email(uid, raw)
            except Exception:
                logger.debug("Prefetch-Fetch fehlgeschlagen fuer UID %d", uid)
                return None
```

In `_parse_email`: die Zeilen `sender = self._decode_header(...)`, `subject = self._decode_header(...)` auf `self._decode_mime_words(...)` umstellen, die alte Methode `_decode_header` löschen, und beim Attachment-Bau:

```python
                    if is_attachment and filename:
                        filename = sanitize_filename(self._decode_mime_words(filename))
```

- [ ] **Step 4: Verifizieren + Commit** — `git add -A && git commit -m "refactor: fetch_email auf IMAPClient, Dateinamen beim Parsen sanitisieren"`

### Task 14: move_email mit UID MOVE, Restklassen portieren

**Files:**
- Modify: `src/belegscanner/services/imap.py`
- Test: `tests/test_imap.py` (Klasse `TestImapServiceMoveEmail`)

- [ ] **Step 1: Tests umstellen**

```python
class TestImapServiceMoveEmail:
    @patch("belegscanner.services.imap.IMAPClient")
    def test_move_uses_move_capability(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.has_capability.side_effect = lambda cap: cap == "MOVE"
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.move_email(5, "INBOX", "Archiv") is True
        mock_client.move.assert_called_once_with([5], "Archiv")
        mock_client.copy.assert_not_called()

    @patch("belegscanner.services.imap.IMAPClient")
    def test_move_falls_back_to_copy_delete_expunge(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.has_capability.side_effect = lambda cap: cap == "UIDPLUS"
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.move_email(5, "INBOX", "Archiv") is True
        mock_client.copy.assert_called_once_with([5], "Archiv")
        mock_client.delete_messages.assert_called_once_with([5])
        mock_client.expunge.assert_called_once_with([5])

    @patch("belegscanner.services.imap.IMAPClient")
    def test_move_returns_false_on_failure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.has_capability.return_value = True
        mock_client.move.side_effect = Exception("kaputt")
        mock_client_cls.return_value = mock_client
        service = ImapService("imap.example.com")
        service.connect("u", "p")
        assert service.move_email(5, "INBOX", "Archiv") is False

    def test_move_returns_false_when_not_connected(self):
        assert ImapService("x").move_email(5, "a", "b") is False
```

- [ ] **Step 2: Fehlschlag verifizieren.**
- [ ] **Step 3: Implementieren**

```python
    def move_email(self, uid: int, source_folder: str, target_folder: str) -> bool:
        if not self._connection:
            return False
        try:
            self._connection.select_folder(source_folder)
            if self._connection.has_capability("MOVE"):
                self._connection.move([uid], target_folder)
            else:
                self._connection.copy([uid], target_folder)
                self._connection.delete_messages([uid])
                if self._connection.has_capability("UIDPLUS"):
                    self._connection.expunge([uid])  # UID EXPUNGE: nur diese Mail
                else:
                    self._connection.expunge()
            return True
        except Exception:
            logger.warning("E-Mail-Verschiebung fehlgeschlagen fuer UID %d", uid)
            return False
```

- [ ] **Step 4: Aufräumen** — `import re` in `imap.py` entfernen (nicht mehr benötigt); alle Skip-Marker aus Task 11 sind jetzt entfernt; `grep -n "imaplib" src/belegscanner/services/imap.py` → keine Treffer.
- [ ] **Step 5: Gesamtsuite + Smoke-Hinweis** — `uv run pytest -q` grün. VOR dem Merge dieser Phase einmal manuell gegen das echte Postfach testen: `BELEGSCANNER_DEBUG=1 uv run belegscanner` → verbinden, Liste prüfen (Umlaut-Betreffs!), eine Mail öffnen, eine archivieren.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "refactor: move_email mit UID MOVE, imaplib vollstaendig abgeloest"`

---

## Phase 3 — Worker und Generation

### Task 15: EmailWorker-Grundgerüst (seriell, Dispatcher-injizierbar)

**Files:**
- Create: `src/belegscanner/services/email_worker.py`
- Test: `tests/test_email_worker.py` (neu)

**Interfaces:**
- Produces:
  - `Command(kind: str, fn: Callable[[], Any], on_done: Callable[[Any], None], on_error: Callable[[Exception], None], uid: int | None = None, generation: int = 0)`
  - `EmailWorker(dispatch: Callable[..., Any], on_busy_changed: Callable[[bool], None] | None = None)`
  - `worker.submit(command, low_priority=False)`, `worker.stop()`, `worker.wait_idle(timeout=5.0) -> bool` (nur Tests).
  - `dispatch` wird als `dispatch(callback, *args)` aufgerufen (kompatibel mit `GLib.idle_add`).

- [ ] **Step 1: Tests schreiben** — `tests/test_email_worker.py`:

```python
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
```

- [ ] **Step 2: Fehlschlag verifizieren** — `uv run pytest tests/test_email_worker.py -v` → FAIL (Modul fehlt).
- [ ] **Step 3: Implementieren** — `src/belegscanner/services/email_worker.py`:

```python
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
            if not busy and self._on_busy_changed:
                busy = True
                self._dispatch(self._on_busy_changed, True)
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
                self._dispatch(self._on_busy_changed, False)
        if busy and self._on_busy_changed:
            self._dispatch(self._on_busy_changed, False)

    def _deliver(
        self, command: Command, result: Any = None, error: Exception | None = None
    ) -> None:
        with self._cv:
            extra = self._waiters.pop(command.uid, []) if command.uid is not None else []
        for cmd in (command, *extra):
            if error is not None:
                self._dispatch(cmd.on_error, error)
            else:
                self._dispatch(cmd.on_done, result)
```

- [ ] **Step 4: Tests grün** — `uv run pytest tests/test_email_worker.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: seriellen EmailWorker mit Dispatcher-Injektion einfuehren"`

### Task 16: Worker: Prioritäten und Fetch-Dedup

**Files:**
- Modify: ggf. `src/belegscanner/services/email_worker.py` (Verhalten existiert aus Task 15; dieser Task beweist es durch Tests)
- Test: `tests/test_email_worker.py`

- [ ] **Step 1: Tests ergänzen**

```python
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
            Command(kind="fetch", uid=7, fn=fetch_fn,
                    on_done=results_a.append, on_error=results_a.append),
            low_priority=True,
        )
        worker.submit(
            Command(kind="fetch", uid=7, fn=fetch_fn,
                    on_done=results_b.append, on_error=results_b.append),
        )
        gate.set()
        assert worker.wait_idle()
        assert calls == [1]                     # nur EIN echter Fetch
        assert "mail-7" in results_a
        assert results_b == ["mail-7"]          # Warter bekommt dasselbe Ergebnis
        worker.stop()

    def test_user_interest_promotes_prefetch_priority(self):
        gate = threading.Event()
        worker = EmailWorker(dispatch=sync_dispatch)
        order: list[str] = []
        worker.submit(make_command(lambda: gate.wait(5) and order.append("gate"), []))
        worker.submit(
            Command(kind="fetch", uid=7, fn=lambda: order.append("fetch7"),
                    on_done=lambda r: None, on_error=lambda e: None),
            low_priority=True,
        )
        worker.submit(make_command(lambda: order.append("other-low"), []), low_priority=True)
        # User waehlt UID 7 -> Prefetch wird hochgestuft
        worker.submit(
            Command(kind="fetch", uid=7, fn=lambda: order.append("nie"),
                    on_done=lambda r: None, on_error=lambda e: None),
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
            Command(kind="fetch", uid=9, fn=failing_fetch,
                    on_done=lambda r: None, on_error=errors_a.append),
            low_priority=True,
        )
        worker.submit(
            Command(kind="fetch", uid=9, fn=failing_fetch,
                    on_done=lambda r: None, on_error=errors_b.append),
        )
        gate.set()
        assert worker.wait_idle()
        assert len(errors_a) == 1 and len(errors_b) == 1
        worker.stop()
```

- [ ] **Step 2: Laufen lassen** — erwartungsgemäß bereits grün (Task-15-Implementierung deckt es ab); falls nicht: Implementierung korrigieren, NICHT die Tests.
- [ ] **Step 3: Commit** — `git add -A && git commit -m "test: Worker-Prioritaeten und Fetch-Dedup absichern"`

### Task 17: Worker: Busy-Übergänge

**Files:**
- Test: `tests/test_email_worker.py`

- [ ] **Step 1: Tests ergänzen**

```python
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
```

- [ ] **Step 2: Grün prüfen, ggf. fixen, Commit** — `git add -A && git commit -m "test: Busy-Uebergaenge des Workers absichern"`

### Task 18: Selektions-Generation im ViewModel, RC-APIs entfernen

**Files:**
- Modify: `src/belegscanner/email_viewmodel.py`
- Test: `tests/test_race_conditions.py`, `tests/test_email_viewmodel.py`

**Interfaces:**
- Produces: `vm.generation: int` (Property), `vm.select_email(uid) -> int` (bumpt und liefert neue Generation), `vm.is_current(generation: int) -> bool`. `clear()` und `set_emails()` bumpen ebenfalls.
- Entfernt: `start_fetch_request`, `complete_fetch_request`, `cancel_fetch_request`, `start_prefetch`, `complete_prefetch`, `is_prefetch_pending_for`, `increment_busy`, `decrement_busy`, `reset_busy`. (`is_busy` bleibt als GObject-Property; einziger Schreiber wird der Worker-Callback im View.)

- [ ] **Step 1: Tests schreiben** — in `tests/test_race_conditions.py` die Klassen `TestFetchRequestTracking`, `TestFetchRequestWithCache`, `TestBusyCounter`, `TestPrefetchCoordination`, `TestWebKitLoadGuard` **löschen** und ersetzen durch:

```python
class TestSelectionGeneration:
    def test_select_bumps_and_returns_generation(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100), make_summary(200)])
        g1 = vm.select_email(100)
        g2 = vm.select_email(200)
        assert g2 == g1 + 1
        assert vm.generation == g2

    def test_is_current_only_for_latest(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100), make_summary(200)])
        g1 = vm.select_email(100)
        g2 = vm.select_email(200)
        assert vm.is_current(g2) is True
        assert vm.is_current(g1) is False

    def test_clear_invalidates_all_generations(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100)])
        g1 = vm.select_email(100)
        vm.clear()
        assert vm.is_current(g1) is False

    def test_set_emails_invalidates_generations(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100)])
        g1 = vm.select_email(100)
        vm.set_emails([make_summary(100)])
        assert vm.is_current(g1) is False

    def test_deselect_invalidates(self):
        vm = EmailViewModel()
        vm.set_emails([make_summary(100)])
        g1 = vm.select_email(100)
        g2 = vm.select_email(-1)
        assert vm.selected_email is None
        assert g2 > g1
```

(`make_summary`/`make_email`-Helper der Datei wiederverwenden.) Die Klassen `TestRefreshAutoSelect`, `TestSnapshotPattern`, `TestImapConnectionGuard` bleiben, sofern sie keine entfernte API benutzen (per grep prüfen); sonst die betroffenen Methoden löschen. In `tests/test_email_viewmodel.py` per `grep -n "busy\|fetch_request\|prefetch" tests/test_email_viewmodel.py` betroffene Tests finden und löschen bzw. auf die neue API umstellen.

- [ ] **Step 2: Fehlschlag verifizieren.**
- [ ] **Step 3: Implementieren** — in `email_viewmodel.py`:

In `__init__` ersetzen: `self._fetch_request_id`, `self._current_fetch_request`, `self._busy_count`, `self._prefetch_pending_uid` löschen; stattdessen `self._generation: int = 0`.

```python
    @property
    def generation(self) -> int:
        """Aktuelle Selektions-Generation (monoton steigend)."""
        return self._generation

    def is_current(self, generation: int) -> bool:
        """True, wenn generation noch die aktuelle Selektion bezeichnet."""
        return generation == self._generation

    def _bump_generation(self) -> int:
        self._generation += 1
        return self._generation

    def select_email(self, uid: int) -> int:
        """Select an email by UID; returns the new selection generation."""
        generation = self._bump_generation()
        for email in self._emails:
            if email.uid == uid:
                self._selected_email = email
                return generation
        self._selected_email = None
        return generation
```

`set_emails`: am Ende `self._bump_generation()` ergänzen. `clear()`: die Zeilen zu `_current_fetch_request`/`_prefetch_pending_uid` ersetzen durch `self._bump_generation()`. Dann die neun genannten Methoden löschen.

- [ ] **Step 4: Kompilierbarkeit des Views** — `email_view.py` benutzt die entfernten APIs noch; dieser Task und Tasks 19–21 werden deshalb als zusammenhängende Serie auf einem Stand ohne zwischenzeitliches `uv run pytest`-grün-Gate für die GESAMTE Suite gefahren: nach diesem Task müssen `tests/test_race_conditions.py`, `tests/test_email_viewmodel.py`, `tests/test_email_worker.py` grün sein (`uv run pytest tests/test_race_conditions.py tests/test_email_viewmodel.py tests/test_email_worker.py -q`); die Gesamtsuite wird am Ende von Task 21 wieder verpflichtend grün.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "refactor: Selektions-Generation ersetzt Fetch-Request- und Prefetch-Tracking"`

### Task 19: EmailView auf Worker umstellen: Verbinden, Aktualisieren, Trennen

**Files:**
- Modify: `src/belegscanner/email_view.py`

**Interfaces:**
- Consumes: `EmailWorker`, `Command` (Task 15), `vm.generation`-API (Task 18).

- [ ] **Step 1: Worker instanziieren** — in `__init__` nach dem ViewModel:

```python
        # Worker: einziger Ort, an dem IMAP-Kommandos laufen
        self.worker = EmailWorker(
            dispatch=GLib.idle_add, on_busy_changed=self._on_worker_busy
        )
```

Import oben: `from belegscanner.services.email_worker import Command, EmailWorker`. Die Attribute `self._prefetch_thread` und `self._imap_credentials` löschen (Credentials werden nicht mehr für eine zweite Connection gebraucht). Neue Methode:

```python
    def _on_worker_busy(self, busy: bool) -> None:
        """Einziger Schreiber von vm.is_busy (kommt via GLib.idle_add)."""
        self.vm.is_busy = busy
```

- [ ] **Step 2: _connect umbauen** — `connect_thread`-Funktion und `threading.Thread`-Aufruf ersetzen durch:

```python
    def _connect(self, server: str, user: str, password: str):
        """Connect to IMAP server (im Worker)."""
        self.vm.status = "Verbinde..."
        self.imap = ImapService(server)
        imap = self.imap
        inbox = self.config.imap_inbox

        def do_connect():
            success, error = imap.connect(user, password)
            if not success:
                raise ConnectionError(error or "Verbindung fehlgeschlagen")
            logger.debug("Verfuegbare IMAP-Ordner: %s", imap.list_folders())
            return imap.list_emails(inbox)

        self.worker.submit(
            Command(
                kind="connect",
                fn=do_connect,
                on_done=self._on_connect_success,
                on_error=self._on_connect_failed,
            )
        )
```

`_on_connect_success(self, emails)`: die Zeile `self.vm.decrement_busy()` löschen (Rest bleibt). `_on_connect_failed` bekommt die Exception:

```python
    def _on_connect_failed(self, error: Exception):
        """Handle connection failure."""
        self.vm.is_connected = False
        self.vm.status = "Verbindung fehlgeschlagen"
        error_msg = str(error)
        message = "IMAP-Verbindung konnte nicht hergestellt werden."
        if "AUTHENTICATIONFAILED" in error_msg or "Invalid credentials" in error_msg:
            message = (
                "Anmeldung fehlgeschlagen.\n\n"
                "Bei Gmail/Google:\n"
                "• Server: imap.gmail.com\n"
                "• App-Passwort erforderlich (nicht das normale Passwort)\n"
                "• Erstellen unter: myaccount.google.com/apppasswords"
            )
        elif error_msg:
            message = f"Fehler: {error_msg}"
        self._show_error("Verbindungsfehler", message)
```

Die `connect_prefetch`-Aufrufe im Connect-Flow entfallen ersatzlos.

- [ ] **Step 3: _on_refresh_clicked umbauen**

```python
    def _on_refresh_clicked(self, button):
        """Refresh email list (im Worker)."""
        if not self.imap or not self.vm.is_connected:
            return
        self.vm.status = "Aktualisiere..."
        imap = self.imap
        inbox = self.config.imap_inbox
        self.worker.submit(
            Command(
                kind="list",
                fn=lambda: imap.list_emails(inbox),
                on_done=self._on_refresh_complete,
                on_error=self._on_refresh_failed,
            )
        )

    def _on_refresh_failed(self, error: Exception):
        self.vm.status = "Aktualisierung fehlgeschlagen"
        logger.warning("Refresh fehlgeschlagen: %s", error)
```

In `_on_refresh_complete` die Zeile `self.vm.decrement_busy()` löschen; Rest (Auto-Select mit Clamp) bleibt unverändert.

- [ ] **Step 4: _disconnect umbauen**

```python
    def _disconnect(self):
        """Disconnect from IMAP."""
        imap = self.imap
        self.imap = None
        if imap:
            self.worker.submit(
                Command(
                    kind="disconnect",
                    fn=imap.disconnect,
                    on_done=lambda _result: None,
                    on_error=lambda _error: None,
                )
            )
        self.vm.is_connected = False
        self.vm.status = "Nicht verbunden"
        self.connect_btn.set_label("Verbinden")
        self.refresh_btn.set_sensitive(False)
        self.vm.clear()  # bumpt die Generation: alle spaeten Ergebnisse verfallen
        self._update_email_list()
        self._clear_details()
```

- [ ] **Step 5: Zwischenstand prüfen** — `uv run ruff check src/belegscanner/email_view.py`; Gesamtsuite erst nach Task 21.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "refactor: Connect/Refresh/Disconnect ueber EmailWorker"`

### Task 20: EmailView: Selektion, Fetch und Prefetch über Worker + Generation

**Files:**
- Modify: `src/belegscanner/email_view.py`

- [ ] **Step 1: _on_email_selected ersetzen**

```python
    def _on_email_selected(self, listbox, row):
        """Handle email selection."""
        if row is None:
            self.vm.select_email(-1)
            self._clear_details()
            return

        uid = row.email_uid
        generation = self.vm.select_email(uid)

        cached_email = self.vm.get_cached_email(uid)
        if cached_email:
            logger.debug("Cache-Treffer fuer UID %d", uid)
            self.vm.set_current_email(cached_email)
            self._update_details()
            self.vm.status = "Bereit"
            return

        if not (self.imap and self.vm.is_connected):
            return

        self.vm.status = "Lade E-Mail..."
        imap = self.imap
        inbox = self.config.imap_inbox
        self.worker.submit(
            Command(
                kind="fetch",
                uid=uid,
                generation=generation,
                fn=lambda: imap.fetch_email(uid, inbox),
                on_done=lambda email, g=generation: self._on_email_fetched(email, g),
                on_error=lambda error, g=generation: self._on_fetch_failed(error, g),
            )
        )
```

- [ ] **Step 2: Callbacks ersetzen** — `_on_email_fetched` komplett ersetzen:

```python
    def _on_email_fetched(self, email, generation: int):
        """Handle email fetch completion (verwirft veraltete Ergebnisse)."""
        if not self.vm.is_current(generation):
            logger.debug("Veraltetes Fetch-Ergebnis verworfen (Generation %d)", generation)
            return
        if email is None:
            self._on_fetch_failed(RuntimeError("E-Mail nicht gefunden"), generation)
            return
        self.vm.cache_email(email)
        self.vm.set_current_email(email)
        self._update_details()
        self.vm.status = "Bereit"

    def _on_fetch_failed(self, error: Exception, generation: int):
        """Fetch-Fehler: Panel leeren, Status setzen — nie stumm haengen bleiben."""
        if not self.vm.is_current(generation):
            return
        logger.warning("E-Mail-Fetch fehlgeschlagen: %s", error)
        self._clear_details()
        self.vm.status = "E-Mail konnte nicht geladen werden"
```

- [ ] **Step 3: Prefetch ersetzen** — `_start_prefetch`, `_on_prefetch_complete`, `_on_prefetch_failed` komplett ersetzen durch:

```python
    def _start_prefetch(self, uid: int):
        """Naechste E-Mail als Low-Priority-Kommando vorladen (nur in den Cache)."""
        if not self.imap or self.vm.get_cached_email(uid):
            return
        logger.debug("Prefetch gestartet fuer UID %d", uid)
        imap = self.imap
        inbox = self.config.imap_inbox
        self.worker.submit(
            Command(
                kind="fetch",
                uid=uid,
                fn=lambda: imap.fetch_email(uid, inbox),
                on_done=self._on_prefetch_done,
                on_error=lambda _error: None,  # Cache bleibt leer; Selektion holt regulaer
            ),
            low_priority=True,
        )

    def _on_prefetch_done(self, email):
        if email is not None:
            self.vm.cache_email(email)
```

Wählt der User die Mail, während ihr Prefetch läuft, dedupliziert der Worker: die Selektion hängt sich mit eigenen Callbacks (inkl. Generation) an das laufende Kommando — Erfolg aktualisiert die UI, Fehler läuft durch `_on_fetch_failed`. Der RC7-Hänger ist damit konstruktiv unmöglich.

- [ ] **Step 4: RC8-Totcode entfernen** — in `_update_body_preview` den Block

```python
        # RC8: Guard - verify this is still the current email before loading
        current = self.vm.current_email
        if current is None or current.uid != email.uid:
            return
```

ersatzlos löschen (Snapshot-Parameter bleibt).

- [ ] **Step 5: Commit** — `git add -A && git commit -m "refactor: Selektion und Prefetch ueber Worker-Dedup und Generation"`

### Task 21: EmailView: Archivieren und Verarbeiten über Worker, threading raus

**Files:**
- Modify: `src/belegscanner/email_view.py`

- [ ] **Step 1: _on_archive_clicked umbauen** — `archive_thread` ersetzen:

```python
        archived_uid = email.uid
        imap = self.imap
        inbox = self.config.imap_inbox
        archive_folder = self.config.imap_archive

        def do_archive():
            if imap is None:
                raise RuntimeError("Nicht verbunden.")
            if not imap.move_email(archived_uid, inbox, archive_folder):
                raise RuntimeError("E-Mail konnte nicht verschoben werden.")
            return archived_uid

        self.worker.submit(
            Command(
                kind="move",
                fn=do_archive,
                on_done=self._on_archive_success,
                on_error=self._on_process_failed,
            )
        )
```

(`self.vm.increment_busy()` und `self.vm.status = "Archiviere..."`: increment-Zeile löschen, Status-Zeile bleibt.)

- [ ] **Step 2: _on_process_clicked umbauen** — `process_thread` ersetzen (Validierung davor bleibt identisch):

```python
        imap = self.imap
        processed_uid = email.uid
        inbox = self.config.imap_inbox
        archive_folder = self.config.imap_archive

        def do_process():
            if attachment_idx >= 0 and attachment_idx < len(email.attachments):
                att = email.attachments[attachment_idx]
                pdf_path = Path(self._temp_dir.name) / "attachment.pdf"
                pdf_path.write_bytes(att.data)
            else:
                pdf_path = Path(self._temp_dir.name) / "email.pdf"
                if not self.email_pdf.create_pdf(
                    sender=email.sender,
                    subject=email.subject,
                    date=email.date,
                    message_id=email.message_id,
                    body_text=email.body_text,
                    body_html=email.body_html,
                    output_path=pdf_path,
                ):
                    raise RuntimeError("PDF konnte nicht erstellt werden.")

            self.archive.base_path = self.config.archive_path
            final_path = self.archive.archive(
                pdf_path, date, desc, category, is_cc, currency=currency, amount=amount
            )

            if imap is None:
                raise RuntimeError("Nicht verbunden.")
            imap.move_email(processed_uid, inbox, archive_folder)
            return final_path

        self.worker.submit(
            Command(
                kind="process",
                fn=do_process,
                on_done=lambda final_path: self._on_process_success(
                    final_path, is_cc, processed_uid
                ),
                on_error=self._on_process_failed,
            )
        )
```

(increment-Zeile löschen; Status bleibt.)

- [ ] **Step 3: Erfolgs-/Fehler-Callbacks anpassen**

```python
    def _on_process_failed(self, error: Exception):
        """Handle processing failure."""
        self.vm.status = "Verarbeitung fehlgeschlagen"
        self._show_error("Fehler", str(error))
```

`_on_archive_success` und `_on_process_success`: Signaturen bleiben; sie enthalten keine Busy-Aufrufe mehr (waren die Leak-Stelle — durch die Worker-Ableitung ist der Zähler weg).

- [ ] **Step 4: KI-Extraktion bleibt Thread** — `_do_ki_extraction` bleibt bewusst ein eigener `threading.Thread` (Ollama-HTTP, kein IMAP; soll parallel zum Worker laufen können). Das ist die EINZIGE verbleibende `threading`-Nutzung in der Datei; Kommentar ergänzen:

```python
        # Bewusst eigener Thread statt EmailWorker: Ollama-HTTP hat mit der
        # seriellen IMAP-Queue nichts zu tun und darf parallel laufen.
```

- [ ] **Step 5: Verifizieren** — `grep -n "increment_busy\|decrement_busy\|reset_busy\|start_prefetch\b\|complete_prefetch\|is_prefetch_pending\|start_fetch_request\|complete_fetch_request" src/belegscanner/` → nur noch `_start_prefetch` (View-Methode) erlaubt; `uv run pytest -q` → GESAMTE Suite grün; `uv run ruff check .` sauber.
- [ ] **Step 6: Manueller Smoke-Test** — `BELEGSCANNER_DEBUG=1 uv run belegscanner`: verbinden, Mail wählen, archivieren → danach MUSS „Aktualisieren" klickbar bleiben (Busy-Leak-Regression), nächste Mail wird auto-selektiert und lädt.
- [ ] **Step 7: Commit** — `git add -A && git commit -m "refactor: Archivieren/Verarbeiten ueber Worker, Busy-Zaehler abgeloest"`

### Task 22: Prefetch-Sonderpfad aus ImapService entfernen

**Files:**
- Modify: `src/belegscanner/services/imap.py`
- Test: `tests/test_imap.py`

- [ ] **Step 1: Tests löschen** — Klasse `TestImapServicePrefetch` komplett entfernen; in Disconnect-Tests die Prefetch-Connection-Assertions entfernen.
- [ ] **Step 2: Implementieren** — `connect_prefetch` und `fetch_email_prefetch` löschen; `self._prefetch_connection` und `self._prefetch_lock` aus `__init__` entfernen; `import threading` entfernen; `disconnect` vereinfachen zu:

```python
    def disconnect(self) -> None:
        """Disconnect from IMAP server."""
        if self._connection is not None:
            try:
                self._connection.logout()
            except Exception:
                logger.debug("Fehler beim IMAP-Logout (ignoriert)")
            self._connection = None
```
- [ ] **Step 3: Verifizieren** — `grep -rn "prefetch" src/belegscanner/services/imap.py` → keine Treffer; `uv run pytest -q` grün.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "refactor: Prefetch-Zweitverbindung entfernt, Worker ist einziger IMAP-Nutzer"`

---

## Phase 4 — Security-Härtung

### Task 23: WebKit-Sandbox nur bei Bedarf deaktivieren

**Files:**
- Create: `src/belegscanner/webkit_env.py`
- Modify: `src/belegscanner/app.py`, `src/belegscanner/email_view.py`
- Test: `tests/test_webkit_env.py` (neu)

**Interfaces:**
- Produces: `webkit_env.user_namespaces_available() -> bool`, `webkit_env.ensure_webkit_sandbox_env() -> None`, Konstante `webkit_env.ENV_VAR`.

- [ ] **Step 1: Tests schreiben** — `tests/test_webkit_env.py`:

```python
"""Tests for the WebKit sandbox environment probe."""

import os
from unittest.mock import patch

from belegscanner.webkit_env import ENV_VAR, ensure_webkit_sandbox_env


class TestEnsureWebkitSandboxEnv:
    def test_respects_existing_env_value(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "0")
        with patch("belegscanner.webkit_env.user_namespaces_available") as probe:
            ensure_webkit_sandbox_env()
        probe.assert_not_called()
        assert os.environ[ENV_VAR] == "0"

    def test_sets_var_when_namespaces_unavailable(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        with patch(
            "belegscanner.webkit_env.user_namespaces_available", return_value=False
        ):
            ensure_webkit_sandbox_env()
        assert os.environ.get(ENV_VAR) == "1"
        monkeypatch.delenv(ENV_VAR, raising=False)

    def test_keeps_sandbox_when_namespaces_available(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        with patch(
            "belegscanner.webkit_env.user_namespaces_available", return_value=True
        ):
            ensure_webkit_sandbox_env()
        assert ENV_VAR not in os.environ
```

- [ ] **Step 2: Fehlschlag verifizieren.**
- [ ] **Step 3: Implementieren** — `src/belegscanner/webkit_env.py`:

```python
"""WebKit-Sandbox-Umgebung pruefen und nur bei Bedarf deaktivieren.

Die WebKit-Sandbox braucht unprivilegierte User-Namespaces. Wo die fehlen
(gehaertete Kernel, manche Container), crasht WebKit mit "bwrap: Permission
denied" - nur dort wird die Sandbox per Env-Var abgeschaltet.
"""

import os
import subprocess
from pathlib import Path

from belegscanner.log import get_logger

logger = get_logger(__name__)

ENV_VAR = "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"


def user_namespaces_available() -> bool:
    """True, wenn unprivilegierte User-Namespaces nutzbar sind."""
    proc_file = Path("/proc/sys/kernel/unprivileged_userns_clone")
    if proc_file.exists():
        try:
            return proc_file.read_text().strip() == "1"
        except OSError:
            pass
    try:
        result = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_webkit_sandbox_env() -> None:
    """Sandbox-Env-Var setzen, falls noetig und nicht schon konfiguriert.

    Muss VOR dem ersten WebKit-Import laufen.
    """
    if ENV_VAR in os.environ:
        return
    if not user_namespaces_available():
        logger.warning("User-Namespaces nicht verfuegbar - WebKit-Sandbox wird deaktiviert")
        os.environ[ENV_VAR] = "1"
```

- [ ] **Step 4: Verkabeln** — in `email_view.py` den Block Zeilen 10–14 (`if "WEBKIT_DISABLE_SANDBOX..." not in os.environ: ...`) samt zugehörigem Kommentar löschen (`import os` entfernen, falls sonst ungenutzt). In `app.py`: den Modul-Top-Import `from belegscanner.window import BelegscannerWindow` löschen und in `do_activate` verschieben; in `main()` vor `app = BelegscannerApp()`:

```python
    ensure_webkit_sandbox_env()
```

mit Import `from belegscanner.webkit_env import ensure_webkit_sandbox_env`. In `do_activate`:

```python
    def do_activate(self):
        """Called when the application is activated."""
        from belegscanner.window import BelegscannerWindow  # nach Sandbox-Probe importieren

        win = self.props.active_window
        if not win:
            win = BelegscannerWindow(application=self)
        win.present()
```

- [ ] **Step 5: Verifizieren + Commit** — `uv run pytest -q`; GUI-Smoke (`uv run belegscanner` startet, Vorschau rendert); `git add -A && git commit -m "security: WebKit-Sandbox nur nach fehlgeschlagener Namespace-Probe deaktivieren"`

### Task 24: Vorschau blockt Remote-Inhalte

**Files:**
- Modify: `src/belegscanner/email_view.py`

GTK-/WebKit-Verhalten ist headless nicht testbar; Absicherung: Code-Struktur + manueller Smoke-Test (Schritt 3).

- [ ] **Step 1: Implementieren** — in `_build_details_panel` nach `settings.set_allow_modal_dialogs(False)`:

```python
        self._install_remote_blocker()
```

Neue Methoden (Imports oben ergänzen: `import json`):

```python
    _BLOCK_REMOTE_FILTER = json.dumps(
        [{"trigger": {"url-filter": "https?://.*"}, "action": {"type": "block"}}]
    )

    def _install_remote_blocker(self):
        """Remote-Loads (Tracking-Pixel) in der Vorschau unterbinden."""
        try:
            store_dir = Path(GLib.get_user_cache_dir()) / "belegscanner" / "webkit-filters"
            store_dir.mkdir(parents=True, exist_ok=True)
            store = WebKit.UserContentFilterStore.new(str(store_dir))
            store.save(
                "block-remote",
                GLib.Bytes.new(self._BLOCK_REMOTE_FILTER.encode()),
                None,
                self._on_remote_filter_ready,
            )
        except Exception:
            logger.warning("Content-Filter nicht verfuegbar - Remote-Bilder deaktiviert")
            self.webview.get_settings().set_auto_load_images(False)

    def _on_remote_filter_ready(self, store, result):
        try:
            content_filter = store.save_finish(result)
            self.webview.get_user_content_manager().add_filter(content_filter)
        except Exception:
            logger.warning("Content-Filter fehlgeschlagen - Remote-Bilder deaktiviert")
            self.webview.get_settings().set_auto_load_images(False)
```

- [ ] **Step 2: Suite + Lint** — `uv run pytest -q && uv run ruff check .`
- [ ] **Step 3: Manueller Smoke-Test** — HTML-Mail mit Remote-Bild öffnen: Bild darf NICHT laden (Platzhalter ok), Inline-Text muss normal rendern.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "security: Vorschau blockt Remote-Inhalte per ContentFilter"`

### Task 25: WeasyPrint-url_fetcher: file:// blocken, http(s) mit Timeout

**Files:**
- Modify: `src/belegscanner/services/email_pdf.py`
- Test: `tests/test_email_pdf.py`

**Interfaces:**
- Produces: `email_pdf._restricted_url_fetcher(url, timeout=FETCH_TIMEOUT, **kwargs)`, Konstante `FETCH_TIMEOUT = 5`.

- [ ] **Step 1: Tests schreiben** — in `tests/test_email_pdf.py` ergänzen:

```python
import pytest

from belegscanner.services.email_pdf import _restricted_url_fetcher


class TestRestrictedUrlFetcher:
    def test_blocks_file_scheme(self):
        with pytest.raises(ValueError, match="Blockiertes URL-Schema"):
            _restricted_url_fetcher("file:///etc/passwd")

    def test_blocks_unknown_scheme(self):
        with pytest.raises(ValueError):
            _restricted_url_fetcher("ftp://example.com/x")

    def test_allows_http_with_timeout(self):
        with patch("belegscanner.services.email_pdf.default_url_fetcher") as mock_fetch:
            _restricted_url_fetcher("https://example.com/logo.png")
            mock_fetch.assert_called_once_with("https://example.com/logo.png", timeout=5)

    def test_allows_inline_data_image(self):
        with patch("belegscanner.services.email_pdf.default_url_fetcher") as mock_fetch:
            _restricted_url_fetcher("data:image/png;base64,AAAA")
            mock_fetch.assert_called_once()


class TestCreatePdfBlocksLocalFiles:
    def test_pdf_with_file_url_image_still_succeeds(self, tmp_path):
        service = EmailPdfService()
        output = tmp_path / "mail.pdf"
        ok = service.create_pdf(
            sender="a@b.de",
            subject="Test",
            date=datetime(2024, 11, 15, 10, 0),
            message_id="<x@y>",
            body_text="",
            body_html='<p>Hallo</p><img src="file:///etc/hostname">',
            output_path=output,
        )
        assert ok is True          # kaputtes/blockiertes Bild bricht das PDF nicht
        assert output.exists()
```

(Vorhandene Imports der Datei prüfen: `datetime`, `patch` ggf. ergänzen.)

- [ ] **Step 2: Fehlschlag verifizieren.**
- [ ] **Step 3: Implementieren** — in `email_pdf.py`:

```python
from weasyprint import HTML, default_url_fetcher

FETCH_TIMEOUT = 5  # Sekunden pro Remote-Ressource


def _restricted_url_fetcher(url: str, timeout: int = FETCH_TIMEOUT, **kwargs):
    """Nur http(s) (mit Timeout) und Inline-data:image zulassen.

    WeasyPrint behandelt eine hier geworfene Exception als fehlende
    Ressource und rendert das PDF ohne sie weiter.
    """
    if url.startswith("data:image/"):
        return default_url_fetcher(url)
    if url.startswith(("http://", "https://")):
        return default_url_fetcher(url, timeout=timeout)
    raise ValueError(f"Blockiertes URL-Schema: {url}")
```

und in `create_pdf` die Render-Zeile ersetzen:

```python
            HTML(string=html_content, url_fetcher=_restricted_url_fetcher).write_pdf(
                output_path
            )
```

- [ ] **Step 4: Verifizieren + Commit** — `uv run pytest tests/test_email_pdf.py -q`; `git add -A && git commit -m "security: WeasyPrint-URL-Fetcher blockt lokale Schemata"`

### Task 26: Scanner-Modus: Whitelist raus, Format-Validierung als Property

**Files:**
- Modify: `src/belegscanner/services/scanner.py`, `src/belegscanner/constants.py`
- Test: `tests/test_scanner.py`

**Interfaces:**
- Produces: `ScannerService.mode` als validierendes Property. Entfernt: `constants.VALID_SCAN_MODES`.

- [ ] **Step 1: Tests umstellen** — in `tests/test_scanner.py` die Klasse `TestScannerValidation` ersetzen:

```python
class TestScannerModeValidation:
    @pytest.mark.parametrize(
        "mode", ["True Gray", "Color", "24bit Color", "Gray[Error Diffusion]", "Black & White"]
    )
    def test_accepts_real_sane_modes(self, mode):
        assert ScannerService(mode=mode).mode == mode

    @pytest.mark.parametrize("mode", ["", "-foo", "--resolution", "a\x00b", "x\ny"])
    def test_rejects_malformed_modes(self, mode):
        with pytest.raises(ValueError, match="Ungueltiger Scan-Modus"):
            ScannerService(mode=mode)

    def test_setter_validates_too(self):
        service = ScannerService()
        with pytest.raises(ValueError):
            service.mode = "-trick"
```

- [ ] **Step 2: Fehlschlag verifizieren** (die neuen SANE-Modi schlagen an der Whitelist fehl).
- [ ] **Step 3: Implementieren** — in `scanner.py`:

```python
    def __init__(
        self,
        resolution: int = DEFAULT_RESOLUTION,
        mode: str = DEFAULT_SCAN_MODE,
    ):
        self.resolution = resolution
        self.mode = mode  # laeuft durch den validierenden Setter

    @property
    def mode(self) -> str:
        """Scan mode passed to scanimage (device-specific, e.g. 'True Gray')."""
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if not value or not value.isprintable() or value.startswith("-"):
            raise ValueError(
                f"Ungueltiger Scan-Modus: {value!r}. "
                "Erwartet: druckbarer Geraete-Modus ohne fuehrendes '-'."
            )
        self._mode = value
```

Import von `VALID_SCAN_MODES` entfernen; in `constants.py` die Zeile `VALID_SCAN_MODES = frozenset(...)` löschen; `grep -rn "VALID_SCAN_MODES" src/ tests/` → keine Treffer.

- [ ] **Step 4: Verifizieren + Commit** — `uv run pytest tests/test_scanner.py -q`; `git add -A && git commit -m "fix: Scan-Modus-Validierung akzeptiert echte SANE-Modi, prueft im Setter"`

### Task 27: Adw.MessageDialog → Adw.AlertDialog

**Files:**
- Modify: `src/belegscanner/window.py` (2 Stellen), `src/belegscanner/email_view.py` (1 Stelle)

- [ ] **Step 1: Umstellen** — Muster für beide `_show_error`-Methoden:

```python
    def _show_error(self, title: str, message: str):
        """Show error dialog."""
        dialog = Adw.AlertDialog(heading=title, body=message)
        dialog.add_response("ok", "OK")
        dialog.present(self.parent_window)   # in window.py: dialog.present(self)
```

Settings-Dialog in `window.py` (`_show_config_dialog`): `Adw.MessageDialog(transient_for=self, heading="Einstellungen")` → `Adw.AlertDialog(heading="Einstellungen")`; `dialog.present()` → `dialog.present(self)`; `set_extra_child`, `add_response`, `set_response_appearance`, `connect("response", ...)` bleiben identisch (gleiche API).

- [ ] **Step 2: Verifizieren** — `grep -rn "MessageDialog" src/` → keine Treffer; `uv run pytest -q`; GUI-Smoke: Einstellungs-Dialog öffnen/speichern, einen Fehlerdialog provozieren (Verbinden ohne Konfiguration).
- [ ] **Step 3: Commit** — `git add -A && git commit -m "refactor: Adw.AlertDialog statt deprecated MessageDialog"`

---

## Phase 5 — Doku und Gesamtverifikation

### Task 28: Dokumentation aktualisieren

**Files:**
- Modify: `README.md`, `docs/INSTALL.md` (falls dort Dependencies gelistet sind)

- [ ] **Step 1: README ergänzen** — im CLI-Optionsblock die Zeile

```
#   -v, -vv          Ausfuehrliche Ausgabe (Info/Debug)
```

und unter „GUI" einen Hinweis:

```markdown
Debug-Ausgabe der GUI: `BELEGSCANNER_DEBUG=1 uv run belegscanner`
```

Feature-Liste ergänzen: `- **IMAP-Verarbeitung** von Rechnungs-Mails (imapclient), Vorschau ohne Remote-Tracking`.

- [ ] **Step 2: INSTALL prüfen** — `grep -n "imaplib\|imapclient" docs/INSTALL.md`; falls Systemvoraussetzungen gelistet sind: `imapclient` wird via `uv sync` installiert, kein System-Paket nötig — nur erwähnen, falls die Datei Dependencies aufzählt.
- [ ] **Step 3: Commit** — `git add -A && git commit -m "docs: Verbositaet, Remote-Blocking und imapclient dokumentieren"`

### Task 29: Gesamtverifikation

**Files:** keine.

- [ ] **Step 1: Volle Suite mit Coverage** — `uv sync --all-extras && uv run pytest --cov --cov-report=term-missing -q` → alles grün; Coverage von `email_worker.py` und `imap.py` prüfen (Ziel: keine ungetesteten Fehlerpfade in den neuen Modulen).
- [ ] **Step 2: Lint/Format** — `uv run ruff check . && uv run ruff format --check .`
- [ ] **Step 3: Leichen-Grep** — alle folgenden Kommandos müssen leer sein:

```bash
grep -rn "imaplib" src/
grep -rn "MessageDialog" src/
grep -rn "VALID_SCAN_MODES" src/ tests/
grep -rn "increment_busy\|decrement_busy\|reset_busy" src/ tests/
grep -rn "print(" src/belegscanner/email_view.py src/belegscanner/services/
```

- [ ] **Step 4: Manuelle Smoke-Checkliste (echtes Postfach)** — `BELEGSCANNER_DEBUG=1 uv run belegscanner`:
  1. Auto-Connect verbindet; Umlaut-Betreffs korrekt in der Liste.
  2. Mail selektieren → Details laden; schnelles Hin- und Herklicken zwischen zwei Mails → Panel zeigt immer die selektierte Mail.
  3. „Nur Archivieren" → Mail verschwindet, nächste wird auto-selektiert, **„Aktualisieren" bleibt klickbar**.
  4. „Verarbeiten & Ablegen" mit Anhang → PDF landet korrekt benannt im Archiv.
  5. Mail mit Remote-Bild → Vorschau lädt das Bild nicht.
  6. Scanner-Tab: Scan + Speichern funktioniert unverändert.
- [ ] **Step 5: Abschluss** — `superpowers:finishing-a-development-branch` für Merge-Entscheidung nutzen.
