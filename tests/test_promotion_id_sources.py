import tempfile
import unittest
from pathlib import Path

from runtime.promotion_browser import PromotionBrowser


class PromotionIdSourceTests(unittest.TestCase):
    def test_promotion_browser_reads_real_candidate_id_from_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "skills" / "markdown_writer").mkdir(parents=True)
            memory_dir = root / ".skills_memory"
            memory_dir.mkdir()
            (memory_dir / "PROMOTION_CANDIDATES.md").write_text(
                "\n".join(
                    [
                        "# Promotion Candidates",
                        "",
                        "## PROMO-F2C535BB - Local candidate",
                        "- Candidate ID: PROMO-F2C535BB",
                        "- Record ID: LRN-8D069561",
                        "- Target Skill: markdown_writer",
                        "- Proposed Change Summary: Local candidate",
                        "- Target Files: skills/markdown_writer/SKILL.md",
                        "- Occurrence Count: 3",
                        "- Promotion Score: 0.81",
                        "- Promotion Decision: promote",
                        "- Eligible Target: skill_rule",
                        "- Status: proposed",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            browser = PromotionBrowser(
                skills_dir=root / "skills",
                global_memory_dir=memory_dir,
                project_root=root,
            )
            ids = [candidate.promo_id for candidate in browser.list_candidates()]

            self.assertIn("PROMO-F2C535BB", ids)
            self.assertNotIn("PROMO-F2C53BB", ids)

    def test_ui_sources_do_not_hardcode_stale_promo_id(self):
        root = Path(__file__).resolve().parents[1]
        stale_id = "PROMO-F2C53BB"
        ui_files = list((root / "web" / "ui" / "src").rglob("*.*"))
        ui_text = "\n".join(path.read_text(encoding="utf-8") for path in ui_files)
        api_text = (root / "web" / "ui" / "src" / "lib" / "api.js").read_text(encoding="utf-8")

        self.assertNotIn(stale_id, ui_text)
        self.assertIn("/api/promotions/${encodeURIComponent(id)}/evolve", api_text)


if __name__ == "__main__":
    unittest.main()
