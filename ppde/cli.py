#!/usr/bin/env python3
"""
PPDE CLI

Thin wrapper over the analysis engine.
"""
import argparse
import sys
from pathlib import Path

from ppde.orchestrator import analyze_repo


def main():
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

    parser.add_argument(
        "command",
        choices=["analyze"],
        help="Command to run",
    )

    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to Git repository (default: current directory)",
    )

    args = parser.parse_args()

    if args.command != "analyze":
        parser.error(f"Unknown command: {args.command}")

    repo_path = Path(args.path).resolve()
    if not repo_path.exists():
        print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
        sys.exit(1)

    try:
        explanations = analyze_repo(repo_path)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(2)

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
        return

    for i, explanation in enumerate(explanations, 1):
        detector_name = explanation.warning.score.detector_name

        print(f"Finding #{i}")
        print(f"Detector: {detector_name}")
        print()
        print(explanation.message)
        print()
        print("-" * 70)
        print()


if __name__ == "__main__":
    main()
