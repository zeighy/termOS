"""The termOS colours: the single source for every app and config file.

After changing a colour run  artwork/make-theme.py  to regenerate the static
configs (GTK, labwc, foot, mako). The termOS apps read this file directly.
"""

COLORS = {
    "crust": "#11111b",    # panel, lock screen
    "mantle": "#181825",   # sidebars, title bars
    "base": "#1e1e2e",     # window background
    "card": "#272839",     # cards
    "raised": "#313244",   # buttons
    "hover": "#45475a",    # hovered buttons, borders
    "muted": "#a6adc8",    # secondary text
    "faint": "#7f849c",    # inactive window titles
    "text": "#cdd6f4",
    "bright": "#f5f7ff",
    "accent": "#89b4fa",
    "red": "#f38ba8",
    "danger": "#a6303f",   # destructive buttons (white text stays readable)
    "orange": "#fab387",
    "yellow": "#f9e2af",
    "green": "#a6e3a1",
    "teal": "#94e2d5",
    "mauve": "#cba6f7",
    "pink": "#f5c2e7",
}

UI_FONT = "Adwaita Sans"
MONO_FONT = "DejaVu Sans Mono"
ICON_FONT = "Symbols Nerd Font"


def rgb(name):
    h = COLORS[name]
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


def gtk_named_colors():
    """Named colours understood by adw-gtk3, so stock GTK apps match termOS."""
    roles = {
        "window_bg_color": "base", "window_fg_color": "text",
        "view_bg_color": "mantle", "view_fg_color": "text",
        "headerbar_bg_color": "mantle", "headerbar_fg_color": "text",
        "headerbar_backdrop_color": "crust",
        "sidebar_bg_color": "mantle", "sidebar_fg_color": "text",
        "sidebar_backdrop_color": "mantle",
        "card_bg_color": "card", "card_fg_color": "text",
        "popover_bg_color": "card", "popover_fg_color": "text",
        "dialog_bg_color": "base", "dialog_fg_color": "text",
        "accent_bg_color": "accent", "accent_color": "accent", "accent_fg_color": "crust",
        "destructive_bg_color": "danger", "destructive_color": "red", "destructive_fg_color": "bright",
        "success_color": "green", "warning_color": "yellow", "error_color": "red",
    }
    return "".join(f"@define-color {role} {COLORS[c]};\n" for role, c in roles.items())
