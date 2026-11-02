"""The bench's sentinel on Linux: trycua's BenchSentinel, a window that plays the computer's user, writing the same log,
so trycua's own summarizer scores it. In the background condition it is the user's "User activity" window at the bench's
frame, whose field gets one character a second while it is the active window and holds the input focus; in the
foreground condition it is the "Bench Sentinel" witness at the screen's bottom right, which doesn't type.

Either way it logs, one JSON line per event with ``ev``, ``t`` (epoch ms) and ``armed``, all that disturbs that user: a
20 Hz sample of the pointer, the front app, whether its window is active and holds the focus, the clipboard's change
count, whether it is on the current desktop, a dialog on it and the other apps' windows above it; and its focus and
activation changes, the front app's, the desktop's, and every key, click and scroll delivered to it. SIGUSR1 activates
it, SIGUSR2 arms or disarms it, SIGTERM stops it.

X11 stands in for macOS: the input focus for the key window, ``_NET_ACTIVE_WINDOW`` for the active app, a window's
WM_CLASS for an app's name, the window manager's stacking order for the windows above, the CLIPBOARD selection's owner
for the pasteboard, and the desktop for the Space. Its own windows are those its Tk connection created, by X's resource
id base. Run as a script, it is the app's launch."""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Callable, Optional

from Xlib import X, Xatom, display, error
from Xlib.ext import xfixes

from app import BenchSentinel

#: The sentinel's app as its log names it: trycua's bundle id, which their summarizer takes for the user's own app.
OWN_BID = "ai.cua.benchsentinel"
WM_CLASS = "BenchSentinel"
LOG = Path.home() / ".bench-sentinel" / "sentinel.jsonl"
USER_SCRIPT = "the user keeps writing notes while the agent works in the background. "
#: The user's window in the background condition, its outer frame's x, y, width and height, as trycua's runner sets it.
USER_FRAME = (420, 340, 900, 520)
WITNESS_SIZE = (360, 140)
WITNESS_MARGIN = 24
SAMPLE_MS = 50
TYPE_MS = 1000
#: The window types that count as raised over the user's window, as macOS counts only its normal window layer: none,
#: normal, dialog and utility windows, not docks, menus, tooltips or notifications.
RAISING_TYPES = frozenset({None, "_NET_WM_WINDOW_TYPE_NORMAL", "_NET_WM_WINDOW_TYPE_DIALOG",
                           "_NET_WM_WINDOW_TYPE_UTILITY"})
ALL_DESKTOPS = 0xFFFFFFFF
#: X's buttons as macOS numbers them: left 0, right 1, middle 2; and X's scroll buttons as a scroll's dx and dy.
MAC_BUTTONS = {1: 0, 2: 2, 3: 1}
SCROLLS = {4: (0.0, 1.0), 5: (0.0, -1.0), 6: (1.0, 0.0), 7: (-1.0, 0.0)}


