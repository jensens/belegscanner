# Belegscanner GUI - Implementierungsplan

## Zusammenfassung
CLI-basierter Belegscanner wird zu GTK4/libadwaita GUI umgebaut für GNOME/Linux.

## Framework-Entscheidung: GTK4 mit libadwaita

**Warum GTK4:**
- Nativer GNOME-Look, respektiert System Dark/Light Mode
- libadwaita bietet moderne Widgets (AdwPreferencesWindow, AdwToast)
- Leichter als Qt auf GTK-basierten Desktops
- `python3-gi` und `gir1.2-adw-1` sind kleine Pakete

## UI-Layout

```
+------------------------------------------------------------------+
|  Belegscanner                                          [Settings]|
+------------------------------------------------------------------+
|  [Scannen]  [Nochmal]                                            |
+------------------------------------------------------------------+
|                              |                                   |
|     +------------------+     |  Datum:     [15.11.2024    ]      |
|     |                  |     |             (Erkannt: 15.11.2024) |
|     |   Scan Preview   |     |                                   |
|     |   (scrollable)   |     |  Beschreibung: [bauhaus____]      |
|     |                  |     |             (Erkannt: bauhaus)    |
|     |   [Seite 1/3]    |     |                                   |
|     |   [<] [>]        |     |  Kategorie:   [Kassa         v]   |
|     +------------------+     |                                   |
|                              |  Seiten: 1  [+ Seite hinzufuegen] |
|                              |                                   |
|                              |         [  Speichern  ]           |
+------------------------------------------------------------------+
|  Status: Bereit                                                  |
+------------------------------------------------------------------+
```

## Dateistruktur

```
belegscanner/
├── pyproject.toml              # + PyGObject + pytest Dependencies
├── src/belegscanner/
│   ├── __init__.py
│   ├── app.py                  # Adw.Application, Entry Point
│   ├── window.py               # Hauptfenster
│   ├── viewmodel.py            # State + Signals
│   ├── services/
│   │   ├── __init__.py
│   │   ├── scanner.py          # scanimage Wrapper
│   │   ├── ocr.py              # tesseract + Threshold-Logik
│   │   ├── pdf.py              # ocrmypdf Wrapper
│   │   ├── archive.py          # Ablage-Logik
│   │   └── config.py           # Settings
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── preview_panel.py    # Bildvorschau mit Zoom
│   │   ├── input_panel.py      # Eingabefelder
│   │   └── preferences.py      # Einstellungen-Dialog
│   └── constants.py            # Kategorien etc.
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Fixtures (tmp_path, mock scanner)
│   ├── test_config.py
│   ├── test_ocr.py
│   ├── test_archive.py
│   ├── test_scanner.py
│   ├── test_pdf.py
│   └── test_viewmodel.py
├── docs/
│   └── PLAN_GUI.md             # Dieser Plan
├── scan-beleg.py               # CLI bleibt erhalten, nutzt services/
└── INSTALL.md                  # + GTK System-Pakete
```

## Code-Wiederverwendung

Aus `scan-beleg.py` extrahieren:

| Funktion | Neuer Ort |
|----------|-----------|
| `scan_page()` | `services/scanner.py` |
| `find_best_threshold()` | `services/ocr.py` |
| `extract_date()`, `extract_vendor()` | `services/ocr.py` |
| `create_pdf_with_ocr()` | `services/pdf.py` |
| `archive()`, `calc_target_month()` | `services/archive.py` |
| `load_config()` | `services/config.py` |

CLI (`scan-beleg.py`) importiert dann aus `belegscanner.services`.

## Async-Strategie

Scannen und OCR blockieren nicht die UI:
```python
def scan_async(self):
    task = Gio.Task.new(self, None, self._on_scan_done, None)
    task.run_in_thread(self._scan_in_thread)

def _scan_in_thread(self, task, ...):
    result = self.scanner.scan_page(...)
    GLib.idle_add(self._update_preview, result)  # UI-Update im Main Thread
```

## Implementierungsreihenfolge (TDD)

Jeder Schritt folgt dem Red-Green-Refactor Zyklus:
1. **Red**: Test schreiben, der fehlschlägt
2. **Green**: Minimaler Code, damit Test besteht
3. **Refactor**: Code aufräumen

### Phase 1: Projekt-Setup
1. Verzeichnisstruktur anlegen inkl. `tests/`
2. pytest als Test-Framework einrichten
3. pyproject.toml mit Test-Dependencies

### Phase 2: Services extrahieren (TDD)

**ConfigManager:**
- Test: `test_config_load_creates_default()`
- Test: `test_config_load_reads_existing()`
- Implementierung: `services/config.py`

**OcrService (reine Logik, kein subprocess):**
- Test: `test_extract_date_formats()`
- Test: `test_extract_vendor_cleanup()`
- Implementierung: `services/ocr.py`

**ArchiveService:**
- Test: `test_calc_target_month_regular()`
- Test: `test_calc_target_month_creditcard()`
- Test: `test_archive_creates_path()`
- Test: `test_archive_handles_duplicates()`
- Implementierung: `services/archive.py`

**ScannerService (mit Mock für subprocess):**
- Test: `test_scan_page_calls_scanimage()`
- Test: `test_scan_page_returns_path_on_success()`
- Implementierung: `services/scanner.py`

**PdfService (mit Mock für subprocess):**
- Test: `test_create_pdf_calls_ocrmypdf()`
- Implementierung: `services/pdf.py`

### Phase 3: ViewModel (TDD)
- Test: `test_viewmodel_initial_state()`
- Test: `test_viewmodel_scan_updates_pages()`
- Test: `test_viewmodel_emits_signals()`
- Implementierung: `viewmodel.py`

### Phase 4: GUI-Widgets
- Manuelle Tests (GTK-Widgets schwer unit-testbar)
- Fokus auf Integration mit ViewModel
- `app.py`, `window.py`, `widgets/`

### Phase 5: Integration
- Test: `test_full_workflow_mock_scanner()`
- End-to-End mit gemocktem Scanner

## Abhängigkeiten

**pyproject.toml:**
```toml
dependencies = [
    "python-dateutil>=2.9.0",
    "PyGObject>=3.46.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
]

[project.gui-scripts]
belegscanner = "belegscanner.app:main"
```

**System-Pakete (INSTALL.md):**
```bash
sudo apt install python3-gi gir1.2-adw-1 gir1.2-gtk-4.0
```

## Kritische Dateien

- `/home/jensens/ws/kup/belegscanner/scan-beleg.py` - Quellcode für Services
- `/home/jensens/ws/kup/belegscanner/pyproject.toml` - Dependencies
- Neu: `src/belegscanner/viewmodel.py` - Zentraler State
- Neu: `src/belegscanner/window.py` - Hauptfenster
