"""CLI entry point for the debate training tool."""

import argparse
import sys

from debate.case_generator import generate_case
from debate.models import Side


def main() -> None:
    """Main entry point for the debate CLI."""
    parser = argparse.ArgumentParser(
        description="Practice Public Forum debate against an AI opponent",
        prog="debate",
    )

    parser.add_argument(
        "resolution",
        type=str,
        help="The debate resolution (e.g., 'Resolved: The US should ban TikTok')",
    )

    parser.add_argument(
        "--side",
        type=str,
        choices=["pro", "con"],
        required=True,
        help="Which side to generate a case for",
    )

    args = parser.parse_args()

    side = Side.PRO if args.side == "pro" else Side.CON

    print(f"\nGenerating {args.side.upper()} case for: {args.resolution}\n")
    print("This may take a moment...\n")

    try:
        case = generate_case(args.resolution, side)
        print(case.format())
    except Exception as e:
        print(f"Error generating case: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
