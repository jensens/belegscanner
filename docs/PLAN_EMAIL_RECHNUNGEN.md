# Plan: E-Mail-Rechnungsverarbeitung für Belegscanner

## Zusammenfassung

Neue Ansicht im Belegscanner zum Abrufen und Verarbeiten von Rechnungen aus einem IMAP-Postfach. E-Mails mit PDF-Anhängen oder E-Mails als Rechnung selbst können nach dem bekannten Schema (Datum, Beschreibung, Kategorie) abgelegt werden.

---

## Neue Dateien

```
src/belegscanner/
├── services/
│   ├── imap.py              # ImapService: IMAP-Verbindung, E-Mail-Abruf
│   ├── credential.py        # CredentialService: Keyring (libsecret)
│   └── email_pdf.py         # EmailPdfService: E-Mail → PDF (weasyprint)
├── email_view.py            # GTK-Widget für E-Mail-Ansicht
└── email_viewmodel.py       # GObject ViewModel

tests/
├── test_imap.py
├── test_credential.py
├── test_email_pdf.py
└── test_email_viewmodel.py
```

## Zu ändernde Dateien

| Datei | Änderung |
|-------|----------|
| `services/config.py` | IMAP-Konfiguration (Server, User, Ordner) |
| `services/__init__.py` | Export neuer Services |
| `constants.py` | IMAP-Defaults |
| `window.py` | Adw.ViewStack + ViewSwitcher für Navigation |
| `pyproject.toml` | reportlab Dependency |

---

## UI-Design

```
+------------------------------------------------------------------+
|  Belegscanner                          [Scanner] [E-Mail] [Gear] |
+------------------------------------------------------------------+
|  [Verbinden]  [Aktualisieren]                                    |
+------------------------------------------------------------------+
|  E-Mail-Liste (links)      |   Detail/Vorschau (rechts)          |
|  +----------------------+  |   +----------------------------+    |
|  | > Amazon.de          |  |   | Von: rechnung@amazon.de    |    |
|  |   Rechnung #123      |  |   | Betreff: Ihre Rechnung     |    |
|  |   15.11.2024         |  |   | Datum: 15.11.2024          |    |
|  |   Telekom            |  |   +----------------------------+    |
|  |   Ihre Rechnung      |  |   | Anhänge:                   |    |
|  |   01.11.2024         |  |   | (o) Rechnung.pdf  [144KB]  |    |
|  +----------------------+  |   | ( ) AGB.pdf       [23KB]   |    |
|                            |   | ( ) E-Mail als PDF         |    |
|                            |   +----------------------------+    |
|                            |   | Datum:    [15.11.2024    ] |    |
|                            |   | Beschr.:  [amazon        ] |    |
|                            |   | Kategorie:[ER          v] |    |
|                            |   | [  Verarbeiten & Ablegen ] |    |
+------------------------------------------------------------------+
|  Status: 5 E-Mails im Rechnungseingang                           |
+------------------------------------------------------------------+
```

Navigation: `Adw.ViewSwitcher` in HeaderBar zwischen "Scanner" und "E-Mail".

---

## Implementierungsreihenfolge (TDD!)

### Phase 1: Basis-Services

1. **CredentialService** - Keyring mit libsecret
   - Tests: store/get/delete password, is_available
   - Fallback: Warnung wenn Keyring nicht verfügbar

2. **ConfigManager erweitern**
   - Tests für neue IMAP-Felder
   - Felder: IMAP_SERVER, IMAP_USER, IMAP_INBOX, IMAP_ARCHIVE

### Phase 2: IMAP-Service

3. **ImapService - Verbindung**
   - Tests: connect, disconnect, is_connected, list_folders
   - Implementierung mit `imaplib.IMAP4_SSL`

4. **ImapService - E-Mail-Abruf**
   - Tests: list_emails, fetch_email (mit Attachments)
   - Datenklassen: EmailSummary, EmailMessage, EmailAttachment

5. **ImapService - Verschieben**
   - Tests: move_email
   - IMAP COPY + DELETE

### Phase 3: E-Mail-zu-PDF

6. **EmailPdfService**
   - Tests: create_pdf (Text + HTML)
   - Implementierung mit weasyprint
   - HTML-Template mit Header (Von, Betreff, Datum, Message-ID) + Body
   - Unterstützt HTML-E-Mails nativ, Plain-Text in `<pre>` gewrappt

