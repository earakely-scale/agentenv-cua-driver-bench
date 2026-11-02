"""The window manager trycua's Linux bench runs in, as a computer app on every bench computer: their session starts
openbox, with its default configuration (``macos_bench/launch/linux_session.py``). The base computer's XFCE session
starts xfwm4, which gives every modal dialog the focus as it maps, even one an app maps without it in the background,
where openbox leaves the focus where it was; so the session's window manager becomes openbox. Their session also runs
picom, which this computer doesn't: with it, the computer fails its own conformance probe at build (a chord stops
selecting in the probe's fixture), and without it the driver captures a window that's behind another the same."""
from pathlib import Path

from agentenv_protocol.computer import ComputerAppEnvironment, Packages, computer_app, install_step, linux

SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]}]
SESSION = Path("/etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml")
XFWM4 = '<value type="string" value="xfwm4"/>'


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
