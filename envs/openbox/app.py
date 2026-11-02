"""The window manager trycua's Linux bench runs in, as a computer app on every bench computer: their session starts
openbox, with its default configuration (``macos_bench/launch/linux_session.py``). The base computer's XFCE session
starts xfwm4, which gives every modal dialog the focus as it maps, even one an app maps without it in the background,
where openbox leaves the focus where it was; so the session's window manager becomes openbox.

Two things differ from their session, each because the computer otherwise fails its own conformance probe at build
(P6, a chord stops selecting in the probe's fixture): openbox keeps the default key bindings an agent would reach for,
those that close, cycle and switch windows and desktops (``KEYS``), not all 26, since rebinding them all as the
driver's typing remaps a key holds the keyboard long enough to drop the next chord; and picom doesn't run, since with
it the chord drops too, while without it the driver captures a window behind another the same."""
import re
from pathlib import Path

from agentenv_protocol.computer import ComputerAppEnvironment, Packages, computer_app, install_step, linux

SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]}]
SESSION = Path("/etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml")
RC = Path("/etc/xdg/openbox/rc.xml")
XFWM4 = '<value type="string" value="xfwm4"/>'
KEYS = ("A-F4", "A-Escape", "A-space", "A-Tab", "A-S-Tab", "C-A-Left", "C-A-Right", "C-A-Up", "C-A-Down", "C-A-Tab")


@computer_app(supports=SUPPORTS)
@linux(packages=Packages(apt=["openbox"]))
class Openbox(ComputerAppEnvironment):
    @install_step(scope="system", os="linux")
    def window_manager(self) -> None:
        """The failsafe session's first client, its window manager, openbox in place of xfwm4."""
        session = SESSION.read_text(encoding="utf-8")
        if session.count(XFWM4) != 1:
            raise RuntimeError(f"{SESSION} doesn't name xfwm4 once as a session client")
        SESSION.write_text(session.replace(XFWM4, '<value type="string" value="openbox"/>'), encoding="utf-8")

    @install_step(scope="system", os="linux")
    def key_bindings(self) -> None:
        """openbox's default configuration with only the key bindings ``KEYS`` names."""
        rc = RC.read_text(encoding="utf-8")
        binds = re.findall(r'<keybind key="([^"]+)">.*?</keybind>', rc, re.S)
        if set(KEYS) - set(binds):
            raise RuntimeError(f"{RC} doesn't bind {sorted(set(KEYS) - set(binds))}")
        RC.write_text(re.sub(r'[ \t]*<keybind key="([^"]+)">.*?</keybind>\n?',
                             lambda bind: bind.group(0) if bind.group(1) in KEYS else "", rc, flags=re.S),
                      encoding="utf-8")
