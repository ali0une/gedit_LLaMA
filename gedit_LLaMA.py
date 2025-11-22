#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# --------------------------------------------------------------
# Gedit 44+ plug-in: "Ask LLaMA" (context-menu version)
# --------------------------------------------------------------
# Sends selected text + a user prompt to a /v1/chat/completions
# endpoint (e.g. a locally-run llama.cpp server) and displays the
# answer in a popup dialog with streaming support.
# --------------------------------------------------------------
# install org.gnome.gedit.plugins.gedit_llama.gschema.xml schema before activating the plugin :
# cp org.gnome.gedit.plugins.gedit_llama.gschema.xml ~/.local/share/glib-2.0/schemas/
# glib-compile-schemas ~/.local/share/glib-2.0/schemas/
# --------------------------------------------------------------

# SPDX-License-Identifier: MIT
# Copyright © 2025 <ali0une>
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import json
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gedit', '3.0')
gi.require_version('Gio', '2.0')
from gi.repository import GObject, Gedit, Gtk, GLib, Gio

import requests   # pip install requests   (or distro package python3-requests)

# Configuration: adapt to your own llama.cpp server
API_URL = "http://127.0.0.1:5000/v1/chat/completions"   # llama.cpp URL
API_KEY = ""                                            # optional
MODEL   = "llama.cpp"                                   # model name sent in JSON
SHORTCUT = "<Ctrl><Alt>l"                              # default shortcut


class LLaMAChatDialog(Gtk.Dialog):
    """
    Dialog that asks the user for a (potentially multiline) custom prompt.
    It uses a Gtk.TextView wrapped in a ScrolledWindow, so you get a real
    "textarea" that can grow to several lines.
    """

    def __init__(self, parent):
        super().__init__(title="Ask LLaMA",
                         transient_for=parent,
                         flags=0)

        # Buttons
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK,     Gtk.ResponseType.OK
        )

        # Set dialog size relative to parent window (60% of parent width, 40% of height)
        self._set_relative_size(parent, 0.6, 0.4)

        # Layout
        box = self.get_content_area()

        # Short explanatory label
        label = Gtk.Label(label="Additional instruction / question:")
        label.set_halign(Gtk.Align.START)
        box.add(label)

        # ScrolledWindow → TextView gives us a multiline textarea
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC,
                            Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)   # wrap long lines
        self.textview.set_left_margin(4)
        self.textview.set_right_margin(4)

        # placeholder fallback
        try:
            # works on GTK ≥ 3.22
            self.textview.set_placeholder_text("Type your prompt here…")
        except AttributeError:
            # older GTK: silently ignore
            pass

        scrolled.add(self.textview)
        box.add(scrolled)

        # Show everything
        self.show_all()

    def _set_relative_size(self, parent, width_ratio, height_ratio):
        """Set dialog size as a percentage of the parent window."""
        if parent:
            try:
                # Get parent window dimensions
                parent_width = parent.get_allocated_width()
                parent_height = parent.get_allocated_height()
                
                # Calculate relative sizes
                width = int(parent_width * width_ratio)
                height = int(parent_height * height_ratio)
                
                # Set the dialog size
                self.set_default_size(width, height)
            except Exception:
                # Fallback to fixed size if we can't get parent dimensions
                self.set_default_size(500, 300)

    def get_user_prompt(self):
        """Return the full text the user typed in the textarea."""
        buffer = self.textview.get_buffer()
        start, end = buffer.get_start_iter(), buffer.get_end_iter()
        return buffer.get_text(start, end, True).strip()


