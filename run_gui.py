#!/usr/bin/env python3
"""Start the Belegscanner GUI."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from belegscanner.app import main

if __name__ == "__main__":
    sys.exit(main())
