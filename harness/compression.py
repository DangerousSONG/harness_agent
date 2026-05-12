# harness/compression.py
# === SECTION: compression (s06) ===
import json
import time
from pathlib import Path


def estimate_tokens(messages: list) -> int:
    """
    Rough token estimator.
    1 token ≈ 4 chars is enough for local compaction trigger.
    """
    return len(json.dumps(messages, default=str, ensure_ascii=False)) // 4


def microcompact(messages: list):
    """
    Lightly clear old large tool outputs.

    Supports both:
    1. old Anthropic-style tool_result blocks:
       {"role": "user", "content": [{"type": "tool_result", ...}]}

    2. OpenAI-style tool messages:
       {"role": "tool", "content": "..."}
    """
    tool_parts = []

    for msg in messages:
        # OpenAI-style tool result
        if msg.get("role") == "tool":
            tool_parts.append(msg)
            continue

        # Anthropic-style tool_result block, kept for compatibility
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    tool_parts.append(part)

    if len(tool_parts) <= 3:
        return

    for part in tool_parts[:-3]:
        content = part.get("content")

        if isinstance(content, str) and len(content) > 100:
            part["content"] = "[cleared]"


def auto_compact(
    *,
    messages: list,
    client,
    model: str,
    transcript_dir: Path,
) -> list:
    """
    Save full transcript, ask model to summarize recent context,
    then return compressed message list.
    """
    transcript_dir.mkdir(parents=True, exist_ok=True)

    path = transcript_dir / f"transcript_{int(time.time())}.jsonl"

    with open(path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str, ensure_ascii=False) + "\n")

    conv_text = json.dumps(messages, default=str, ensure_ascii=False)[-80000:]

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    "Summarize the following conversation for continuity. "
                    "Preserve current goals, constraints, decisions, open tasks, "
                    "important files, tool results, and next steps.\n\n"
                    f"{conv_text}"
                ),
            }
        ],
        max_tokens=2000,
    )

    summary = response.choices[0].message.content or "(empty summary)"

    return [
        {
            "role": "user",
            "content": f"[Compressed. Transcript: {path}]\n{summary}",
        }
    ]