class Desktop:
    """What the sentinel reads of the X display, on a connection of its own: the window manager's properties, the
    pointer and the input focus. A window that vanishes as it's read reads as nothing. ``own_window`` is any window of
    the sentinel's Tk connection, whose resource id base marks all its windows."""

    def __init__(self, own_window: int) -> None:
        self.x = display.Display()
        self.root = self.x.screen().root
        mask = self.x.display.info.resource_id_mask
        self._mask, self._base = mask, own_window & ~mask
        self._atoms: dict[str, int] = {}
        self._clients: tuple[int, ...] = ()
        self._apps: dict[int, tuple[Optional[str], int]] = {}
        self._kinds: dict[int, Optional[str]] = {}
        self._main: Optional[int] = None

    def own(self, window: Optional[int]) -> bool:
        return bool(window) and window & ~self._mask == self._base

    def main(self) -> Optional[int]:
        """The sentinel's window as the window manager manages it: its first client that's transient for nothing."""
        if self._main is None:
            self._main = next((w for w in self.clients() if self.own(w) and self.transient_for(w) is None), None)
        return self._main

    def pointer(self) -> list[int]:
        reply = self.root.query_pointer()
        return [reply.root_x, reply.root_y]

    def active(self) -> Optional[int]:
        return (self._prop(self.root.id, "_NET_ACTIVE_WINDOW") or [None])[0] or None

    def focus(self) -> Optional[int]:
        focus = self.x.get_input_focus().focus
        return focus if isinstance(focus, int) else focus.id

    def current_desktop(self) -> int:
        return (self._prop(self.root.id, "_NET_CURRENT_DESKTOP") or [0])[0]

    def window_desktop(self, window: int) -> Optional[int]:
        return (self._prop(window, "_NET_WM_DESKTOP") or [None])[0]

    def frame_extents(self, window: int) -> list[int]:
        """The window manager's decorations around ``window``: left, right, top and bottom."""
        return (self._prop(window, "_NET_FRAME_EXTENTS") or [0, 0, 0, 0])[:4]

    def workarea(self) -> Optional[list[int]]:
        """The first desktop's area that docks and panels leave, x, y, width and height."""
        return (self._prop(self.root.id, "_NET_WORKAREA") or [])[:4] or None

    def clients(self) -> tuple[int, ...]:
        clients = tuple(self._prop(self.root.id, "_NET_CLIENT_LIST") or ())
        if clients != self._clients:
            self._clients = clients
            self._apps = {w: app for w, app in self._apps.items() if w in clients}
            self._kinds = {w: kind for w, kind in self._kinds.items() if w in clients}
        return clients

    def stacking(self) -> list[int]:
        return list(self._prop(self.root.id, "_NET_CLIENT_LIST_STACKING") or [])

    def app(self, window: int) -> tuple[Optional[str], int]:
        """The app a window belongs to: its WM_CLASS class and its _NET_WM_PID, None and -1 for what it doesn't say."""
        if window not in self._apps:
            try:
                wm_class = self.x.create_resource_object("window", window).get_wm_class()
            except error.XError:
                wm_class = None
            self._apps[window] = (wm_class[1] if wm_class else None,
                                  (self._prop(window, "_NET_WM_PID") or [-1])[0])
        return self._apps[window]

    def kind(self, window: int) -> Optional[str]:
        if window not in self._kinds:
            kinds = self._prop(window, "_NET_WM_WINDOW_TYPE")
            self._kinds[window] = self.x.get_atom_name(kinds[0]) if kinds else None
        return self._kinds[window]

    def hidden(self, window: int) -> bool:
        return self._atom("_NET_WM_STATE_HIDDEN") in (self._prop(window, "_NET_WM_STATE") or [])

    def transient_for(self, window: int) -> Optional[int]:
        return (self._prop(window, "WM_TRANSIENT_FOR", Xatom.WINDOW) or [None])[0] or None

    def _atom(self, name: str) -> int:
        if name not in self._atoms:
            self._atoms[name] = self.x.intern_atom(name)
        return self._atoms[name]

    def _prop(self, window: int, name: str, kind: int = X.AnyPropertyType) -> Optional[list[int]]:
        try:
            value = self.x.create_resource_object("window", window).get_full_property(self._atom(name), kind)
        except error.XError:
            return None
        return list(value.value) if value is not None else None


