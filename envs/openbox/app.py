"""The window manager trycua's Linux bench runs in, as a computer app on every bench computer: their session starts
openbox, with its default configuration, and picom (``macos_bench/launch/linux_session.py``). The base computer's
XFCE session starts xfwm4, which gives every modal dialog the focus as it maps, even one an app maps without focus in
the background, where openbox leaves the focus where it was; so the session's window manager becomes openbox, and picom
runs as trycua runs it."""
from pathlib import Path

from agentenv_protocol.computer import (ComputerAppEnvironment, Packages, Service, computer_app, install_step,
                                        linux)

SUPPORTS = [{"os": {"type": "linux", "display": ["x11"]}, "arch": ["amd64", "arm64"]}]
SESSION = Path("/etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml")
XFWM4 = '<value type="string" value="xfwm4"/>'
PICOM = "/usr/local/bin/start-desktop with-x picom --backend xrender --config /dev/null"


@computer_app(supports=SUPPORTS)
@linux(packages=Packages(apt=["openbox", "picom"]), services=[Service(name="picom", command=PICOM)])
class Openbox(ComputerAppEnvironment):
    @install_step(scope="system", os="linux")
    def window_manager(self) -> None:
        """The failsafe session's first client, its window manager, openbox in place of xfwm4."""
        session = SESSION.read_text(encoding="utf-8")
        if session.count(XFWM4) != 1:
            raise RuntimeError(f"{SESSION} doesn't name xfwm4 once as a session client")
        SESSION.write_text(session.replace(XFWM4, '<value type="string" value="openbox"/>'), encoding="utf-8")
