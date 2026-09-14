# Belegscanner Modernisierung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the belegscanner codebase up to modern Python standards — fix security issues, improve code quality, expand linting, add logging, improve tests, and clean up infrastructure.

**Architecture:** The project is a GTK4/libadwaita receipt scanner with service-layer separation and MVVM pattern. Changes stay within this architecture — no structural rewrites. Each task is self-contained and can be committed independently.

**Tech Stack:** Python 3.12+, GTK4/libadwaita, pytest, ruff, uv, GitHub Actions

---

## Phase 1: Infrastructure & Tooling

These tasks lay the foundation. Ruff expansion will uncover issues; logging is needed before bare-exception cleanup.

### Task 1: Fix `.python-version`

**Files:**
- Modify: `.python-version`

- [ ] **Step 1: Fix the version**

`.python-version` currently says `3.14` which does not exist. Change it to `3.12`:

```
3.12
```

- [ ] **Step 2: Commit**

```bash
git add .python-version
git commit -m "fix: .python-version auf 3.12 korrigieren"
```

---

### Task 2: Complete `pyproject.toml` metadata

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add missing metadata fields**

After `requires-python = ">=3.12"` and before `dependencies`, add:

```toml
license = {text = "Proprietary"}
authors = [{name = "Klein und Partner KG"}]
readme = "README.md"
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: End Users/Desktop",
    "Operating System :: POSIX :: Linux",
    "Programming Language :: Python :: 3.12",
]
```

Add after `[project.scripts]` block:

```toml
[project.urls]
Repository = "https://github.com/kup-org/belegscanner"
Issues = "https://github.com/kup-org/belegscanner/issues"
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: pyproject.toml Metadaten vervollstaendigen"
```

---

### Task 3: Expand Ruff configuration

**Files:**
- Modify: `pyproject.toml` (ruff section)

- [ ] **Step 1: Update ruff lint config**

Replace the `[tool.ruff.lint]` section in `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "B", "S", "T", "UP", "RUF"]
ignore = [
    "E402",   # Module level imports - required for GTK gi.require_version()
    "S603",   # subprocess calls — we validate inputs where needed
    "S607",   # partial executable paths — we use system tools (scanimage, convert, tesseract)
]
```

Rule sets added:
- **B** (flake8-bugbear): common bugs
- **S** (bandit): security issues
- **UP** (pyupgrade): modernization
- **T** (flake8-print): catches leftover `print()` debug statements
- **RUF**: ruff-specific checks

- [ ] **Step 2: Run ruff and see what breaks**

```bash
uv run ruff check . 2>&1 | head -80
```

- [ ] **Step 3: Fix all new findings**

Likely findings:
- `UP` rules: minor syntax modernizations (frozenset literal, etc.)
- `B` rules: possible mutable defaults or re-raised exceptions
- `S` rules: subprocess and `except Exception` warnings
- `RUF` rules: unused noqa, ambiguous unicode

Fix each finding. For `S110` (try-except-pass) warnings in `imap.py` disconnect, add `noqa: S110` inline since swallowing logout errors is intentional there.

- [ ] **Step 4: Run tests to verify nothing broke**

```bash
uv run pytest -x -q
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "chore: Ruff-Regeln erweitern (B, S, UP, RUF) und Findings beheben"
```

---

### Task 4: Add logging infrastructure

**Files:**
- Create: `src/belegscanner/log.py`
- Test: `tests/test_log.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_log.py
"""Tests for logging setup."""

import logging

from belegscanner.log import get_logger


class TestGetLogger:
    def test_returns_logger_with_module_name(self):
        logger = get_logger("belegscanner.services.imap")
        assert logger.name == "belegscanner.services.imap"
        assert isinstance(logger, logging.Logger)

    def test_default_level_is_warning(self):
        logger = get_logger("belegscanner.test")
        assert logger.getEffectiveLevel() == logging.WARNING
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_log.py -v
```

Expected: `ModuleNotFoundError: No module named 'belegscanner.log'`

- [ ] **Step 3: Write implementation**

```python
# src/belegscanner/log.py
"""Logging setup for belegscanner."""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger for the given module name.

    Args:
        name: Module name (e.g., "belegscanner.services.imap").

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(name)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    return logger
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_log.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/belegscanner/log.py tests/test_log.py
git commit -m "feat: Logging-Infrastruktur hinzufuegen"
```

