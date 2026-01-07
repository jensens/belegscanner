# Plan: Betrag im Dateinamen

## Ziel
Dateinamen-Format erweitern von `2025-12-06_LIEFERANT.pdf` auf `2025-12-06_EUR27-07_LIEFERANT.pdf`

## Betroffene Bereiche

### 1. OCR-Service erweitern (ocr.py)
- Neue Methode `extract_amount(text: str) -> tuple[str, str] | None`
- Rückgabe: `(currency, amount)` z.B. `("EUR", "27.07")` oder `None`
- Patterns für Währungen + Beträge:
  - `€`, `EUR` → EUR
  - `$`, `USD` → USD
  - `CHF` → CHF
  - Weitere Währungscodes (3 Buchstaben)
- Patterns für Gesamtbeträge (Priorität):
  1. `Brutto`, `Gesamt`, `Summe`, `Total`, `Endbetrag`, `zu zahlen`
  2. Letzter Betrag mit Währungssymbol als Fallback
- Betragsformat: `XX,XX` oder `XX.XX` (deutsche/englische Notation)

### 2. ViewModels erweitern
**viewmodel.py (Scanner):**
- Property `suggested_currency` (default: "EUR")
- Property `suggested_amount` (z.B. "27.07")

**email_viewmodel.py (Email):**
- Property `suggested_currency` (default: "EUR")
- Property `suggested_amount`

### 3. UI erweitern
**window.py (Scanner-View):**
- `Adw.ComboRow` für Währung (EUR, USD, CHF, + manuelle Eingabe)
- `Adw.EntryRow` für Betrag (z.B. "27,07")
- Hint-Labels für erkannte Werte
- Validierung: Pflichtfeld, Format XX,XX oder XX.XX

**email_view.py (Email-View):**
- Gleiche Felder wie Scanner-View
- Bei PDF-Anhängen: OCR zur Betragserkennung ausführen

### 4. Archive-Service anpassen (archive.py)
- `archive()` Methode: Parameter `currency: str`, `amount: str` hinzufügen (Pflicht)
- Dateinamen-Format: `{date}_{currency}{amount}_{description}.pdf`
- Betrag formatieren: `27.07` → `27-07` (Dezimaltrenner → Bindestrich)
- Beispiel: `2025-12-06_EUR27-07_rewe.pdf`

### 5. Email-PDF-Service (email_pdf.py)
- Bei Konvertierung: OCR für Betragserkennung einbauen

## Dateien zu ändern

| Datei | Änderung |
|-------|----------|
| `services/ocr.py` | `extract_amount()` Methode |
| `viewmodel.py` | Property `suggested_amount` |
| `email_viewmodel.py` | Property `suggested_amount` |
| `window.py` | Betrag-Eingabefeld + OCR-Integration |
| `email_view.py` | Betrag-Eingabefeld + OCR-Integration |
| `services/archive.py` | Dateinamen-Format anpassen |
| `tests/test_ocr.py` | Tests für `extract_amount()` |
| `tests/test_archive.py` | Tests für neues Dateinamen-Format |

## Implementierungsreihenfolge (TDD)

1. **Tests für OCR-Betragserkennung** schreiben
2. **`extract_amount()`** implementieren
3. **Tests für Archive** erweitern (neues Dateiformat)
4. **Archive-Service** anpassen
5. **ViewModels** erweitern
6. **Scanner-UI** erweitern (window.py)
7. **Email-UI** erweitern (email_view.py)
8. Integration testen

## Anforderungen (geklärt)

- **Währung**: Primär EUR, aber auch USD, CHF und andere (Reisen)
- **Betrag**: Pflichtfeld (erzwungen)
- **Dezimalstellen**: Immer 2 Stellen (z.B. `EUR100-00`, `USD50-99`)

## Dateinamen-Format

```
2025-12-06_EUR27-07_lieferant.pdf
2025-12-06_USD150-00_hotel_xyz.pdf
2025-12-06_CHF89-50_migros.pdf
```
