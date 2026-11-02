"""Tkinter main window for Image Manipulator."""

import logging
import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

from .config import config, get_app_dir
from .dialogs import AboutDialog, ErrorDialog
from .pipeline import ImageManipulator, load_image
from .positioning import center_on_screen
from .resize import OutputFormat
from .settings_store import clear_settings, load_settings, save_settings
from .text_overlay import TextOverlay

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

        # State
        self.image_paths: list[str] = []
        self.current_index: int = -1
        self.original_image: Optional[Image.Image] = None
        self.font_path: Optional[str] = None
        self._preview_after_id: Optional[str] = None
        self._save_after_id: Optional[str] = None
        self._processing = False
        self._applying_preset = False
        self._events: queue.Queue = queue.Queue()
        self._window_icon = None

        self._setup_window()
        self._set_window_icon()
        self._create_vars()
        self._create_menu()
        self._create_widgets()

        # Restore Saved settings, then start reacting to future changes.
        self._apply_saved_settings(load_settings())
        self._bind_live_updates()
        self._setup_dnd()

        self._poll_events()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        center_on_screen(self.root, config.window_width, config.window_height)

        logger.info("UI initialized")

    # --- Construction ---

    def _setup_window(self) -> None:
        """Configure the main window."""
        self.root.title(config.name)
        self.root.geometry(f"{config.window_width}x{config.window_height}")
        self.root.minsize(920, 680)

    def _set_window_icon(self) -> None:
        """Set the window and taskbar icon from the bundled PNG."""
        try:
            from .icon import load_icon_image

            self._window_icon = ImageTk.PhotoImage(load_icon_image())
            self.root.iconphoto(True, self._window_icon)
        except Exception as e:
            logger.warning(f"Could not set the window icon: {e}")

    def _create_vars(self) -> None:
        """Create Tk variables with default values."""
        # Resize settings
        self.width_var = tk.StringVar(value=str(config.default_width))
        self.height_var = tk.StringVar(value=str(config.default_height))
        self.preset_var = tk.StringVar(value="Custom")
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
        self.position_var = tk.StringVar(value=config.default_position)
        self.offset_up_var = tk.StringVar(value=str(config.default_offset_up))
        self.offset_left_var = tk.StringVar(value=str(config.default_offset_left))
        self.font_family_var = tk.StringVar(value=config.default_font_family)
        self.font_style_var = tk.StringVar(value=config.default_font_style)
        self.font_size_var = tk.StringVar(value=str(config.default_font_size))

        # Output
        self.output_dir_var = tk.StringVar(value=self._default_output_dir())
        self.overwrite_var = tk.BooleanVar(value=False)

        # Display
        self.current_name_var = tk.StringVar(value="No image selected")
        self.output_size_var = tk.StringVar(value="Output size: —")
        self.status_var = tk.StringVar(value="Ready")

    def _create_menu(self) -> None:
        """Create the application menu."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Add Images…", command=self.load_images)
        file_menu.add_command(label="Remove Selected", command=self.remove_selected)
        file_menu.add_command(label="Clear List", command=self.clear_images)
        file_menu.add_separator()
        file_menu.add_command(label="Reset Settings", command=self.reset_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    def _create_widgets(self) -> None:
        """Create all UI widgets."""
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)
        self._main_frame = main

        self._create_load_section(main)
        self._create_settings_section(main)
        self._create_preview_section(main)
        self._create_output_section(main)
        self._create_action_section(main)

    def _create_load_section(self, parent: ttk.Frame) -> None:
        """Create the image list and buttons."""
        frame = ttk.LabelFrame(parent, text="Images", padding="8")
        frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        frame.columnconfigure(3, weight=1)

        ttk.Button(frame, text="Add Images…", command=self.load_images).grid(
            row=0, column=0, padx=(0, 5)
        )
        ttk.Button(frame, text="Remove Selected", command=self.remove_selected).grid(
            row=0, column=1, padx=5
        )
        ttk.Button(frame, text="Clear List", command=self.clear_images).grid(
            row=0, column=2, padx=5
        )

        hint = (
            "Drag & drop images anywhere, or use Add Images…"
            if HAS_DND
            else "Use Add Images… to load files (install tkinterdnd2 for drag & drop)"
        )
        ttk.Label(frame, text=hint, foreground="#666666").grid(
            row=0, column=3, sticky="w", padx=(12, 0)
        )

        list_frame = ttk.Frame(frame)
        list_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        list_frame.columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(
            list_frame, height=4, selectmode=tk.EXTENDED, activestyle="dotbox"
        )
        self.file_listbox.grid(row=0, column=0, sticky="ew")
        self.file_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.file_listbox.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_listbox.config(yscrollcommand=scrollbar.set)

    def _create_settings_section(self, parent: ttk.Frame) -> None:
        """Create the Resize / Text settings notebook."""
        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

        resize_tab = ttk.Frame(self.notebook, padding=10)
        text_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(resize_tab, text="Resize")
        self.notebook.add(text_tab, text="Text")

        self._create_resize_tab(resize_tab)
        self._create_text_tab(text_tab)

    def _create_resize_tab(self, tab: ttk.Frame) -> None:
        """Create the resizing controls."""
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(3, weight=1)

        ttk.Label(tab, text="Width (px):").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Spinbox(
            tab,
            from_=config.min_dimension,
            to=config.max_dimension,
            textvariable=self.width_var,
            width=12,
        ).grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(tab, text="Height (px):").grid(
            row=0, column=2, sticky="w", padx=(16, 0), pady=5
        )
        ttk.Spinbox(
            tab,
            from_=config.min_dimension,
            to=config.max_dimension,
            textvariable=self.height_var,
            width=12,
        ).grid(row=0, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(tab, text="Preset:").grid(row=1, column=0, sticky="w", pady=5)
        preset_combo = ttk.Combobox(
            tab,
            textvariable=self.preset_var,
            values=[p[0] for p in config.presets],
            state="readonly",
            width=14,
        )
        preset_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        ttk.Checkbutton(
            tab,
            text="Maintain aspect ratio",
            variable=self.maintain_aspect_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=5)

        ttk.Checkbutton(
            tab,
            text="Add size to filename",
            variable=self.add_dimensions_var,
        ).grid(row=2, column=2, columnspan=2, sticky="w", pady=5)

        ttk.Checkbutton(
            tab,
            text="Rotate portrait images to landscape (90° clockwise)",
            variable=self.rotate_portrait_var,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=5)

        ttk.Separator(tab, orient="horizontal").grid(
            row=4, column=0, columnspan=4, sticky="ew", pady=10
        )

        ttk.Label(
            tab,
            text=(
                "Resizing happens first, then the text is drawn on the\n"
                "result. Font size is measured in output pixels."
            ),
            foreground="#666666",
            justify="left",
        ).grid(row=5, column=0, columnspan=4, sticky="w")

    def _create_text_tab(self, tab: ttk.Frame) -> None:
        """Create the text overlay controls."""
        tab.columnconfigure(1, weight=1)
        tab.columnconfigure(3, weight=1)

        ttk.Label(tab, text="Text:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(tab, textvariable=self.text_var).grid(
            row=0, column=1, columnspan=3, sticky="ew", padx=5, pady=5
        )

        ttk.Label(tab, text="Color:").grid(row=1, column=0, sticky="w", pady=5)
        self.color_preview = tk.Label(
            tab,
            bg=self.text_color,
            width=5,
            height=1,
            relief=tk.RIDGE,
            bd=2,
        )
        self.color_preview.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        ttk.Button(tab, text="Choose color", command=self.choose_color).grid(
            row=1, column=2, columnspan=2, sticky="w", pady=5
        )

        ttk.Label(tab, text="Position:").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Combobox(
            tab,
            textvariable=self.position_var,
            values=list(config.text_positions),
            state="readonly",
            width=16,
        ).grid(row=2, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(tab, text="Font style:").grid(
            row=2, column=2, sticky="w", padx=(16, 0), pady=5
        )
        ttk.Combobox(
            tab,
            textvariable=self.font_style_var,
            values=list(config.font_styles),
            state="readonly",
            width=16,
        ).grid(row=2, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(tab, text="Offset up (px):").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(tab, textvariable=self.offset_up_var, width=12).grid(
            row=3, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(tab, text="Offset left (px):").grid(
            row=3, column=2, sticky="w", padx=(16, 0), pady=5
        )
        ttk.Entry(tab, textvariable=self.offset_left_var, width=12).grid(
            row=3, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(tab, text="Font:").grid(row=4, column=0, sticky="w", pady=5)
        self.font_family_combo = ttk.Combobox(
            tab,
            textvariable=self.font_family_var,
            values=self._system_font_families(),
            width=22,
            postcommand=self._refresh_font_families,
        )
        self.font_family_combo.grid(row=4, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(tab, text="Font size:").grid(
            row=4, column=2, sticky="w", padx=(16, 0), pady=5
        )
        ttk.Spinbox(
            tab,
            from_=config.min_font_size,
            to=config.max_font_size,
            textvariable=self.font_size_var,
            width=12,
        ).grid(row=4, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(tab, text="Font file:").grid(row=5, column=0, sticky="w", pady=5)
        self.font_file_label = ttk.Label(tab, text="System (default)", width=22)
        self.font_file_label.grid(row=5, column=1, sticky="w", padx=5, pady=5)
        ttk.Button(tab, text="Select font", command=self.choose_font).grid(
            row=5, column=2, sticky="w", padx=(16, 0), pady=5
        )
        ttk.Button(tab, text="Use system font", command=self.use_system_font).grid(
            row=5, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(
            tab,
            text="A custom font file takes precedence over the font family.",
            foreground="#666666",
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def _create_preview_section(self, parent: ttk.Frame) -> None:
        """Create the preview panel."""
        frame = ttk.LabelFrame(parent, text="Preview", padding="8")
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

        ttk.Label(frame, textvariable=self.current_name_var, anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )
        ttk.Label(frame, textvariable=self.output_size_var, anchor="w").grid(
            row=2, column=0, sticky="ew"
        )

    def _create_output_section(self, parent: ttk.Frame) -> None:
        """Create output folder and format controls."""
        frame = ttk.LabelFrame(parent, text="Output", padding="8")
        frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.output_dir_var).grid(
            row=0, column=1, sticky="ew", padx=5
        )
        ttk.Button(frame, text="Browse", command=self.browse_output_dir).grid(
            row=0, column=2, padx=(5, 0)
        )

        options = ttk.Frame(frame)
        options.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(options, text="Format:").pack(side=tk.LEFT)
        ttk.Combobox(
            options,
            textvariable=self.output_format_var,
            values=list(config.output_formats),
            state="readonly",
            width=8,
        ).pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(options, text="JPEG/WEBP quality:").pack(side=tk.LEFT)
        ttk.Spinbox(
            options,
            from_=config.min_jpeg_quality,
            to=config.max_jpeg_quality,
            textvariable=self.jpeg_quality_var,
            width=6,
        ).pack(side=tk.LEFT, padx=(5, 20))

        ttk.Checkbutton(
            options,
            text="Overwrite original files",
            variable=self.overwrite_var,
        ).pack(side=tk.LEFT)

    def _create_action_section(self, parent: ttk.Frame) -> None:
        """Create action buttons and the status bar."""
        actions = ttk.Frame(parent)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.process_button = ttk.Button(
            actions, text="Process All", command=self.start_processing, width=20
        )
        self.process_button.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            actions, text="Refresh Preview", command=self._refresh_preview
        ).pack(side=tk.LEFT, padx=5)

        ttk.Label(
            actions,
            text=(
                "Text is applied after resizing; the result is saved with the "
                "chosen format."
            ),
            foreground="#666666",
        ).pack(side=tk.LEFT, padx=(16, 0))

        ttk.Label(
            parent,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor="w",
            padding=(6, 3),
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
        ):
            var.trace_add("write", self._on_setting_changed)

        self.width_var.trace_add("write", self._on_dimension_changed)
        self.height_var.trace_add("write", self._on_dimension_changed)

    def _on_dimension_changed(self, *_args) -> None:
        """Mark the preset as custom when width or height is edited."""
        if not self._applying_preset:
            self.preset_var.set("Custom")
        self._on_setting_changed()

    def _on_setting_changed(self, *_args) -> None:
        """Refresh the preview and autosave, both debounced."""
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
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
            except Exception as e:
                logger.warning(f"Could not enable drag & drop on {widget}: {e}")

    # --- Preview ---

    def _schedule_preview(self) -> None:
        """Schedule a debounced preview refresh."""
        if self._preview_after_id is not None:
            try:
                self.root.after_cancel(self._preview_after_id)
            except Exception:
                pass
        self._preview_after_id = self.root.after(
            config.preview_debounce_ms, self._refresh_preview
        )

    def _cancel_scheduled_preview(self) -> None:
        """Cancel a pending preview refresh, if any."""
        if self._preview_after_id is not None:
            try:
                self.root.after_cancel(self._preview_after_id)
            except Exception:
                pass
            self._preview_after_id = None

    def _refresh_preview(self) -> None:
        """Render the current settings on the current image and show it."""
        self._preview_after_id = None

        if self.original_image is None:
            self.output_size_var.set("Output size: —")
            return

        try:
            rendered = self._build_manipulator().render(self.original_image)
        except Exception as e:
            logger.exception("Preview failed")
            self.status_var.set(f"Preview failed: {e}")
            return

        self.output_size_var.set(
            f"Output size: {rendered.width} × {rendered.height} px"
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
        self.preview_canvas.image = photo

    # --- Image list ---

    def load_images(self) -> None:
        """Open a file dialog and add the selected images."""
        patterns = " ".join("*" + ext for ext in config.valid_extensions)
        paths = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Images", patterns), ("All files", "*.*")],
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
            ErrorDialog.show_warning(
                "No Images",
                "No supported image files were added.",
                parent=self.root,
            )
            return

        self.status_var.set(f"Added {added} image(s)")
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
            ErrorDialog.show_error(
                "Cannot Load Image",
                f"Failed to load {os.path.basename(path)}:\n{e}",
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
        self.current_name_var.set("No image selected")
        self.output_size_var.set("Output size: —")
        self.preview_canvas.delete("all")

    # --- Settings persistence ---

    def _schedule_settings_save(self) -> None:
        """Schedule a debounced settings autosave."""
        if self._save_after_id is not None:
            try:
                self.root.after_cancel(self._save_after_id)
            except Exception:
                pass
        self._save_after_id = self.root.after(
            config.settings_save_debounce_ms, self._save_settings_now
        )

    def _cancel_scheduled_settings_save(self) -> None:
        """Cancel a pending settings autosave, if any."""
        if self._save_after_id is not None:
            try:
                self.root.after_cancel(self._save_after_id)
            except Exception:
                pass
            self._save_after_id = None

    def _save_settings_now(self) -> None:
        """Write the Saved settings to the Settings file immediately."""
        self._save_after_id = None
        save_settings(self._get_settings_snapshot())

    def _get_settings_snapshot(self) -> dict:
        """Snapshot every persisted setting from the widgets."""
        return {
            "width": self._int_value(
                self.width_var, config.default_width,
                config.min_dimension, config.max_dimension,
            ),
            "height": self._int_value(
                self.height_var, config.default_height,
                config.min_dimension, config.max_dimension,
            ),
            "maintain_aspect": bool(self.maintain_aspect_var.get()),
            "add_dimensions": bool(self.add_dimensions_var.get()),
            "rotate_portrait": bool(self.rotate_portrait_var.get()),
            "output_format": self.output_format_var.get(),
            "jpeg_quality": self._int_value(
                self.jpeg_quality_var, config.default_jpeg_quality,
                config.min_jpeg_quality, config.max_jpeg_quality,
            ),
            "text": self.text_var.get(),
            "color": self.text_color,
            "font_family": (
                self.font_family_var.get().strip() or config.default_font_family
            ),
            "font_path": self.font_path,
            "font_size": self._int_value(
                self.font_size_var, config.default_font_size,
                config.min_font_size, config.max_font_size,
            ),
            "font_style": self.font_style_var.get(),
            "position": self.position_var.get(),
            "offset_up": self._int_value(
                self.offset_up_var, config.default_offset_up, 0
            ),
            "offset_left": self._int_value(
                self.offset_left_var, config.default_offset_left, 0
            ),
            "output_dir": self.output_dir_var.get().strip(),
            "overwrite": bool(self.overwrite_var.get()),
        }

    def _apply_saved_settings(self, saved: Optional[dict]) -> None:
        """Apply loaded Saved settings to the widgets; ignore None."""
        if not saved:
            return

        self.width_var.set(str(saved["width"]))
        self.height_var.set(str(saved["height"]))
        self.maintain_aspect_var.set(saved["maintain_aspect"])
        self.add_dimensions_var.set(saved["add_dimensions"])
        self.rotate_portrait_var.set(saved["rotate_portrait"])
        self.output_format_var.set(saved["output_format"])
        self.jpeg_quality_var.set(str(saved["jpeg_quality"]))

        self.text_var.set(saved["text"])
        self.text_color = saved["color"]
        self.color_preview.config(bg=self.text_color)
        self.position_var.set(saved["position"])
        self.offset_up_var.set(str(saved["offset_up"]))
        self.offset_left_var.set(str(saved["offset_left"]))
        self.font_family_var.set(saved["font_family"])
        self.font_style_var.set(saved["font_style"])
        self.font_size_var.set(str(saved["font_size"]))

        self.font_path = saved.get("font_path")
        if self.font_path and not os.path.exists(self.font_path):
            logger.warning(f"Saved font file is missing: {self.font_path}")
            self.font_path = None
        if self.font_path:
            self.font_file_label.config(text=os.path.basename(self.font_path))
            self.font_family_combo.config(state="disabled")
        else:
            self.font_file_label.config(text="System (default)")
            self.font_family_combo.config(state="normal")

        self.output_dir_var.set(saved["output_dir"] or self._default_output_dir())
        self.overwrite_var.set(saved["overwrite"])

    def reset_settings(self) -> None:
        """Return all settings to their defaults after confirmation."""
        if not messagebox.askyesno(
            "Reset Settings",
            "Return all settings to their defaults?\n\n"
            "The saved settings file will be removed.",
            parent=self.root,
        ):
            return
        clear_settings()
        self._reset_settings_widgets()
        self.status_var.set("Settings reset to defaults")

    def _reset_settings_widgets(self) -> None:
        """Reset all setting widgets to their defaults."""
        self.width_var.set(str(config.default_width))
        self.height_var.set(str(config.default_height))
        self.preset_var.set("Custom")
        self.maintain_aspect_var.set(config.default_maintain_aspect_ratio)
        self.add_dimensions_var.set(config.default_add_dimensions_to_filename)
        self.rotate_portrait_var.set(config.default_rotate_portrait_to_landscape)
        self.output_format_var.set(config.default_output_format)
        self.jpeg_quality_var.set(str(config.default_jpeg_quality))

        self.text_var.set(config.default_text)
        self.text_color = config.default_color
        self.color_preview.config(bg=self.text_color)
        self.position_var.set(config.default_position)
        self.offset_up_var.set(str(config.default_offset_up))
        self.offset_left_var.set(str(config.default_offset_left))
        self.font_family_var.set(config.default_font_family)
        self.font_style_var.set(config.default_font_style)
        self.font_size_var.set(str(config.default_font_size))

        self.font_path = None
        self.font_file_label.config(text="System (default)")
        self.font_family_combo.config(state="normal")

        self.output_dir_var.set(self._default_output_dir())
        self.overwrite_var.set(False)

    # --- Text settings widget handlers ---

    def choose_color(self) -> None:
        """Open the color picker."""
        color = colorchooser.askcolor(
            color=self.text_color, title="Select text color", parent=self.root
        )
        if color[1]:
            self.text_color = color[1]
            self.color_preview.config(bg=self.text_color)
            self._on_setting_changed()

    def choose_font(self) -> None:
        """Pick a custom .ttf/.otf font file."""
        path = filedialog.askopenfilename(
            title="Select font file",
            filetypes=[("Fonts", "*.ttf *.otf")],
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
        self.font_file_label.config(text="System (default)")
        self.font_family_combo.config(state="normal")
        self._on_setting_changed()

    def _system_font_families(self) -> list:
        """List installed font families, sorted alphabetically."""
        try:
            return sorted(tkfont.families(root=self.root))
        except tk.TclError as e:
            logger.warning(f"Failed to enumerate system fonts: {e}")
            return []

    def _refresh_font_families(self) -> None:
        """Refresh the family dropdown each time it opens."""
        self.font_family_combo["values"] = self._system_font_families()

    def browse_output_dir(self) -> None:
        """Pick the output folder."""
        folder = filedialog.askdirectory(
            title="Select Output Folder", initialdir=self.app_dir
        )
        if folder:
            self.output_dir_var.set(folder)

    # --- Processing ---

    def start_processing(self) -> None:
        """Process every loaded image in a background thread."""
        if self._processing:
            return
        if not self.image_paths:
            ErrorDialog.show_warning(
                "No Images", "Please add image files first.", parent=self.root
            )
            return

        manipulator = self._build_manipulator()
        overwrite = bool(self.overwrite_var.get())
        if overwrite and not messagebox.askyesno(
            "Overwrite Originals",
            f"This will overwrite {len(self.image_paths)} original file(s).\n"
            "Continue?",
            parent=self.root,
        ):
            return

        output_dir = self.output_dir_var.get().strip() or self._default_output_dir()
        paths = list(self.image_paths)

        self._processing = True
        self.process_button.config(state="disabled")
        self.status_var.set("Processing…")

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

        for index, path in enumerate(paths, start=1):
            self._events.put(
                ("status", f"Processing {index}/{total}: {os.path.basename(path)}")
            )
            result = manipulator.process_path(path, output_dir, overwrite=overwrite)
            if result.success:
                success += 1
            elif result.error:
                errors.append(result.error)

        self._events.put(("complete", success, total, errors, output_dir, overwrite))

    def _poll_events(self) -> None:
        """Apply worker events on the UI thread."""
        try:
            while True:
                event = self._events.get_nowait()
                if event[0] == "status":
                    self.status_var.set(event[1])
                elif event[0] == "complete":
                    self._on_processing_complete(*event[1:])
        except queue.Empty:
            pass

        self.root.after(100, self._poll_events)

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
            self.status_var.set(f"Done: {success} of {total} image(s) processed")
            destination = "the original files" if overwrite else output_dir
            ErrorDialog.show_info(
                "Complete",
                f"Processed {success} image(s).\n\nSaved to: {destination}",
                parent=self.root,
            )
            return

        self.status_var.set(
            f"Processed {success} of {total} image(s); {len(errors)} failed"
        )
        summary = "\n".join(errors[:3])
        if len(errors) > 3:
            summary += f"\n… and {len(errors) - 3} more"
        ErrorDialog.show_warning(
            "Completed with Errors",
            f"Processed {success} of {total} image(s).\n\n{summary}",
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
                self.font_size_var, config.default_font_size,
                config.min_font_size, config.max_font_size,
            ),
            font_style=self.font_style_var.get(),
            position=self.position_var.get(),
            offset_up=self._int_value(
                self.offset_up_var, config.default_offset_up, 0
            ),
            offset_left=self._int_value(
                self.offset_left_var, config.default_offset_left, 0
            ),
        )

        return ImageManipulator(
            target_width=self._int_value(
                self.width_var, config.default_width,
                config.min_dimension, config.max_dimension,
            ),
            target_height=self._int_value(
                self.height_var, config.default_height,
                config.min_dimension, config.max_dimension,
            ),
            maintain_aspect=bool(self.maintain_aspect_var.get()),
            rotate_portrait_to_landscape=bool(self.rotate_portrait_var.get()),
            output_format=OutputFormat.from_name(self.output_format_var.get()),
            jpeg_quality=self._int_value(
                self.jpeg_quality_var, config.default_jpeg_quality,
                config.min_jpeg_quality, config.max_jpeg_quality,
            ),
            add_dimensions_to_filename=bool(self.add_dimensions_var.get()),
            text_overlay=text_overlay,
        )

    # --- Helpers ---

    @staticmethod
    def _int_value(
        var: tk.Variable,
        default: int,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
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
        """Default output folder next to the application."""
        return os.path.join(self.app_dir, config.default_output_dir)

    # --- Lifecycle ---

    def _on_close(self) -> None:
        """Flush pending settings and close the window."""
        self._cancel_scheduled_preview()
        self._cancel_scheduled_settings_save()
        self._save_settings_now()
        self.root.destroy()

    def show_about(self) -> None:
        """Show the About dialog."""
        AboutDialog(self.root)