class Sentinel:
    """The sentinel's state and log, apart from its window: what a sample, a typing tick, an arm or disarm, and each
    change the desktop reports write. ``user`` is the user's field in the background condition, None in the
    foreground."""

    def __init__(self, desktop: Desktop, user: Optional[UserField], write: Callable[[str], None],
                 clock: Callable[[], float] = time.time) -> None:
        self.desktop, self.user, self._write, self._clock = desktop, user, write, clock
        self.armed = False
        self.clip = 0
        self.typed = 0
        self.expected = ""
        self._active = desktop.own(desktop.active())
        self._front = self.front(desktop.active())

    def emit(self, ev: str, **fields: object) -> None:
        self._write(json.dumps({"ev": ev, "t": self._clock() * 1000, "armed": self.armed, **fields}, sort_keys=True))

    def front(self, window: Optional[int]) -> dict:
        """The app of ``window`` as macOS names the front app: its id and pid, the sentinel's own as trycua's."""
        if not window:
            return {"bid": None, "pid": -1}
        if self.desktop.own(window):
            return {"bid": OWN_BID, "pid": os.getpid()}
        bid, pid = self.desktop.app(window)
        return {"bid": bid, "pid": pid}

    def sample(self) -> dict:
        d = self.desktop
        active, main = d.active(), d.main()
        current, mine = d.current_desktop(), d.window_desktop(main) if main else None
        above = self._above(main, current)
        fields = {"mouse": d.pointer(), "front": self.front(active), "active": d.own(active), "key": d.own(d.focus()),
                  "clip": self.clip, "onspace": mine is None or mine in (current, ALL_DESKTOPS),
                  "sheet": self._sheet(main), "above_n": len(above)}
        if above:
            fields["above"] = above
        return fields

    def _above(self, main: Optional[int], current: int) -> list[str]:
        """The apps whose shown windows the window manager stacks above the sentinel's, each once, in that order."""
        d, owners = self.desktop, []
        stacking = d.stacking()
        if main not in stacking:
            return owners
        for window in stacking[stacking.index(main) + 1:]:
            if (d.own(window) or d.kind(window) not in RAISING_TYPES or d.hidden(window)
                    or d.window_desktop(window) not in (current, ALL_DESKTOPS, None)):
                continue
            bid, pid = d.app(window)
            owner = bid or (f"pid:{pid}" if pid >= 0 else f"win:{window:#x}")
            if owner not in owners:
                owners.append(owner)
        return owners

    def _sheet(self, main: Optional[int]) -> bool:
        """Whether a window of the sentinel's own besides its main one shows, or any app's window transient for it."""
        d = self.desktop
        return any(window != main and (d.own(window) or (main is not None and d.transient_for(window) == main))
                   and not d.hidden(window) for window in d.clients())

    def focus_changed(self, key: bool) -> None:
        """Its window got or lost the input focus, as macOS's key window."""
        self.emit("didBecomeKey" if key else "didResignKey", front=self.front(self.desktop.active()))

    def key(self, chars: str, code: int, synthetic: bool) -> None:
        """A key delivered to its window, which leaked into the user's."""
        self.emit("keyDown", chars=chars, keyCode=code, synthetic=synthetic)

    def button(self, number: int, down: bool, at: list[int], synthetic: bool) -> None:
        """A button delivered to its window: a scroll for X's buttons 4 to 7, else a click, which leaked into the
        user's."""
        if number in SCROLLS:
            if down:
                dx, dy = SCROLLS[number]
                self.emit("scrollWheel", dx=dx, dy=dy, synthetic=synthetic)
        else:
            self.emit("mouseDown" if down else "mouseUp", button=MAC_BUTTONS.get(number, number - 1), loc=at,
                      synthetic=synthetic)

    def changed(self, what: str, window: Optional[int] = None) -> None:
        """Log a change the desktop reported: the active window (its app's activation and the front app), the current
        desktop, or the clipboard's owner."""
        if what == "active":
            active, front = self.desktop.own(window), self.front(window)
            if active != self._active:
                self._active = active
                self.emit("didBecomeActive" if active else "didResignActive", front=front)
            if front != self._front:
                self._front = front
                self.emit("front", front=front)
        elif what == "desktop":
            main = self.desktop.main()
            mine = self.desktop.window_desktop(main) if main else None
            self.emit("space", onspace=mine is None or mine in (self.desktop.current_desktop(), ALL_DESKTOPS))
        elif what == "clipboard":
            self.clip += 1

    def type_tick(self) -> None:
        """The user's second: while armed, a character typed at the end of the field when the sentinel's window is
        active and holds the focus, else ``user_blocked``; text it didn't type is ``user_text_disrupted``."""
        if not self.armed or self.user is None:
            return
        text = self.user.text()
        if text != self.expected:
            self.emit("user_text_disrupted", expected_len=len(self.expected), actual_len=len(text))
            self.expected = text
        d = self.desktop
        active_window = d.active()
        active, key = d.own(active_window), d.own(d.focus())
        if not (active and key and self.user.focused()):
            self.emit("user_blocked", active=active, key=key, front=self.front(active_window))
            return
        self.user.append(USER_SCRIPT[self.typed % len(USER_SCRIPT)])
        self.typed += 1
        self.expected = self.user.text()
        self.emit("user_type", n=self.typed)

    def toggle(self) -> None:
        """Arm, or disarm: disarming says first whether the user's text is what it typed."""
        self.armed = not self.armed
        if self.user is not None and not self.armed:
            text = self.user.text()
            self.emit("user_text", expected_len=len(self.expected), actual_len=len(text), intact=text == self.expected)
        if self.user is not None and self.armed:
            self.expected = self.user.text()
        self.emit("armed" if self.armed else "disarmed", **self.sample())


class UserField:
    """The user's text field: its text, whether it holds the focus within the sentinel, and typing at its end."""

    def __init__(self, entry: tk.Entry) -> None:
        self.entry = entry

    def text(self) -> str:
        return self.entry.get()

    def focused(self) -> bool:
        return self.entry.focus_get() is self.entry

    def append(self, text: str) -> None:
        self.entry.insert("end", text)


