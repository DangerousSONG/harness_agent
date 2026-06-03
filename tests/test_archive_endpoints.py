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


def _seed_skill(root: Path, name: str = "markdown_writer", *, user_created: bool = True) -> None:
    skill_dir = root / "skills" / name
    (skill_dir / "memory").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: " + name + "\n---\n\n# " + name + "\n",
        encoding="utf-8",
    )
    if user_created:
        LifecycleStore(root).write(
            kind="skill", name=name, lifecycle_status="active",
            provenance="user_created",
        )


def _seed_tool(root: Path, name: str = "weather_query", *, user_created: bool = True) -> None:
    tool_dir = root / "tools" / name
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.yaml").write_text(
        "name: " + name + "\nentry_type: http_get\n",
        encoding="utf-8",
    )
    if user_created:
        LifecycleStore(root).write(
            kind="tool", name=name, lifecycle_status="active",
            provenance="user_created",
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

    # ----------------------------------------------------------- restore

    def test_restore_brings_skill_back_to_active(self) -> None:
        from runtime.skill_profile import SkillProfileStore

        _seed_skill(self.root, "markdown_writer")
        self.client.post("/api/skills/markdown_writer/archive")
        response = self.client.post("/api/skills/markdown_writer/restore")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["lifecycle_status"], "active")

        record = LifecycleStore(self.root).read("skill", "markdown_writer")
        self.assertEqual(record.lifecycle_status, "active")

        names = {p.skill_name for p in SkillProfileStore(self.root / "skills").list_profiles()}
        self.assertIn("markdown_writer", names)

    def test_restore_unknown_skill_returns_404(self) -> None:
        response = self.client.post("/api/skills/missing/restore")
        self.assertEqual(response.status_code, 404)

    def test_double_restore_is_idempotent(self) -> None:
        _seed_skill(self.root, "report_writer")
        self.client.post("/api/skills/report_writer/archive")
        first = self.client.post("/api/skills/report_writer/restore").json()
        second = self.client.post("/api/skills/report_writer/restore").json()
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertIn("已经处于已上架", second["message"])

    # ------------------------------------------------------- hard delete

    def test_hard_delete_archived_skill_removes_files(self) -> None:
        _seed_skill(self.root, "obsolete_skill")
        self.client.post("/api/skills/obsolete_skill/archive")
        response = self.client.delete("/api/skills/obsolete_skill")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(
            (self.root / "skills" / "obsolete_skill").exists(),
            "asset directory must be removed by hard delete",
        )
        # Lifecycle marker also gone (it lived inside the removed dir).
        self.assertIsNone(LifecycleStore(self.root).read("skill", "obsolete_skill"))

    def test_hard_delete_refuses_active_asset(self) -> None:
        _seed_skill(self.root, "still_in_use")
        response = self.client.delete("/api/skills/still_in_use")
        self.assertEqual(response.status_code, 409)
        self.assertTrue((self.root / "skills" / "still_in_use").exists())

    def test_hard_delete_tool_blocks_execution(self) -> None:
        from runtime.tool_registry import ToolRegistry

        _seed_tool(self.root, "deprecated_tool")
        self.client.post("/api/tools/deprecated_tool/archive")
        self.client.delete("/api/tools/deprecated_tool")
        self.assertFalse((self.root / "tools" / "deprecated_tool").exists())

        # And the tool registry status check now reports it as missing.
        registry = ToolRegistry(
            self.root,
            handlers={"deprecated_tool": lambda inputs: {"ok": True}},
        )
        result = registry.run("deprecated_tool", {})
        self.assertFalse(result["ok"])

    # ----------------------------------------------- built-in protection

    def test_archive_refuses_built_in_skill(self) -> None:
        # Skill seeded without the user_created marker = built-in.
        _seed_skill(self.root, "system_skill", user_created=False)
        response = self.client.post("/api/skills/system_skill/archive")
        self.assertEqual(response.status_code, 403)
        # Files untouched.
        self.assertTrue((self.root / "skills" / "system_skill" / "SKILL.md").exists())
        # And lifecycle marker is still missing / built-in.
        store = LifecycleStore(self.root)
        self.assertFalse(store.is_user_created("skill", "system_skill"))

    def test_archive_refuses_built_in_tool(self) -> None:
        _seed_tool(self.root, "system_tool", user_created=False)
        response = self.client.post("/api/tools/system_tool/archive")
        self.assertEqual(response.status_code, 403)
        self.assertTrue((self.root / "tools" / "system_tool" / "tool.yaml").exists())

    def test_restore_refuses_built_in_skill(self) -> None:
        _seed_skill(self.root, "system_skill", user_created=False)
        response = self.client.post("/api/skills/system_skill/restore")
        self.assertEqual(response.status_code, 403)

    def test_hard_delete_refuses_built_in_skill(self) -> None:
        _seed_skill(self.root, "system_skill", user_created=False)
        response = self.client.delete("/api/skills/system_skill")
        self.assertEqual(response.status_code, 403)
        self.assertTrue((self.root / "skills" / "system_skill" / "SKILL.md").exists())

    def test_user_created_marker_exposes_is_built_in_false(self) -> None:
        _seed_skill(self.root, "user_skill", user_created=True)
        _seed_skill(self.root, "system_skill", user_created=False)
        skills = self.client.get("/api/skills").json()["data"]
        by_name = {s["name"]: s for s in skills}
        self.assertFalse(by_name["user_skill"]["is_built_in"])
        self.assertTrue(by_name["system_skill"]["is_built_in"])

    def test_hard_delete_does_not_touch_reviews_or_versions(self) -> None:
        _seed_skill(self.root, "delete_me")
        # Stage a fake review + version snapshot so we can assert they
        # survive the destructive delete.
        reviews_dir = self.root / ".reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        (reviews_dir / "REV-keepme.json").write_text(
            json.dumps({"target_skill": "delete_me"}), encoding="utf-8",
        )
        versions_dir = self.root / ".skills_versions" / "delete_me"
        versions_dir.mkdir(parents=True, exist_ok=True)
        (versions_dir / "v1.json").write_text("{}", encoding="utf-8")

        self.client.post("/api/skills/delete_me/archive")
        self.client.delete("/api/skills/delete_me")

        self.assertTrue((reviews_dir / "REV-keepme.json").exists())
        self.assertTrue((versions_dir / "v1.json").exists())


if __name__ == "__main__":
    unittest.main()
