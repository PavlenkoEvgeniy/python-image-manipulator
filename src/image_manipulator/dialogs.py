"""UI dialogs for the Image Manipulator application."""

import tkinter as tk
from tkinter import ttk

from . import __author__, __email__, __version__
from .config import config
from .positioning import center_over_parent


class AboutDialog:
    """About dialog window."""

    def __init__(self, parent: tk.Wm):
        """Create the about dialog.

        Args:
            parent: Parent window.
        """
        self.window = tk.Toplevel(parent)
        self.window.title(f"About {config.name}")
        self.window.resizable(False, False)
        self.window.transient(parent)

        # Build content first, then size the dialog from its real dimensions
        # and center it on the parent window before it settles.
        self.window.withdraw()
        self._create_content()
        self.window.deiconify()
        center_over_parent(parent, self.window)
        self.window.grab_set()
        self.window.focus_set()

    def _create_content(self) -> None:
        """Create the dialog content."""
        frame = ttk.Frame(self.window, padding="24")
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=f"🖼️ {config.name}",
            font=("Arial", 16, "bold"),
        ).pack(pady=(0, 8))

        ttk.Label(frame, text=f"Version {__version__}").pack(pady=(0, 14))

        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=(0, 14))

        ttk.Label(frame, text="License: Freeware").pack(anchor=tk.W, pady=2)
        ttk.Label(frame, text="Copyright © 2026").pack(anchor=tk.W, pady=2)
        ttk.Label(frame, text=f"Author: {__author__}").pack(anchor=tk.W, pady=2)
        ttk.Label(frame, text=f"Email: {__email__}").pack(anchor=tk.W, pady=2)

        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=14)

        description = (
            "Resize images and overlay text in a single pass.\n"
            "Images are resized first, then the text is drawn on the result, "
            "so font size matches the output dimensions."
        )
        tk.Label(
            frame,
            text=description,
            font=("Arial", 9),
            wraplength=380,
            justify=tk.CENTER,
        ).pack(pady=(0, 14))

        ttk.Button(frame, text="Close", command=self.window.destroy).pack()


class MessageDialog:
    """Modal message dialog centered over its parent window."""

    _STYLES = {
        "error": ("✖", "#b3261e"),
        "warning": ("⚠", "#b36b00"),
        "info": ("ℹ", "#1b6ec2"),
    }

    def __init__(self, parent: tk.Wm, level: str, title: str, message: str):
        """Create the message dialog.

        Args:
            parent: Parent window to center over.
            level: One of "error", "warning", "info".
            title: Dialog title.
            message: Message text.
        """
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.resizable(False, False)
        self.window.transient(parent)

        icon_text, color = self._STYLES[level]
        frame = ttk.Frame(self.window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        body = ttk.Frame(frame)
        body.pack()
        tk.Label(body, text=icon_text, fg=color, font=("Arial", 24)).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Label(body, text=message, wraplength=360, justify=tk.LEFT).pack(
            side=tk.LEFT
        )

        self.ok_button = ttk.Button(
            frame, text="OK", command=self.window.destroy, width=10
        )
        self.ok_button.pack(pady=(16, 0))

        center_over_parent(self.window, parent)

        self.window.bind("<Return>", lambda event: self.window.destroy())
        self.window.bind("<Escape>", lambda event: self.window.destroy())
        self.window.wait_visibility()
        self.window.grab_set()
        self.ok_button.focus_set()


class ErrorDialog:
    """Helper class for showing message dialogs centered over the main window."""

    @staticmethod
    def show_error(title: str, message: str, parent: tk.Wm) -> None:
        """Show an error message box."""
        MessageDialog(parent, "error", title, message)

    @staticmethod
    def show_warning(title: str, message: str, parent: tk.Wm) -> None:
        """Show a warning message box."""
        MessageDialog(parent, "warning", title, message)

    @staticmethod
    def show_info(title: str, message: str, parent: tk.Wm) -> None:
        """Show an info message box."""
        MessageDialog(parent, "info", title, message)