class LLaMAResultDialog(Gtk.Dialog):
    """
    Dialog that displays the LLM response in a read-only text view with streaming support.
    """

    def __init__(self, parent, result):
        super().__init__(title="LLM Response",
                         transient_for=parent,
                         flags=0)

        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK)

        # Close the dialog when OK is pressed
        self.connect("response",
                     lambda d, r: d.destroy() if r == Gtk.ResponseType.OK else None)
        # Set dialog size relative to parent window (80% of parent width, 60% of height)
        self._set_relative_size(parent, 0.8, 0.6)

        # Layout
        box = self.get_content_area()

        label = Gtk.Label(label="LLM Response:")
        label.set_halign(Gtk.Align.START)
        box.add(label)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC,
                            Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textview.set_left_margin(4)
        self.textview.set_right_margin(4)
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)

        self.buffer = self.textview.get_buffer()
        self.buffer.set_text(result)

        scrolled.add(self.textview)
        box.add(scrolled)

        # Copy-to-clipboard button (icon)
        copy_btn = Gtk.Button()
        copy_icon = Gtk.Image.new_from_icon_name("edit-copy", Gtk.IconSize.BUTTON)
        copy_btn.set_image(copy_icon)
        copy_btn.set_tooltip_text("Copy result to clipboard")
        copy_btn.connect("clicked", self._on_copy_clicked)

        # Place the button at the top-right of the dialog
        box.add(copy_btn)
        copy_btn.show()

        self.show_all()

    def _set_relative_size(self, parent, width_ratio, height_ratio):
        """Set dialog size as a percentage of the parent window."""
        if parent:
            try:
                # Get parent window dimensions
                parent_width = parent.get_allocated_width()
                parent_height = parent.get_allocated_height()
                
                # Calculate relative sizes
                width = int(parent_width * width_ratio)
                height = int(parent_height * height_ratio)
                
                # Set the dialog size
                self.set_default_size(width, height)
            except Exception:
                # Fallback to fixed size if we can't get parent dimensions
                self.set_default_size(500, 300)

    def append_text(self, text):
        """Append text to the response TextView."""
        if text is not None:  # Check for None values
            # Use GLib.idle_add to ensure UI updates happen on main thread
            GLib.idle_add(self._append_text_internal, text)
    
    def _append_text_internal(self, text):
        """Internal method to append text to the buffer."""
        # Check if dialog is still valid before updating
        if not self.get_window() or not self.is_visible():
            return False
            
        end_iter = self.buffer.get_end_iter()
        self.buffer.insert(end_iter, text)  # Now we know text is a string
        # Scroll to the end
        mark = self.buffer.create_mark(None, end_iter, False)
        self.textview.scroll_to_mark(mark, 0.0, True, 0.0, 0.0)
        return False   # stop the idle handler

    def _on_copy_clicked(self, button):
        """Copy the dialog’s entire text to the clipboard."""
        from gi.repository import Gdk

        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

        buffer = self.buffer
        start, end = buffer.get_start_iter(), buffer.get_end_iter()
        text = buffer.get_text(start, end, True).strip()

        # Pass the text length (or -1 for auto-detect)
        clipboard.set_text(text, len(text))

class LLaMAConfigDialog(Gtk.Dialog):
    """
    Configuration dialog for LLaMA plugin settings.
    """

    def __init__(self, parent, api_url, api_key, model, shortcut):
        super().__init__(title="LLaMA Plugin Configuration",
                         transient_for=parent,
                         flags=0)

        # Buttons
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK,     Gtk.ResponseType.OK
        )

        # Set dialog size
        self.set_default_size(500, 250)

        # Layout
        box = self.get_content_area()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add(vbox)

        # API URL
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        label = Gtk.Label(label="API URL:")
        label.set_halign(Gtk.Align.START)
        hbox.pack_start(label, False, False, 0)

        self.api_url_entry = Gtk.Entry()
        self.api_url_entry.set_text(api_url)
        self.api_url_entry.set_hexpand(True)
        hbox.pack_start(self.api_url_entry, True, True, 0)
        vbox.pack_start(hbox, False, False, 0)

        # API Key
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        label = Gtk.Label(label="API Key:")
        label.set_halign(Gtk.Align.START)
        hbox.pack_start(label, False, False, 0)

        self.api_key_entry = Gtk.Entry()
        self.api_key_entry.set_text(api_key)
        self.api_key_entry.set_hexpand(True)
        self.api_key_entry.set_visibility(False)
        hbox.pack_start(self.api_key_entry, True, True, 0)
        vbox.pack_start(hbox, False, False, 0)

        # Model
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        label = Gtk.Label(label="Model Name:")
        label.set_halign(Gtk.Align.START)
        hbox.pack_start(label, False, False, 0)

        self.model_entry = Gtk.Entry()
        self.model_entry.set_text(model)
        self.model_entry.set_hexpand(True)
        hbox.pack_start(self.model_entry, True, True, 0)
        vbox.pack_start(hbox, False, False, 0)

        # Shortcut
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        label = Gtk.Label(label="Shortcut:")
        label.set_halign(Gtk.Align.START)
        hbox.pack_start(label, False, False, 0)

        self.shortcut_entry = Gtk.Entry()
        self.shortcut_entry.set_text(shortcut)
        self.shortcut_entry.set_hexpand(True)
        hbox.pack_start(self.shortcut_entry, True, True, 0)
        vbox.pack_start(hbox, False, False, 0)

        # Show everything
        self.show_all()

    def get_settings(self):
        """Return the configured settings."""
        return {
            "api_url": self.api_url_entry.get_text().strip(),
            "api_key": self.api_key_entry.get_text().strip(),
            "model": self.model_entry.get_text().strip(),
            "shortcut": self.shortcut_entry.get_text().strip()
        }


