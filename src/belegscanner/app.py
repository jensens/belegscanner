"""Belegscanner GTK Application."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from belegscanner.window import BelegscannerWindow


class BelegscannerApp(Adw.Application):
    """Main application class.

    Handles application lifecycle and creates the main window.
    """

    def __init__(self):
        """Initialize the application."""
        super().__init__(
            application_id="de.kup.Belegscanner",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        """Called when the application is activated."""
        win = self.props.active_window
        if not win:
            win = BelegscannerWindow(application=self)
        win.present()


def main():
    """Entry point for the GUI application."""
    app = BelegscannerApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