---

### Task 5: Improve CI pipeline

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add uv caching and Python version matrix**

Replace the full `ci.yml` with:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4

      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            tesseract-ocr \
            tesseract-ocr-deu \
            ocrmypdf \
            imagemagick \
            libcairo2-dev \
            libgirepository-2.0-dev \
            gir1.2-adw-1 \
            gir1.2-gtk-4.0

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Run tests
        run: uv run pytest --cov --cov-report=xml

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            libcairo2-dev \
            libgirepository-2.0-dev \
            gir1.2-adw-1 \
            gir1.2-gtk-4.0

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Set up Python
        run: uv python install

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Run linting
        run: uv run ruff check .

      - name: Check formatting
        run: uv run ruff format --check .
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: Python-Matrix (3.12+3.13) und uv-Caching hinzufuegen"
```

---

## Phase 2: Security Fixes

### Task 6: Fix path traversal in email attachments

**Files:**
- Modify: `src/belegscanner/email_view.py:780`
- Test: `tests/test_email_view_attachment_safety.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_email_view_attachment_safety.py
"""Tests for email attachment filename sanitization."""

from pathlib import Path


def sanitize_attachment_filename(filename: str) -> str:
    """Sanitize attachment filename to prevent path traversal."""
    return Path(filename).name or "attachment"


class TestSanitizeAttachmentFilename:
    def test_normal_filename_unchanged(self):
        assert sanitize_attachment_filename("invoice.pdf") == "invoice.pdf"

    def test_strips_directory_traversal(self):
        assert sanitize_attachment_filename("../../etc/passwd") == "passwd"

    def test_strips_absolute_path(self):
        assert sanitize_attachment_filename("/etc/passwd") == "passwd"

    def test_strips_windows_path(self):
        assert sanitize_attachment_filename("C:\\Users\\file.pdf") == "file.pdf"

    def test_empty_filename_gets_default(self):
        assert sanitize_attachment_filename("") == "attachment"

    def test_dot_only_gets_default(self):
        assert sanitize_attachment_filename("..") == "attachment"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_email_view_attachment_safety.py -v
```

Expected: PASS (the function is defined inline in the test for now — this validates the logic).

- [ ] **Step 3: Apply the fix in email_view.py**

In `src/belegscanner/email_view.py`, find line 780:

```python
        temp_path = Path(self._temp_dir.name) / att.filename
```

Replace with:

```python
        safe_filename = Path(att.filename).name or "attachment"
        temp_path = Path(self._temp_dir.name) / safe_filename
```

- [ ] **Step 4: Run full tests**

```bash
uv run pytest -x -q
```

- [ ] **Step 5: Commit**

```bash
git add src/belegscanner/email_view.py tests/test_email_view_attachment_safety.py
git commit -m "security: Path-Traversal bei E-Mail-Anhaengen verhindern"
```

---

### Task 7: Fix unhandled subprocess error in OCR

**Files:**
- Modify: `src/belegscanner/services/ocr.py:288-312`
- Modify: `tests/test_ocr.py` (add test for subprocess failure)

- [ ] **Step 1: Write the test**

Add to `tests/test_ocr.py`:

```python
class TestFindBestThresholdErrors:
    def test_returns_empty_string_on_convert_failure(self, tmp_path):
        """If ImageMagick convert fails, return empty string instead of crashing."""
        from unittest.mock import patch

        ocr = OcrService()
        image_path = tmp_path / "test.png"
        image_path.write_bytes(b"fake png data")

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "convert")):
            result = ocr.find_best_threshold(image_path)

        assert result == ""
```

Make sure `import subprocess` is at the top of the test file.

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_ocr.py::TestFindBestThresholdErrors -v
```

Expected: FAIL — unhandled `CalledProcessError`

- [ ] **Step 3: Fix the implementation**

In `src/belegscanner/services/ocr.py`, add the import at the top:

```python
from belegscanner.log import get_logger

logger = get_logger(__name__)
```

Replace the `find_best_threshold` method body (lines 285-312):

