"""Entrypoint — matches Alpic's Python template convention (`uv run main.py`)."""

import sys
from pathlib import Path

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from server import main

if __name__ == "__main__":
    main()
