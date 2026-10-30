"""Ingest a folder of company files: ``python -m shadowcost.ingest data/sample``."""

from __future__ import annotations

import argparse
from pathlib import Path

from shadowcost.ingest import ingest_folder, save_events


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="shadowcost-ingest",
        description="Turn spreadsheet snapshots, bank exports and email logs into one event table.",
    )
    parser.add_argument("folder", type=Path)
    parser.add_argument("--out", type=Path, help="write the event table to this CSV file")
    args = parser.parse_args(argv)

    result = ingest_folder(args.folder)
    print(result.summary())
    if args.out:
        save_events(result.events, args.out)
        print(f"Wrote {len(result.events)} events to {args.out}")


if __name__ == "__main__":
    main()
