"""Generate a synthetic company dataset: ``python -m shadowcost.synth --out data/sample``."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from shadowcost.synth import Config, simulate, write_dataset


def main(argv: list[str] | None = None) -> None:
    defaults = Config()
    parser = argparse.ArgumentParser(
        prog="shadowcost-synth",
        description="Generate a small company's invoicing data with known ground truth.",
    )
    parser.add_argument("--out", type=Path, default=Path("data/sample"))
    parser.add_argument("--seed", type=int, default=defaults.seed)
    parser.add_argument("--days", type=int, default=defaults.days, help="calendar days")
    parser.add_argument("--start", type=date.fromisoformat, default=defaults.start)
    parser.add_argument("--overwrite", action="store_true", help="replace an existing dataset")
    args = parser.parse_args(argv)

    result = simulate(Config(seed=args.seed, start=args.start, days=args.days))
    manifest = write_dataset(result, args.out, overwrite=args.overwrite)
    summary = ", ".join(f"{n} {name}" for name, n in manifest["counts"].items())
    print(f"Wrote {args.out}: {summary}")


if __name__ == "__main__":
    main()