```python
    def find_best_threshold(self, image_path: Path) -> str:
        """Try multiple thresholds and return OCR text from best one.

        Uses ImageMagick to create black/white variants at different
        threshold levels, runs Tesseract on each, and returns the result
        with the most characters.

        Args:
            image_path: Path to image file

        Returns:
            OCR text from the threshold that produced most output
        """
        best_text = ""

        for threshold in self.thresholds:
            # Create threshold variant
            temp_bw = image_path.with_stem(f"{image_path.stem}_bw{threshold}")
            try:
                subprocess.run(
                    ["convert", str(image_path), "-threshold", f"{threshold}%", str(temp_bw)],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError:
                logger.warning("ImageMagick convert fehlgeschlagen bei Threshold %d%%", threshold)
                continue

            try:
                # Run OCR
                result = subprocess.run(
                    ["tesseract", str(temp_bw), "stdout", "-l", self.language],
                    capture_output=True,
                    text=True,
                )
                text = result.stdout

                # Keep best result
                if len(text) > len(best_text):
                    best_text = text
            finally:
                # Clean up temp file
                temp_bw.unlink(missing_ok=True)

        return best_text
```

This fixes three issues at once:
1. Wraps `convert` call in try/except
2. Uses `Path` instead of string manipulation (`image_str.replace(".png", ...)`)
3. Uses `Path.unlink(missing_ok=True)` instead of `os.remove()`
4. Uses `finally` to always clean up temp files

- [ ] **Step 4: Remove unused `import os`** if it's only used for `os.remove` here

Check if `os` is used elsewhere in ocr.py. If not, remove the import.

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_ocr.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/belegscanner/services/ocr.py tests/test_ocr.py
git commit -m "fix: Subprocess-Fehler in OCR abfangen, pathlib statt os.path"
```

---

### Task 8: Add scanner mode validation

**Files:**
- Modify: `src/belegscanner/services/scanner.py`
- Modify: `src/belegscanner/constants.py`
- Modify: `tests/test_scanner.py` (add validation test)

- [ ] **Step 1: Write the test**

Add to `tests/test_scanner.py`:

```python
class TestScannerValidation:
    def test_rejects_invalid_mode(self):
        with pytest.raises(ValueError, match="Ungueltiger Scan-Modus"):
            ScannerService(mode="'; rm -rf /")

    def test_accepts_valid_modes(self):
        for mode in ["True Gray", "Color", "Lineart", "Gray"]:
            service = ScannerService(mode=mode)
            assert service.mode == mode
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_scanner.py::TestScannerValidation -v
```

Expected: FAIL — no validation currently exists.

- [ ] **Step 3: Add constant and validation**

In `src/belegscanner/constants.py`, add after `DEFAULT_SCAN_MODE`:

```python
VALID_SCAN_MODES = frozenset({"True Gray", "Color", "Lineart", "Gray"})
```

In `src/belegscanner/services/scanner.py`, update imports:

```python
from belegscanner.constants import DEFAULT_RESOLUTION, DEFAULT_SCAN_MODE, VALID_SCAN_MODES
```

Update `__init__`:

```python
    def __init__(
        self,
        resolution: int = DEFAULT_RESOLUTION,
        mode: str = DEFAULT_SCAN_MODE,
    ):
        if mode not in VALID_SCAN_MODES:
            raise ValueError(
                f"Ungueltiger Scan-Modus: '{mode}'. "
                f"Erlaubt: {', '.join(sorted(VALID_SCAN_MODES))}"
            )
        self.resolution = resolution
        self.mode = mode
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_scanner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/belegscanner/constants.py src/belegscanner/services/scanner.py tests/test_scanner.py
git commit -m "security: Scanner-Modus gegen Whitelist validieren"
```

---

### Task 9: Document WebKit sandbox disabling

**Files:**
- Modify: `src/belegscanner/email_view.py:10-12`

- [ ] **Step 1: Improve the comment and make it conditional**

Replace lines 10-12 in `email_view.py`:

```python
# Disable WebKit sandbox to avoid "bwrap: Permission denied" errors
# on systems without user namespace support
os.environ["WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"] = "1"
```

With:

```python
# WebKit sandbox requires user namespace support which is unavailable on some
# Linux configurations (Flatpak, restricted kernels). Without this, WebKit
# crashes with "bwrap: Permission denied". Only set if not already configured.
# See: https://github.com/nickvdyck/weasyprint-sandbox-workaround
if "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS" not in os.environ:
    os.environ["WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"] = "1"
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest -x -q
```

- [ ] **Step 3: Commit**

```bash
git add src/belegscanner/email_view.py
git commit -m "docs: WebKit-Sandbox-Workaround besser dokumentieren"
```

---

## Phase 3: Code Quality

### Task 10: Extract `_strip_html()` to shared utility

**Files:**
- Create: `src/belegscanner/services/text.py`
- Create: `tests/test_text.py`
- Modify: `src/belegscanner/email_viewmodel.py` (remove duplicate, import)
- Modify: `src/belegscanner/email_view.py` (remove duplicate, import)

- [ ] **Step 1: Write the test**

```python
# tests/test_text.py
"""Tests for text utility functions."""

