"""Command-line interface for the meeting agent."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax

from .agent import MeetingAgent
from .parser import TranscriptParser

console = Console()


@click.group()
def cli() -> None:
    """Meeting Agent - AI-powered meeting assistant."""


@cli.command()
@click.argument("transcript", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--output",
    "-o",
    default="meeting-notes.md",
    show_default=True,
    help="Path for the meeting notes Markdown output.",
)
@click.option(
    "--email",
    "-e",
    default="followup.md",
    show_default=True,
    help="Path for the follow-up email draft Markdown output.",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Claude model to use.",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    default=None,
    help="Anthropic API key (defaults to ANTHROPIC_API_KEY env var).",
)
@click.option(
    "--pre-process / --no-pre-process",
    default=True,
    show_default=True,
    help="Pre-process transcript with TranscriptParser before sending to agent.",
)
def process(
    transcript: str,
    output: str,
    email: str,
    model: str,
    api_key: str | None,
    pre_process: bool,
) -> None:
    """Process TRANSCRIPT and extract meeting insights.

    Reads the transcript file, calls the AI agent to extract decisions,
    action items and open questions, then writes structured meeting notes
    to OUTPUT and a follow-up email draft to EMAIL.

    Example:

    \b
        meeting-agent process standup.txt --output notes.md --email email.md
    """
    transcript_path = Path(transcript)

    # ------------------------------------------------------------------
    # Optional pre-processing
    # ------------------------------------------------------------------
    if pre_process:
        raw_text = transcript_path.read_text(encoding="utf-8")
        parser = TranscriptParser()
        segments = parser.parse(raw_text)
        speakers = parser.speakers(segments)

        if speakers:
            console.print(
                Panel(
                    "[bold]Detected speakers:[/bold] "
                    + ", ".join(f"[cyan]{s}[/cyan]" for s in speakers),
                    title="Transcript analysis",
                    border_style="blue",
                )
            )

        cleaned = parser.clean(raw_text)

        # Write cleaned transcript to a temp file so the agent can read it
        cleaned_path = transcript_path.with_suffix(".cleaned.txt")
        cleaned_path.write_text(cleaned, encoding="utf-8")
        effective_path = str(cleaned_path)
        console.print(
            f"[dim]Pre-processed transcript written to {cleaned_path}[/dim]"
        )
    else:
        effective_path = str(transcript_path.resolve())

    # ------------------------------------------------------------------
    # Run the agent
    # ------------------------------------------------------------------
    agent = MeetingAgent(api_key=api_key, model=model)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(description="Analysing transcript with AI...", total=None)
        try:
            result = agent.process(
                transcript_path=effective_path,
                output_path=output,
                email_path=email,
            )
        except Exception as exc:  # noqa: BLE001
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    # ------------------------------------------------------------------
    # Report results
    # ------------------------------------------------------------------
    console.print()
    console.print(
        Panel(
            f"[green]Meeting notes[/green] saved to [bold]{result['notes_path']}[/bold]\n"
            f"[green]Follow-up email[/green] saved to [bold]{result['email_path']}[/bold]",
            title="[bold green]Done![/bold green]",
            border_style="green",
        )
    )

    # Preview the notes
    notes_file = Path(result["notes_path"])
    if notes_file.exists():
        console.print()
        console.print("[bold]Meeting notes preview:[/bold]")
        preview = notes_file.read_text(encoding="utf-8")[:2000]
        console.print(Syntax(preview, "markdown", theme="monokai", word_wrap=True))

    # Clean up temp file
    if pre_process and cleaned_path.exists():
        cleaned_path.unlink(missing_ok=True)


@cli.command()
@click.argument("transcript", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--window",
    "-w",
    default=10,
    show_default=True,
    help="Time window size in minutes for segmentation.",
)
def inspect(
    transcript: str,
    window: int,
) -> None:
    """Inspect TRANSCRIPT structure without running the AI agent.

    Displays detected speakers and time-based segments.
    """
    raw = Path(transcript).read_text(encoding="utf-8")
    parser = TranscriptParser()
    segments = parser.parse(raw)

    console.print(f"\n[bold]Total segments:[/bold] {len(segments)}")

    speakers = parser.speakers(segments)
    console.print(f"[bold]Speakers ({len(speakers)}):[/bold] " + ", ".join(speakers))

    windows = parser.segment_by_time(segments, window_minutes=window)
    console.print(f"[bold]Time windows ({window}min each):[/bold] {len(windows)}\n")

    for idx, win in enumerate(windows, 1):
        console.print(f"  [cyan]Window {idx}[/cyan] ({len(win)} segments)")
        for seg in win[:3]:
            preview = seg.text[:80] + ("..." if len(seg.text) > 80 else "")
            console.print(f"    [{seg.timestamp}] [yellow]{seg.speaker}[/yellow]: {preview}")
        if len(win) > 3:
            console.print(f"    [dim]... and {len(win) - 3} more[/dim]")


def main() -> None:
    """Entry point for the meeting-agent CLI."""
    cli()


if __name__ == "__main__":
    main()
