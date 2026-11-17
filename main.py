"""Entry point for Image Manipulator."""

import sys
from pathlib import Path

# Make ``python main.py`` work without installing the package first.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from image_manipulator.app import main

if __name__ == "__main__":
    main()
