"""Application bootstrap: logging, root window and main loop."""

import logging
import tkinter as tk

from .logging_config import setup_logging


def create_root() -> tk.Tk:
    """Create the root window, using drag & drop support when available."""
    try:
        from tkinterdnd2 import TkinterDnD

        return TkinterDnD.Tk()
    except Exception:
        return tk.Tk()


def main() -> None:
    """Application entry point."""
    setup_logging(logging.INFO)

    from .ui import ManipulatorApp

    root = create_root()
    ManipulatorApp(root)
    root.mainloop()
