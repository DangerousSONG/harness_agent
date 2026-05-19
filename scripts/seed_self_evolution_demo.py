from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.promotion_browser import PromotionBrowser
from runtime.skill_memory import SkillMemoryManager, normalize_name


DEMO_TITLE = "Book note structure"
DEMO_CONTENT = (
    "From now on, when markdown_writer writes book-note Markdown, always use "
    "Title / Core Insights / Three Takeaways / Action List."
)


def seed_demo(root: Path | str = ROOT, skill: str = "markdown_writer") -> dict[str, Any]:
    root = Path(root)
    skill_name = normalize_name(skill)
    manager = SkillMemoryManager(root / "skills", root / ".skills_memory")

    messages = []
    for _ in range(3):
        messages.append(
            manager.record_learning(
                skill_name,
                DEMO_TITLE,
                DEMO_CONTENT.replace("markdown_writer", skill_name),
                source="seed_self_evolution_demo",
                attribution_confidence="high",
            )
        )

    browser = PromotionBrowser(
        skills_dir=root / "skills",
        global_memory_dir=root / ".skills_memory",
        project_root=root,
    )
    candidates = [
        candidate
        for candidate in browser.list_candidates()
        if candidate.target_skill == skill_name
        and candidate.source_memory_type == "learning"
        and candidate.promotion_decision
        and candidate.promotion_decision != "legacy"
        and candidate.promotion_score != "legacy"
        and candidate.eligible_target
        and candidate.eligible_target != "legacy"
        and candidate.source_memory_exists
        and candidate.status not in {"archived", "legacy_rejected", "stale", "dangling", "invalid"}
        and DEMO_TITLE in browser.source_memory_text(candidate)
    ]
    if not candidates:
        raise RuntimeError("Failed to generate a healthy eligible PROMO from real learning memory.")

    promo = candidates[-1]
    source_text = browser.source_memory_text(promo)
    source_memory_id = promo.source_memory_ids[0] if promo.source_memory_ids else ""
    if not source_memory_id or source_memory_id not in source_text:
        raise RuntimeError("Generated PROMO does not reference an existing learning record.")

    return {
        "skill": skill_name,
        "learning_record_id": source_memory_id,
        "learning_source": promo.source_memory_file,
        "promo_id": promo.promo_id,
        "promotion_decision": promo.promotion_decision,
        "promotion_score": promo.promotion_score,
        "eligible_target": promo.eligible_target,
        "source_memory_exists": promo.source_memory_exists,
        "messages": messages,
        "next_actions": [
            f"GET /api/promotions",
            f"GET /api/promotions/{promo.promo_id}",
            f"POST /api/promotions/{promo.promo_id}/evolve",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed healthy local SafeHarness self-evolution demo data.",
    )
    parser.add_argument("--skill", default="markdown_writer", help="target skill name")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        result = seed_demo(ROOT, args.skill)
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Seeded healthy self-evolution demo data.")
        print(f"Skill: {result['skill']}")
        print(f"Learning record: {result['learning_record_id']}")
        print(f"PROMO: {result['promo_id']}")
        print(f"Decision: {result['promotion_decision']}")
        print(f"Score: {result['promotion_score']}")
        print(f"Eligible target: {result['eligible_target']}")
        print("Next:")
        for action in result["next_actions"]:
            print(f"- {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
