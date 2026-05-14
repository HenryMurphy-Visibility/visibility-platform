# color_schemes.py

import tkinter as tk
from tkinter import ttk

# Define themes
themes = {
    "vibrant": {
        "PRIMARY_COLOR": "#004080",
        "SECONDARY_COLOR": "#0066cc",
        "HOVER_COLOR": "#0052a3",
        "BACKGROUND_COLOR": "#e6f2ff",
        "BORDER_COLOR": "#002060",
        "BUTTON_TEXT_COLOR": "white",
    },
    "dark": {
        "PRIMARY_COLOR": "#1E1E1E",
        "SECONDARY_COLOR": "#333333",
        "HOVER_COLOR": "#444444",
        "BACKGROUND_COLOR": "#121212",
        "BORDER_COLOR": "#0D0D0D",
        "BUTTON_TEXT_COLOR": "#E6E6E6",
    },
}

# Initialize default theme
current_theme = themes["vibrant"]

# Store widget references for dynamic updates
widget_refs = {}


def apply_theme_to_widgets():
    """Apply the current theme to all registered widgets."""
    for widget_type, widgets in widget_refs.items():
        for widget in widgets:
            if widget_type == "button":
                widget.configure(bg=current_theme["PRIMARY_COLOR"], fg=current_theme["BUTTON_TEXT_COLOR"])
            elif widget_type == "frame":
                widget.configure(bg=current_theme["BACKGROUND_COLOR"])
            elif widget_type == "label":
                widget.configure(bg=current_theme["PRIMARY_COLOR"], fg=current_theme["BUTTON_TEXT_COLOR"])
            elif widget_type == "treeview":
                widget.tag_configure("oddrow", background=current_theme["SECONDARY_COLOR"])
                widget.tag_configure("evenrow", background=current_theme["BACKGROUND_COLOR"])
            elif widget_type == "toplevel":
                widget.configure(bg=current_theme["BACKGROUND_COLOR"])


def apply_theme(theme_name):
    """Switch the theme dynamically."""
    global current_theme
    if theme_name in themes:
        current_theme = themes[theme_name]
        apply_theme_to_widgets()
    else:
        raise ValueError(f"Theme '{theme_name}' does not exist.")


def create_button(parent, text, command=None):
    """Create a themed button and register it for updates."""
    button = tk.Button(parent, text=text, command=command, bg=current_theme["PRIMARY_COLOR"], fg=current_theme["BUTTON_TEXT_COLOR"])
    widget_refs.setdefault("button", []).append(button)
    return button


def create_frame(parent):
    """Create a themed frame and register it for updates."""
    frame = tk.Frame(parent, bg=current_theme["BACKGROUND_COLOR"])
    widget_refs.setdefault("frame", []).append(frame)
    return frame


def style_treeview(tree):
    """Apply theme to Treeview."""
    tree.tag_configure("oddrow", background=current_theme["SECONDARY_COLOR"])
    tree.tag_configure("evenrow", background=current_theme["BACKGROUND_COLOR"])
    tree.configure(selectbackground=current_theme["HOVER_COLOR"], highlightbackground=current_theme["BORDER_COLOR"], highlightthickness=1)
    widget_refs.setdefault("treeview", []).append(tree)
