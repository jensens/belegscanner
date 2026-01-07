# Plan: Direkt-Verbindung für E-Mail

## Ziel
Beim Klick auf "Verbinden" im E-Mail-Tab soll direkt verbunden werden, wenn die Zugangsdaten bereits konfiguriert sind. Die IMAP-Zugangsdaten sollen im Einstellungs-Dialog verwaltet werden.

## Aktueller Zustand
- `_on_connect_clicked()` zeigt `_show_connect_dialog()` mit Server/User/Passwort
- Einstellungs-Dialog (`_show_config_dialog()` in window.py) zeigt nur Ablage-Pfad
- Credentials werden im Keyring gespeichert (via CredentialService)

## Gewünschter Zustand
1. **Verbinden-Button**: Verbindet direkt mit gespeicherten Credentials
2. **Einstellungen**: IMAP-Server, User und Passwort verwalten
3. **Fallback**: Wenn keine Credentials vorhanden, Hinweis mit Link zu Einstellungen

## Implementierungsschritte

### 1. Tests aktualisieren/schreiben
- Test: Verbinden mit vorhandenen Credentials verbindet direkt
- Test: Verbinden ohne Credentials zeigt Fehler/Hinweis
- Test: Einstellungs-Dialog zeigt IMAP-Felder

### 2. Einstellungs-Dialog erweitern (window.py)
- IMAP-Server Eingabe
- E-Mail-Adresse Eingabe
- Passwort Eingabe (PasswordEntry)
- "Passwort speichern" Checkbox
- IMAP-Ordner (Inbox, Archiv)

### 3. EmailView anpassen (email_view.py)
- `_on_connect_clicked()`: Direkt verbinden wenn Credentials vorhanden
- `_show_connect_dialog()` entfernen
- Bei fehlenden Credentials: Toast/Dialog mit Hinweis auf Einstellungen

### 4. Passwort aus Keyring laden
- Beim Verbinden: `credential.get_password(config.imap_user)`
- Falls nicht vorhanden: Fehler anzeigen

## Dateien
- `src/belegscanner/window.py` - Einstellungs-Dialog erweitern
- `src/belegscanner/email_view.py` - Direkt-Verbindung implementieren
- `tests/test_email_view.py` - Tests für neues Verhalten
