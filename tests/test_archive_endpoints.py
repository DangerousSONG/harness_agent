"""Archive endpoints + their lifecycle effect.

The "delete" affordance on the Assets page surfaces ``POST
/api/skills/{name}/archive`` and ``POST /api/tools/{name}/archive``.
Both endpoints flip the lifecycle marker to ``archived`` so the
SkillProfileStore / ToolRegistry runtime gates stop loading /
executing the asset, while the files themselves remain on disk for
audit and recovery.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from runtime.asset_lifecycle import LifecycleStore
from web.server import create_app


def _seed_skill(root: Path, name: str = "markdown_writer") -> None:
    skill_dir = root / "skills" / name
    (skill_dir / "memory").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: " + name + "\n---\n\n# " + name + "\n",
        encoding="utf-8",
    )


def _seed_tool(root: Path, name: str = "weather_query") -> None:
    tool_dir = root / "tools" / name
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.yaml").write_text(
        "name: " + name + "\nentry_type: http_get\n",
        encoding="utf-8",
    )


class ArchiveEndpointTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "skills").mkdir()
        (self.root / "tools").mkdir()
        (self.root / ".skills_memory").mkdir()
        self.app = create_app(self.root)
        self.client = TestClient(self.app)

    # ----------------------------------------------------------- skill

    def test_archiving_skill_marks_lifecycle_and_hides_from_router(self) -> None:
        _seed_skill(self.root, "markdown_writer")

        response = self.client.post("/api/skills/markdown_writer/archive")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["data"]["lifecycle_status"], "archived")

        record = LifecycleStore(self.root).read("skill", "markdown_writer")
        self.assertIsNotNone(record)
        self.assertEqual(record.lifecycle_status, "archived")

        # Files stay on disk so audit + version trails remain intact.
        self.assertTrue((self.root / "skills" / "markdown_writer" / "SKILL.md").exists())

        # SkillProfileStore drops archived skills so the router never
        # surfaces them.
        from runtime.skill_profile import SkillProfileStore
        names = {p.skill_name for p in SkillProfileStore(self.root / "skills").list_profiles()}
        self.assertNotIn("markdown_writer", names)

    def test_archive_unknown_skill_returns_404(self) -> None:
        response = self.client.post("/api/skills/does_not_exist/archive")
        self.assertEqual(response.status_code, 404)

    def test_double_archive_is_idempotent(self) -> None:
        _seed_skill(self.root, "report_writer")
        first = self.client.post("/api/skills/report_writer/archive").json()
        second = self.client.post("/api/skills/report_writer/archive").json()
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["data"]["lifecycle_status"], "archived")
        # Second call mentions it was already archived rather than
        # re-running the write path.
        self.assertIn("已经处于已归档", second["message"])

    # ------------------------------------------------------------ tool

    def test_archiving_tool_blocks_execution(self) -> None:
        from runtime.tool_registry import ToolRegistry

        _seed_tool(self.root, "weather_query")
        response = self.client.post("/api/tools/weather_query/archive")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["lifecycle_status"], "archived")

        registry = ToolRegistry(
            self.root,
            handlers={"weather_query": lambda inputs: {"ok": True, "data": "x"}},
        )
        result = registry.run("weather_query", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "TOOL_NOT_ACTIVE")

    # -------------------------------------------------- audit / refresh

    def test_archive_writes_audit_log_entry(self) -> None:
        _seed_skill(self.root, "scratch_skill")
        self.client.post("/api/skills/scratch_skill/archive")

        # The operation log lives under .audit/operations.jsonl in the
        # standard server wiring; tolerate either single-file or per-
        # entry layouts and just look for ``skill.archive``.
        audit_dir = self.root / ".audit"
        self.assertTrue(audit_dir.exists())
        found = False
        for path in audit_dir.rglob("*"):
            if path.is_file():
                try:
                    body = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "skill.archive" in body and "scratch_skill" in body:
                    found = True
                    break
        self.assertTrue(found, "expected skill.archive audit entry")


if __name__ == "__main__":
    unittest.main()
