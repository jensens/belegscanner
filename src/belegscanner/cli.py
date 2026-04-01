"""Command-line interface for Belegscanner."""

import argparse
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from belegscanner.constants import CATEGORIES
from belegscanner.services import (
    ArchiveService,
    ConfigManager,
    OcrService,
    PdfService,
    ScannerService,
)


def main():
    """CLI entry point for scanning receipts."""
    parser = argparse.ArgumentParser(
        description="Scan receipts and archive them with OCR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Kategorien:
  1 = Kassa (Barbelege)
  2 = ER (Eingangsrechnungen)
  3 = ER-KKJK (Kreditkarte JK, Ablage +1 Monat)
  4 = ER-KKCB (Kreditkarte CB, Ablage +1 Monat)

Beispiel:
  scan-beleg --kategorie 1 --datum 15.11.2024 --beschreibung rewe
        """,
    )
    parser.add_argument(
        "-k",
        "--kategorie",
        choices=["1", "2", "3", "4"],
        required=True,
        help="Ablage-Kategorie (1-4)",
    )
    parser.add_argument(
        "-d",
        "--datum",
        help="Belegdatum (TT.MM.JJJJ), default: aus OCR",
    )
    parser.add_argument(
        "-b",
        "--beschreibung",
        help="Beschreibung/Lieferant, default: aus OCR",
    )
    parser.add_argument(
        "-s",
        "--seiten",
        type=int,
        default=1,
        help="Anzahl Seiten zu scannen (default: 1)",
    )
    parser.add_argument(
        "--ablage",
        help="Ablage-Pfad (überschreibt Config)",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Starte GUI statt CLI",
    )

    args = parser.parse_args()

    # Start GUI if requested
    if args.gui:
        from belegscanner.app import main as gui_main

        return gui_main()

    # Initialize services
    config = ConfigManager()
    scanner = ScannerService()
    ocr = OcrService()
    pdf = PdfService()
    archive = ArchiveService()

    # Get archive path
    archive_path = args.ablage or config.archive_path
    if not archive_path:
        print("Fehler: Kein Ablage-Pfad konfiguriert.", file=sys.stderr)
        print("Setze mit: scan-beleg --ablage /pfad/zu/ablage ...", file=sys.stderr)
        return 1

    archive.base_path = archive_path

    # Check scanner
    if not scanner.is_available():
        print("Fehler: Kein Scanner gefunden.", file=sys.stderr)
        return 1

    # Scan pages
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        pages = []

        for i in range(args.seiten):
            page_num = i + 1
            print(f"Scanne Seite {page_num}/{args.seiten}...", end=" ", flush=True)

            page_path = temp_path / f"page_{page_num:03d}.png"
            if scanner.scan_page(page_path):
                pages.append(page_path)
                print("OK")
            else:
                print("FEHLER")
                return 1

            if i < args.seiten - 1:
                input("Nächste Seite einlegen und Enter drücken...")

        # OCR for date/vendor if not provided
        date_str = args.datum
        description = args.beschreibung

        if not date_str or not description:
            print("OCR läuft...", end=" ", flush=True)
            text = ocr.find_best_threshold(pages[0])

            if not date_str:
                date_str = ocr.extract_date(text)
                if date_str:
                    print(f"Datum: {date_str}", end=" ")

            if not description:
                description = ocr.extract_vendor(text)
                if description:
                    print(f"Beschreibung: {description}", end=" ")

            print()

        # Validate
        if not date_str:
            date_str = input("Datum (TT.MM.JJJJ): ")

        if not description:
            description = input("Beschreibung: ")

        try:
            receipt_date = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            print(f"Fehler: Ungültiges Datum '{date_str}'", file=sys.stderr)
            return 1

        # Create PDF
        print("Erstelle PDF...", end=" ", flush=True)
        pdf_path = temp_path / "output.pdf"
        if not pdf.create_pdf(pages, pdf_path):
            print("FEHLER")
            return 1
        print("OK")

        # Archive
        category, is_cc = CATEGORIES[args.kategorie]
        print(f"Archiviere nach {category}...", end=" ", flush=True)

        try:
            final_path = archive.archive(
                source_path=pdf_path,
                date=receipt_date,
                description=description,
                category=category,
                is_credit_card=is_cc,
            )
            print("OK")
            print(f"\nGespeichert: {final_path}")

            if is_cc:
                print("(Kreditkarte: Ablage im Folgemonat)")

        except Exception as e:
            print(f"FEHLER: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
