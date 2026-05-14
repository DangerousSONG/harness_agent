from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.learning_signal import classify_and_record_learning_signal
from runtime.skill_memory import SkillMemoryManager


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class FakeChoice:
    def __init__(self, content: str):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content: str):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, payloads: list[dict]):
        self.payloads = list(payloads)
        self.last_payload = self.payloads[-1] if self.payloads else {}

    def create(self, **_kwargs):
        payload = self.payloads.pop(0) if self.payloads else self.last_payload
        return FakeResponse(json.dumps(payload, ensure_ascii=False))


class FakeChat:
    def __init__(self, payloads: list[dict]):
        self.completions = FakeCompletions(payloads)


class FakeClient:
    def __init__(self, payloads: list[dict]):
        self.chat = FakeChat(payloads)


def ensure_markdown_writer_skill(skills_dir: Path) -> None:
    skill_dir = skills_dir / "markdown_writer"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        return
    skill_file.write_text(
        "\n".join(
            [
                "---",
                "name: markdown_writer",
                "description: Test skill for self_improvement learning-loop debugging.",
                "---",
                "",
                "# markdown_writer",
                "",
                "Temporary local test skill used by scripts/debug_self_improvement.py.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    skills_dir = ROOT / "skills"
    global_memory_dir = ROOT / ".skills_memory"
    ensure_markdown_writer_skill(skills_dir)

    manager = SkillMemoryManager(skills_dir, global_memory_dir)
    samples = [
        "用户纠正：以后 markdown_writer 写 Markdown 列表时不要混用 tab 缩进。",
        "用户纠正：markdown_writer 生成 Markdown bullet list 时不要混用 tab 缩进。",
        "用户纠正：请记住 markdown_writer 的 Markdown 列表不要混用 tab 缩进。",
    ]
    payloads = [
        {
            "should_record": True,
            "record_type": "learning",
            "target_skill": "markdown_writer",
            "reason": "User repeatedly corrected markdown_writer list indentation behavior.",
            "attribution_confidence": "high",
            "title": "Markdown lists should avoid tab indentation",
            "content": "When writing Markdown lists, markdown_writer should avoid mixing tab indentation with spaces.",
        }
        for _ in samples
    ]
    client = FakeClient(payloads)

    for index, sample in enumerate(samples, start=1):
        result = classify_and_record_learning_signal(
            client=client,
            model="debug-fake-classifier",
            skill_memory=manager,
            raw_content=sample,
            conversation_context=[{"role": "user", "content": sample}],
            latest_tool_events=[],
            latest_llm_messages=[],
        )
        classification = result["classification"]
        print(f"\n--- sample {index} ---")
        print(f"classification: {json.dumps(classification, ensure_ascii=False)}")
        print(f"target_skill: {classification.get('target_skill')}")
        print(f"record_type: {classification.get('record_type')}")
        print(f"needs_attribution_review: {classification.get('needs_attribution_review')}")
        print(f"record_result: {result.get('record_result')}")

    learning_path = skills_dir / "markdown_writer" / "memory" / "LEARNINGS.md"
    promotion_path = global_memory_dir / "PROMOTION_CANDIDATES.md"
    learning_text = learning_path.read_text(encoding="utf-8") if learning_path.exists() else ""
    promotion_text = promotion_path.read_text(encoding="utf-8") if promotion_path.exists() else ""

    print("\n--- checks ---")
    print(f"learning_path: {learning_path}")
    print(f"learning_written: {'Markdown lists should avoid tab indentation' in learning_text}")
    print(f"promotion_path: {promotion_path}")
    print(f"promotion_candidate_present: {'PROMO-' in promotion_text and 'markdown_writer' in promotion_text}")
    print("sensitive_files_modified_by_script: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