### Phase 4: ViewModel

7. **EmailViewModel**
   - GObject-Properties: status, is_busy, is_connected, selected_email_uid
   - Methoden: connect_imap, refresh_emails, select_email, process_selected
   - Async mit Threading + GLib.idle_add

### Phase 5: UI-Integration

8. **window.py umbauen**
   - Adw.ViewStack mit zwei Pages
   - Adw.ViewSwitcher in HeaderBar
   - Scanner-Code in eigene Methode refactoren

9. **EmailView implementieren**
   - Gtk.ListBox für E-Mail-Liste
   - Detail-Panel mit RadioButtons für Anhang-Auswahl
   - Eingabefelder für Bestätigung (wie Scanner)

### Phase 6: Polish

10. **Settings-Dialog erweitern**
    - IMAP-Konfiguration
    - Optional: Ordner-Auswahl aus IMAP-Tree

11. **Dokumentation**
    - Benutzer-Hilfe für E-Mail-Setup

---

## Services API

### ImapService
```python
class ImapService:
    def connect(self, username: str, password: str) -> bool
    def disconnect(self) -> None
    def list_folders(self) -> list[str]
    def list_emails(self, folder: str) -> list[EmailSummary]
    def fetch_email(self, uid: int, folder: str) -> EmailMessage
    def move_email(self, uid: int, source: str, target: str) -> bool
```

### CredentialService
```python
class CredentialService:
    def store_password(self, username: str, password: str) -> bool
    def get_password(self, username: str) -> str | None
    def delete_password(self, username: str) -> bool
    @staticmethod
    def is_available() -> bool
```

### EmailPdfService
```python
class EmailPdfService:
    """E-Mail → PDF mit weasyprint.

    Baut HTML aus E-Mail-Header + Body, rendert mit weasyprint zu PDF.
    Unterstützt HTML-E-Mails nativ, Plain-Text wird in <pre> gewrappt.
    """

    def create_pdf(
        self,
        sender: str,
        subject: str,
        date: datetime,
        message_id: str,
        body_text: str,
        body_html: str | None,
        output_path: Path
    ) -> bool:
        """Erstelle PDF aus E-Mail-Daten.

        Wenn body_html vorhanden, wird dieses verwendet (mit Header).
        Sonst wird body_text in HTML konvertiert.
        """
```

---

## Neue Dependencies

**pyproject.toml:**
```toml
dependencies = [
    ...
    "weasyprint>=60.0",  # HTML → PDF für E-Mail-Konvertierung
]
```

**System:**
```bash
sudo apt install gir1.2-secret-1  # libsecret für Keyring
# weasyprint braucht: pango, cairo, gdk-pixbuf (meist schon vorhanden bei GTK)
```

---

## Config-Erweiterung

`~/.config/belegscanner.conf`:
```ini
ABLAGE_PFAD=/home/user/nextcloud/finanzen
IMAP_SERVER=imap.example.com
IMAP_USER=user@example.com
IMAP_INBOX=Rechnungseingang
IMAP_ARCHIVE=Rechnungseingang/archiviert
```

---

## Workflow

1. Benutzer wechselt zu E-Mail-Ansicht
2. Klickt "Verbinden" → IMAP-Login (Passwort aus Keyring oder Dialog)
3. E-Mail-Liste wird geladen aus "Rechnungseingang"
4. Benutzer wählt E-Mail → Details werden angezeigt
5. Benutzer wählt: PDF-Anhang ODER "E-Mail als PDF"
6. Datum/Beschreibung werden vorgeschlagen (aus E-Mail-Header/PDF-OCR)
7. Benutzer bestätigt Datum, Beschreibung, Kategorie
8. "Verarbeiten & Ablegen" → PDF wird abgelegt
9. E-Mail wird nach "Rechnungseingang/archiviert" verschoben
10. Nächste E-Mail kann verarbeitet werden

---

## Offene Punkte (MVP → Später)

- [x] ~~HTML-E-Mails als PDF rendern~~ → Mit weasyprint von Anfang an dabei
- [ ] Ordner-Auswahl aus IMAP-Tree im Settings-Dialog
- [ ] E-Mail-Cache für Offline-Zugriff
- [ ] Batch-Verarbeitung mehrerer E-Mails
