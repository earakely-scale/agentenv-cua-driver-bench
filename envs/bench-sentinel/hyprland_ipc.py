"""trycua's Hyprland IPC client (their ``hypr.py``) made to wait out a busy Hyprland, and their sentinel run on it.
Hyprland's socket refuses a connect with EAGAIN while its listen queue is full, as at boot, when Omarchy's shell asks it
much at once; their client raises then, which ends their sentinel's search for its own window before it says it's
ready, and makes a sample of it fail. ``python3 hyprland_ipc.py SENTINEL ARGS...`` runs their sentinel on it. The same
file is in each of the bench's apps on Omarchy."""
import runpy
import sys
import time
from pathlib import Path

#: How long a request waits for Hyprland to take its connection.
BUSY_S = 10.0
RETRY_S = 0.05


def patient(hypr):
    """``hypr``, trycua's module, whose requests retry a connect Hyprland refused for a full queue, for ``BUSY_S``."""
    request = hypr.request

    def waiting(command, timeout=8.0):
        deadline = time.monotonic() + BUSY_S
        while True:
            try:
                return request(command, timeout)
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(RETRY_S)

    hypr.request = waiting
    return hypr


if __name__ == "__main__":
    sentinel = Path(sys.argv[1])
    sys.path.insert(0, str(sentinel.parent))
    import hypr

    patient(hypr)
    sys.argv = sys.argv[1:]
    runpy.run_path(str(sentinel), run_name="__main__")
