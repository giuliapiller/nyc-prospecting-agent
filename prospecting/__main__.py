import argparse
import logging
from pathlib import Path

from . import phase1


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m prospecting", description="NYC prospecting signals")
    ap.add_argument("command", choices=["phase1"], help="which step to run")
    ap.add_argument("--companies", type=Path, default=Path("companies.csv"))
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--board-overrides", type=Path, default=Path("config/board_overrides.csv"))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(args.out / "run.log", mode="w")])
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    if args.command == "phase1":
        phase1.run(args.companies, args.out, args.board_overrides)


if __name__ == "__main__":
    main()
