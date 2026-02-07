"""Prompt Editor web app server."""

import json
import re
import subprocess
import time
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Prompt Editor")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Reasonable defaults for template variables
VARIABLE_DEFAULTS: dict[str, str] = {
    "resolution": "Resolved: The United States federal government should substantially increase its regulation of artificial intelligence.",
    "side": "PRO",
    "side_description": "affirms the resolution",
    "side_instruction": "Argue in favor of the resolution",
    "side_value": "PRO",
    "time_limit_seconds": "240",
    "word_limit": "600",
    "num_cards": "3",
    "max_turns": "10",
    "total_cards": "50",
    "goal": "Deliver a compelling rebuttal that attacks opponent arguments and defends your own contentions.",
    "round_context": "[Round context would appear here with prior speeches and crossfire exchanges.]",
    "available_evidence": "[Available evidence cards would appear here.]",
    "evidence_buckets": "[Evidence buckets organized by contention would appear here.]",
    "search_results": "[Search results from Brave API would appear here.]",
    "search_query": "artificial intelligence regulation economic impact",
    "topic": "economic impacts of AI regulation",
    "team_a_side": "PRO",
    "team_b_side": "CON",
    "existing_arguments": "(none yet)",
    "existing_answers": "(none yet)",
    "opponent_side": "CON",
    "argument": "TikTok ban eliminates creator economy jobs",
    "evidence_type": "support",
    "retry_instructions": "",
    "task_lines": "1. [abc123] TikTok ban eliminates creator jobs (evidence: support)\n2. [def456] Platform ban accelerates decentralized adoption (evidence: support)",
}

MODEL_MAP: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-5-20251101",
}


def get_prompt_files() -> list[dict[str, str]]:
    """List all prompt markdown files."""
    files = sorted(PROMPTS_DIR.glob("*.md"))
    return [{"name": f.stem, "filename": f.name} for f in files]


def extract_variables(content: str) -> list[str]:
    """Extract {variable} patterns from prompt content, skipping {{escaped}} braces."""
    # Remove double-brace escapes first
    stripped = content.replace("{{", "").replace("}}", "")
    return sorted(set(re.findall(r"\{(\w+)\}", stripped)))


class RunRequest(BaseModel):
    variables: dict[str, str]
    content: str
    model: str = "sonnet"


class PrRequest(BaseModel):
    content: str


class ChatRequest(BaseModel):
    messages: list[dict[str, str]]
    prompt_content: str


@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text())


@app.get("/api/prompts")
async def list_prompts():
    return get_prompt_files()


@app.get("/api/prompts/{name}")
async def get_prompt(name: str):
    filepath = PROMPTS_DIR / f"{name}.md"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")
    content = filepath.read_text()
    variables = extract_variables(content)
    defaults = {v: VARIABLE_DEFAULTS.get(v, "") for v in variables}
    return {"name": name, "content": content, "variables": variables, "defaults": defaults}


@app.post("/api/prompts/{name}/run")
async def run_prompt(name: str, req: RunRequest):
    # Fill variables into the template
    rendered = req.content
    for var, val in req.variables.items():
        rendered = rendered.replace(f"{{{var}}}", val)

    model_id = MODEL_MAP.get(req.model, MODEL_MAP["sonnet"])
    client = anthropic.Anthropic()

    def stream_response():
        with client.messages.stream(
            model=model_id,
            max_tokens=4096,
            messages=[{"role": "user", "content": rendered}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")


CHAT_SYSTEM_PROMPT = """You are a prompt engineering assistant helping edit debate prompt templates.

The user is working on a prompt template. They may ask you to improve it, fix issues, or make changes.

When you want to suggest an edit to the prompt, use this exact format:

<<<EDIT>>>
<<<OLD>>>
exact text to find in the prompt
<<<NEW>>>
replacement text
<<<END>>>

Rules for edits:
- The OLD text must be an exact match of text in the current prompt
- You can suggest multiple edit blocks in one response
- Explain your reasoning before or after the edit blocks
- Keep edits focused and minimal"""


@app.post("/api/chat")
async def chat(req: ChatRequest):
    client = anthropic.Anthropic()

    system = f"{CHAT_SYSTEM_PROMPT}\n\nCurrent prompt content:\n```\n{req.prompt_content}\n```"

    messages = [{"role": m["role"], "content": m["content"]} for m in req.messages]

    def stream_response():
        with client.messages.stream(
            model=MODEL_MAP["sonnet"],
            max_tokens=4096,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")


@app.post("/api/prompts/{name}/pr")
async def create_pr(name: str, req: PrRequest):
    filepath = PROMPTS_DIR / f"{name}.md"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")

    project_root = Path(__file__).parent.parent.parent
    timestamp = int(time.time())
    branch_name = f"prompt-edit/{name}-{timestamp}"

    def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=check,
        )

    try:
        # Capture current branch
        result = run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        original_branch = result.stdout.strip()

        # Stash any changes
        run_git(["git", "stash"], check=False)

        # Create and switch to new branch
        run_git(["git", "checkout", "-b", branch_name])

        # Write the updated prompt
        filepath.write_text(req.content)

        # Stage and commit
        run_git(["git", "add", str(filepath)])
        run_git(["git", "commit", "-m", f"Update prompt: {name}"])

        # Push
        run_git(["git", "push", "-u", "origin", branch_name])

        # Create PR
        pr_result = run_git(
            [
                "gh",
                "pr",
                "create",
                "--title",
                f"Update prompt: {name}",
                "--body",
                f"Updated prompt template `{name}.md` via Prompt Editor.",
            ]
        )
        pr_url = pr_result.stdout.strip()

        # Return to original branch
        run_git(["git", "checkout", original_branch])
        run_git(["git", "stash", "pop"], check=False)

        return {"pr_url": pr_url}

    except subprocess.CalledProcessError as e:
        # Try to recover to original branch
        run_git(["git", "checkout", original_branch], check=False)
        run_git(["git", "stash", "pop"], check=False)
        raise HTTPException(status_code=500, detail=f"Git error: {e.stderr or e.stdout}") from None
