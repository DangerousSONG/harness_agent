import tempfile
import unittest
from pathlib import Path

from runtime.promotion_browser import PromotionBrowser
from scripts.seed_self_evolution_demo import seed_demo


class SeedSelfEvolutionDemoTests(unittest.TestCase):
    def test_seed_generates_consistent_learning_and_promo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = seed_demo(root, "markdown_writer")

            learning_id = result["learning_record_id"]
            promo_id = result["promo_id"]
            learning_path = root / "skills" / "markdown_writer" / "memory" / "LEARNINGS.md"
            promo_path = root / ".skills_memory" / "PROMOTION_CANDIDATES.md"

            self.assertRegex(learning_id, r"LRN-[A-Z0-9]{8}")
            self.assertRegex(promo_id, r"PROMO-[A-Z0-9]{8}")
            self.assertIn(learning_id, learning_path.read_text(encoding="utf-8"))
            self.assertIn(promo_id, promo_path.read_text(encoding="utf-8"))
            self.assertIn(f"- Record ID: {learning_id}", promo_path.read_text(encoding="utf-8"))

            browser = PromotionBrowser(
                skills_dir=root / "skills",
                global_memory_dir=root / ".skills_memory",
                project_root=root,
            )
            promo = browser.get_candidate(promo_id)
            self.assertIsNotNone(promo)
            self.assertTrue(promo.source_memory_exists)
            self.assertEqual(promo.missing_source_memory_ids, [])
            self.assertNotEqual(promo.promotion_decision, "legacy")
            self.assertNotEqual(promo.promotion_score, "legacy")
            self.assertNotEqual(promo.eligible_target, "legacy")


if __name__ == "__main__":
    unittest.main()
