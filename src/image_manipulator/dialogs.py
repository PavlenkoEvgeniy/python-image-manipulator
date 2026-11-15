"""UI dialogs for the Image Manipulator application."""

import logging
import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from . import __author__, __email__, __version__
from .config import config
from .i18n import tr
from .icon import load_icon_image
from .positioning import center_over_parent
from .uifonts import ui_font

logger = logging.getLogger(__name__)


class AboutDialog:
    """About dialog window."""

    def __init__(self, parent: tk.Wm):
        """Create the about dialog.

        Args:
            parent: Parent window.
        """
        self.window = tk.Toplevel(parent)
        self.window.title(tr("about.title", name=config.name))
        self.window.resizable(False, False)
        self.window.transient(parent)

        # Build content first, then size the dialog from its real dimensions
        # and center it on the parent window before it settles.
        self.window.withdraw()
        self._create_content()
        self.window.deiconify()
        center_over_parent(window=self.window, parent=parent)
        self.window.grab_set()
        self.window.focus_set()

    def _create_content(self) -> None:
        """Create the dialog content."""
        frame = ttk.Frame(self.window, padding="24")
        frame.pack(fill=tk.BOTH, expand=True)

        try:
            photo = ImageTk.PhotoImage(load_icon_image(96))
            # The label, not the dialog, owns the image. Dialog instances are
            # discarded right after construction, and a PhotoImage referenced
            # only by them is destroyed by garbage collection: Tk deletes the
            # image while the label keeps its size, leaving blank space.
            logo = tk.Label(frame, image=photo, borderwidth=0)
            logo.image = photo
            logo.pack(pady=(0, 4))
        except Exception as exc:
            logger.warning("Could not load the About dialog icon: %s", exc)

        tk.Label(
            frame,
            text=config.name,
            font=ui_font(16, "bold"),
        ).pack(pady=(0, 8))

        ttk.Label(frame, text=tr("about.version", version=__version__)).pack(
            pady=(0, 14)
        )

        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=(0, 14))

        ttk.Label(frame, text=tr("about.license")).pack(anchor=tk.W, pady=2)
        ttk.Label(frame, text=tr("about.copyright")).pack(anchor=tk.W, pady=2)
        ttk.Label(frame, text=tr("about.author", author=__author__)).pack(
            anchor=tk.W, pady=2
        )
        ttk.Label(frame, text=tr("about.email", email=__email__)).pack(
            anchor=tk.W, pady=2
        )

        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=14)

        tk.Label(
            frame,
            text=tr("about.description"),
            font=ui_font(9),
            wraplength=380,
            justify=tk.CENTER,
        ).pack(pady=(0, 14))

        ttk.Button(frame, text=tr("about.close"), command=self.window.destroy).pack()


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
        tk.Label(body, text=icon_text, fg=color, font=ui_font(24)).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Label(body, text=message, wraplength=360, justify=tk.LEFT).pack(
            side=tk.LEFT
        )

        self.ok_button = ttk.Button(
            frame, text=tr("dialog.ok"), command=self.window.destroy, width=10
        )
        self.ok_button.pack(pady=(16, 0))

        center_over_parent(window=self.window, parent=parent)

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
