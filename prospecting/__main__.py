import argparse
import logging
import os
import sys
from pathlib import Path

from . import github, phase1, phase3


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m prospecting", description="NYC prospecting signals")
    ap.add_argument("command", choices=["run", "phase1", "phase2", "phase3"],
                    help="run = all three phases (the weekly refresh); or a single phase")
    ap.add_argument("--companies", type=Path, default=Path("companies.csv"))
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--board-overrides", type=Path, default=Path("config/board_overrides.csv"))
    ap.add_argument("--github-orgs", type=Path, default=Path("config/github_orgs.csv"))
    ap.add_argument("--skip-github", action="store_true",
                    help="run: reuse the existing output/phase2_github.csv instead of rescanning GitHub")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    if args.command == "run":
        if args.skip_github and not (args.out / "phase2_github.csv").exists():
            ap.error(f"--skip-github needs an existing {args.out / 'phase2_github.csv'}")
        if not args.skip_github and not os.environ.get("GITHUB_TOKEN"):
            ap.error("GITHUB_TOKEN is not set; set it, or pass --skip-github to reuse the last GitHub scan")

    args.out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(args.out / "run.log", mode="w")])
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    if args.command == "run":
        phase1.run(args.companies, args.out, args.board_overrides)
        if not args.skip_github:
            github.run(args.companies, args.out, args.github_orgs)
        phase3.run(args.companies, args.out)
    elif args.command == "phase1":
        phase1.run(args.companies, args.out, args.board_overrides)
    elif args.command == "phase2":
        github.run(args.companies, args.out, args.github_orgs)
    elif args.command == "phase3":
        phase3.run(args.companies, args.out)


if __name__ == "__main__":
    main()
