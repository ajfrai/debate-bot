"""Interactive input system for debate speeches with word counting."""

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style
from pygments.lexers.markup import MarkdownLexer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text


def count_words(text: str) -> int:
    """Count words in text."""
    if not text.strip():
        return 0
    return len(text.split())


def get_multiline_speech(
    speech_type: str,
    time_seconds: int,
    target_word_count: int = None,
) -> str:
    """Get multiline speech input with word counter.

    Args:
        speech_type: Type of speech (e.g., "Constructive", "Rebuttal")
        time_seconds: Time limit in seconds
        target_word_count: Optional target word count (calculated from time if not provided)

    Returns:
        The complete speech text
    """
    console = Console()

    # Calculate target word count if not provided (150 wpm speaking rate)
    if target_word_count is None:
        target_word_count = int((time_seconds / 60) * 150)

    # Display header
    time_minutes = time_seconds // 60
    console.print()
    console.print(Panel(
        f"[bold cyan]{speech_type}[/bold cyan] - {time_minutes} minute{'s' if time_minutes != 1 else ''}\n"
        f"Target: ~{target_word_count} words (at 150 wpm)\n\n"
        f"[dim]Type your speech below. Press ESC then Enter when finished.[/dim]",
        style="bold blue",
        expand=False,
    ))
    console.print()

    # Create key bindings
    kb = KeyBindings()

    @kb.add('escape', 'enter')
    def _(event):
        """Exit on ESC + Enter."""
        event.app.exit()

    # Create custom bottom toolbar that shows word count
    def bottom_toolbar():
        text = session.default_buffer.text
        word_count = count_words(text)

        # Color based on progress
        if word_count < target_word_count * 0.8:
            color = '#888888'  # Gray
        elif word_count < target_word_count * 0.95:
            color = '#ffa500'  # Orange
        elif word_count <= target_word_count * 1.1:
            color = '#00ff00'  # Green
        else:
            color = '#ff0000'  # Red

        return HTML(
            f' <b>Words:</b> <style fg="{color}">{word_count}</style> / ~{target_word_count} '
            f'<b>|</b> ESC + Enter to finish'
        )

    # Create style
    style = Style.from_dict({
        'bottom-toolbar': '#333333 bg:#88ff88',
    })

    # Create session
    session = PromptSession(
        multiline=True,
        key_bindings=kb,
        bottom_toolbar=bottom_toolbar,
        lexer=PygmentsLexer(MarkdownLexer),
        style=style,
    )

    try:
        text = session.prompt('> ')
        word_count = count_words(text)

        # Show summary
        console.print()
        if word_count < target_word_count * 0.7:
            console.print(f"[yellow]⚠[/yellow] Speech recorded: {word_count} words (shorter than target)")
        elif word_count > target_word_count * 1.3:
            console.print(f"[yellow]⚠[/yellow] Speech recorded: {word_count} words (longer than target)")
        else:
            console.print(f"[green]✓[/green] Speech recorded: {word_count} words")
        console.print()

        return text

    except (EOFError, KeyboardInterrupt):
        console.print("\n[red]Input cancelled[/red]\n")
        return ""


def display_speech_header(speech_type: str, speaker: str, time_seconds: int):
    """Display a formatted header for a speech.

    Args:
        speech_type: Type of speech
        speaker: Who is speaking (e.g., "You", "AI Opponent")
        time_seconds: Time limit
    """
    console = Console()
    time_minutes = time_seconds // 60

    console.print()
    console.print("=" * 60)
    console.print(f"[bold]{speaker}: {speech_type}[/bold] ({time_minutes} minute{'s' if time_minutes != 1 else ''})")
    console.print("=" * 60)
    console.print()


def display_crossfire_header(cf_type: str, time_seconds: int):
    """Display a formatted header for crossfire.

    Args:
        cf_type: Type of crossfire (e.g., "First", "Second", "Grand")
        time_seconds: Time limit
    """
    console = Console()
    time_minutes = time_seconds // 60

    console.print()
    console.print("=" * 60)
    console.print(f"[bold cyan]CROSSFIRE: {cf_type.title()}[/bold cyan] ({time_minutes} minute{'s' if time_minutes != 1 else ''})")
    console.print("=" * 60)
    console.print("[dim]Answer opponent questions and ask your own strategic questions.[/dim]")
    console.print()


def get_single_line_input(prompt_text: str) -> str:
    """Get single-line input with rich prompt.

    Args:
        prompt_text: Prompt to display

    Returns:
        User input
    """
    console = Console()
    session = PromptSession()

    try:
        return session.prompt(HTML(f'<b>{prompt_text}</b> '))
    except (EOFError, KeyboardInterrupt):
        console.print("\n[red]Input cancelled[/red]")
        return ""
