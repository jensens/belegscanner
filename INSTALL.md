# Installation Brother DS-640 Scanner unter Linux

## Voraussetzungen

Debian-basiertes Linux (Ubuntu, Linux Mint, Pop!_OS, etc.)

## 1. System-Pakete installieren

```bash
sudo apt install sane-utils tesseract-ocr tesseract-ocr-deu ocrmypdf imagemagick
```

## 2. Brother DS-640 Treiber installieren

Der Scanner benötigt den proprietären Brother-Treiber (brscan5).

### Download

```bash
wget https://download.brother.com/welcome/dlf104033/brscan5-1.2.11-0.amd64.deb
```

Oder neuere Version von: https://support.brother.com/g/b/downloadtop.aspx?c=eu_ot&lang=en&prod=ds640_eu_as

### Installation

```bash
sudo dpkg --force-all -i brscan5-*.deb
```

Die `--force-all` Option ist nötig, weil das Paket `libsane` erwartet, moderne Systeme aber `libsane1` haben.

## 3. USB-Berechtigungen einrichten

udev-Regel für den DS-640 erstellen:

```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="04f9", ATTR{idProduct}=="0468", MODE="0666", GROUP="scanner"' | sudo tee /etc/udev/rules.d/99-brother-ds640.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## 4. Benutzer zur Scanner-Gruppe hinzufügen

```bash
sudo usermod -aG scanner $USER
```

**Wichtig:** Danach ausloggen und wieder einloggen (oder `newgrp scanner`).

## 5. Scanner anschließen und testen

1. Scanner per USB anschließen
2. Scanner einschalten (LED sollte grün leuchten)
3. Test:

```bash
scanimage -L
```

Erwartete Ausgabe:
```
device `brother5:bus3;dev2' is a Brother DS-640 USB scanner
```

## 6. GTK4 und libadwaita für GUI

Build-Abhängigkeiten für PyGObject:
```bash
sudo apt install libcairo2-dev libgirepository-2.0-dev gir1.2-adw-1 gir1.2-gtk-4.0
```

Dies installiert:
- `libcairo2-dev` - Cairo Grafikbibliothek (Build-Dependency)
- `libgirepository-2.0-dev` - GObject Introspection (Build-Dependency)
- `gir1.2-adw-1` - libadwaita Typelib für moderne GNOME-Widgets
- `gir1.2-gtk-4.0` - GTK4 Typelib

## 7. Python-Abhängigkeiten

```bash
cd /pfad/zu/belegscanner
uv sync --extra dev
```

Oder ohne uv:
```bash
pip install python-dateutil
```

## Troubleshooting

### Scanner nicht erkannt

```bash
# USB-Verbindung prüfen
lsusb | grep Brother

# Berechtigungen prüfen
sane-find-scanner 2>&1 | grep -i brother
```

### "Access denied"

- Scanner abstecken und wieder anstecken
- Prüfen ob User in `scanner` Gruppe: `groups`
- Falls nicht: `sudo usermod -aG scanner $USER` und neu einloggen

### "Document feeder jammed"

- LED am Scanner muss **grün** leuchten (nicht orange/blinkend)
- Falls orange: Knopf am Scanner kurz drücken
- Papier muss richtig im Einzug liegen

### Scan-Modus Fehler

Der DS-640 unterstützt diese Modi:
- `True Gray` (empfohlen für Belege)
- `Black & White`
- `24bit Color[Fast]`
- `Gray[Error Diffusion]`

Nicht: `Gray` (funktioniert nicht!)
