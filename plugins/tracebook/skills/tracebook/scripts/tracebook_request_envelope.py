"""Create an ASCII-safe Tracebook request envelope on POSIX or Windows."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.request_transport import encode_envelope
else:
    from .request_transport import encode_envelope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--request",
        required=True,
        help="Path to a UTF-8 JSON request, or '-' to read UTF-8 bytes from stdin.",
    )
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read() if args.request == "-" else Path(args.request).read_bytes()
        encoded = encode_envelope(raw)
    except (OSError, ValueError) as error:
        sys.stderr.write(f"request envelope error: {error}\n")
        return 2
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
