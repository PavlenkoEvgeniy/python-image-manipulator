"""Tkinter main window for Image Manipulator."""

import contextlib
import logging
import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, filedialog, messagebox

from PIL import Image, ImageTk

from . import __version__
from .config import config, get_app_dir
from .debounce import Debouncer
from .dialogs import AboutDialog, MessageDialogs, UpdateDialog
from .font_selector import FontFamilySelector
from .i18n import (
    LANGUAGES,
    canonical_enum,
    detect_system_language,
    get_language,
    language_info,
    set_language,
    tr,
    translate_enum,
    validate_language,
)
from .pipeline import ImageManipulator, load_image
from .positioning import center_on_screen
from .resize import OutputFormat
from .settings_snapshot import SettingsSnapshot
from .settings_store import clear_settings, load_settings, save_settings
from .text_overlay import TextOverlay
from .ui_events import (
    CompleteEvent,
    PreviewEvent,
    StatusEvent,
    UpdateEvent,
    WorkerEvent,
)
from .uifonts import apply_ui_family
from .update_checker import check_for_update

logger = logging.getLogger(__name__)

try:
    from tkinterdnd2 import DND_FILES

    HAS_DND = True
except ImportError:  # pragma: no cover - depends on the environment
    HAS_DND = False
    logger.warning(
        "tkinterdnd2 not installed. Drag & drop disabled. "
        "Install with: pip install tkinterdnd2"
    )


