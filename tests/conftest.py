"""Pytest configuration for image_manipulator tests."""

import os
import sys

# Add src to path so tests run without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