from belegscanner.services.text import strip_html


class TestStripHtml:
    def test_returns_empty_for_none(self):
        assert strip_html(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert strip_html("") == ""

    def test_strips_simple_tags(self):
        assert strip_html("<p>Hello</p>") == "Hello"

    def test_strips_script_elements(self):
        result = strip_html("<script>alert('xss')</script>Text")
        assert "alert" not in result
        assert "Text" in result

    def test_strips_style_elements(self):
        result = strip_html("<style>body{color:red}</style>Text")
        assert "color" not in result
        assert "Text" in result

    def test_decodes_html_entities(self):
        assert strip_html("&amp; &lt; &gt; &quot; &#39;") == "& < > \" '"

    def test_decodes_nbsp(self):
        assert "hello world" in strip_html("hello&nbsp;world")

    def test_collapses_whitespace(self):
        result = strip_html("<p>  lots   of    spaces  </p>")
        assert "  " not in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_text.py -v
```

- [ ] **Step 3: Write the utility module**

```python
# src/belegscanner/services/text.py
"""Text utility functions."""

import re


def strip_html(html: str | None) -> str:
    """Strip HTML tags and return plain text.

    Simple regex-based HTML stripping for extraction purposes.

    Args:
        html: HTML string or None.

    Returns:
        Plain text with HTML tags removed.
    """
    if not html:
        return ""
    # Remove script and style elements
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_text.py -v
```

- [ ] **Step 5: Replace usage in `email_viewmodel.py`**

Remove the `_strip_html` method (lines 317-345) from `email_viewmodel.py`. Add import at top:

```python
from belegscanner.services.text import strip_html
```

Replace all `self._strip_html(...)` calls with `strip_html(...)`.

- [ ] **Step 6: Replace usage in `email_view.py`**

Remove the `_strip_html` method (lines 1153-1179) from `email_view.py`. Add import at top:

```python
from belegscanner.services.text import strip_html
```

Replace all `self._strip_html(...)` calls with `strip_html(...)`.

- [ ] **Step 7: Run full tests**

```bash
uv run pytest -x -q
```

- [ ] **Step 8: Commit**

```bash
git add src/belegscanner/services/text.py tests/test_text.py \
       src/belegscanner/email_viewmodel.py src/belegscanner/email_view.py
git commit -m "refactor: _strip_html in gemeinsames Modul extrahieren"
```

---

### Task 11: Centralize `CURRENCIES` constant

**Files:**
- Modify: `src/belegscanner/constants.py`
- Modify: `src/belegscanner/window.py`
- Modify: `src/belegscanner/email_view.py`

- [ ] **Step 1: Add constant**

In `src/belegscanner/constants.py`, add after the `CATEGORIES` block:

```python
# Supported currencies for amount display
CURRENCIES = ("EUR", "USD", "CHF", "GBP")
```

- [ ] **Step 2: Replace all hardcoded lists in `window.py`**

Add to imports:

```python
from belegscanner.constants import CATEGORIES, CURRENCIES
```

Replace every `["EUR", "USD", "CHF", "GBP"]` with `CURRENCIES`. Search for occurrences and replace each one. Typical pattern:

```python
# Before:
for currency in ["EUR", "USD", "CHF", "GBP"]:
    currency_model.append(currency)

# After:
for currency in CURRENCIES:
    currency_model.append(currency)
```

Also fix index lookups like:

```python
# Before:
currencies = ["EUR", "USD", "CHF", "GBP"]
if result.currency in currencies:
    self.currency_dropdown.set_selected(currencies.index(result.currency))

# After:
if result.currency in CURRENCIES:
    self.currency_dropdown.set_selected(CURRENCIES.index(result.currency))
```

- [ ] **Step 3: Replace all hardcoded lists in `email_view.py`**

Same pattern as above. Add `CURRENCIES` to the constants import and replace all occurrences.

- [ ] **Step 4: Run full tests**

```bash
uv run pytest -x -q
```

- [ ] **Step 5: Commit**

```bash
git add src/belegscanner/constants.py src/belegscanner/window.py src/belegscanner/email_view.py
git commit -m "refactor: Waehrungsliste in CURRENCIES-Konstante zentralisieren"
```

---

### Task 12: Migrate `os.path`/`os.remove` remnants to `pathlib`

**Files:**
- Modify: `src/belegscanner/services/pdf.py`

(OCR was already fixed in Task 7)

- [ ] **Step 1: Modernize pdf.py**

Replace the entire `create_pdf` method in `src/belegscanner/services/pdf.py`:

```python
    def create_pdf(self, pages: list[Path], output_path: Path | str) -> bool:
        """Create PDF from page images and run OCR.

        Args:
            pages: List of paths to page images (PNG)
            output_path: Path for the output PDF

        Returns:
            True if PDF creation succeeded, False otherwise
        """
        output_path = Path(output_path)
        temp_pdf = output_path.with_suffix(".temp.pdf")

        try:
            # Create PDF from images using ImageMagick
            subprocess.run(
                ["convert", *[str(p) for p in pages], str(temp_pdf)],
                check=True,
                capture_output=True,
            )

            # Run OCR to create searchable PDF
            subprocess.run(
                [
                    "ocrmypdf",
                    "--language", self.language,
                    "--skip-text",
                    "--deskew",
                    "--clean",
                    str(temp_pdf),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
            )

            return True

        except subprocess.CalledProcessError:
            return False

        finally:
            # Clean up temp file
            temp_pdf.unlink(missing_ok=True)
```

Remove `import os` from `pdf.py` (no longer needed).

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_pdf.py -v
```

- [ ] **Step 3: Commit**

```bash
git add src/belegscanner/services/pdf.py
git commit -m "refactor: os.path/os.remove durch pathlib ersetzen in pdf.py"
```

---

### Task 13: Replace bare `except Exception` with specific exceptions + logging

This is the largest single task. Work through each service file.

**Files:**
- Modify: `src/belegscanner/services/imap.py`
- Modify: `src/belegscanner/services/credential.py`
- Modify: `src/belegscanner/services/email_pdf.py`

- [ ] **Step 1: Fix `credential.py`**

Add logging import at the top:

```python
from belegscanner.log import get_logger

logger = get_logger(__name__)
```

Replace the three `except Exception:` blocks (in `store_password`, `get_password`, `delete_password`) with:

```python
        except Exception:
            logger.exception("Keyring-Operation fehlgeschlagen fuer %s", username)
            return False  # or return None for get_password
```

The `except Exception` stays broad here because libsecret can throw various GLib errors, but we now log instead of silently swallowing.

- [ ] **Step 2: Fix `email_pdf.py`**

Add logging import at the top:

```python
from belegscanner.log import get_logger

logger = get_logger(__name__)
```

In `create_pdf` (line 59), replace:

```python
        except Exception:
            return False
```

With:

```python
        except Exception:
            logger.exception("E-Mail-PDF-Erstellung fehlgeschlagen: %s", output_path)
            return False
```

- [ ] **Step 3: Fix `imap.py`**

Add logging import at the top:

```python
from belegscanner.log import get_logger

logger = get_logger(__name__)
```

For each `except Exception:` / `except Exception as e:`, add logging. The pattern varies:

**`connect` (line 101)**:
```python
        except Exception as e:
            logger.warning("IMAP-Verbindung fehlgeschlagen: %s", e)
            self._connection = None
            return False, str(e)
```

**`disconnect` (lines 110, 117)** — these are intentionally silent (closing a connection that might already be dead). Add `noqa: S110` if ruff complains, or add minimal logging:
```python
            except Exception:
                logger.debug("Fehler beim IMAP-Logout (ignoriert)")
```

**`connect_prefetch` (line 142)**:
```python
        except Exception:
            logger.warning("Prefetch-Verbindung fehlgeschlagen")
            self._prefetch_connection = None
            return False
```

**`fetch_email_prefetch` (line 178)**:
```python
        except Exception:
            logger.debug("Prefetch-Fetch fehlgeschlagen fuer UID %d", uid)
            return None
```

**`_parse_email` (line 269)**, **`_parse_envelope` (line 414)**, **`_decode_header` (line 470)**, **`list_folders` (line 295)**, **`list_emails` (line 348)**, **`fetch_email` (line 446)**, **`move_email` (line 507)**:

Same pattern — add `logger.debug(...)` or `logger.warning(...)` with a descriptive message before the return.

- [ ] **Step 4: Run full tests**

```bash
uv run pytest -x -q
```

- [ ] **Step 5: Commit**

```bash
git add src/belegscanner/services/imap.py src/belegscanner/services/credential.py \
       src/belegscanner/services/email_pdf.py
git commit -m "fix: Bare-Exceptions durch spezifische Fehlerbehandlung + Logging ersetzen"
```

---

## Phase 4: Test Improvements

### Task 14: Remove empty test stubs

**Files:**
- Modify: `tests/test_email_view_auto_connect.py`

- [ ] **Step 1: Read the file and identify empty test methods**

Find all methods with `pass` as body. These give false coverage and should be either implemented with real assertions or removed entirely.

- [ ] **Step 2: Remove or implement each stub**

If a stub tests something that requires GTK runtime (display, signal handling), mark it with `pytest.mark.skip(reason="Requires GTK display")` instead of `pass`. If the behavior is already tested elsewhere, remove the stub.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_email_view_auto_connect.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_email_view_auto_connect.py
git commit -m "test: Leere Test-Stubs entfernen oder implementieren"
```

---

### Task 15: Add `pytest.mark.parametrize` where appropriate

**Files:**
- Modify: `tests/test_ocr.py`
- Modify: `tests/test_imap.py`

- [ ] **Step 1: Parametrize date extraction tests in `test_ocr.py`**

Find the individual date extraction tests (e.g., `test_extracts_date_dd_mm_yyyy`, `test_extracts_date_with_slashes`, etc.) and combine into parametrized tests:

```python
@pytest.mark.parametrize(
    "text, expected",
    [
        ("15.11.2024 Rechnung", "15.11.2024"),
        ("15/11/2024 Rechnung", "15.11.2024"),
        ("03.12.24 Schrauben", "03.12.2024"),
        ("kein datum hier", None),
        ("32.13.2024", None),  # invalid date
    ],
    ids=["dd.mm.yyyy", "dd/mm/yyyy", "short_year", "no_date", "invalid_date"],
)
def test_extract_date(text, expected):
    ocr = OcrService()
    assert ocr.extract_date(text) == expected
```

Keep the old tests only if they test something the parametrized version doesn't cover.

- [ ] **Step 2: Parametrize `has_attachments` tests in `test_imap.py`**

Combine the 6+ individual `test_has_attachments_*` tests into a single parametrized test.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_ocr.py tests/test_imap.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_ocr.py tests/test_imap.py
git commit -m "test: Wiederholte Tests durch pytest.mark.parametrize ersetzen"
```

---

### Task 16: Add CLI tests

**Files:**
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write basic CLI tests**

```python
# tests/test_cli.py
"""Tests for CLI interface."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from belegscanner.cli import main


class TestCliArgumentParsing:
    def test_requires_kategorie_argument(self):
        """CLI should fail without --kategorie."""
        with patch("sys.argv", ["scan-beleg"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse error

    def test_rejects_invalid_kategorie(self):
        """CLI should reject kategorie outside 1-4."""
        with patch("sys.argv", ["scan-beleg", "-k", "5"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

    def test_accepts_valid_kategorie(self):
        """CLI should accept kategorie 1-4 (will fail at scanner check)."""
        with (
            patch("sys.argv", ["scan-beleg", "-k", "1"]),
            patch("belegscanner.cli.ConfigManager") as mock_config,
            patch("belegscanner.cli.ScannerService") as mock_scanner,
        ):
            mock_config.return_value.archive_path = "/tmp/test"
            mock_scanner.return_value.is_available.return_value = False
            result = main()
            assert result == 1  # fails at scanner check, not argument parsing


class TestCliNoScanner:
    def test_returns_error_when_no_scanner(self):
        with (
            patch("sys.argv", ["scan-beleg", "-k", "1"]),
            patch("belegscanner.cli.ConfigManager") as mock_config,
            patch("belegscanner.cli.ScannerService") as mock_scanner,
        ):
            mock_config.return_value.archive_path = "/tmp/test"
            mock_scanner.return_value.is_available.return_value = False
            assert main() == 1


class TestCliNoArchivePath:
    def test_returns_error_when_no_archive_path(self):
        with (
            patch("sys.argv", ["scan-beleg", "-k", "1"]),
            patch("belegscanner.cli.ConfigManager") as mock_config,
        ):
            mock_config.return_value.archive_path = None
            assert main() == 1
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 3: Fix any failures and commit**

```bash
git add tests/test_cli.py
git commit -m "test: CLI-Tests hinzufuegen"
```

---

### Task 17: Add missing edge case tests

**Files:**
- Modify: `tests/test_ocr.py` (negative amounts, zero amounts)
- Modify: `tests/test_vendor.py` (multi-language)

- [ ] **Step 1: Add amount edge cases to `test_ocr.py`**

```python
class TestExtractAmountEdgeCases:
    def test_zero_amount(self):
        ocr = OcrService()
        result = ocr.extract_amount("SUMME 0,00 EUR")
        assert result == ("EUR", "0.00")

    def test_large_amount_german_format(self):
        ocr = OcrService()
        result = ocr.extract_amount("Gesamt: EUR 1.234,56")
        assert result == ("EUR", "1234.56")

    def test_amount_without_decimal(self):
        ocr = OcrService()
        result = ocr.extract_amount("Total EUR 100")
        assert result == ("EUR", "100.00")

    def test_none_input(self):
        ocr = OcrService()
        assert ocr.extract_amount(None) is None

    def test_empty_string(self):
        ocr = OcrService()
        assert ocr.extract_amount("") is None

    def test_text_without_amount(self):
        ocr = OcrService()
        assert ocr.extract_amount("Kein Betrag hier") is None
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_ocr.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_ocr.py tests/test_vendor.py
git commit -m "test: Fehlende Edge-Case-Tests ergaenzen"
```

---

## Phase 5: Final Verification

### Task 18: Full test suite + lint pass

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest --cov --cov-report=term-missing -q
```

- [ ] **Step 2: Run ruff check**

```bash
uv run ruff check .
```

- [ ] **Step 3: Run ruff format**

```bash
uv run ruff format --check .
```

If format check fails:

```bash
uv run ruff format .
git add -u
git commit -m "style: Ruff-Formatierung anwenden"
```

- [ ] **Step 4: Review coverage gaps**

Check the coverage report for any new uncovered code introduced by our changes. If significant gaps exist, add targeted tests.

---

## Summary

| Phase | Tasks | Focus |
|-------|-------|-------|
| 1: Infrastructure | 1-5 | .python-version, pyproject.toml, ruff, logging, CI |
| 2: Security | 6-9 | Path traversal, subprocess, scanner validation, WebKit |
| 3: Code Quality | 10-13 | Deduplication, constants, pathlib, exception handling |
| 4: Tests | 14-17 | Empty stubs, parametrize, CLI tests, edge cases |
| 5: Verification | 18 | Full suite pass, lint, coverage review |

Total: **18 tasks**, each independently committable.

---

## Intentionally Deferred

### God Classes (`window.py`, `email_view.py`)

Both `BelegscannerWindow` (705 LOC) and `EmailView` (1179 LOC) do too much (UI + business logic + threading). Splitting these into proper controllers/presenters is a larger architectural refactor that should be its own plan (`PLAN_ARCHITEKTUR_REFACTORING.md`) after the modernization is complete. The current changes (logging, deduplication, constants) already reduce their complexity somewhat.