class ManipulatorApp:
    """Main application window: load images, configure, preview, process."""

    def __init__(self, root: tk.Tk) -> None:
        """Initialize the application.

        Args:
            root: Tkinter root window.
        """
        self.root = root
        self.app_dir = get_app_dir()

        # Translation must be active before the first widget or dialog is built.
        saved_settings = load_settings()
        language = (
            validate_language(saved_settings.get("language"))
            if saved_settings
            else detect_system_language()
        )
        set_language(language)
        apply_ui_family(self.root, language_info(language).preferred_fonts)

        # State
        self.image_paths: list[str] = []
        self.current_index: int = -1
        self.original_image: Image.Image | None = None
        self.font_path: str | None = None
        self._preview_generation = 0
        self._preview_debouncer = Debouncer(
            self.root, config.preview_debounce_ms, self._refresh_preview
        )
        self._save_debouncer = Debouncer(
            self.root,
            config.settings_save_debounce_ms,
            self._save_settings_now,
        )
        self._processing = False
        self._cancel_event = threading.Event()
        self._applying_preset = False
        self._resetting = False
        self._update_check_running = False
        self._events: queue.Queue[WorkerEvent] = queue.Queue()
        self._window_icon: ImageTk.PhotoImage | None = None
        self._font_families_cache: list[str] | None = None

        self._setup_window()
        self._set_window_icon()
        self._create_vars()
        self._create_widgets()

        # Restore Saved settings, then start reacting to future changes.
        self._apply_saved_settings(saved_settings)
        self._bind_live_updates()
        self._setup_dnd()

        self._poll_events()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        center_on_screen(self.root, config.window_width, config.window_height)
        self.root.after(config.update_check_startup_delay_ms, self._maybe_check_updates)

        logger.info("UI initialized")

    # --- Construction ---

    def _setup_window(self) -> None:
        """Configure the main window."""
        self.root.title(f"{config.name} v{config.version}")
        self.root.geometry(f"{config.window_width}x{config.window_height}")
        self.root.minsize(920, 680)

    def _set_window_icon(self) -> None:
        """Set the window and taskbar icon from the bundled PNG."""
        try:
            from .icon import load_icon_image

            photo = ImageTk.PhotoImage(load_icon_image())
            self._window_icon = photo
            self.root.iconphoto(True, photo)  # type: ignore[arg-type]
        except Exception as e:
            logger.warning(f"Could not set the window icon: {e}")

    def _create_vars(self) -> None:
        """Create Tk variables with default values."""
        # Resize settings
        self.width_var = tk.StringVar(value=str(config.default_width))
        self.height_var = tk.StringVar(value=str(config.default_height))
        self.preset_var = tk.StringVar(value=tr("resize.custom"))
        self.maintain_aspect_var = tk.BooleanVar(
            value=config.default_maintain_aspect_ratio
        )
        self.add_dimensions_var = tk.BooleanVar(
            value=config.default_add_dimensions_to_filename
        )
        self.rotate_portrait_var = tk.BooleanVar(
            value=config.default_rotate_portrait_to_landscape
        )
        self.output_format_var = tk.StringVar(value=config.default_output_format)
        self.jpeg_quality_var = tk.StringVar(value=str(config.default_jpeg_quality))

        # Text settings
        self.text_var = tk.StringVar(value=config.default_text)
        self.text_color = config.default_color
        self.position_var = tk.StringVar(
            value=translate_enum("position", config.default_position)
        )
        self.offset_up_var = tk.StringVar(value=str(config.default_offset_up))
        self.offset_left_var = tk.StringVar(value=str(config.default_offset_left))
        self.font_family_var = tk.StringVar(value=config.default_font_family)
        self.font_style_var = tk.StringVar(
            value=translate_enum("font_style", config.default_font_style)
        )
        self.font_size_var = tk.StringVar(value=str(config.default_font_size))

        # Output
        self.output_dir_var = tk.StringVar(value=self._default_output_dir())
        self.overwrite_var = tk.BooleanVar(value=False)

        # Interface
        self.language_var = tk.StringVar(value=get_language())
        self.check_updates_var = tk.BooleanVar(value=config.default_check_updates)

        # Display
        self.current_name_var = tk.StringVar(value=tr("preview.no_image"))
        self.output_size_var = tk.StringVar(value=tr("preview.output_size_empty"))
        self.status_var = tk.StringVar(value=tr("status.ready"))

    def _create_toolbar(self) -> None:
        """Create the compact top toolbar instead of a slow native menubar."""
        toolbar = tk.Frame(self.root, bd=1, relief=tk.GROOVE, padx=6, pady=4)
        toolbar.pack(fill=tk.X)

        language_button = tk.Menubutton(
            toolbar,
            text=tr("menu.file.language"),
            relief=tk.RAISED,
            padx=6,
        )
        language_menu = tk.Menu(language_button, tearoff=0)
        for language in LANGUAGES:
            language_menu.add_radiobutton(
                label=language.native_name,
                variable=self.language_var,
                value=language.code,
                command=self._on_language_selected,
            )
        language_button.config(menu=language_menu)
        language_button.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            toolbar,
            text=tr("menu.file.reset_settings"),
            command=self.reset_settings,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            toolbar,
            text=tr("menu.help.check_updates"),
            command=self.check_updates_now,
        ).pack(side=tk.LEFT, padx=4)
        tk.Checkbutton(
            toolbar,
            text=tr("menu.help.check_updates_auto"),
            variable=self.check_updates_var,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            toolbar,
            text=tr("menu.help.about"),
            command=self.show_about,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            toolbar,
            text=tr("menu.file.exit"),
            command=self._on_close,
        ).pack(side=tk.LEFT, padx=4)

    def _on_language_selected(self) -> None:
        """Save the chosen language; it applies after the next restart."""
        self._schedule_settings_save()
        MessageDialogs.show_info(
            tr("menu.file.language.restart_title"),
            tr("menu.file.language.restart_message"),
            parent=self.root,
        )

    def _create_widgets(self) -> None:
        """Create all UI widgets."""
        self._create_toolbar()
        main = tk.Frame(self.root, padx=10, pady=10)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)

        self._create_load_section(main)
        self._create_settings_section(main)
        self._create_preview_section(main)
        self._create_output_section(main)
        self._create_action_section(main)

    def _create_load_section(self, parent: tk.Frame) -> None:
        """Create the image list and buttons."""
        frame = tk.LabelFrame(parent, text=tr("section.images"), padx=8, pady=8)
        frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        frame.columnconfigure(3, weight=1)

        tk.Button(
            frame, text=tr("menu.file.add_images"), command=self.load_images
        ).grid(row=0, column=0, padx=(0, 5))
        tk.Button(
            frame, text=tr("menu.file.remove_selected"), command=self.remove_selected
        ).grid(row=0, column=1, padx=5)
        tk.Button(
            frame, text=tr("menu.file.clear_list"), command=self.clear_images
        ).grid(row=0, column=2, padx=5)

        hint = tr("hint.drag_drop") if HAS_DND else tr("hint.no_drag_drop")
        tk.Label(frame, text=hint, foreground="#666666").grid(
            row=0, column=3, sticky="w", padx=(12, 0)
        )

        list_frame = tk.Frame(frame)
        list_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        list_frame.columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(
            list_frame, height=4, selectmode=tk.EXTENDED, activestyle="dotbox"
        )
        self.file_listbox.grid(row=0, column=0, sticky="ew")
        self.file_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        scrollbar = tk.Scrollbar(
            list_frame, orient="vertical", command=self.file_listbox.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_listbox.config(yscrollcommand=scrollbar.set)

    def _create_settings_section(self, parent: tk.Frame) -> None:
        """Create the Resize / Text settings area with lightweight tabs."""
        section = tk.Frame(parent)
        section.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        section.columnconfigure(0, weight=1)
        section.rowconfigure(1, weight=1)

        tab_bar = tk.Frame(section)
        tab_bar.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.tab_var = tk.StringVar(value="resize")
        for value, label_key in (("resize", "tab.resize"), ("text", "tab.text")):
            tk.Radiobutton(
                tab_bar,
                text=tr(label_key),
                variable=self.tab_var,
                value=value,
                indicatoron=False,
                width=12,
                command=self._show_tab,
            ).pack(side=tk.LEFT, padx=2)

        self.resize_tab = tk.Frame(section, padx=10, pady=10)
        self.text_tab = tk.Frame(section, padx=10, pady=10)
        self.resize_tab.grid(row=1, column=0, sticky="nsew")
        self.text_tab.grid(row=1, column=0, sticky="nsew")

        self._create_resize_tab(self.resize_tab)
        self._create_text_tab(self.text_tab)
        self._show_tab()

    def _show_tab(self) -> None:
        """Raise the selected settings tab."""
        tab = self.resize_tab if self.tab_var.get() == "resize" else self.text_tab
        tab.tkraise()

    def _create_resize_tab(self, tab: tk.Frame) -> None:
        """Create the resizing controls."""
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(3, weight=1)

        tk.Label(tab, text=tr("resize.width")).grid(row=0, column=0, sticky="w", pady=5)
        tk.Spinbox(
            tab,
            from_=config.min_dimension,
            to=config.max_dimension,
            textvariable=self.width_var,
            width=12,
        ).grid(row=0, column=1, sticky="w", padx=5, pady=5)

        tk.Label(tab, text=tr("resize.height")).grid(
            row=0, column=2, sticky="w", padx=(16, 0), pady=5
        )
        tk.Spinbox(
            tab,
            from_=config.min_dimension,
            to=config.max_dimension,
            textvariable=self.height_var,
            width=12,
        ).grid(row=0, column=3, sticky="w", padx=5, pady=5)

        tk.Label(tab, text=tr("resize.preset")).grid(
            row=1, column=0, sticky="w", pady=5
        )
        preset_names = [
            tr("resize.custom") if name == "Custom" else name
            for name, _, _ in config.presets
        ]
        preset_frame = tk.Frame(tab)
        for name in preset_names:
            tk.Radiobutton(
                preset_frame,
                text=name,
                variable=self.preset_var,
                value=name,
                command=self._on_preset_selected,
            ).pack(side=tk.LEFT, padx=2)
        preset_frame.grid(row=1, column=1, columnspan=3, sticky="w", padx=5)

        tk.Checkbutton(
            tab,
            text=tr("resize.maintain_aspect"),
            variable=self.maintain_aspect_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=5)

        tk.Checkbutton(
            tab,
            text=tr("resize.add_size"),
            variable=self.add_dimensions_var,
        ).grid(row=2, column=2, columnspan=2, sticky="w", pady=5)

        tk.Checkbutton(
            tab,
            text=tr("resize.rotate_portrait"),
            variable=self.rotate_portrait_var,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=5)

        tk.Frame(tab, height=2, bd=1, relief=tk.SUNKEN).grid(
            row=4, column=0, columnspan=4, sticky="ew", pady=10
        )

        tk.Label(
            tab,
            text=tr("resize.hint"),
            foreground="#666666",
            justify="left",
        ).grid(row=5, column=0, columnspan=4, sticky="w")

    def _create_text_tab(self, tab: tk.Frame) -> None:
        """Create the text overlay controls."""
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(3, weight=1)

        tk.Label(tab, text=tr("text.label")).grid(row=0, column=0, sticky="w", pady=5)
        tk.Entry(tab, textvariable=self.text_var).grid(
            row=0, column=1, columnspan=3, sticky="ew", padx=5, pady=5
        )

        tk.Label(tab, text=tr("text.color")).grid(row=1, column=0, sticky="w", pady=5)
        self.color_preview = tk.Label(
            tab,
            bg=self.text_color,
            width=5,
            height=1,
            relief=tk.RIDGE,
            bd=2,
        )
        self.color_preview.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        tk.Button(tab, text=tr("text.choose_color"), command=self.choose_color).grid(
            row=1, column=2, columnspan=2, sticky="w", pady=5
        )

        tk.Label(tab, text=tr("text.position")).grid(
            row=2, column=0, sticky="w", pady=5
        )
        position_frame = tk.Frame(tab)
        for value in config.text_positions:
            label = translate_enum("position", value)
            tk.Radiobutton(
                position_frame,
                text=label,
                variable=self.position_var,
                value=label,
            ).pack(side=tk.LEFT, padx=2)
        position_frame.grid(row=2, column=1, columnspan=3, sticky="w", padx=5)

        tk.Label(tab, text=tr("text.font_style")).grid(
            row=3, column=0, sticky="w", pady=5
        )
        style_frame = tk.Frame(tab)
        for value in config.font_styles:
            label = translate_enum("font_style", value)
            tk.Radiobutton(
                style_frame,
                text=label,
                variable=self.font_style_var,
                value=label,
            ).pack(side=tk.LEFT, padx=2)
        style_frame.grid(row=3, column=1, columnspan=3, sticky="w", padx=5)

        tk.Label(tab, text=tr("text.offset_up")).grid(
            row=4, column=0, sticky="w", pady=5
        )
        tk.Entry(tab, textvariable=self.offset_up_var, width=12).grid(
            row=4, column=1, sticky="w", padx=5, pady=5
        )

        tk.Label(tab, text=tr("text.offset_left")).grid(
            row=4, column=2, sticky="w", padx=(16, 0), pady=5
        )
        tk.Entry(tab, textvariable=self.offset_left_var, width=12).grid(
            row=4, column=3, sticky="w", padx=5, pady=5
        )

        tk.Label(tab, text=tr("text.font")).grid(row=5, column=0, sticky="w", pady=5)
        self.font_family_combo = FontFamilySelector(
            tab,
            self.font_family_var,
            self._system_font_families,
        )
        self.font_family_combo.grid(row=5, column=1, sticky="ew", padx=5, pady=5)

        tk.Label(tab, text=tr("text.font_size")).grid(
            row=5, column=2, sticky="w", padx=(16, 0), pady=5
        )
        tk.Spinbox(
            tab,
            from_=config.min_font_size,
            to=config.max_font_size,
            textvariable=self.font_size_var,
            width=12,
        ).grid(row=5, column=3, sticky="w", padx=5, pady=5)

        tk.Label(tab, text=tr("text.font_file")).grid(
            row=6, column=0, sticky="w", pady=5
        )
        self.font_file_label = tk.Label(tab, text=tr("text.system_default"), width=22)
        self.font_file_label.grid(row=6, column=1, sticky="w", padx=5, pady=5)
        tk.Button(tab, text=tr("text.select_font"), command=self.choose_font).grid(
            row=6, column=2, sticky="w", padx=(16, 0), pady=5
        )
        tk.Button(
            tab, text=tr("text.use_system_font"), command=self.use_system_font
        ).grid(row=6, column=3, sticky="w", padx=5, pady=5)

        tk.Label(
            tab,
            text=tr("text.hint"),
            foreground="#666666",
        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def _create_preview_section(self, parent: tk.Frame) -> None:
        """Create the preview panel."""
        frame = tk.LabelFrame(parent, text=tr("section.preview"), padx=8, pady=8)
        frame.grid(row=1, column=1, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(
            frame,
            bg="#3a3a3a",
            highlightthickness=0,
            width=460,
            height=340,
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")

        tk.Label(frame, textvariable=self.current_name_var, anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )
        tk.Label(frame, textvariable=self.output_size_var, anchor="w").grid(
            row=2, column=0, sticky="ew"
        )

    def _create_output_section(self, parent: tk.Frame) -> None:
        """Create output folder and format controls."""
        frame = tk.LabelFrame(parent, text=tr("section.output"), padx=8, pady=8)
        frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        frame.columnconfigure(1, weight=1)

        tk.Label(frame, text=tr("output.folder")).grid(row=0, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.output_dir_var).grid(
            row=0, column=1, sticky="ew", padx=5
        )
        tk.Button(frame, text=tr("output.browse"), command=self.browse_output_dir).grid(
            row=0, column=2, padx=(5, 0)
        )

        options = tk.Frame(frame)
        options.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        tk.Label(options, text=tr("output.format")).pack(side=tk.LEFT)
        format_frame = tk.Frame(options)
        for value in config.output_formats:
            tk.Radiobutton(
                format_frame,
                text=value,
                variable=self.output_format_var,
                value=value,
            ).pack(side=tk.LEFT, padx=2)
        format_frame.pack(side=tk.LEFT, padx=(5, 20))

        tk.Label(options, text=tr("output.quality")).pack(side=tk.LEFT)
        tk.Spinbox(
            options,
            from_=config.min_jpeg_quality,
            to=config.max_jpeg_quality,
            textvariable=self.jpeg_quality_var,
            width=6,
        ).pack(side=tk.LEFT, padx=(5, 20))

        tk.Checkbutton(
            options,
            text=tr("output.overwrite"),
            variable=self.overwrite_var,
        ).pack(side=tk.LEFT)

    def _create_action_section(self, parent: tk.Frame) -> None:
        """Create action buttons and the status bar."""
        actions = tk.Frame(parent)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.process_button = tk.Button(
            actions,
            text=tr("action.process_all"),
            command=self.start_processing,
            width=20,
        )
        self.process_button.pack(side=tk.LEFT, padx=(0, 5))

        tk.Button(
            actions, text=tr("action.refresh_preview"), command=self._refresh_preview
        ).pack(side=tk.LEFT, padx=5)

        tk.Label(
            actions,
            text=tr("action.hint"),
            foreground="#666666",
        ).pack(side=tk.LEFT, padx=(16, 0))

        tk.Label(
            parent,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor="w",
            padx=6,
            pady=3,
        ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    # --- Bindings ---

    def _bind_live_updates(self) -> None:
        """Schedule preview and autosave when any setting changes."""
        for var in (
            self.maintain_aspect_var,
            self.add_dimensions_var,
            self.rotate_portrait_var,
            self.output_format_var,
            self.jpeg_quality_var,
            self.text_var,
            self.position_var,
            self.offset_up_var,
            self.offset_left_var,
            self.font_family_var,
            self.font_style_var,
            self.font_size_var,
            self.output_dir_var,
            self.overwrite_var,
            self.language_var,
            self.check_updates_var,
        ):
            var.trace_add("write", self._on_setting_changed)

        self.width_var.trace_add("write", self._on_dimension_changed)
        self.height_var.trace_add("write", self._on_dimension_changed)

    def _on_dimension_changed(self, *_args) -> None:
        """Mark the preset as custom when width or height is edited."""
        if not self._applying_preset:
            self.preset_var.set(tr("resize.custom"))
        self._on_setting_changed()

    def _on_setting_changed(self, *_args) -> None:
        """Refresh the preview and autosave, both debounced."""
        if self._resetting:
            return
        self._schedule_preview()
        self._schedule_settings_save()

    def _on_preset_selected(self, event=None) -> None:
        """Apply a preset resolution."""
        name = self.preset_var.get()
        width, height = config.get_preset_dimensions(name)
        if width <= 0 or height <= 0:
            return
        self._applying_preset = True
        try:
            self.width_var.set(str(width))
            self.height_var.set(str(height))
        finally:
            self._applying_preset = False

    def _setup_dnd(self) -> None:
        """Enable drag & drop when tkinterdnd2 is available."""
        if not HAS_DND:
            return
        for widget in (self.root, self.file_listbox, self.preview_canvas):
            self._enable_dnd(widget)

    def _enable_dnd(self, widget) -> None:
        """Enable drop handling on one widget without breaking the others."""
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
        except Exception as e:
            logger.warning(f"Could not enable drag & drop on {widget}: {e}")

    # --- Preview ---

    def _schedule_preview(self) -> None:
        """Schedule a debounced preview refresh."""
        self._preview_generation += 1
        self._preview_debouncer.schedule()

    def _cancel_scheduled_preview(self) -> None:
        """Cancel a pending preview refresh, if any."""
        self._preview_debouncer.cancel()

    def _refresh_preview(self) -> None:
        """Start rendering the current settings in a background thread."""
        self._preview_generation += 1
        generation = self._preview_generation

        if self.original_image is None:
            self.output_size_var.set(tr("preview.output_size_empty"))
            return

        # Building the manipulator reads Tk variables, so it must happen on
        # the UI thread. Rendering itself is pure Pillow work and is moved off
        # the UI thread to keep large images from freezing the window.
        try:
            manipulator = self._build_manipulator()
        except Exception as exc:
            logger.exception("Preview failed")
            self.status_var.set(tr("status.preview_failed", error=exc))
            return
        image = self.original_image
        threading.Thread(
            target=self._preview_worker,
            args=(generation, manipulator, image),
            daemon=True,
        ).start()

    def _preview_worker(
        self,
        generation: int,
        manipulator: ImageManipulator,
        image: Image.Image,
    ) -> None:
        """Render a preview off the UI thread and report through the queue."""
        try:
            rendered = manipulator.render(image)
        except Exception as exc:
            logger.exception("Preview failed")
            self._events.put(PreviewEvent(generation, None, exc))
            return
        self._events.put(PreviewEvent(generation, rendered, None))

    def _on_preview_ready(self, generation: int, rendered, error) -> None:
        """Show a preview result unless a newer request superseded it."""
        if generation != self._preview_generation:
            return
        if error is not None:
            self.status_var.set(tr("status.preview_failed", error=error))
            return
        if rendered is None:
            return
        self.output_size_var.set(
            tr("preview.output_size", width=rendered.width, height=rendered.height)
        )
        self._show_image(rendered)

    def _show_image(self, image: Image.Image) -> None:
        """Fit an image into the preview canvas."""
        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width, canvas_height = 460, 340

        thumbnail = image.copy()
        thumbnail.thumbnail(
            (max(1, canvas_width - 12), max(1, canvas_height - 12)),
            Image.Resampling.LANCZOS,
        )
        photo = ImageTk.PhotoImage(thumbnail)

        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=photo,
            anchor=tk.CENTER,
        )
        # Keep a reference so Tk does not garbage-collect the image.
        self.preview_canvas.image = photo  # type: ignore[attr-defined]

    # --- Image list ---

    def load_images(self) -> None:
        """Open a file dialog and add the selected images."""
        patterns = " ".join("*" + ext for ext in config.valid_extensions)
        paths = filedialog.askopenfilenames(
            title=tr("dialog.select_images"),
            filetypes=[
                (tr("dialog.filter_images"), patterns),
                (tr("dialog.filter_all"), "*.*"),
            ],
        )
        if paths:
            self._add_files(paths)

    def _add_files(self, files) -> None:
        """Add supported image files to the list."""
        added = 0
        for file_path in files:
            path = os.path.abspath(file_path)
            if not os.path.isfile(path):
                continue
            if not path.lower().endswith(config.valid_extensions):
                continue
            if path in self.image_paths:
                continue
            self.image_paths.append(path)
            self.file_listbox.insert(tk.END, os.path.basename(path))
            added += 1

        if not added:
            MessageDialogs.show_warning(
                tr("dialog.no_images.title"),
                tr("dialog.no_images.message"),
                parent=self.root,
            )
            return

        self.status_var.set(tr("status.added", count=added))
        if self.current_index < 0 and self.image_paths:
            self._select_index(len(self.image_paths) - added)

    def _on_drop(self, event) -> None:
        """Handle files dropped onto the window."""
        files = self.root.tk.splitlist(event.data)
        self._add_files(files)

    def _on_listbox_select(self, event=None) -> None:
        """Load the image selected in the list."""
        selection = self.file_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index == self.current_index and self.original_image is not None:
            return
        self.current_index = index
        self._load_current_image()

    def _select_index(self, index: int) -> None:
        """Programmatically select and load an image list entry."""
        if not (0 <= index < len(self.image_paths)):
            return
        self.current_index = index
        self.file_listbox.selection_clear(0, tk.END)
        self.file_listbox.selection_set(index)
        self.file_listbox.activate(index)
        self._load_current_image()

    def _load_current_image(self) -> None:
        """Load the image at the current index into memory and preview it."""
        if not (0 <= self.current_index < len(self.image_paths)):
            return
        path = self.image_paths[self.current_index]
        try:
            self.original_image, _ = load_image(path)
        except Exception as e:
            logger.error(f"Failed to load {path}: {e}")
            MessageDialogs.show_error(
                tr("dialog.cannot_load.title"),
                tr(
                    "dialog.cannot_load.message",
                    name=os.path.basename(path),
                    error=e,
                ),
                parent=self.root,
            )
            return

        self.current_name_var.set(os.path.basename(path))
        self._refresh_preview()

    def remove_selected(self) -> None:
        """Remove the selected images from the list."""
        selected = list(self.file_listbox.curselection())
        if not selected:
            return
        for index in reversed(selected):
            self.file_listbox.delete(index)
            del self.image_paths[index]

        self._clear_current_view()
        if self.image_paths:
            self._select_index(min(selected[0], len(self.image_paths) - 1))

    def clear_images(self) -> None:
        """Remove every image from the list."""
        self.image_paths.clear()
        self.file_listbox.delete(0, tk.END)
        self._clear_current_view()

    def _clear_current_view(self) -> None:
        """Clear the currently loaded image and the preview."""
        self.current_index = -1
        self.original_image = None
        self._preview_generation += 1
        self.current_name_var.set(tr("preview.no_image"))
        self.output_size_var.set(tr("preview.output_size_empty"))
        self.preview_canvas.delete("all")

    # --- Settings persistence ---

    def _schedule_settings_save(self) -> None:
        """Schedule a debounced settings autosave."""
        self._save_debouncer.schedule()

    def _cancel_scheduled_settings_save(self) -> None:
        """Cancel a pending settings autosave, if any."""
        self._save_debouncer.cancel()

    def _save_settings_now(self) -> None:
        """Write the Saved settings to the Settings file immediately."""
        save_settings(self._get_settings_snapshot())

    def _get_settings_snapshot(self) -> dict:
        """Snapshot every persisted setting from the widgets."""
        snapshot = SettingsSnapshot(
            language=validate_language(self.language_var.get()),
            check_updates=bool(self.check_updates_var.get()),
            width=self._int_value(
                self.width_var,
                config.default_width,
                config.min_dimension,
                config.max_dimension,
            ),
            height=self._int_value(
                self.height_var,
                config.default_height,
                config.min_dimension,
                config.max_dimension,
            ),
            maintain_aspect=bool(self.maintain_aspect_var.get()),
            add_dimensions=bool(self.add_dimensions_var.get()),
            rotate_portrait=bool(self.rotate_portrait_var.get()),
            output_format=self.output_format_var.get(),
            jpeg_quality=self._int_value(
                self.jpeg_quality_var,
                config.default_jpeg_quality,
                config.min_jpeg_quality,
                config.max_jpeg_quality,
            ),
            text=self.text_var.get(),
            color=self.text_color,
            font_family=(
                self.font_family_var.get().strip() or config.default_font_family
            ),
            font_path=self.font_path,
            font_size=self._int_value(
                self.font_size_var,
                config.default_font_size,
                config.min_font_size,
                config.max_font_size,
            ),
            font_style=canonical_enum("font_style", self.font_style_var.get()),
            position=canonical_enum("position", self.position_var.get()),
            offset_up=self._int_value(self.offset_up_var, config.default_offset_up, 0),
            offset_left=self._int_value(
                self.offset_left_var, config.default_offset_left, 0
            ),
            output_dir=self.output_dir_var.get().strip(),
            overwrite=bool(self.overwrite_var.get()),
        )
        return snapshot.to_settings()

    def _apply_saved_settings(self, saved: dict | None) -> None:
        """Apply loaded Saved settings to the widgets; ignore None."""
        if not saved:
            return
        self._apply_settings(SettingsSnapshot.from_settings(saved))

    def _apply_settings(self, snapshot: SettingsSnapshot) -> None:
        """Apply one settings snapshot to every widget."""
        self.language_var.set(snapshot.language)
        self.check_updates_var.set(snapshot.check_updates)
        self.width_var.set(str(snapshot.width))
        self.height_var.set(str(snapshot.height))
        self.preset_var.set(tr("resize.custom"))
        self.maintain_aspect_var.set(snapshot.maintain_aspect)
        self.add_dimensions_var.set(snapshot.add_dimensions)
        self.rotate_portrait_var.set(snapshot.rotate_portrait)
        self.output_format_var.set(snapshot.output_format)
        self.jpeg_quality_var.set(str(snapshot.jpeg_quality))

        self.text_var.set(snapshot.text)
        self.text_color = snapshot.color
        self.color_preview.config(bg=self.text_color)
        self.position_var.set(translate_enum("position", snapshot.position))
        self.offset_up_var.set(str(snapshot.offset_up))
        self.offset_left_var.set(str(snapshot.offset_left))
        self.font_family_var.set(snapshot.font_family)
        self.font_style_var.set(translate_enum("font_style", snapshot.font_style))
        self.font_size_var.set(str(snapshot.font_size))

        self.font_path = snapshot.font_path
        if self.font_path and not os.path.exists(self.font_path):
            logger.warning("Saved font file is missing: %s", self.font_path)
            self.font_path = None
        if self.font_path:
            self.font_file_label.config(text=os.path.basename(self.font_path))
            self.font_family_combo.config(state="disabled")
        else:
            self.font_file_label.config(text=tr("text.system_default"))
            self.font_family_combo.config(state="normal")

        self.output_dir_var.set(snapshot.output_dir or self._default_output_dir())
        self.overwrite_var.set(snapshot.overwrite)

    def reset_settings(self) -> None:
        """Return all settings to their defaults after confirmation."""
        if not messagebox.askyesno(
            tr("dialog.reset.title"),
            tr("dialog.reset.message"),
            parent=self.root,
        ):
            return
        self._cancel_scheduled_preview()
        self._cancel_scheduled_settings_save()
        previous_language = get_language()
        self._resetting = True
        try:
            clear_settings()
            self._apply_settings(
                SettingsSnapshot.defaults(language=detect_system_language())
            )
        finally:
            self._resetting = False
        self.status_var.set(tr("status.settings_reset"))
        if self.language_var.get() != previous_language:
            MessageDialogs.show_info(
                tr("menu.file.language.restart_title"),
                tr("menu.file.language.restart_message"),
                parent=self.root,
            )

    # --- Text settings widget handlers ---

    def choose_color(self) -> None:
        """Open the color picker."""
        color = colorchooser.askcolor(
            color=self.text_color,
            title=tr("dialog.select_text_color"),
            parent=self.root,
        )
        if color[1]:
            self.text_color = color[1]
            self.color_preview.config(bg=self.text_color)
            self._on_setting_changed()

    def choose_font(self) -> None:
        """Pick a custom .ttf/.otf font file."""
        patterns = " ".join("*" + ext for ext in config.font_extensions)
        path = filedialog.askopenfilename(
            title=tr("dialog.select_font_file"),
            filetypes=[(tr("dialog.filter_fonts"), patterns)],
        )
        if not path:
            return
        self.font_path = path
        self.font_file_label.config(text=os.path.basename(path))
        self.font_family_combo.config(state="disabled")
        self._on_setting_changed()

    def use_system_font(self) -> None:
        """Drop the custom font file and use the selected family again."""
        self.font_path = None
        self.font_file_label.config(text=tr("text.system_default"))
        self.font_family_combo.config(state="normal")
        self._on_setting_changed()

    def _system_font_families(self) -> list:
        """List installed font families, sorted alphabetically and cached."""
        if self._font_families_cache is not None:
            return list(self._font_families_cache)
        try:
            families = sorted(tkfont.families(root=self.root))
        except tk.TclError as e:
            logger.warning(f"Failed to enumerate system fonts: {e}")
            families = []
        self._font_families_cache = families
        return list(families)

    def _refresh_font_families(self) -> None:
        """Refresh the family dropdown each time it opens."""
        self.font_family_combo["values"] = self._system_font_families()

    def browse_output_dir(self) -> None:
        """Pick the output folder, starting in the current destination."""
        current = self.output_dir_var.get().strip()
        initial = (
            current
            if current and os.path.isdir(current)
            else self._default_output_dir()
        )
        folder = filedialog.askdirectory(
            title=tr("dialog.select_output_folder"), initialdir=initial
        )
        if folder:
            self.output_dir_var.set(folder)

    # --- Processing ---

    def start_processing(self) -> None:
        """Process every loaded image in a background thread."""
        if self._processing:
            return
        if not self.image_paths:
            MessageDialogs.show_warning(
                tr("dialog.no_images.title"),
                tr("dialog.no_images_for_processing.message"),
                parent=self.root,
            )
            return

        manipulator = self._build_manipulator()
        overwrite = bool(self.overwrite_var.get())
        if overwrite and not messagebox.askyesno(
            tr("dialog.overwrite.title"),
            tr("dialog.overwrite.message", count=len(self.image_paths)),
            parent=self.root,
        ):
            return

        output_dir = self.output_dir_var.get().strip() or self._default_output_dir()
        paths = list(self.image_paths)

        self._processing = True
        self._cancel_event.clear()
        self.process_button.config(state="disabled")
        self.status_var.set(tr("status.processing"))

        threading.Thread(
            target=self._process_worker,
            args=(paths, manipulator, output_dir, overwrite),
            daemon=True,
        ).start()

    def _process_worker(
        self,
        paths: list[str],
        manipulator: ImageManipulator,
        output_dir: str,
        overwrite: bool,
    ) -> None:
        """Process images off the UI thread and report through the queue."""
        total = len(paths)
        success = 0
        errors = []

        try:
            for index, path in enumerate(paths, start=1):
                if self._cancel_event.is_set():
                    break
                self._events.put(
                    StatusEvent(
                        tr(
                            "status.processing_item",
                            index=index,
                            total=total,
                            name=os.path.basename(path),
                        )
                    )
                )
                result = manipulator.process_path(path, output_dir, overwrite=overwrite)
                if result.success:
                    success += 1
                elif result.error:
                    errors.append(result.error)
        except Exception as exc:
            # The UI waits for the completion event to unlock the controls;
            # never leave it hanging, whatever went wrong in the loop. Report
            # the failure in the error list so the completion dialog cannot
            # claim success when files were skipped.
            logger.exception("Batch worker stopped early")
            errors.append(tr("status.batch_failed", error=exc))
        finally:
            self._events.put(
                CompleteEvent(success, total, errors, output_dir, overwrite)
            )

    def _poll_events(self) -> None:
        """Apply worker events on the UI thread.

        Each event is dispatched under its own guard and the next tick is
        always rescheduled: an exception escaping this loop used to stop it
        forever, which froze the status bar and left the Process All button
        disabled after a batch run.
        """
        try:
            self._drain_events()
        except Exception:
            logger.exception("Event polling failed")
        with contextlib.suppress(RuntimeError, tk.TclError):
            self.root.after(100, self._poll_events)
        # If after() raised, the window is gone and polling stops with it.

    def _drain_events(self) -> None:
        """Apply every queued event; one bad event must not block the rest."""
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                return
            try:
                self._dispatch_event(event)
            except Exception:
                logger.exception("Failed to apply event %r", event)

    def _dispatch_event(self, event: WorkerEvent) -> None:
        """Apply a single worker/UI event on the UI thread."""
        if isinstance(event, StatusEvent):
            self.status_var.set(event.text)
        elif isinstance(event, CompleteEvent):
            self._on_processing_complete(
                event.success,
                event.total,
                event.errors,
                event.output_dir,
                event.overwrite,
            )
        elif isinstance(event, PreviewEvent):
            self._on_preview_ready(event.generation, event.image, event.error)
        elif isinstance(event, UpdateEvent):
            self._on_update_result(event.manual, event.info, event.error)

    def _on_processing_complete(
        self,
        success: int,
        total: int,
        errors: list[str],
        output_dir: str,
        overwrite: bool,
    ) -> None:
        """Re-enable controls and summarize the batch result."""
        self._processing = False
        self.process_button.config(state="normal")

        if not errors:
            self.status_var.set(tr("status.done", success=success, total=total))
            destination = tr("dialog.complete.originals") if overwrite else output_dir
            MessageDialogs.show_info(
                tr("dialog.complete.title"),
                tr(
                    "dialog.complete.message",
                    count=success,
                    destination=destination,
                ),
                parent=self.root,
            )
            return

        self.status_var.set(
            tr(
                "status.partial",
                success=success,
                total=total,
                failed=len(errors),
            )
        )
        summary = "\n".join(errors[:3])
        if len(errors) > 3:
            summary += "\n" + tr("dialog.errors.more", count=len(errors) - 3)
        MessageDialogs.show_warning(
            tr("dialog.errors.title"),
            tr(
                "dialog.errors.message",
                success=success,
                total=total,
                summary=summary,
            ),
            parent=self.root,
        )

    def _build_manipulator(self) -> ImageManipulator:
        """Build a pipeline instance from the current widget values."""
        text_overlay = TextOverlay(
            text=self.text_var.get(),
            color=self.text_color,
            font_family=self.font_family_var.get().strip() or None,
            font_path=self.font_path,
            font_size=self._int_value(
                self.font_size_var,
                config.default_font_size,
                config.min_font_size,
                config.max_font_size,
            ),
            font_style=canonical_enum("font_style", self.font_style_var.get()),
            position=canonical_enum("position", self.position_var.get()),
            offset_up=self._int_value(self.offset_up_var, config.default_offset_up, 0),
            offset_left=self._int_value(
                self.offset_left_var, config.default_offset_left, 0
            ),
        )

        return ImageManipulator(
            target_width=self._int_value(
                self.width_var,
                config.default_width,
                config.min_dimension,
                config.max_dimension,
            ),
            target_height=self._int_value(
                self.height_var,
                config.default_height,
                config.min_dimension,
                config.max_dimension,
            ),
            maintain_aspect=bool(self.maintain_aspect_var.get()),
            rotate_portrait_to_landscape=bool(self.rotate_portrait_var.get()),
            output_format=OutputFormat.from_name(self.output_format_var.get()),
            jpeg_quality=self._int_value(
                self.jpeg_quality_var,
                config.default_jpeg_quality,
                config.min_jpeg_quality,
                config.max_jpeg_quality,
            ),
            add_dimensions_to_filename=bool(self.add_dimensions_var.get()),
            text_overlay=text_overlay,
        )

    # --- Helpers ---

    @staticmethod
    def _int_value(
        var: tk.Variable,
        default: int,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        """Read an integer from a Tk variable, falling back to a default."""
        try:
            value = int(str(var.get()).strip())
        except (TypeError, ValueError):
            value = default
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _default_output_dir(self) -> str:
        """Default output folder: ``processed_images`` on the Desktop."""
        return config.default_output_directory()

    # --- Lifecycle ---

    def _on_close(self) -> None:
        """Flush pending settings and close the window."""
        if self._processing:
            if not messagebox.askyesno(
                tr("dialog.close_running.title"),
                tr("dialog.close_running.message"),
                parent=self.root,
            ):
                return
            self._cancel_event.set()
        self._cancel_scheduled_preview()
        self._cancel_scheduled_settings_save()
        self._save_settings_now()
        self.root.destroy()

    def show_about(self) -> None:
        """Show the About dialog."""
        AboutDialog(self.root)

    # --- Update check ---

    def _maybe_check_updates(self) -> None:
        """Run the automatic check at startup when it is enabled."""
        if not self.check_updates_var.get():
            return
        self._start_update_check(manual=False)

    def check_updates_now(self) -> None:
        """Run an update check requested from the menu."""
        self._start_update_check(manual=True)

    def _start_update_check(self, manual: bool) -> None:
        """Start a background check; manual checks ignore the setting."""
        if self._update_check_running:
            return
        if not manual and not self.check_updates_var.get():
            return
        self._update_check_running = True
        if manual:
            self.status_var.set(tr("status.checking_updates"))
        threading.Thread(
            target=self._update_worker, args=(manual,), daemon=True
        ).start()

    def _update_worker(self, manual: bool) -> None:
        """Query GitHub off the UI thread and report through the queue."""
        try:
            info = check_for_update()
        except Exception as exc:
            logger.info("Update check failed: %s", exc)
            self._events.put(UpdateEvent(manual, None, str(exc)))
            return

        self._events.put(UpdateEvent(manual, info, None))

    def _on_update_result(self, manual: bool, info, error) -> None:
        """Show the result on the UI thread; automatic checks stay quiet."""
        self._update_check_running = False
        checking_text = tr("status.checking_updates")
        if manual and self.status_var.get() == checking_text:
            self.status_var.set(tr("status.ready"))

        if error:
            if manual:
                MessageDialogs.show_warning(
                    tr("dialog.update_failed.title"),
                    tr("dialog.update_failed.message", error=error),
                    parent=self.root,
                )
            return

        if info is not None:
            UpdateDialog(self.root, info)
        elif manual:
            MessageDialogs.show_info(
                tr("dialog.update_latest.title"),
                tr("dialog.update_latest.message", version=__version__),
                parent=self.root,
            )
