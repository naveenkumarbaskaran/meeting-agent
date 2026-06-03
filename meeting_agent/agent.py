"""MeetingAgent: extracts structured insights from meeting transcripts using Claude."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You are an expert meeting assistant. Your job is to analyse meeting transcripts and
produce clear, actionable summaries.

When given a transcript you MUST use the available tools to:
1. Read the transcript file to obtain its contents.
2. Extract and structure the following information:
   - **Decisions made** during the meeting (concrete agreements or choices).
   - **Action items** – each item must have an *owner* (person responsible) and a
     *deadline* (date or relative time, e.g. "end of week"). If no deadline is
     mentioned, write "TBD".
   - **Open questions** that were raised but not resolved.
   - A polished **follow-up email draft** addressed to all attendees that summarises
     the above and thanks them for their time.
3. Write the meeting notes to the requested output file.
4. Write the follow-up email to the requested email file.

Format your notes as well-structured Markdown. Be concise but comprehensive.
"""


def _read_transcript(path: str) -> str:
    """Read a transcript file and return its contents as a string."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return f"ERROR: File not found: {path}"
    try:
        return resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return f"ERROR reading file: {exc}"


def _write_file(path: str, content: str) -> str:
    """Write *content* to *path*, creating parent directories as needed."""
    resolved = Path(path).expanduser().resolve()
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"OK: wrote {len(content)} characters to {path}"
    except OSError as exc:
        return f"ERROR writing file: {exc}"


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOLS: list[anthropic.types.ToolParam] = [
    {
        "name": "read_transcript",
        "description": (
            "Read the contents of a meeting transcript file from disk. "
            "Returns the full text of the file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the transcript file.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write text content to a file on disk. "
            "Creates parent directories if they do not exist. "
            "Use this to save meeting notes and the follow-up email."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Destination file path.",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
]


def _dispatch_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Execute a tool by name and return a string result."""
    if name == "read_transcript":
        return _read_transcript(tool_input["path"])
    if name == "write_file":
        return _write_file(tool_input["path"], tool_input["content"])
    return f"ERROR: Unknown tool '{name}'"


# ---------------------------------------------------------------------------
# MeetingAgent
# ---------------------------------------------------------------------------


class MeetingAgent:
    """Agent that processes a meeting transcript and produces structured outputs.

    Parameters
    ----------
    api_key:
        Anthropic API key.  Defaults to the ``ANTHROPIC_API_KEY`` environment
        variable when *None*.
    model:
        Claude model identifier to use.
    max_tokens:
        Maximum tokens for each model response.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = MODEL,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        transcript_path: str,
        output_path: str,
        email_path: str,
    ) -> dict[str, str]:
        """Process a meeting transcript and write outputs.

        Parameters
        ----------
        transcript_path:
            Path to the plain-text or Markdown transcript file.
        output_path:
            Destination path for the meeting notes Markdown file.
        email_path:
            Destination path for the follow-up email Markdown file.

        Returns
        -------
        dict
            Keys ``"notes_path"`` and ``"email_path"`` pointing to the
            written files, plus ``"summary"`` with a brief status message.
        """
        user_message = (
            f"Please process the meeting transcript at '{transcript_path}'.\n"
            f"Write the structured meeting notes (decisions, action items, open "
            f"questions) as Markdown to '{output_path}'.\n"
            f"Write the follow-up email draft as Markdown to '{email_path}'."
        )

        messages: list[anthropic.types.MessageParam] = [
            {"role": "user", "content": user_message}
        ]

        # Agentic loop -------------------------------------------------------
        while True:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            # Append assistant turn to history
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract the final text summary if present
                summary = next(
                    (
                        block.text
                        for block in response.content
                        if hasattr(block, "text")
                    ),
                    "Processing complete.",
                )
                return {
                    "notes_path": output_path,
                    "email_path": email_path,
                    "summary": summary,
                }

            if response.stop_reason == "tool_use":
                tool_results: list[anthropic.types.ToolResultBlockParam] = []
                for block in response.content:
                    if block.type == "tool_use":
                        result_text = _dispatch_tool(
                            block.name,
                            dict(block.input),  # type: ignore[arg-type]
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            }
                        )
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason – surface as an error
            raise RuntimeError(
                f"Unexpected stop_reason '{response.stop_reason}' from Claude."
            )
