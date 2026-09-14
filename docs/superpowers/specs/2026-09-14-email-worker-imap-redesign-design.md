# Spec: E-Mail-Worker, IMAP-Modernisierung und Review-Härtung

**Datum:** 2026-09-14
**Status:** Entwurf zur Review
**Nachfolger von:** `docs/PLAN_MODERNISIERUNG.md` (18 Tasks, umgesetzt auf `feature/modernisierung`)

## 1. Ziel und Begründung

Ein vollständiges Codebase-Review (2026-09-14) hat drei Problem-Ebenen ergeben:

1. **Konkrete Bugs**, vor allem im E-Mail-Flow: Der RC7-Prefetch-Guard hat keinen
   Fallback (UI hängt auf „Lade E-Mail...", Detail-Panel zeigt die vorherige Mail,
   „Verarbeiten" kann die falsche E-Mail archivieren), der Busy-Zähler leakt nach
   jedem erfolgreichen Archivieren, der Prefetch-Thread crasht bei Disconnect,
   der RC8-Guard ist toter Code, die CI-Python-Matrix testet zweimal 3.12.
2. **Strukturelle Ursache:** `email_view.py` (1179 Zeilen) spawnt pro Aktion einen
   Thread auf eine geteilte, ungelockte imaplib-Connection; die RC1–RC8-Guards
   flicken Symptome. Tests sichern mehrfach Kopien der Logik statt des
   Produktionscodes ab („Test einer Kopie").
3. **Fragiler IMAP-Layer:** ENVELOPE/BODYSTRUCTURE werden per Regex über
   Roh-Bytes geparst, Betreff/Absender werden nie RFC-2047-dekodiert, kein
   Socket-Timeout, `expunge()` wirkt ordnerweit.

Dieser Spec beseitigt alle drei Ebenen. Erwartetes Ergebnis: kein bekannter
Bug im E-Mail-Flow, die RC-Bug-Klasse ist konstruktiv unmöglich, jeder Test
prüft Produktionscode, Logging ist zur Laufzeit steuerbar, HTML-Mails werden
ohne Tracking-Vorschau und ohne `file://`-Zugriff verarbeitet.

## 2. Getroffene Grundsatzentscheidungen

| Entscheidung | Gewählt |
|---|---|
| Scope | Voller Umfang: Fixes + State-Redesign + IMAP-Umbau |
| IMAP-Bibliothek | Neue Dependency `imapclient` (statt stdlib-Regex-Parsing) |
| Nebenläufigkeit | Ein serieller IMAP-Worker-Thread mit Prioritäts-Queue |
| Remote-Inhalte | Vorschau blockt http(s)-Ressourcen; E-Mail-als-PDF lädt sie (mit Timeout); `file://` überall geblockt |
| Branch-Strategie | `feature/modernisierung` sofort mergen; gesamte Arbeit auf frischem Branch |

## 3. Architektur

### 3.1 EmailWorker (`services/email_worker.py`, neu)

- Ein dedizierter Worker-Thread arbeitet alle IMAP-Kommandos **seriell** ab:
  `connect`, `list_emails`, `fetch`, `prefetch`, `move`, `disconnect`.
- **Zwei Prioritäten** (zwei Deques): User-Kommandos vor Prefetch-Kommandos.
  Es gibt nur noch **eine** IMAP-Connection; die separate Prefetch-Connection
  entfällt. Schlimmster Fall: ein User-Fetch wartet die Dauer eines laufenden
  Prefetch (~1 s, durch Socket-Timeout begrenzt).
- **Dedup:** Ein Fetch-Kommando für eine UID, die bereits gequeued oder in
  Arbeit ist, wird nicht dupliziert; nachträgliche Interessenten (z. B. eine
  Selektion während laufendem Prefetch) hängen sich an das laufende Kommando.
  Damit verschwindet die RC7-Lücke als Problemklasse: auch ein
  Prefetch-Fehler läuft durch den normalen Fehlerpfad des wartenden Fetch.
- **Ergebnis-Dispatch:** über injizierbaren Dispatcher (Default
  `GLib.idle_add`, in Tests synchroner Aufruf). Der Worker importiert kein GTK
  und ist damit headless testbar.
- **Fehlerpfad:** Jedes Kommando liefert entweder Ergebnis oder Fehler an den
  Callback; es gibt keinen Pfad, der State setzt und nie auflöst.
- **Busy-State:** Der Worker meldet Übergänge idle↔arbeitend; `vm.is_busy`
  wird daraus abgeleitet. Die Methoden `increment_busy`/`decrement_busy`/
  `reset_busy` und der handgeführte Zähler entfallen.

### 3.2 Selektions-Generation (ersetzt RC1–RC8)

- `EmailViewModel` führt eine monoton steigende **Generation**. Jede Selektion
  (auch Deselektion und `clear()`) erhöht sie.
- Jedes vom View ausgelöste Kommando trägt die Generation seiner Entstehung.
  Ergebnis-Callbacks verwerfen Resultate mit veralteter Generation.
- Damit entfallen ersatzlos: `start_fetch_request`/`complete_fetch_request`/
  `cancel_fetch_request`, `start_prefetch`/`complete_prefetch`/
  `is_prefetch_pending_for`, der RC8-Guard in `_update_body_preview` sowie
  sämtliche `[TIMING]`-Print-Choreografie.
- Prefetch-Resultate landen ausschließlich im `EmailCache`; die UI wird nur
  aktualisiert, wenn die Generation des wartenden Fetch noch aktuell ist.

### 3.3 EmailView entkoppeln

- `email_view.py` behält UI-Aufbau und Handler; alle IMAP-Arbeit delegiert
  an Worker + ViewModel. Einzige verbleibende `threading`-Nutzung ist die
  Ollama-KI-Extraktion (bewusst: HTTP-Aufruf, der parallel zur seriellen
  IMAP-Queue laufen darf).
- Zielgröße: deutlich unter 700 Zeilen.
- Fehlerzustände setzen Status **und** räumen das Detail-Panel; ein Zustand
  „Panel zeigt Mail X, selektiert ist Mail Y" ist nicht mehr erreichbar
  (Aktionen wie Archivieren/Verarbeiten lesen die UID aus der aktuellen
  Selektion, validiert gegen die Generation).

### 3.4 ImapService auf IMAPClient (`services/imap.py`, Umbau)

- Neue Runtime-Dependency: `imapclient>=3.0`.
- Öffentliche API bleibt stabil (`connect`, `list_emails`, `fetch_email`,
  `move_email`, `disconnect`, Datenklassen `EmailSummary`/`EmailMessage`/
  `EmailAttachment`), damit Phase 2 ohne View-Umbau mergefähig ist. Die
  Prefetch-Spezialmethoden (`connect_prefetch`, `fetch_email_prefetch`)
  entfallen mit Phase 3.
- `list_emails`: `search()` + `fetch([ENVELOPE, BODYSTRUCTURE])`, geparste
  Objekte statt Regex; Betreff/Absender RFC-2047-dekodiert;
  `has_attachments` aus der echten BODYSTRUCTURE.
- `fetch_email`: RFC822-Fetch, Parsing über das `email`-Modul (eine einzige
  Parse-Stelle). Attachment-Dateinamen werden **beim Parsen** durch
  `sanitize_filename()` geschickt — kein Consumer sieht je einen feindlichen
  Namen.
- `move_email`: `UID MOVE` bei vorhandener Server-Capability, sonst
  COPY + STORE + `UID EXPUNGE` (nicht mehr ordnerweites `EXPUNGE`).
- Socket-Timeout (imapclient-`timeout`-Parameter) gegen Minuten-Hänger.
- Thread-Ownership: Der Service wird ausschließlich vom Worker-Thread
  benutzt; Locks sind dadurch unnötig. Docstring dokumentiert das.

### 3.5 Text-Utilities (`services/text.py`, Ausbau)

- `sanitize_filename(name) -> str`: Backslash-Normalisierung, `Path().name`,
  Dot-only-Abfang, NUL-/Steuerzeichen entfernen, Fallback `"attachment"`.
  Wird von `imap.py` (beim Parsen) und den Tests benutzt.
- `strip_html`: Entity-Dekodierung über `html.unescape()` (behebt
  `&euro;`-Lücke und Doppel-Dekodierung von `&amp;lt;`); die drei
  Regex-Patterns werden auf Modulebene vorkompiliert.

### 3.6 Logging (`log.py`, Umbau)

- `setup_logging(level)` konfiguriert **einmalig** den Paket-Logger
  `belegscanner` (ein `StreamHandler` auf stderr, Format wie bisher);
  `get_logger(name)` wird zu purem `logging.getLogger(name)`.
- CLI: `-v` → INFO, `-vv` → DEBUG. GUI: Umgebungsvariable
  `BELEGSCANNER_DEBUG=1` → DEBUG. Default bleibt WARNING.
- Alle `[TIMING]`/`[DEBUG]`-`print()` in `email_view.py` werden zu
  `logger.debug(...)`; die `T201`-per-file-Ausnahme in `pyproject.toml`
  entfällt. `cli.py` erhält stattdessen eine per-file-ignore-Zeile für
  `T201` (print ist dort die UI), die 19 inline-`noqa` entfallen.
- Log-Höhen-Konvention: erwartbare Umgebungsausfälle (kein Keyring, Ollama
  nicht erreichbar) → `debug`; fehlgeschlagene User-Aktionen → `warning`;
  `logger.exception` nur für unerwartete Fehler. `credential.py` und
  `ollama.py` werden entsprechend angepasst.

### 3.7 Security

- **WebKit-Sandbox:** Das Setzen von `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS`
  wandert vom Import-Nebeneffekt in den App-Start (`app.py`, vor dem ersten
  WebKit-Import) und passiert nur, wenn eine Probe ergibt, dass User-Namespaces
  nicht verfügbar sind (Check `/proc/sys/kernel/unprivileged_userns_clone`,
  bei Unklarheit ein `bwrap --ro-bind / / true`-Probelauf); mit
  `logger.warning` dokumentiert.
- **Vorschau:** Der WebView blockt Remote-Loads. Primär über einen
  WebKit-UserContentFilter (Content-Blocker-Regel „block http/https");
  falls das im Ziel-WebKitGTK nicht trägt, Fallback
  `settings.set_auto_load_images(False)` plus deaktivierte Plugins/Fetches.
  JavaScript bleibt aus.
- **E-Mail-als-PDF:** WeasyPrint erhält einen eigenen `url_fetcher`:
  `http`/`https` erlaubt mit Timeout (5 s) und Fehler-Toleranz (fehlendes
  Bild bricht das PDF nicht ab), alle anderen Schemes (`file`, `data:`
  ausgenommen inline-`data:image`) werden verweigert.
- **Scanner-Modus:** Die hartkodierte Whitelist `VALID_SCAN_MODES` entfällt
  (sie lehnt reale SANE-Modi wie „24bit Color" ab). Stattdessen
  Format-Validierung in einem Property-Setter: nicht-leer, druckbare
  Zeichen, kein führendes `-` (verhindert Options-Injection in die
  scanimage-argv). Validierung greift damit auch bei späterer Zuweisung.

### 3.8 Kleinzeug (läuft in Phase 1 mit)

- `DEFAULT_CURRENCY = "EUR"` in `constants.py`; Dropdown-Resets über
  `CURRENCIES.index(DEFAULT_CURRENCY)` statt `set_selected(0)`.
- `OcrService.KNOWN_CURRENCIES` wird in `constants.py` aus `CURRENCIES`
  abgeleitet (`frozenset(CURRENCIES) | {…extras}`).
- Ollama-Prompt rendert die Währungsliste aus `CURRENCIES` (GBP fehlt heute).
- README-Clone-URL an `pyproject.toml`-URL angleichen.
- `Adw.MessageDialog` → `Adw.AlertDialog` (deprecated seit libadwaita 1.6).
- `ConfigManager.load()`/`save()` (Legacy-Duplikat der Property) entfernen.
- `docs/PLAN_MODERNISIERUNG.md` einchecken.

## 4. Teststrategie

**Grundregel:** Kein Test asserted gegen eine Kopie von Produktionslogik.

- `test_email_view_attachment_safety.py` importiert `sanitize_filename` aus
  `services/text.py`; neue Fälle für NUL-/Steuerzeichen.
- Die RC-Simulationstests (`TestWebKitLoadGuard` u. a.) werden durch Tests
  der echten Generation-/Worker-Mechanik ersetzt: Serialität, Prioritäten,
  Dedup, Verwerfen veralteter Generationen, Fehlerpfade, Busy-Ableitung —
  alles headless über den injizierten Dispatcher.
- `ImapService`-Tests mocken `imapclient.IMAPClient`; Fälle: RFC-2047-Betreff,
  UID-MOVE-Capability vorhanden/fehlend, Timeout, kaputte Struktur.
- OCR-Cleanup-Test erzeugt echte Temp-Dateien (gefaktes `convert` legt
  Dateien an) und asserted deren Abwesenheit nach dem Lauf.
- `url_fetcher`-Tests: `file://` verweigert, http-Fehler bricht PDF nicht.
- Aufräumen: doppelter CLI-Test entfällt, `test_constants.py` schrumpft auf
  eine Assertion, unerreichbare `raise` unter `@skip` werden Docstrings.
- CI: `uv sync --python ${{ matrix.python-version }}`, damit die
  3.12/3.13-Matrix real testet.

## 5. Nicht-Ziele

- Kein Umbau des Scanner-Flows in `window.py` (funktioniert; nur Kleinzeug
  wie AlertDialog/DEFAULT_CURRENCY fasst ihn an).
- Keine neuen Features (kein Multi-Konto, keine Ordnerauswahl-UI).
- Keine Async-/asyncio-Migration.
- Kein Umbau von OCR-/Ollama-Extraktionslogik über die genannten Punkte hinaus.

## 6. Phasen und Lieferung

Jede Phase ist einzeln merge-fähig; durchgehend TDD; Arbeit im Worktree.

| Phase | Inhalt | Risiko |
|---|---|---|
| 0 | `feature/modernisierung` nach `main` mergen; frischer Branch; Plan-Doks eingecheckt | gering |
| 1 | Fundament: Logging-Umbau, `text.py`-Ausbau, CI-Fix, Test-Aufräumen, Kleinzeug (3.8) | gering |
| 2 | IMAP-Layer auf IMAPClient bei stabiler Service-API | mittel |
| 3 | Worker + Generation: `email_worker.py`, ViewModel-Verschlankung, `email_view.py`-Entkopplung, RC-APIs löschen | hoch |
| 4 | Security: Sandbox-Probe, Vorschau-Blocking, `url_fetcher`, Scanner-Validierung, AlertDialog | mittel |
| 5 | Doku (README, docs/), Gesamtverifikation, Coverage-Blick | gering |

**Bekanntes akzeptiertes Risiko:** Zwischen Phase 0 und Abschluss von Phase 3
trägt `main` die RC7-Regression (bewusste Entscheidung, Einzelnutzer-Tool).

## 7. Risiken und Gegenmaßnahmen

- **WebKit-Content-Filter-API variiert je WebKitGTK-Version** → Fallback
  `auto_load_images(False)` ist Teil des Designs, nicht Improvisation.
- **IMAPClient-Verhalten gegen echte Server** (Gmail-Eigenheiten) → die
  bestehenden Response-Format-Testfälle werden als Mock-Fixtures übernommen;
  manueller Smoke-Test gegen das echte Postfach vor Merge von Phase 2.
- **Serieller Worker fühlt sich träger an als zwei Connections** → Prefetch
  bleibt (niedrigprior), Cache bleibt; falls messbar spürbar, ist eine zweite
  Worker-Connection eine lokale Erweiterung des Workers, kein Redesign.
