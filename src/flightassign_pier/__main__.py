"""CLI entry point.

Usage:
    python -m flightassign_pier              # post once to Slack
    python -m flightassign_pier --dry-run    # print to stdout, do not post
    python -m flightassign_pier --loop       # post every 20 minutes
"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import CONFIG
from .post import loop, post_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flightassign-pier")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render the message to stdout instead of posting to Slack.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Post every 20 minutes until interrupted (in-process scheduler).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.loop:
        loop(CONFIG, dry_run=args.dry_run)
        return 0

    post_once(CONFIG, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