def watch(changes: queue.Queue) -> None:
    """Report, on a connection of its own, each change of the active window, the current desktop and the clipboard's
    owner, for the sentinel to log at its next sample."""
    x = display.Display()
    root = x.screen().root
    root.change_attributes(event_mask=X.PropertyChangeMask)
    x.xfixes_query_version()
    x.xfixes_select_selection_input(root, x.intern_atom("CLIPBOARD"), xfixes.XFixesSetSelectionOwnerNotifyMask)
    active, current = x.intern_atom("_NET_ACTIVE_WINDOW"), x.intern_atom("_NET_CURRENT_DESKTOP")
    while True:
        event = x.next_event()
        if event.type == X.PropertyNotify and event.atom == active:
            value = root.get_full_property(active, X.AnyPropertyType)
            changes.put(("active", value.value[0] if value is not None and len(value.value) else None))
        elif event.type == X.PropertyNotify and event.atom == current:
            changes.put(("desktop", None))
        elif (event.type, getattr(event, "sub_code", None)) == x.extension_event.SetSelectionOwnerNotify:
            changes.put(("clipboard", None))


def main(condition: str) -> None:
    background = condition == "background"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    root = tk.Tk(className=WM_CLASS)
    root.title("User activity" if background else "Bench Sentinel")
    entry = tk.Entry(root, font=("DejaVu Sans", 14))
    entry.place(x=20, rely=1.0, y=-68, relwidth=1.0, width=-40, height=28)
    desktop = Desktop(root.winfo_id())
    x, y, width, height = USER_FRAME if background else _witness(desktop)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.update()
    _await_managed(desktop)
    _fit_frame(root, desktop, (x, y, width, height))
    sentinel = Sentinel(desktop, UserField(entry) if background else None,
                        lambda line: os.write(log, (line + "\n").encode()))
    changes: queue.Queue = queue.Queue()

    def sample() -> None:
        while not changes.empty():
            sentinel.changed(*changes.get_nowait())
        sentinel.emit("s", **sentinel.sample())
        root.after(SAMPLE_MS, sample)

    def type_tick() -> None:
        sentinel.type_tick()
        root.after(TYPE_MS, type_tick)

    def activate() -> None:
        subprocess.run(["wmctrl", "-i", "-a", hex(desktop.main())], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        root.deiconify()
        root.lift()
        entry.focus_force()
        sentinel.emit("activate", front=sentinel.front(desktop.active()))

    def stop() -> None:
        sentinel.emit("exit")
        root.destroy()

    root.bind("<FocusIn>", lambda event: event.widget is root and sentinel.focus_changed(True))
    root.bind("<FocusOut>", lambda event: event.widget is root and sentinel.focus_changed(False))
    root.bind_all("<KeyPress>", lambda event: sentinel.key(event.char, event.keycode, bool(event.send_event)))
    root.bind_all("<ButtonPress>", lambda event: sentinel.button(event.num, True, [event.x, event.y],
                                                                 bool(event.send_event)))
    root.bind_all("<ButtonRelease>", lambda event: sentinel.button(event.num, False, [event.x, event.y],
                                                                   bool(event.send_event)))
    signal.signal(signal.SIGUSR1, lambda *_: root.after(0, activate))
    signal.signal(signal.SIGUSR2, lambda *_: root.after(0, sentinel.toggle))
    signal.signal(signal.SIGTERM, lambda *_: root.after(0, stop))
    threading.Thread(target=watch, args=(changes,), daemon=True).start()
    sentinel.emit("start", pid=os.getpid(), bid=OWN_BID, condition=condition, front=sentinel.front(desktop.active()))
    activate()
    root.after(SAMPLE_MS, sample)
    root.after(TYPE_MS, type_tick)
    root.mainloop()


def _witness(desktop: Desktop) -> tuple[int, int, int, int]:
    """The witness's frame: its size at the bottom right of the area the desktop's panels leave."""
    area_x, area_y, area_width, area_height = desktop.workarea() or [0, 0, *_screen(desktop)]
    width, height = WITNESS_SIZE
    return (area_x + area_width - width - WITNESS_MARGIN, area_y + area_height - height - WITNESS_MARGIN,
            width, height)


def _screen(desktop: Desktop) -> tuple[int, int]:
    screen = desktop.x.screen()
    return screen.width_in_pixels, screen.height_in_pixels


def _await_managed(desktop: Desktop, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while desktop.main() is None:
        if time.monotonic() > deadline:
            raise SystemExit("the window manager never managed the sentinel's window")
        time.sleep(0.1)


def _fit_frame(root: tk.Tk, desktop: Desktop, frame: tuple[int, int, int, int]) -> None:
    """Size the window so that its outer frame, the window manager's decorations included, is ``frame``, as macOS's
    frame is the outer one."""
    left, right, top, bottom = desktop.frame_extents(desktop.main())
    x, y, width, height = frame
    root.geometry(f"{width - left - right}x{height - top - bottom}+{x}+{y}")
    root.update()


if __name__ == "__main__":
    main(BenchSentinel().settings.condition)
