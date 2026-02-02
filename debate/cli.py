"""CLI entry point for the debate training tool."""

import argparse
import sys

from debate.case_generator import generate_case
from debate.evidence_storage import (
    find_evidence_bucket,
    list_evidence_buckets,
    save_evidence_bucket,
)
from debate.models import Side
from debate.research_agent import research_evidence


def cmd_generate(args) -> None:
    """Generate a debate case."""
    side = Side.PRO if args.side == "pro" else Side.CON

    print(f"\nGenerating {args.side.upper()} case for: {args.resolution}\n")

    # Load evidence buckets if requested
    evidence_buckets = []
    if args.with_evidence:
        print("Loading evidence buckets...")
        all_buckets = list_evidence_buckets(resolution=args.resolution)

        # Filter by side
        for bucket_info in all_buckets:
            if bucket_info["side"] == side.value:
                bucket = find_evidence_bucket(
                    args.resolution,
                    side,
                    bucket_info["topic"],
                )
                if bucket:
                    evidence_buckets.append(bucket)
                    print(f"  - Loaded {bucket_info['num_cards']} cards for '{bucket_info['topic']}'")

        if not evidence_buckets:
            print("  No evidence found. Run 'debate research' first to cut evidence cards.")
            print("  Generating case without evidence...\n")
        else:
            print()

    print("This may take a moment...\n")

    try:
        case = generate_case(args.resolution, side, evidence_buckets if evidence_buckets else None)
        print(case.format())
    except Exception as e:
        print(f"Error generating case: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_research(args) -> None:
    """Research evidence for a topic."""
    side = Side.PRO if args.side == "pro" else Side.CON

    print(f"\nResearching evidence for: {args.topic}")
    print(f"Resolution: {args.resolution}")
    print(f"Side: {args.side.upper()}")
    print(f"Cards to cut: {args.num_cards}\n")
    print("This may take a moment...\n")

    try:
        bucket = research_evidence(
            resolution=args.resolution,
            side=side,
            topic=args.topic,
            num_cards=args.num_cards,
            search_query=args.query,
        )

        # Save the bucket
        filepath = save_evidence_bucket(bucket)
        print(f"\n✓ Researched {len(bucket.cards)} evidence cards")
        print(f"✓ Saved to: {filepath}\n")

        # Show table of contents
        print(bucket.get_table_of_contents())
        print()

        # Show each card
        for i, card in enumerate(bucket.cards, 1):
            print(f"\n{'=' * 60}")
            print(f"Card {i}: {card.tag}")
            print('=' * 60)
            print(card.format_full())

    except Exception as e:
        print(f"Error researching evidence: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_evidence(args) -> None:
    """List or view evidence buckets."""
    if args.resolution:
        # List buckets for specific resolution
        buckets = list_evidence_buckets(resolution=args.resolution)

        if not buckets:
            print(f"\nNo evidence found for: {args.resolution}")
            print("Run 'debate research' to cut evidence cards.\n")
            return

        print(f"\nEvidence for: {args.resolution}\n")
        for bucket_info in buckets:
            print(f"  [{bucket_info['side'].upper()}] {bucket_info['topic']}")
            print(f"      {bucket_info['num_cards']} cards")
            print(f"      {bucket_info['filepath']}")
            print()

    else:
        # List all buckets
        buckets = list_evidence_buckets()

        if not buckets:
            print("\nNo evidence found.")
            print("Run 'debate research' to cut evidence cards.\n")
            return

        print("\nAll Evidence Buckets:\n")

        # Group by resolution
        by_resolution = {}
        for bucket_info in buckets:
            res = bucket_info["resolution"]
            if res not in by_resolution:
                by_resolution[res] = []
            by_resolution[res].append(bucket_info)

        for resolution, res_buckets in by_resolution.items():
            print(f"Resolution: {resolution}")
            for bucket_info in res_buckets:
                print(f"  [{bucket_info['side'].upper()}] {bucket_info['topic']} ({bucket_info['num_cards']} cards)")
            print()


def main() -> None:
    """Main entry point for the debate CLI."""
    parser = argparse.ArgumentParser(
        description="Practice Public Forum debate against an AI opponent",
        prog="debate",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Generate command (default behavior)
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate a debate case",
        aliases=["gen"],
    )
    gen_parser.add_argument(
        "resolution",
        type=str,
        help="The debate resolution (e.g., 'Resolved: The US should ban TikTok')",
    )
    gen_parser.add_argument(
        "--side",
        type=str,
        choices=["pro", "con"],
        required=True,
        help="Which side to generate a case for",
    )
    gen_parser.add_argument(
        "--with-evidence",
        action="store_true",
        help="Use researched evidence cards (must run 'debate research' first)",
    )
    gen_parser.set_defaults(func=cmd_generate)

    # Research command
    research_parser = subparsers.add_parser(
        "research",
        help="Research and cut evidence cards",
        aliases=["res"],
    )
    research_parser.add_argument(
        "resolution",
        type=str,
        help="The debate resolution",
    )
    research_parser.add_argument(
        "--side",
        type=str,
        choices=["pro", "con"],
        required=True,
        help="Which side the evidence supports",
    )
    research_parser.add_argument(
        "--topic",
        type=str,
        required=True,
        help="The topic/argument to research (e.g., 'economic impacts', 'national security')",
    )
    research_parser.add_argument(
        "--num-cards",
        type=int,
        default=3,
        help="Number of cards to cut (default: 3, max: 5)",
    )
    research_parser.add_argument(
        "--query",
        type=str,
        help="Custom search query (auto-generated if not provided)",
    )
    research_parser.set_defaults(func=cmd_research)

    # Evidence command
    evidence_parser = subparsers.add_parser(
        "evidence",
        help="List or view evidence buckets",
        aliases=["ev"],
    )
    evidence_parser.add_argument(
        "--resolution",
        type=str,
        help="Filter by resolution",
    )
    evidence_parser.set_defaults(func=cmd_evidence)

    # Parse args
    args = parser.parse_args()

    # Handle legacy format (direct resolution argument without subcommand)
    if not args.command:
        # Check if first arg looks like a resolution (for backwards compatibility)
        if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
            # Legacy format: debate "resolution" --side pro
            # Convert to: debate generate "resolution" --side pro
            sys.argv.insert(1, "generate")
            args = parser.parse_args()
        else:
            parser.print_help()
            sys.exit(1)

    # Call the appropriate function
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
