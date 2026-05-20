import json
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from web.server import create_app
except (ImportError, RuntimeError):  # pragma: no cover
    TestClient = None
    create_app = None

from runtime.backends.local import LocalReviewStore
from runtime.promotion_browser import PromotionBrowser
from runtime.skill_evolution_registry import SkillEvolutionRegistry
from runtime.skill_memory import SkillMemoryManager

def write_skill(root: Path, skill: str = "markdown_writer") -> None:
    skill_dir = root / "skills" / skill
    (skill_dir / "eval").mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {skill}",
                "description: Markdown writing helper",
                "---",
                "",
                f"# {skill}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (skill_dir / "eval" / "cases.yaml").write_text(f"skill: {skill}\ncases: []\n", encoding="utf-8")


@unittest.skipIf(TestClient is None, "fastapi is not installed")
class WebApiTests(unittest.TestCase):
    def make_client(self, root: Path) -> TestClient:
        return TestClient(create_app(root))

    def make_promo(self, root: Path) -> str:
        write_skill(root)
        manager = SkillMemoryManager(root / "skills", root / ".skills_memory")
        for _ in range(3):
            manager.record_learning(
                "markdown_writer",
                "Use fenced markdown output",
                "For repeated markdown output corrections, use fenced code blocks consistently.",
                source="test",
            )
        browser = PromotionBrowser(
            skills_dir=root / "skills",
            global_memory_dir=root / ".skills_memory",
            project_root=root,
        )
        return browser.list_candidates()[0].promo_id

    def test_get_assets_returns_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.get("/api/assets")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["ok"])
            self.assertIn("skills", payload["data"])

    def test_empty_reviews_returns_empty_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = self.make_client(root)
            response = client.get("/api/reviews")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"], [])

    def test_empty_promotions_returns_empty_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = self.make_client(root)
            response = client.get("/api/promotions")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"], [])

    def test_evolve_promotion_reuses_existing_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            promo_id = self.make_promo(root)
            client = self.make_client(root)
            response = client.post(f"/api/promotions/{promo_id}/evolve")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["data"]["stage"], "regression_pending")
            self.assertRegex(payload["data"]["review_id"], r"REV-[A-Z0-9]{8}")
            reviews = client.get("/api/reviews").json()["data"]
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0]["type"], "skill.regression_case")

    def test_legacy_promo_regeneration_creates_eligible_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            memory_dir = root / "skills" / "markdown_writer" / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)
            (memory_dir / "LEARNINGS.md").write_text(
                "\n".join(
                    [
                        "# Learnings",
                        "",
                        "## LRN-LEGACY1 - Prefer fenced markdown",
                        "- Time: 2026-05-19T00:00:00+00:00",
                        "- Priority: P2",
                        "- Status: open",
                        "- Domain: markdown",
                        "- Source: test",
                        "- Occurrence Count: 3",
                        "- Target Skill: markdown_writer",
                        "- Attribution Confidence: high",
                        "",
                        "### Details",
                        "Always use fenced code blocks when returning reusable Markdown examples.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            promo_dir = root / ".skills_memory"
            promo_dir.mkdir(parents=True, exist_ok=True)
            (promo_dir / "PROMOTION_CANDIDATES.md").write_text(
                "\n".join(
                    [
                        "# Promotion Candidates",
                        "",
                        "## PROMO-LEGACY1 - Old candidate",
                        "- Candidate ID: PROMO-LEGACY1",
                        "- Record ID: LRN-LEGACY1",
                        "- Target Skill: markdown_writer",
                        "- Proposed Change Summary: Old candidate",
                        "- Target Files: skills/markdown_writer/SKILL.md",
                        "- Occurrence Count: 3",
                        "- Status: proposed",
                        "- Evaluation Plan: test",
                        "- Rollback Plan: test",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            client = self.make_client(root)
            legacy = client.get("/api/promotions/PROMO-LEGACY1").json()["data"]
            self.assertTrue(legacy["is_legacy"])
            self.assertEqual(
                legacy["missing_fields"],
                ["promotion_decision", "promotion_score", "eligible_target"],
            )

            rejected = client.post("/api/promotions/PROMO-LEGACY1/evolve")
            self.assertEqual(rejected.status_code, 400)

            response = client.post("/api/promotions/PROMO-LEGACY1/regenerate")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["ok"])
            new_promo = payload["data"]["new_promo"]
            self.assertNotEqual(new_promo["promo_id"], "PROMO-LEGACY1")
            self.assertFalse(new_promo["is_legacy"])
            self.assertIn(new_promo["promotion_decision"], {"promote", "wait", "reject", "policy_review"})
            self.assertNotEqual(new_promo["promotion_score"], "legacy")
            self.assertNotEqual(new_promo["eligible_target"], "legacy")
            old = client.get("/api/promotions/PROMO-LEGACY1").json()["data"]
            self.assertEqual(old["status"], "legacy_rejected")

    def test_approve_does_not_modify_target_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            review_store = LocalReviewStore(root / ".reviews", root)
            review = review_store.create_review(
                type="skill.regression_case",
                source="test",
                candidate_id="PROMO-ABC12345",
                target_skill="markdown_writer",
                target_files=["skills/markdown_writer/eval/cases.yaml"],
                severity="medium",
                reason="test",
                proposed_change="\n".join(
                    [
                        "cases:",
                        "  - id: positive",
                        "    input: \"markdown\"",
                        "    must_include:",
                        "      - \"```\"",
                        "    target_rule: \"Use fences\"",
                        "    source_promo_id: \"PROMO-ABC12345\"",
                        "  - id: negative",
                        "    input: \"plain text\"",
                        "    must_not_include:",
                        "      - \"```\"",
                        "    target_rule: \"Use fences\"",
                        "    source_promo_id: \"PROMO-ABC12345\"",
                        "",
                    ]
                ),
                evaluation_plan="test",
                rollback_plan="test",
                metadata={"source_promo_id": "PROMO-ABC12345"},
            )
            target = root / "skills" / "markdown_writer" / "eval" / "cases.yaml"
            before = target.read_text(encoding="utf-8")
            client = self.make_client(root)
            response = client.post(f"/api/reviews/{review['review_id']}/approve")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["data"]["has_patch"])
            self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_apply_only_works_for_approved_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            review_store = LocalReviewStore(root / ".reviews", root)
            review = review_store.create_review(
                type="skill.regression_case",
                source="test",
                candidate_id="PROMO-ABC12345",
                target_skill="markdown_writer",
                target_files=["skills/markdown_writer/eval/cases.yaml"],
                severity="medium",
                reason="test",
                proposed_change="cases: []",
                evaluation_plan="test",
                rollback_plan="test",
                metadata={"source_promo_id": "PROMO-ABC12345"},
            )
            client = self.make_client(root)
            response = client.post(f"/api/reviews/{review['review_id']}/apply")
            self.assertEqual(response.status_code, 400)
            self.assertFalse(response.json()["ok"])

    def test_skill_versions_returns_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            versions_dir = root / ".skills_versions" / "markdown_writer"
            versions_dir.mkdir(parents=True)
            record = {
                "skill": "markdown_writer",
                "version": "v0.1.1",
                "previous_version": "v0.1.0",
                "promotion_id": "PROMO-ABC12345",
                "skill_review_id": "REV-ABC12345",
                "regression_review_ids": [],
                "base_hash": "a",
                "new_hash": "b",
                "decision": "applied",
                "created_at": "2026-05-19T00:00:00+00:00",
            }
            (versions_dir / "versions.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
            client = self.make_client(root)
            response = client.get("/api/skills/markdown_writer/versions")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"][0]["version"], "v0.1.1")

    def test_rollback_creates_review_without_modifying_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            skill_file = root / "skills" / "markdown_writer" / "SKILL.md"
            before = skill_file.read_text(encoding="utf-8")
            registry = SkillEvolutionRegistry(root)
            version_dir = root / ".skills_versions" / "markdown_writer" / "v0.1.0"
            version_dir.mkdir(parents=True)
            (version_dir / "SKILL.md").write_text(before, encoding="utf-8")
            versions_file = root / ".skills_versions" / "markdown_writer" / "versions.jsonl"
            versions_file.write_text(
                json.dumps({"skill": "markdown_writer", "version": "v0.1.0", "decision": "applied"}) + "\n",
                encoding="utf-8",
            )
            self.assertIsNotNone(registry.get_version("markdown_writer", "v0.1.0"))
            client = self.make_client(root)
            response = client.post("/api/skills/markdown_writer/rollback", json={"version": "v0.1.0"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertRegex(payload["data"]["review_id"], r"REV-[A-Z0-9]{8}")
            self.assertEqual(skill_file.read_text(encoding="utf-8"), before)

    def test_chat_answers_natural_language_with_skill_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u5e2e\u6211\u5199\u4e00\u4e2a\u8bfb\u4e66\u7b14\u8bb0\u6a21\u677f"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["intent"], "writing_request")
            self.assertEqual(payload["type"], "skill_result")
            self.assertEqual(payload["used_skill"], "markdown_writer")
            self.assertIn("writing", payload["why"])
            self.assertIn("\u4e66\u540d", payload["message"])
            self.assertNotIn("Used skill:", payload["message"])
            self.assertNotIn("Only command-mode", payload["message"])

    def test_chat_greeting_is_direct_answer_without_skill_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u4f60\u597d"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "general_chat")
            self.assertEqual(payload["type"], "answer")
            self.assertRegex(payload["run_id"], r"RUN-[A-Z0-9]{8}")
            self.assertIsNone(payload["used_skill"])
            self.assertIn("\u4f60\u597d", payload["message"])
            self.assertNotIn("Used skill:", payload["message"])
            self.assertNotIn("self_improvement", payload["message"])
            self.assertTrue(any(item["type"] == "analyze" for item in payload["trace"]))
            self.assertTrue(any(item["type"] == "final_result" for item in payload["trace"]))

    def test_chat_weather_requests_city_and_realtime_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u4eca\u5929\u5929\u6c14\u600e\u6837\uff1f\u7528\u4e2d\u6587\u56de\u7b54"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "external_realtime_query")
            self.assertEqual(payload["type"], "answer")
            self.assertIsNone(payload["used_skill"])
            self.assertIn("\u57ce\u5e02", payload["message"])
            self.assertIn("\u5b9e\u65f6\u5929\u6c14", payload["message"])
            self.assertNotIn("I can help with writing", payload["message"])
            self.assertTrue(any(item.get("tool_name") == "weather_query" for item in payload["trace"]))

    def test_chat_weather_tool_creation_is_not_weather_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "tool_usage")
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u4f60\u53ef\u4ee5\u5e2e\u6211\u5199\u5929\u6c14\u67e5\u8be2\u7684\u5de5\u5177\u5417\uff1f"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "tool_creation_request")
            self.assertEqual(payload["type"], "skill_result")
            self.assertEqual(payload["used_skill"], "tool_usage")
            self.assertIn("weather_query tool", payload["message"])
            self.assertTrue(payload["actions"])
            self.assertEqual(payload["actions"][0]["kind"], "create_skill_review")
            self.assertEqual(payload["actions"][0]["path"], "/api/skills/propose")
            self.assertEqual(payload["actions"][0]["payload"]["skill_name"], "weather_query")
            self.assertTrue(payload["actions"][0]["requires_confirmation"])
            self.assertNotIn("\u5148\u544a\u8bc9\u6211\u57ce\u5e02", payload["message"])
            self.assertFalse((root / "skills" / "weather_query" / "SKILL.md").exists())

    def test_chat_skill_creation_returns_proposed_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "self_improvement")
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u5e2e\u6211\u521b\u5efa weather_query skill"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "skill_creation_request")
            self.assertEqual(payload["type"], "skill_result")
            self.assertEqual(payload["risk"], "safe_write_preview")
            self.assertIn("weather_query", payload["message"])
            self.assertTrue(any(item["type"] == "approval_event" for item in payload["trace"]))
            self.assertEqual(payload["actions"][0]["kind"], "create_skill_review")
            self.assertEqual(payload["actions"][0]["payload"]["skill_name"], "weather_query")
            reviews = client.get("/api/reviews").json()["data"]
            self.assertEqual(reviews, [])
            self.assertFalse((root / "skills" / "weather_query" / "SKILL.md").exists())

    def test_skill_creation_review_apply_creates_files_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "self_improvement")
            client = self.make_client(root)
            chat = client.post("/api/chat", json={"message": "\u5e2e\u6211\u521b\u5efa weather_query skill"}).json()
            action = chat["actions"][0]
            proposed = client.post(action["path"], json=action["payload"])
            self.assertEqual(proposed.status_code, 200)
            review_id = proposed.json()["data"]["review_id"]
            approve = client.post(f"/api/reviews/{review_id}/approve")
            self.assertEqual(approve.status_code, 200)
            apply = client.post(f"/api/reviews/{review_id}/apply")
            self.assertEqual(apply.status_code, 200)
            self.assertTrue((root / "skills" / "weather_query" / "SKILL.md").exists())
            self.assertTrue((root / "skills" / "weather_query" / "eval" / "cases.yaml").exists())
            versions = client.get("/api/skills/weather_query/versions").json()["data"]
            self.assertEqual(versions[0]["change_type"], "skill_creation")

    def test_chat_captures_explicit_memory_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post(
                "/api/chat",
                json={"message": "\u4ee5\u540e\u8bfb\u4e66\u7b14\u8bb0\u90fd\u6309\u4e66\u540d\u3001\u6838\u5fc3\u89c2\u70b9\u3001\u4e09\u6761\u542f\u53d1\u3001\u884c\u52a8\u6e05\u5355\u6765\u5199"},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "memory_preference")
            self.assertEqual(payload["type"], "memory_captured")
            self.assertRegex(payload["memory_record_id"], r"LRN-[A-Z0-9]{8}")
            self.assertTrue(any(item["type"] == "file_trace" and item.get("operation") == "write" for item in payload["trace"]))
            memory_text = (root / "skills" / "markdown_writer" / "memory" / "LEARNINGS.md").read_text(encoding="utf-8")
            self.assertIn(payload["memory_record_id"], memory_text)

    def test_chat_lists_workspace_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u5f53\u524d\u6709\u54ea\u4e9b skills\uff1f"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "skill_list_query")
            self.assertEqual(payload["type"], "skill_result")
            self.assertIn("markdown_writer", payload["message"])
            self.assertIn("registry", payload["why"])
            self.assertEqual(payload["data"]["skills"][0]["name"], "markdown_writer")
            self.assertTrue(any(item["type"] == "tool_call" and item.get("path") == "/api/skills" for item in payload["trace"]))

    def test_chat_workspace_status_reads_progress_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u73b0\u5728\u7cfb\u7edf\u5361\u5728\u54ea\u4e00\u6b65\uff1f"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "workspace_status_query")
            self.assertEqual(payload["type"], "skill_result")
            self.assertEqual(payload["used_skill"], "self_improvement")
            self.assertIn("dashboard", payload["data"])
            self.assertIn("review", payload["message"])

    def test_chat_apply_requires_confirmation_and_includes_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            review_store = LocalReviewStore(root / ".reviews", root)
            review = review_store.create_review(
                type="skill.regression_case",
                source="test",
                candidate_id="PROMO-ABC12345",
                target_skill="markdown_writer",
                target_files=["skills/markdown_writer/eval/cases.yaml"],
                severity="medium",
                reason="test",
                proposed_change="cases: []",
                evaluation_plan="test",
                rollback_plan="test",
                metadata={"source_promo_id": "PROMO-ABC12345"},
            )
            review_store.approve_review(review["review_id"])
            client = self.make_client(root)
            response = client.post(
                "/api/chat",
                json={
                    "message": "apply \u8fd9\u4e2a review",
                    "context": {"current_review_id": review["review_id"]},
                },
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "review_action_request")
            self.assertEqual(payload["type"], "approval_required")
            self.assertTrue(payload["actions"][0]["requires_confirmation"])
            self.assertIn("/apply", payload["actions"][0]["path"])
            self.assertTrue(payload["data"]["patch"]["has_patch"])
            self.assertTrue(any(item["type"] == "approval_event" for item in payload["trace"]))

    def test_chat_continue_promo_creates_review_trace_without_applying_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            promo_id = self.make_promo(root)
            skill_file = root / "skills" / "markdown_writer" / "SKILL.md"
            before = skill_file.read_text(encoding="utf-8")
            client = self.make_client(root)
            response = client.post(
                "/api/chat",
                json={
                    "message": "\u7ee7\u7eed\u63a8\u8fdb\u5f53\u524d PROMO",
                    "context": {"current_promo_id": promo_id},
                },
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "evolution_action_request")
            self.assertEqual(payload["type"], "approval_required")
            self.assertRegex(payload["data"]["review_id"], r"REV-[A-Z0-9]{8}")
            self.assertTrue(any(item["type"] == "tool_call" and item.get("method") == "POST" for item in payload["trace"]))
            self.assertTrue(any(item["type"] == "approval_event" for item in payload["trace"]))
            self.assertEqual(skill_file.read_text(encoding="utf-8"), before)

    def test_chat_reads_workspace_file_with_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u8bfb\u53d6 skills/markdown_writer/SKILL.md"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "skill_read_request")
            self.assertEqual(payload["risk"], "safe_read")
            self.assertEqual(payload["type"], "file_result")
            self.assertEqual(payload["data"]["path"], "skills/markdown_writer/SKILL.md")
            self.assertTrue(any(item["type"] == "file_trace" and item.get("operation") == "read" for item in payload["trace"]))

    def test_chat_file_write_returns_confirmable_preview_then_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u5e2e\u6211\u5728 docs/demo.md \u5199\u4e00\u6bb5 hello"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "file_write_request")
            self.assertEqual(payload["type"], "proposed_action")
            self.assertFalse((root / "docs" / "demo.md").exists())
            action = payload["actions"][0]
            confirm = client.post(action["path"], json=action["body"])
            self.assertEqual(confirm.status_code, 200)
            self.assertEqual((root / "docs" / "demo.md").read_text(encoding="utf-8"), "hello\n")

    def test_chat_safe_command_runs_git_status_with_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u5e2e\u6211\u770b git status"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "command_run_request")
            self.assertEqual(payload["risk"], "safe_read")
            self.assertEqual(payload["type"], "command_result")
            self.assertTrue(any(item["type"] == "command_trace" and item.get("command") == "git status" for item in payload["trace"]))

    def test_chat_high_risk_delete_command_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root)
            client = self.make_client(root)
            response = client.post("/api/chat", json={"message": "\u5e2e\u6211\u5220\u9664\u6574\u4e2a skills \u76ee\u5f55"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["intent"], "command_run_request")
            self.assertEqual(payload["risk"], "high_risk")
            self.assertEqual(payload["type"], "error")
            self.assertTrue((root / "skills").exists())

    def test_workspace_file_read_refuses_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("OPENAI_API_KEY=secret", encoding="utf-8")
            client = self.make_client(root)
            response = client.get("/api/workspace/files/read", params={"path": ".env"})
            self.assertEqual(response.status_code, 403)
