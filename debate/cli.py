"""CLI entry point for the debate training tool."""

import argparse
import sys

from rich.console import Console

from debate.case_generator import generate_case
from debate.evidence_storage import (
    find_evidence_bucket,
    list_debate_files,
    list_evidence_buckets,
    load_debate_file,
    save_evidence_bucket,
)
from debate.models import Side
from debate.research_agent import research_evidence
from debate.round_controller import RoundController


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
        debate_file = research_evidence(
            resolution=args.resolution,
            side=side,
            topic=args.topic,
            num_cards=args.num_cards,
            search_query=args.query,
        )

        print(f"\n✓ Debate file now contains {len(debate_file.cards)} total cards")

        # Show table of contents
        print("\n" + debate_file.get_table_of_contents())

        # Show the newly added cards
        sections = debate_file.get_sections_for_side(side)
        for section in sections:
            if section.argument.lower() == args.topic.lower():
                print(f"\n{'=' * 60}")
                print(f"{section.get_heading()}")
                print('=' * 60)
                for card_id in section.card_ids:
                    card = debate_file.get_card(card_id)
                    if card:
                        print(f"\n[{card_id}] {card.tag}")
                        if card.purpose:
                            print(f"Purpose: {card.purpose}")
                        print("-" * 40)
                        print(card.format_full())
                        print()

    except Exception as e:
        print(f"Error researching evidence: {e}", file=sys.stderr)
        sys.exit(1)


def _find_matching_debate_file(query: str, debate_files: list[dict]):
    """Find a debate file by number or partial match."""
    # Try as number first
    try:
        idx = int(query) - 1
        if 0 <= idx < len(debate_files):
            return debate_files[idx]
    except ValueError:
        pass

    # Try exact match
    for df in debate_files:
        if df["resolution"].lower() == query.lower():
            return df

    # Try partial match (case-insensitive)
    query_lower = query.lower()
    matches = [df for df in debate_files if query_lower in df["resolution"].lower()]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"\nMultiple matches for '{query}':")
        for i, df in enumerate(matches, 1):
            print(f"  {i}. {df['resolution']}")
        return None

    return None


def cmd_evidence(args) -> None:
    """List or view evidence (debate files)."""
    debate_files = list_debate_files()

    if args.query:
        # User provided a query - find matching debate file
        match = _find_matching_debate_file(args.query, debate_files)

        if match:
            debate_file = load_debate_file(match["resolution"])
            if debate_file:
                print(debate_file.render_full_file())
                return

        # Try legacy buckets with exact resolution match
        buckets = list_evidence_buckets(resolution=args.query)
        if buckets:
            print(f"\nEvidence for: {args.query} (legacy format)\n")
            for bucket_info in buckets:
                print(f"  [{bucket_info['side'].upper()}] {bucket_info['topic']}")
                print(f"      {bucket_info['num_cards']} cards")
            return

        if not match:
            print(f"\nNo evidence found matching: {args.query}")
            print("Use 'debate evidence' to list available resolutions.\n")
            return

    else:
        # No query - list all with numbers for easy selection
        if debate_files:
            print("\nDebate Files (use number or keyword to view):\n")
            for i, file_info in enumerate(debate_files, 1):
                print(f"  [{i}] {file_info['resolution']}")
                print(f"      {file_info['num_cards']} cards | PRO: {file_info['num_pro_sections']} sections | CON: {file_info['num_con_sections']} sections")
                print()
            print("Example: debate evidence 1")
            print("Example: debate evidence tiktok")

        # Also show legacy buckets if any
        buckets = list_evidence_buckets()
        legacy_only = [b for b in buckets if not any(
            d['resolution'] == b['resolution'] for d in debate_files
        )]

        if legacy_only:
            print("\nLegacy Evidence Buckets:\n")
            by_resolution = {}
            for bucket_info in legacy_only:
                res = bucket_info["resolution"]
                if res not in by_resolution:
                    by_resolution[res] = []
                by_resolution[res].append(bucket_info)

            for resolution, res_buckets in by_resolution.items():
                print(f"  {resolution}")
                for bucket_info in res_buckets:
                    print(f"    [{bucket_info['side'].upper()}] {bucket_info['topic']} ({bucket_info['num_cards']} cards)")
                print()

        if not debate_files and not buckets:
            print("\nNo evidence found.")
            print("Run 'debate research' to cut evidence cards.\n")


def cmd_run(args) -> None:
    """Run a complete debate round."""
    side = Side.PRO if args.side == "pro" else Side.CON

    print(f"\nStarting debate round: {args.resolution}")
    print(f"You are debating {args.side.upper()}\n")

    # Initialize and run the round (AI case generated automatically)
    try:
        controller = RoundController(
            resolution=args.resolution,
            user_side=side,
            user_case=None,  # User delivers their constructive as a speech
            ai_case=None,  # Generated automatically by controller
        )

        decision = controller.run_round()

        # Print final summary with rich formatting
        console = Console()
        console.print("\n" + "=" * 60)
        console.print("[bold yellow]FINAL RESULT[/bold yellow]")
        console.print("=" * 60)

        # Highlight winner
        winner_color = "green" if decision.winning_team == "Team A" else "blue"
        console.print(f"[bold {winner_color}]Winner: {decision.winning_team} ({decision.winner.value.upper()})[/bold {winner_color}]")

        console.print("\n[bold]Voting Issues:[/bold]")
        for i, issue in enumerate(decision.voting_issues, 1):
            console.print(f"  {i}. {issue}")

        console.print("\n[bold]Feedback:[/bold]")
        for feedback in decision.feedback:
            console.print(f"  • {feedback}")
        console.print()

    except Exception as e:
        console = Console()
        console.print(f"[red]Error running debate:[/red] {e}", file=sys.stderr)
        sys.exit(1)


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
        help="List or view evidence (use number or keyword)",
        aliases=["ev"],
    )
    evidence_parser.add_argument(
        "query",
        type=str,
        nargs="?",
        help="Resolution number, keyword, or full name (optional - lists all if omitted)",
    )
    evidence_parser.set_defaults(func=cmd_evidence)

    # Run command (debate round)
    run_parser = subparsers.add_parser(
        "run",
        help="Run a complete debate round against the AI",
    )
    run_parser.add_argument(
        "resolution",
        type=str,
        help="The debate resolution",
    )
    run_parser.add_argument(
        "--side",
        type=str,
        choices=["pro", "con"],
        required=True,
        help="Which side you will debate",
    )
    run_parser.set_defaults(func=cmd_run)

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
