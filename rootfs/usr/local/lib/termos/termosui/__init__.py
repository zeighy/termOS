"""Shared code for the termOS desktop apps (shell, lock screen, settings...)."""
import gi

# Pin the toolkit before any module imports it. Without this, PyGObject takes
# GTK 4 as soon as some update happens to install it, and every app breaks.
# (termos-pin doesn't import this package; it uses only the standard library.)
for _name, _version in (("Gtk", "3.0"), ("Gdk", "3.0"), ("PangoCairo", "1.0")):
    gi.require_version(_name, _version)
