#!/usr/bin/env python3
"""
PPDE CLI

Thin wrapper over the analysis engine.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ppde.orchestrator import analyze_repo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ppde",
        description="Analyze Python code for deviations from your historical patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ppde analyze .
  ppde analyze /path/to/repo
        """,
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="{analyze}",
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze a Git repository",
    )
    analyze_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to Git repository (default: current directory)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        repo_path = Path(args.path).resolve()

        if not repo_path.exists():
            print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
            return 1

        try:
            explanations = analyze_repo(repo_path)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        except Exception:
            print("Internal error while analyzing repository.", file=sys.stderr)
            print("Run with --debug for details.", file=sys.stderr)
            return 2

        print(f"Analyzed repository: {repo_path}")
        print(f"Total findings: {len(explanations)}")
        print()

        if not explanations:
            print("No warnings (COLD START MODE).")
            print()
            print("The frequency table is empty - all patterns are blocked by sparsity gate.")
            print("This is conservative: the system refuses to guess when data is missing.")
            print()
            print("See README for implementation details.")
            return 0

        for i, explanation in enumerate(explanations, 1):
            detector_name = explanation.warning.score.detector_name

            print(f"Finding #{i}")
            print(f"Detector: {detector_name}")
            print()
            print(explanation.message)
            print()
            print("-" * 70)
            print()

        return 0

    # This should never happen because argparse enforces commands
    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