class LLaMAChatPlugin(GObject.Object, Gedit.WindowActivatable):
    """Main plug-in class: one instance per Gedit window."""
    __gtype_name__ = "LLaMAChatPlugin"
    window = GObject.Property(type=Gedit.Window)

    # Life-cycle callbacks
    def __init__(self):
        super().__init__()
        self._action_name = "ask-llama"
        self._configure_action_name = "configure-llama"
        self._connected_views = set()   # keep track so we don't double-connect
        self._result_dialog = None
        
        # Load settings from GSettings with error handling
        try:
            self.settings = Gio.Settings.new("org.gnome.gedit.plugins.gedit_llama")
            self._load_settings()
        except Exception as e:
            print("[LLaMAChat] GSettings schema not found, using defaults:", e)
            # Keep default values: do **not** override the loader

    def _load_settings(self):
        """Load saved settings from GSettings."""
        # Keep existing global variables as defaults
        global API_URL, API_KEY, MODEL, SHORTCUT
        try:
            api_url = self.settings.get_string("api-url")
            if api_url:
                API_URL = api_url

            api_key = self.settings.get_string("api-key")
            if api_key:
                API_KEY = api_key

            model = self.settings.get_string("model")
            if model:
                MODEL = model

            shortcut = self.settings.get_string("shortcut")
            if shortcut:
                SHORTCUT = shortcut
        except Exception as e:
            print("[LLaMAChat] Error loading settings:", e)
            # keep defaults
            """API_URL = "http://127.0.0.1:5000/v1/chat/completions"
            API_KEY = ""
            MODEL = "llama.cpp"
            SHORTCUT = "<Ctrl><Alt>l" """

    def _save_settings(self):
        """Save settings to GSettings."""
        try:
            self.settings.set_string("api-url", API_URL)
            self.settings.set_string("api-key", API_KEY)
            self.settings.set_string("model", MODEL)
            self.settings.set_string("shortcut", SHORTCUT)
        except Exception as e:
            print("[LLaMAChat] Could not save settings:", e)

    def do_activate(self):
        """Called when the plug-in is activated for a window."""
        # Create the GIO action (used by the shortcut)
        action = Gio.SimpleAction.new(self._action_name, None)
        action.connect("activate", self.on_activate)
        self.window.add_action(action)

        # Create the configuration action
        configure_action = Gio.SimpleAction.new(self._configure_action_name, None)
        configure_action.connect("activate", self._on_configure_activate)
        self.window.add_action(configure_action)

        # Attach to the current view's context menu
        view = self.window.get_active_view()
        if view:
            self._attach_to_view(view)

        # Keep track of newly opened tabs
        self._tab_added_id = self.window.connect("tab-added", self._on_tab_added)
        self._tab_switched_id = self.window.connect("active-tab-changed",
                                                    self._on_active_tab_changed)

    def do_deactivate(self):
        """Called when the plug-in is deactivated for a window."""
        self.window.remove_action(self._action_name)
        self.window.remove_action(self._configure_action_name)
        if hasattr(self, "_tab_added_id"):
            self.window.disconnect(self._tab_added_id)
        if hasattr(self, "_tab_switched_id"):
            self.window.disconnect(self._tab_switched_id)

    def do_update_state(self):
        """Enable/disable the action depending on whether a view exists."""
        view = self.window.get_active_view()
        act = self.window.lookup_action(self._action_name)
        if act:
            act.set_enabled(view is not None)

    # Helper: attach our context-menu handler to a GtkTextView
    def _attach_to_view(self, view):
        """Add our ‘populate-popup’ handler to *view* (once only)."""
        if view in self._connected_views:
            return
        view.connect("populate-popup", self._on_populate_popup)
        """remove view from the set when it is destroyed"""
        view.connect_after("destroy", lambda w: self._connected_views.discard(view))

        self._connected_views.add(view)

    def _on_tab_added(self, window, tab):
        view = tab.get_view()
        self._attach_to_view(view)

    def _on_active_tab_changed(self, window, tab):
        view = tab.get_view()
        self._attach_to_view(view)

    # Context-menu callback
    def _on_populate_popup(self, view, menu):
        main_item = Gtk.MenuItem(label="Gedit LLaMA")
        main_menu = Gtk.Menu()
        main_item.set_submenu(main_menu)

        ask_item = Gtk.MenuItem(label="Ask LLaMA")
        ask_item.connect("activate", lambda *_:
                         self.window.lookup_action(self._action_name).activate(None))
        main_menu.append(ask_item)
        ask_item.show()

        configure_item = Gtk.MenuItem(label="Configure LLaMA")
        configure_item.connect("activate", lambda *_:
                               self.window.lookup_action(self._configure_action_name).activate(None))
        main_menu.append(configure_item)
        configure_item.show()

        menu.append(main_item)
        main_item.show()

    # Configuration menu callback
    def _on_configure_activate(self, action, param):
        """Show configuration dialog."""
        global API_URL, API_KEY, MODEL, SHORTCUT
        dialog = LLaMAConfigDialog(self.window, API_URL, API_KEY, MODEL, SHORTCUT)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            settings = dialog.get_settings()
            API_URL = settings["api_url"]
            API_KEY = settings["api_key"]
            MODEL = settings["model"]
            SHORTCUT = settings["shortcut"]
            self._save_settings()
            try:
                app = Gedit.App.get_default()
                app.set_accels_for_action(f"win.{self._action_name}",
                                          [SHORTCUT])
            except Exception as e:
                print("[LLaMAChat] Could not set shortcut:", e)
        dialog.destroy()

    # Core functionality (modified to show result in popup)
    def on_activate(self, action, param):
        view = self.window.get_active_view()
        if not view:
            return

        buffer = view.get_buffer()
        if buffer.get_has_selection():
            start, end = buffer.get_selection_bounds()
            selected_text = buffer.get_text(start, end, True)
        else:
            selected_text = ""

        dialog = LLaMAChatDialog(self.window)
        response = dialog.run()
        user_prompt = dialog.get_user_prompt() if response == Gtk.ResponseType.OK else ""
        dialog.destroy()

        if not user_prompt:
            return

        messages = []
        if selected_text:
            messages.append({"role": "system",
                             "content": f"The following text is selected in the editor:\n\n{selected_text}"})
        messages.append({"role": "user", "content": user_prompt})

        payload = {"model": MODEL,
                   "messages": messages,
                   "temperature": 0.7,
                   "max_tokens": 1024,
                   "stream": True}

        # Create dialog and keep a reference
        self._result_dialog = LLaMAResultDialog(self.window, "")
        self._result_dialog.show_all()          # show immediately

        # Start worker thread, passing the dialog instance
        threading.Thread(target=self._call_api,
                         args=(payload, self._result_dialog),
                         daemon=True).start()

    # Networking: runs in a worker thread
    def _call_api(self, payload, result_dialog):
        headers = {"Content-Type": "application/json"}
        if API_KEY:
            headers["Authorization"] = f"Bearer {API_KEY}"
        try:
            resp = requests.post(API_URL,
                                 headers=headers,
                                 data=json.dumps(payload),
                                 timeout=120,
                                 stream=True)
            resp.raise_for_status()

            if 'text/event-stream' in resp.headers.get('content-type', ''):
                for line in resp.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_json = line_str[6:]
                            if data_json == '[DONE]':
                                break
                            try:
                                data = json.loads(data_json)
                                if 'choices' in data and len(data['choices']) > 0:
                                    delta = data['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        GLib.idle_add(result_dialog.append_text,
                                                     delta['content'])
                            except json.JSONDecodeError:
                                continue
            else:  # non-streaming fallback
                response_data = resp.json()
                try:
                    answer = response_data["choices"][0]["message"]["content"]
                except (KeyError, IndexError):
                    GLib.idle_add(self._show_error, "Unexpected response format.")
                    return
                GLib.idle_add(self._show_result, answer)

        except Exception as exc:
            GLib.idle_add(self._show_error, f"Request failed: {exc}")
            return
    # UI updates: executed on the main GTK thread via GLib.idle_add()
    def _show_result(self, result):
        """Display the LLM response in a popup dialog."""
        dialog = LLaMAResultDialog(self.window, result)
        # Show the dialog - let it handle its own closing
        dialog.show_all()
        return False   # stop the idle handler

    def _show_error(self, message):
        dlg = Gtk.MessageDialog(transient_for=self.window,
                                flags=0,
                                message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.OK,
                                text="LLaMA Chat: error")
        dlg.format_secondary_text(message)
        dlg.run()
        dlg.destroy()
        return False   # stop the idle handler

# Register the plug-in with Gedit
GObject.type_register(LLaMAChatPlugin)
