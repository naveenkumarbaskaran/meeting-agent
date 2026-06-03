# Meeting Agent AI

AI-powered meeting assistant that transcribes audio, extracts action items, and writes follow-up emails — powered by [Claude](https://www.anthropic.com/claude) via the Anthropic SDK.

## Features

- **Structured extraction** — Automatically identifies decisions made, action items (with owner + deadline), and open questions.
- **Follow-up email** — Generates a polished draft email summarising the meeting.
- **Transcript parsing** — Pre-processes raw transcripts: detects speakers, segments by time window, and strips filler words (uh, um, you know…).
- **Rich CLI** — Colourful terminal output with a live spinner, speaker list preview, and notes preview.

## Installation

```bash
pip install meeting-agent-ai
```

Or install from source:

```bash
git clone https://github.com/example/meeting-agent-ai
cd meeting-agent-ai
pip install -e .
```

## Quick start

### 1. Set your API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 2. Process a transcript

```bash
meeting-agent process standup.txt --output meeting-notes.md --email followup.md
```

The agent will:
1. Read and pre-process the transcript (speaker detection, filler-word removal).
2. Call Claude (`claude-sonnet-4-6`) to extract structured insights.
3. Write `meeting-notes.md` with decisions, action items, and open questions.
4. Write `followup.md` with a ready-to-send email draft.

### 3. Inspect a transcript (without AI)

```bash
meeting-agent inspect standup.txt --window 5
```

Displays detected speakers and time-windowed segments.

## CLI reference

### `meeting-agent process`

```
Usage: meeting-agent process [OPTIONS] TRANSCRIPT

  Process TRANSCRIPT and extract meeting insights.

Arguments:
  TRANSCRIPT  Path to the plain-text transcript file.  [required]

Options:
  -o, --output PATH        Path for the meeting notes output.  [default: meeting-notes.md]
  -e, --email PATH         Path for the follow-up email draft.  [default: followup.md]
  --model TEXT             Claude model to use.  [default: claude-sonnet-4-6]
  --api-key TEXT           Anthropic API key (or set ANTHROPIC_API_KEY).
  --pre-process / --no-pre-process
                           Pre-process transcript before sending to agent.  [default: pre-process]
  --help                   Show this message and exit.
```

### `meeting-agent inspect`

```
Usage: meeting-agent inspect [OPTIONS] TRANSCRIPT

  Inspect TRANSCRIPT structure without running the AI agent.

Arguments:
  TRANSCRIPT  Path to the transcript file.  [required]

Options:
  -w, --window INTEGER  Time window size in minutes.  [default: 10]
  --help                Show this message and exit.
```

## Transcript format

The parser handles several common formats:

```
# Format 1 — timestamp then speaker
[00:01:30] Alice: Let's review the sprint goals.
[00:01:45] Bob: I finished the auth module yesterday.

# Format 2 — speaker then timestamp
Alice [00:01:30]: Let's review the sprint goals.

# Format 3 — timestamp dash speaker
00:01:30 - Alice: Let's review the sprint goals.

# Format 4 — simple speaker labels (no timestamp)
Alice: Let's review the sprint goals.
Bob: I finished the auth module yesterday.
```

## Example output

### `meeting-notes.md`

```markdown
# Meeting Notes — 2024-01-15

## Decisions
- Adopt trunk-based development for the backend team.
- Delay the v2 launch to Q2 to allow additional testing.

## Action Items
| Owner  | Task                                    | Deadline       |
|--------|-----------------------------------------|----------------|
| Alice  | Update the deployment runbook           | Friday EOD     |
| Bob    | Migrate auth service to the new pattern | End of sprint  |
| Carol  | Schedule stakeholder review             | TBD            |

## Open Questions
- Which monitoring provider will we use post-migration?
- Do we need a dedicated QA environment for the v2 branch?
```

### `followup.md`

```markdown
Subject: Meeting follow-up — Sprint Planning 2024-01-15

Hi team,

Thank you for joining today's sprint planning session. Here's a quick summary…
```

## Architecture

```
CLI (click + rich)
  └── MeetingAgent
        ├── Anthropic SDK  (claude-sonnet-4-6)
        ├── Tool: read_transcript  → reads file from disk
        └── Tool: write_file       → writes notes / email

TranscriptParser  (standalone, no API calls)
  ├── parse()          → list[Segment]
  ├── speakers()       → list[str]
  ├── clean()          → cleaned transcript string
  ├── by_speaker()     → dict[str, list[Segment]]
  └── segment_by_time()→ list[list[Segment]]
```

`MeetingAgent` runs a standard agentic loop: it sends the user request to Claude, handles `tool_use` responses by dispatching to local Python functions (`read_transcript`, `write_file`), feeds results back, and loops until Claude signals `end_turn`.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy meeting_agent
```

## License

MIT
