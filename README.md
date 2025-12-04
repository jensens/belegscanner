# Belegscanner

Scannt Belege, erkennt Datum und Lieferant per OCR und archiviert sie als durchsuchbare PDFs.

## Features

- **GUI** (GTK4/libadwaita) und **CLI**
- Automatische **Texterkennung** (OCR) mit Tesseract
- **Datum und Lieferant** werden aus dem Scan extrahiert
- Durchsuchbare **PDF-Erstellung** mit ocrmypdf
- Strukturierte **Archivierung** nach Jahr/Monat/Kategorie
- **Kreditkarten-Modus**: Ablage im Folgemonat

## Quickstart

```bash
# System-Abhängigkeiten (Debian/Ubuntu)
sudo apt install sane-utils tesseract-ocr tesseract-ocr-deu \
    ocrmypdf imagemagick python3-gi gir1.2-adw-1 gir1.2-gtk-4.0

# Projekt installieren
git clone <repo-url> && cd belegscanner
uv sync

# GUI starten
uv run belegscanner

# Oder CLI verwenden
uv run scan-beleg -k 1 --help
```

## Verwendung

### GUI

```bash
uv run belegscanner
```

1. **Scannen** klicken - scannt eine Seite
2. Datum und Beschreibung werden automatisch erkannt
3. Kategorie wählen (Kassa, ER, Kreditkarte)
4. **Speichern** - PDF wird archiviert

### CLI

```bash
# Einfacher Scan mit automatischer OCR
uv run scan-beleg -k 1

# Mit vorgegebenen Werten
uv run scan-beleg -k 2 -d 15.11.2024 -b "bauhaus" -s 3

# Optionen
#   -k, --kategorie  1=Kassa, 2=ER, 3=ER-KKJK, 4=ER-KKCB
#   -d, --datum      Belegdatum (TT.MM.JJJJ)
#   -b, --beschreibung  Lieferant/Beschreibung
#   -s, --seiten     Anzahl Seiten (default: 1)
```

## Kategorien

| Nr | Ordner | Beschreibung |
|----|--------|--------------|
| 1 | Kassa | Barbelege |
| 2 | ER | Eingangsrechnungen |
| 3 | ER-KKJK | Kreditkarte JK (Ablage +1 Monat) |
| 4 | ER-KKCB | Kreditkarte CB (Ablage +1 Monat) |

## Archiv-Struktur

```
/pfad/zur/ablage/
├── 2024/
│   ├── 11/
│   │   ├── Kassa/
│   │   │   └── 2024-11-15_rewe.pdf
│   │   └── ER/
│   │       └── 2024-11-03_bauhaus.pdf
│   └── 12/
│       └── ER-KKJK/
│           └── 2024-11-20_amazon.pdf  # Nov-Beleg, Ablage Dez
```

## Konfiguration

Beim ersten Start wird nach dem Ablage-Pfad gefragt. Die Konfiguration liegt in:

```
~/.config/belegscanner.conf
```

```ini
# Belegscanner Konfiguration
ABLAGE_PFAD=/home/user/Nextcloud/Finanzen
```

## Entwicklung

```bash
# Dev-Dependencies installieren
uv sync --all-extras

# Tests ausführen
uv run pytest -v

# Linting
uv run ruff check src/ tests/
```

## Abhängigkeiten

**System-Pakete:**
- `sane-utils` - Scanner-Zugriff (scanimage)
- `tesseract-ocr` + `tesseract-ocr-deu` - OCR
- `ocrmypdf` - PDF mit OCR-Layer
- `imagemagick` - Bildverarbeitung
- `python3-gi`, `gir1.2-adw-1`, `gir1.2-gtk-4.0` - GTK4 GUI

**Python-Pakete:**
- `python-dateutil` - Datumsberechnung
- `PyGObject` - GTK-Bindings

## Lizenz

MIT
