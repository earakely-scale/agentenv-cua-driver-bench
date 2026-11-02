"""ship.py INSTANCE LOCAL REMOTE: copy a small file to INSTANCE over SSM, checked by sha256."""
import sys
from pathlib import Path

from common import ship


def main():
    instance, local, remote = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    ship(instance, local, remote)
    print(instance, "ok")


if __name__ == "__main__":
    main()
