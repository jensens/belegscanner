# Plan: E-Mail-Ansicht Features

## Übersicht
Drei neue Features für die E-Mail-Ansicht im Belegscanner:
1. **Filter/Suche** - E-Mails durchsuchen (Header)
2. **Anhang-Indikator** - Zuverlässiger + prominenter anzeigen
3. **E-Mail-Preview** - Vorschau (HTML) mit PDF-Anzeige (extern)

---

## Feature 1: Filter/Suche (Header)

### Implementierung (TDD)

**1. Tests** (`tests/test_email_viewmodel.py`)
- `test_filter_emails_by_sender` - Filter auf Absender
- `test_filter_emails_by_subject` - Filter auf Betreff
- `test_filter_emails_empty_query` - Leerer Query = alle E-Mails
- `test_filter_emails_case_insensitive` - Groß/Klein egal

**2. ViewModel** (`src/belegscanner/email_viewmodel.py`)
- Property `filter_query: str`
- Property `filtered_emails: list[EmailSummary]` (computed)
- Methode `set_filter(query: str)` - setzt Filter und aktualisiert Liste

**3. UI** (`src/belegscanner/email_view.py`)
- `Gtk.SearchEntry` über der ListBox
- `search-changed` Signal → `vm.set_filter()`
- `_update_email_list()` nutzt `vm.filtered_emails`

---

## Feature 2: Anhang-Indikator (verbessert)

### Problem
- Aktuelle Erkennung: `"MULTIPART" in data_str` ist unzuverlässig
- Icon erscheint nur als kleiner Suffix, nicht prominent

### Implementierung (TDD)

**1. Tests** (`tests/test_imap.py`)
- `test_has_attachments_with_pdf` - E-Mail mit PDF-Anhang
- `test_has_attachments_multipart_no_attachment` - Multipart ohne Anhang (HTML+Text)
- `test_has_attachments_single_part` - Einfache E-Mail ohne Anhang

**2. IMAP-Service** (`src/belegscanner/services/imap.py`)
- `_parse_envelope()` verbessern: BODYSTRUCTURE auf `attachment` prüfen statt nur `MULTIPART`
- Regex: `attachment|ATTACHMENT` im Content-Disposition suchen

**3. UI** (`src/belegscanner/email_view.py`)
- Icon prominenter darstellen: **VOR** dem Sender als Prefix
- `row.add_prefix(icon)` statt `row.add_suffix(icon)`

---

## Feature 3: E-Mail-Preview + PDF extern öffnen

### Implementierung (TDD)

**1. Tests**
- `tests/test_email_viewmodel.py`: `test_preview_text_plain`, `test_preview_text_html`
- `tests/test_email_view.py`: `test_open_pdf_attachment`

**2. UI-Layout** (`src/belegscanner/email_view.py`)

```
+------------------------------------------+
| [Verbinden] [Aktualisieren]              |
+------------------------------------------+
| [🔍 Suche...                           ] |
+------------------------------------------+
| Email List     | E-Mail Details          |
| 📎 Sender      | Von: xxx                |
|    Betreff     | Betreff: xxx            |
|    12.01.2025  | Datum: xxx              |
|                |-------------------------|
|                | [WebKitWebView]         |  <- HTML Preview
|                | (scrollbar, ~200px)     |
|                |-------------------------|
|                | Quelle:                 |
|                | ○ anhang.pdf [Öffnen]   |  <- Button öffnet extern
|                | ○ E-Mail als PDF        |
|                |-------------------------|
|                | Beleg-Daten: ...        |
+------------------------------------------+
```

**3. WebKitWebView für HTML-Rendering**
- `gi.require_version("WebKit", "6.0")` (GTK4-kompatibel)
- `WebKit.WebView()` im ScrolledWindow
- `webview.load_html(email.body_html or email.body_text)`
- Fallback auf Plain-Text wenn kein HTML

**4. PDF extern öffnen**
- Button "Öffnen" neben jedem PDF-Anhang
- `Gtk.FileLauncher` (GTK4) oder `xdg-open` via subprocess
- Anhang als temp-Datei speichern, dann öffnen

---

## Zu bearbeitende Dateien

| Datei | Änderungen |
|-------|------------|
| `tests/test_email_viewmodel.py` | Filter-Tests, Preview-Tests |
| `tests/test_imap.py` | Anhang-Erkennung Tests |
| `src/belegscanner/email_viewmodel.py` | `filter_query`, `filtered_emails`, `set_filter()` |
| `src/belegscanner/services/imap.py` | `_parse_envelope()` verbessern |
| `src/belegscanner/email_view.py` | SearchEntry, Icon-Position, WebKitWebView, PDF-Button |

---

## Reihenfolge

1. **Feature 2**: Anhang-Indikator (kleinste Änderung, schneller Erfolg)
2. **Feature 1**: Filter/Suche (unabhängig)
3. **Feature 3**: E-Mail-Preview + PDF (aufwändigste Änderung)
