from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import re
from typing import Any

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing.
    raise RuntimeError(
        "FastAPI is required for web.server. Install dependencies with requirements.txt."
    ) from exc

from runtime.backends.local import LocalReviewStore
from runtime.promotion_browser import PromotionBrowser
from runtime.regression_case_proposal import parse_regression_cases
from runtime.skill_evolution_flow import evolve_skill_from_promotion
from runtime.skill_evolution_registry import SkillEvolutionRegistry, normalize_skill_name
from runtime.skill_loader import SkillLoader
from runtime.skill_memory import MEMORY_FILES, SkillMemoryManager, normalize_name
from safety.policy_config import load_policy
from tools.schemas import build_tools


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALID_MSG_TYPES = {
    "message",
    "broadcast",
    "shutdown_request",
    "shutdown_response",
    "plan_approval_response",
}
MEMORY_FILE_TO_TYPE = {filename: record_type for record_type, filename in MEMORY_FILES.items()}
MEMORY_CATEGORY_NAMES = {
    "LEARNINGS": "learning",
    "ERRORS": "error",
    "FEATURE_REQUESTS": "feature_request",
    "POLICY_CANDIDATES": "policy_candidate",
    "REGRESSION_TESTS": "regression_test",
}
HANDLER_NAMES = {
    "__skill_memory__",
    "bash",
    "read_file",
    "write_file",
    "edit_file",
    "TodoWrite",
    "task",
    "load_skill",
    "record_learning",
    "record_error",
    "record_feature_request",
    "record_policy_candidate",
    "record_regression_test",
    "propose_memory_promotion",
    "evaluate_evolution_candidate",
    "classify_and_record_learning_signal",
    "classify_learning_signal",
    "summarize_skill_memory",
    "list_skill_memory",
    "compress",
    "background_run",
    "check_background",
    "task_create",
    "task_get",
    "task_update",
    "task_list",
    "claim_task",
    "spawn_teammate",
    "list_teammates",
    "send_message",
    "read_inbox",
    "broadcast",
    "shutdown_request",
    "plan_approval",
    "idle",
}


def ok(
    data: Any = None,
    message: str = "",
    next_actions: list[str] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": True,
            "data": {} if data is None else data,
            "message": message,
            "next_actions": next_actions or [],
            "errors": [],
        },
    )


def fail(
    message: str,
    *,
    errors: list[str] | None = None,
    next_actions: list[str] | None = None,
    status_code: int = 400,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "data": None,
            "message": message,
            "next_actions": next_actions or [],
            "errors": errors or [message],
        },
    )


def chat_ok(
    *,
    response_type: str,
    message: str,
    used_skill: str | None = None,
    why: str = "",
    memory_record_id: str = "",
    actions: list[dict[str, Any]] | None = None,
    data: Any = None,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": True,
            "type": response_type,
            "message": message,
            "used_skill": used_skill,
            "why": why,
            "memory_record_id": memory_record_id,
            "actions": actions or [],
            "data": {} if data is None else data,
            "next_actions": [action.get("path", "") for action in actions or [] if action.get("path")],
            "errors": [],
        },
    )


class WebContext:
    def __init__(self, project_root: Path | str = PROJECT_ROOT):
        self.project_root = Path(project_root)
        self.skills_dir = self.project_root / "skills"
        self.global_memory_dir = self.project_root / ".skills_memory"
        self.skill_loader = SkillLoader(self.skills_dir)
        self.skill_memory = SkillMemoryManager(self.skills_dir, self.global_memory_dir)
        self.review_store = LocalReviewStore(
            self.project_root / ".reviews",
            self.project_root,
            skill_loader=self.skill_loader,
            skill_memory=self.skill_memory,
        )
        self.promotions = PromotionBrowser(
            skills_dir=self.skills_dir,
            global_memory_dir=self.global_memory_dir,
            project_root=self.project_root,
        )
        self.versions = SkillEvolutionRegistry(self.project_root)
        self.policy = load_policy()


def create_app(project_root: Path | str = PROJECT_ROOT) -> FastAPI:
    ctx = WebContext(project_root)
    app = FastAPI(title="Agent Asset Governance API", version="0.1.0")
    app.state.ctx = ctx

    @app.exception_handler(Exception)
    async def json_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        return fail("Internal server error.", errors=[str(exc)], status_code=500)

    @app.get("/api/assets")
    def assets() -> JSONResponse:
        reviews = _reviews(ctx)
        promotions = _promotions(ctx)
        return ok(
            {
                "skills": len(_skills(ctx)),
                "tools": len(_tool_views(ctx)),
                "memories": len(_memory_records(ctx)),
                "knowledge_bases": len(_knowledge_bases(ctx)),
                "reviews": _count_by_status(reviews, ["pending", "approved", "applied"]),
                "promotions": _count_by_status(promotions, ["proposed", "applied"]),
                "versions": len(_all_versions(ctx)),
            }
        )

    @app.get("/api/assets/recent")
    def recent_assets() -> JSONResponse:
        reviews = sorted(_reviews(ctx), key=lambda item: item.get("created_at", ""), reverse=True)[:5]
        promos = _promotions(ctx)[:5]
        versions = sorted(_all_versions(ctx), key=lambda item: item.get("created_at", ""), reverse=True)[:5]
        memories = sorted(_memory_records(ctx), key=lambda item: item.get("updated_at", ""), reverse=True)[:5]
        return ok(
            {
                "reviews": reviews,
                "promotions": promos,
                "versions": versions,
                "memories": memories,
            }
        )

    @app.get("/api/skills")
    def skills() -> JSONResponse:
        return ok(_skills(ctx))

    @app.get("/api/skills/{skill}")
    def skill_detail(skill: str) -> JSONResponse:
        skill_name = normalize_name(skill)
        skill_file = ctx.skills_dir / skill_name / "SKILL.md"
        if not skill_file.exists():
            return fail(f"Unknown skill: {skill}", status_code=404)
        text = skill_file.read_text(encoding="utf-8")
        frontmatter, body = _frontmatter(text)
        versions = ctx.versions.list_versions(skill_name)
        promotions = [
            promo for promo in _promotions(ctx)
            if promo.get("target_skill") == skill_name
        ]
        return ok(
            {
                "name": skill_name,
                "frontmatter": frontmatter,
                "description": frontmatter.get("description", ""),
                "active_file": f"skills/{skill_name}/SKILL.md",
                "memory": _memory_summary(ctx, skill_name),
                "eval_cases": _eval_summary(ctx, skill_name),
                "versions": {
                    "count": len(versions),
                    "latest_version": versions[-1].get("version") if versions else "",
                    "items": versions,
                },
                "linked_promotions": promotions,
                "body_preview": body[:1000],
            }
        )

    @app.get("/api/skills/{skill}/active")
    def active_skill(skill: str) -> JSONResponse:
        skill_name = normalize_name(skill)
        path = ctx.skills_dir / skill_name / "SKILL.md"
        if not path.exists():
            return fail(f"Unknown skill: {skill}", status_code=404)
        return ok({"skill": skill_name, "path": f"skills/{skill_name}/SKILL.md", "content": path.read_text(encoding="utf-8")})

    @app.get("/api/skills/{skill}/eval-cases")
    def skill_eval_cases(skill: str) -> JSONResponse:
        skill_name = normalize_name(skill)
        path = ctx.skills_dir / skill_name / "eval" / "cases.yaml"
        if not path.exists():
            return ok({"skill": skill_name, "path": f"skills/{skill_name}/eval/cases.yaml", "cases": [], "raw": ""})
        raw = path.read_text(encoding="utf-8")
        return ok({"skill": skill_name, "path": f"skills/{skill_name}/eval/cases.yaml", "cases": parse_regression_cases(raw), "raw": raw})

    @app.get("/api/skills/{skill}/memory")
    def skill_memory(skill: str) -> JSONResponse:
        return ok(_memory_summary(ctx, normalize_name(skill)))

    @app.get("/api/skills/{skill}/memory/{memory_type}")
    def skill_memory_type(skill: str, memory_type: str) -> JSONResponse:
        skill_name = normalize_name(skill)
        record_type = _normalize_memory_type(memory_type)
        if not record_type:
            return fail(f"Unknown memory type: {memory_type}", status_code=404)
        path = ctx.skills_dir / skill_name / "memory" / MEMORY_FILES[record_type]
        return ok(
            {
                "skill": skill_name,
                "type": record_type,
                "source_file": _display_path(ctx, path),
                "records": _records_from_file(ctx, path, skill_name, record_type),
            }
        )

    @app.get("/api/tools")
    def tools() -> JSONResponse:
        return ok(_tool_views(ctx))

    @app.get("/api/tools/{tool_name}")
    def tool_detail(tool_name: str) -> JSONResponse:
        tool = next((item for item in _tool_views(ctx) if item["name"] == tool_name), None)
        if not tool:
            return fail(f"Unknown tool: {tool_name}", status_code=404)
        recent_reviews = [
            review for review in _reviews(ctx)
            if review.get("tool_name") == tool_name
        ][-5:]
        recent_errors = [
            memory for memory in _memory_records(ctx)
            if memory.get("type") == "error" and tool_name.lower() in json.dumps(memory, ensure_ascii=False).lower()
        ][:5]
        return ok({**tool, "recent_review_history": recent_reviews, "recent_errors": recent_errors})

    @app.get("/api/memories")
    def memories(
        skill: str | None = None,
        type: str | None = None,
        promoted: bool | None = None,
        needs_review: bool | None = None,
    ) -> JSONResponse:
        records = _memory_records(ctx)
        if skill:
            records = [record for record in records if record["skill"] == normalize_name(skill)]
        if type:
            record_type = _normalize_memory_type(type)
            records = [record for record in records if record["type"] == record_type]
        if promoted is not None:
            records = [record for record in records if bool(record.get("linked_promo_id")) == promoted]
        if needs_review is not None:
            records = [record for record in records if bool(record.get("needs_attribution_review")) == needs_review]
        return ok(records)

    @app.get("/api/memories/{memory_id}")
    def memory_detail(memory_id: str) -> JSONResponse:
        record = _find_memory(ctx, memory_id)
        if not record:
            return fail(f"Unknown memory_id: {memory_id}", status_code=404)
        return ok(record)

    @app.post("/api/memories/{memory_id}/promote")
    def promote_memory(memory_id: str) -> JSONResponse:
        record = _find_memory(ctx, memory_id)
        if not record:
            return fail(f"Unknown memory_id: {memory_id}", status_code=404)
        if record.get("type") not in MEMORY_FILES:
            return ok(
                {"status": "not_implemented", "memory_id": memory_id},
                "Promotion is not implemented for this memory type.",
            )
        message = ctx.skill_memory.propose_memory_promotion(record["skill"], memory_id)
        return ok({"memory_id": memory_id, "message": message}, next_actions=["/api/promotions"])

    @app.get("/api/knowledge-bases")
    def knowledge_bases() -> JSONResponse:
        return ok(
            _knowledge_bases(ctx),
            "Knowledge base assets are not implemented yet.",
        )

    @app.get("/api/knowledge-bases/{kb_id}")
    def knowledge_base_detail(kb_id: str) -> JSONResponse:
        kb = next((item for item in _knowledge_bases(ctx) if item.get("kb_id") == kb_id), None)
        if not kb:
            return fail(f"Knowledge base asset was not found: {kb_id}", status_code=404)
        return ok(kb)

    @app.get("/api/reviews")
    def reviews(
        status: str | None = None,
        type: str | None = None,
        severity: str | None = None,
        candidate_id: str | None = None,
        target_skill: str | None = None,
    ) -> JSONResponse:
        records = _reviews(ctx, status)
        if type:
            records = [record for record in records if record.get("type") == type]
        if severity:
            records = [record for record in records if record.get("severity") == severity]
        if candidate_id:
            records = [record for record in records if record.get("candidate_id") == candidate_id]
        if target_skill:
            records = [record for record in records if record.get("target_skill") == normalize_name(target_skill)]
        return ok([_review_summary(record) for record in records])

    @app.get("/api/reviews/{review_id}")
    def review_detail(review_id: str) -> JSONResponse:
        review = ctx.review_store.get_review(review_id)
        if not review:
            return fail(f"Unknown review_id: {review_id}", status_code=404)
        return ok(review)

    @app.get("/api/reviews/{review_id}/patch")
    def review_patch(review_id: str) -> JSONResponse:
        review = ctx.review_store.get_review(review_id)
        if not review:
            return fail(f"Unknown review_id: {review_id}", status_code=404)
        patch_path = ctx.project_root / ".reviews" / "patches" / f"{review_id}.diff"
        if not patch_path.exists():
            return ok(
                {"has_patch": False, "patch": ""},
                "No patch preview is needed for this review.",
            )
        return ok({"has_patch": True, "patch_path": _display_path(ctx, patch_path), "patch": patch_path.read_text(encoding="utf-8")})

    @app.post("/api/reviews/{review_id}/approve")
    def approve_review(review_id: str) -> JSONResponse:
        review = ctx.review_store.get_review(review_id)
        if not review:
            return fail(f"Unknown review_id: {review_id}", status_code=404)
        before = _target_snapshots(ctx, review)
        try:
            approved, patch_path = ctx.review_store.approve_review(review_id)
        except ValueError as exc:
            return fail(str(exc))
        after = _target_snapshots(ctx, review)
        if before != after:
            return fail(
                "Approve unexpectedly modified target files.",
                errors=["Approval must only create a patch preview."],
                status_code=500,
            )
        has_patch = bool(patch_path and Path(patch_path).exists())
        return ok(
            {
                "status": approved.get("status"),
                "patch_path": _display_path(ctx, Path(patch_path)) if patch_path else "",
                "has_patch": has_patch,
            },
            "Review approved. No target file was modified.",
            _next_review_actions(review_id, approved.get("status", "")),
        )

    @app.post("/api/reviews/{review_id}/apply")
    def apply_review(review_id: str) -> JSONResponse:
        review = ctx.review_store.get_review(review_id)
        if not review:
            return fail(f"Unknown review_id: {review_id}", status_code=404)
        if review.get("status") != "approved":
            return fail(f"Review {review_id} must be approved before apply.", next_actions=[f"/api/reviews/{review_id}/approve"])
        before = _target_snapshots(ctx, review)
        try:
            applied, message = ctx.review_store.apply_review(review_id)
        except ValueError as exc:
            return fail(str(exc))
        after = _target_snapshots(ctx, applied)
        modified_files = [path for path, value in after.items() if before.get(path) != value]
        recorded_version = ""
        if applied.get("type") == "skill.promotion":
            recorded_version = _version_for_review(ctx, applied.get("target_skill", ""), review_id)
        return ok(
            {
                "status": applied.get("status"),
                "modified_files": modified_files,
                "message": message,
                "recorded_version": recorded_version,
            },
            message,
        )

    @app.post("/api/reviews/{review_id}/reject")
    def reject_review(review_id: str) -> JSONResponse:
        if not ctx.review_store.get_review(review_id):
            return fail(f"Unknown review_id: {review_id}", status_code=404)
        try:
            rejected = ctx.review_store.reject_review(review_id)
        except ValueError as exc:
            return fail(str(exc))
        return ok({"status": rejected.get("status"), "review_id": review_id}, "Review rejected.")

    @app.get("/api/promotions")
    def promotions() -> JSONResponse:
        return ok(_promotions(ctx))

    @app.get("/api/promotions/{promo_id}")
    def promotion_detail(promo_id: str) -> JSONResponse:
        promo = ctx.promotions.get_candidate(promo_id)
        if not promo:
            return fail(f"Unknown promo_id: {promo_id}", status_code=404)
        data = _promotion_view(ctx, promo)
        data["source_memory"] = ctx.promotions.source_memory_text(promo)
        data["suggested_target"] = data.get("eligible_target")
        data["review_status"] = data.get("linked_reviews", [])
        return ok(data)

    @app.post("/api/promotions/{promo_id}/evolve")
    def evolve_promotion(promo_id: str) -> JSONResponse:
        result = evolve_skill_from_promotion(
            browser=ctx.promotions,
            review_store=ctx.review_store,
            promo_id=promo_id,
            project_root=ctx.project_root,
        )
        stage = _api_stage(result.stage)
        data = {
            "stage": stage,
            "review_id": result.review_id,
            "message": result.message,
            "version": _version_for_promo(ctx, promo_id) if stage == "completed" else "",
        }
        return ok(data, result.message, _flow_next_actions(result.review_id, stage)) if result.ok else fail(result.message)

    @app.post("/api/promotions/{promo_id}/regenerate")
    def regenerate_promotion(promo_id: str) -> JSONResponse:
        promo = ctx.promotions.get_candidate(promo_id)
        if not promo:
            return fail(f"Unknown promo_id: {promo_id}", status_code=404)
        missing = _missing_promotion_eligibility(promo)
        if not missing:
            return ok(
                {"old_promo_id": promo_id, "new_promo": _promotion_view(ctx, promo), "missing_fields": []},
                "Promotion candidate already has Promotion Eligibility fields.",
            )
        if not promo.source_memory_ids:
            return fail(
                f"Cannot regenerate {promo_id}: source memory id is missing.",
                errors=["Legacy PROMO must include a source memory id before eligibility can be regenerated."],
            )
        record_id = promo.source_memory_ids[0]
        result = ctx.skill_memory.regenerate_promotion_candidate(
            promo.target_skill or "self_improvement",
            record_id,
            legacy_promo_id=promo_id,
        )
        if not result.get("ok"):
            return fail(str(result.get("message", "Promotion regeneration failed.")))
        new_promo_id = str(result["candidate"].get("candidate_id", ""))
        ctx.promotions = PromotionBrowser(
            skills_dir=ctx.skills_dir,
            global_memory_dir=ctx.global_memory_dir,
            project_root=ctx.project_root,
        )
        new_promo = ctx.promotions.get_candidate(new_promo_id)
        return ok(
            {
                "old_promo_id": promo_id,
                "old_status": "legacy_rejected",
                "new_promo_id": new_promo_id,
                "new_promo": _promotion_view(ctx, new_promo) if new_promo else result["candidate"],
                "missing_fields": missing,
            },
            f"Regenerated {promo_id} with Promotion Eligibility as {new_promo_id}.",
            [f"/api/promotions/{new_promo_id}", f"/api/promotions/{new_promo_id}/evolve"],
        )

    @app.get("/api/skills/{skill}/versions")
    def skill_versions(skill: str) -> JSONResponse:
        return ok(ctx.versions.list_versions(skill))

    @app.get("/api/skills/{skill}/versions/{version}")
    def skill_version_detail(skill: str, version: str) -> JSONResponse:
        skill_name = normalize_skill_name(skill)
        record = ctx.versions.get_version(skill_name, version)
        if not record:
            return fail(f"Unknown skill version: {skill_name} {version}", status_code=404)
        version_dir = ctx.project_root / ".skills_versions" / skill_name / version
        snapshot_path = version_dir / "SKILL.md"
        patch_path = version_dir / "patch.diff"
        eval_path = version_dir / "eval_result.json"
        return ok(
            {
                "record": record,
                "snapshot_path": _display_path(ctx, snapshot_path),
                "patch_path": _display_path(ctx, patch_path),
                "eval_result_path": _display_path(ctx, eval_path),
                "snapshot_content": _read_text(snapshot_path),
                "patch_content": _read_text(patch_path),
                "eval_result": _read_json(eval_path),
            }
        )

    @app.post("/api/skills/{skill}/rollback")
    async def rollback_skill(skill: str, request: Request) -> JSONResponse:
        body = await request.json()
        version = str(body.get("version", "")).strip()
        if not version:
            return fail("Missing rollback version.")
        skill_name = normalize_skill_name(skill)
        skill_file = ctx.skills_dir / skill_name / "SKILL.md"
        before = _read_text(skill_file)
        item = ctx.versions.create_rollback_review(
            review_store=ctx.review_store,
            skill=skill_name,
            version=version,
        )
        after = _read_text(skill_file)
        if before != after:
            return fail("Rollback API unexpectedly modified SKILL.md.", status_code=500)
        return ok(
            {"review_id": item["review_id"], "status": item["status"]},
            f"Created rollback review {item['review_id']}. No skill file was modified.",
            [f"/api/reviews/{item['review_id']}", f"/api/reviews/{item['review_id']}/approve"],
        )

    @app.post("/api/chat")
    async def chat(request: Request) -> JSONResponse:
        body = await request.json()
        message = str(body.get("message", "")).strip()
        if not message:
            return fail("Message is required.")
        context = body.get("context", {})
        if not isinstance(context, dict):
            context = {}
        data = _handle_chat(ctx, message, context)
        return chat_ok(
            response_type=data.get("type", "answer"),
            message=data.get("message", ""),
            used_skill=data.get("used_skill", ""),
            why=data.get("why", ""),
            memory_record_id=data.get("memory_record_id", ""),
            actions=data.get("actions", []),
            data=data.get("data", {}),
            status_code=data.get("status_code", 200),
        )

    @app.post("/api/chat/send")
    async def chat_send(request: Request) -> JSONResponse:
        body = await request.json()
        message = str(body.get("message", "")).strip()
        if not message:
            return fail("Message is required.")
        context = body.get("context", {})
        if not isinstance(context, dict):
            context = {}
        data = _handle_chat(ctx, message, context)
        return chat_ok(
            response_type=data.get("type", "answer"),
            message=data.get("message", ""),
            used_skill=data.get("used_skill", ""),
            why=data.get("why", ""),
            memory_record_id=data.get("memory_record_id", ""),
            actions=data.get("actions", []),
            data=data.get("data", {}),
            status_code=data.get("status_code", 200),
        )

    @app.get("/api/chat/events")
    def chat_events() -> JSONResponse:
        return ok(_recent_events(ctx))

    @app.get("/api/dashboard")
    def dashboard() -> JSONResponse:
        pending = _reviews(ctx, "pending")
        promotions_data = _promotions(ctx)
        missing_regression = sum(
            1
            for promo in promotions_data
            if promo.get("promotion_decision") == "promote"
            and promo.get("eligible_target") == "skill_rule"
            and not _has_regression_coverage(ctx, promo.get("target_skill", ""), promo.get("promo_id", ""))
        )
        return ok(
            {
                "pending_reviews": len(pending),
                "promotions": len(promotions_data),
                "missing_regression": missing_regression,
                "applied_skill_versions": len(_all_versions(ctx)),
                "recent_events": _recent_events(ctx),
            }
        )

    @app.get("/api/evolution/{promo_id}/state")
    def evolution_state(promo_id: str) -> JSONResponse:
        promo = ctx.promotions.get_candidate(promo_id)
        if not promo:
            return fail(f"Unknown promo_id: {promo_id}", status_code=404)
        reviews_for_promo = [
            review for review in _reviews(ctx)
            if review.get("candidate_id") == promo_id
        ]
        regression = _first_review(reviews_for_promo, "skill.regression_case")
        skill_review = _first_review(reviews_for_promo, "skill.promotion")
        version = _version_for_promo(ctx, promo_id)
        steps = [
            {"name": "memory", "status": "completed"},
            {"name": "promo", "status": "completed"},
            {
                "name": "regression_review",
                "status": regression.get("status", "waiting") if regression else "waiting",
                "review_id": regression.get("review_id", "") if regression else "",
            },
            {
                "name": "skill_promotion_review",
                "status": skill_review.get("status", "waiting") if skill_review else "waiting",
                "review_id": skill_review.get("review_id", "") if skill_review else "",
            },
            {"name": "version", "status": "completed" if version else "waiting", "version": version},
        ]
        return ok(
            {
                "promo_id": promo_id,
                "target_skill": promo.target_skill,
                "steps": steps,
                "next_action": _next_evolution_action(regression, skill_review, version),
            }
        )

    return app


def _skills(ctx: WebContext) -> list[dict[str, Any]]:
    skills = []
    for path in sorted(ctx.skills_dir.glob("*/SKILL.md")):
        skill_name = path.parent.name
        text = path.read_text(encoding="utf-8")
        frontmatter, _body = _frontmatter(text)
        memory_summary = _memory_summary(ctx, skill_name)
        versions = ctx.versions.list_versions(skill_name)
        promotions = [
            promo for promo in ctx.promotions.list_candidates()
            if promo.target_skill == skill_name
        ]
        latest = versions[-1].get("version") if versions else ""
        skills.append(
            {
                "name": skill_name,
                "description": frontmatter.get("description", ""),
                "path": _display_path(ctx, path),
                "has_memory": any(item["count"] for item in memory_summary.values()),
                "has_eval_cases": bool(_eval_summary(ctx, skill_name)["case_count"]),
                "active_version": latest or "active",
                "latest_version": latest,
                "memory_count": sum(item["count"] for item in memory_summary.values()),
                "promotion_count": len(promotions),
                "updated_at": _mtime(path),
            }
        )
    return skills


def _reviews(ctx: WebContext, status: str | None = None) -> list[dict[str, Any]]:
    return ctx.review_store.list_reviews(status)


def _review_summary(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_id": review.get("review_id", ""),
        "type": review.get("type", ""),
        "status": review.get("status", ""),
        "severity": review.get("severity", ""),
        "target_skill": review.get("target_skill", ""),
        "candidate_id": review.get("candidate_id", ""),
        "target_files": review.get("target_files", []),
        "reason": review.get("reason", ""),
        "created_at": review.get("created_at", ""),
        "next_actions": _next_review_actions(review.get("review_id", ""), review.get("status", "")),
    }


def _promotions(ctx: WebContext) -> list[dict[str, Any]]:
    return [_promotion_view(ctx, candidate) for candidate in ctx.promotions.list_candidates()]


def _promotion_view(ctx: WebContext, candidate: Any) -> dict[str, Any]:
    data = candidate.to_dict() if hasattr(candidate, "to_dict") else asdict(candidate)
    promo_id = data.get("promo_id", "")
    missing_fields = _missing_promotion_eligibility(candidate)
    schema_status = "legacy" if missing_fields else "eligible"
    linked_reviews = [
        review.get("review_id")
        for review in _reviews(ctx)
        if review.get("candidate_id") == promo_id
    ]
    linked_version = _version_for_promo(ctx, promo_id)
    return {
        "promo_id": promo_id,
        "target_skill": data.get("target_skill", ""),
        "source_memory_type": data.get("source_memory_type", ""),
        "source_memory_ids": data.get("source_memory_ids", []),
        "source_memory_file": data.get("source_memory_file", ""),
        "occurrence_count": data.get("occurrence_count", 0),
        "promotion_score": data.get("promotion_score", "legacy"),
        "promotion_decision": data.get("promotion_decision", ""),
        "eligible_target": data.get("eligible_target", ""),
        "schema_status": schema_status,
        "is_legacy": bool(missing_fields),
        "missing_fields": missing_fields,
        "requires_regeneration": bool(missing_fields),
        "source_memory_exists": data.get("source_memory_exists", True),
        "missing_source_memory_ids": data.get("missing_source_memory_ids") or [],
        "source_memory_id": (data.get("missing_source_memory_ids") or data.get("source_memory_ids") or [""])[0],
        "error_code": data.get("error_code", ""),
        "suggested_action": data.get("suggested_action", ""),
        "is_dangling": data.get("error_code") == "SOURCE_MEMORY_NOT_FOUND",
        "status": "applied" if linked_version else data.get("status", "proposed"),
        "summary": data.get("summary", ""),
        "proposed_change": data.get("proposed_change", ""),
        "evaluation_plan": data.get("evaluation_plan", ""),
        "rollback_plan": data.get("rollback_plan", ""),
        "linked_reviews": linked_reviews,
        "linked_version": linked_version,
    }


def _missing_promotion_eligibility(candidate: Any) -> list[str]:
    data = candidate.to_dict() if hasattr(candidate, "to_dict") else dict(candidate)
    missing = []
    if data.get("promotion_decision") in {"", None, "legacy"}:
        missing.append("promotion_decision")
    if data.get("promotion_score") in {"", None, "legacy"}:
        missing.append("promotion_score")
    if data.get("eligible_target") in {"", None, "legacy"}:
        missing.append("eligible_target")
    return missing


def _tool_views(ctx: WebContext) -> list[dict[str, Any]]:
    tools = []
    policy_tools = ctx.policy.get("tools", {})
    for tool in build_tools(sorted(VALID_MSG_TYPES)):
        function = tool.get("function", {})
        name = function.get("name", "")
        policy = policy_tools.get(name, {})
        tools.append(
            {
                "name": name,
                "description": function.get("description", ""),
                "capability": policy.get("capability", ""),
                "risk_level": policy.get("risk", ""),
                "requires_approval_by_policy": _policy_requires_approval(policy),
                "handler_available": name in HANDLER_NAMES,
                "schema": function,
                "safety_policy": policy,
            }
        )
    return tools


def _memory_records(ctx: WebContext) -> list[dict[str, Any]]:
    records = []
    for path in sorted(ctx.skills_dir.glob("*/memory/*.md")):
        skill = path.parent.parent.name
        record_type = MEMORY_FILE_TO_TYPE.get(path.name, path.stem.lower())
        records.extend(_records_from_file(ctx, path, skill, record_type))
    return records


def _policy_requires_approval(policy: dict[str, Any]) -> bool:
    if policy.get("default_action") == "require_approval":
        return True
    return any(str(key).startswith("require_approval") and bool(value) for key, value in policy.items())


def _records_from_file(ctx: WebContext, path: Path, skill: str, record_type: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for record in ctx.skill_memory._read_records(path):
        fields = dict(record.get("fields", {}))
        memory_id = str(record.get("record_id", ""))
        records.append(
            {
                "memory_id": memory_id,
                "skill": skill,
                "type": record_type,
                "title": str(record.get("title", "")),
                "occurrence_count": _parse_int(fields.get("Occurrence Count"), 1),
                "source_file": _display_path(ctx, path),
                "linked_promo_id": _linked_promo_id(ctx, memory_id),
                "needs_attribution_review": str(fields.get("Needs Attribution Review", "")).lower() == "true",
                "created_at": fields.get("Time", ""),
                "updated_at": _mtime(path),
                "fields": fields,
                "details": str(record.get("details", "")),
                "block": str(record.get("block", "")),
            }
        )
    return records


def _find_memory(ctx: WebContext, memory_id: str) -> dict[str, Any] | None:
    for record in _memory_records(ctx):
        if record.get("memory_id") == memory_id:
            return record
    return None


def _memory_summary(ctx: WebContext, skill: str) -> dict[str, dict[str, Any]]:
    summary = {}
    for display, record_type in MEMORY_CATEGORY_NAMES.items():
        path = ctx.skills_dir / skill / "memory" / MEMORY_FILES[record_type]
        records = _records_from_file(ctx, path, skill, record_type)
        summary[display] = {
            "type": record_type,
            "count": len(records),
            "recent_titles": [record["title"] for record in records[-2:]],
        }
    return summary


def _eval_summary(ctx: WebContext, skill: str) -> dict[str, Any]:
    path = ctx.skills_dir / skill / "eval" / "cases.yaml"
    if not path.exists():
        return {"case_count": 0, "path": _display_path(ctx, path)}
    cases = parse_regression_cases(path.read_text(encoding="utf-8"))
    return {"case_count": len(cases), "path": _display_path(ctx, path)}


def _knowledge_bases(ctx: WebContext) -> list[dict[str, Any]]:
    roots = [ctx.project_root / "knowledge_bases", ctx.project_root / "knowledge"]
    items = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(item for item in root.iterdir() if item.is_dir()):
            items.append({"kb_id": path.name, "path": _display_path(ctx, path), "updated_at": _mtime(path)})
    return items


def _all_versions(ctx: WebContext) -> list[dict[str, Any]]:
    records = []
    skill_names = {path.parent.name for path in ctx.skills_dir.glob("*/SKILL.md")}
    versions_root = ctx.project_root / ".skills_versions"
    if versions_root.exists():
        skill_names.update(path.name for path in versions_root.iterdir() if path.is_dir())
    for skill_name in sorted(skill_names):
        records.extend(ctx.versions.list_versions(skill_name))
    return records


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    marker = text.find("\n---\n", 4)
    if marker == -1:
        return {}, text
    meta = {}
    for line in text[4:marker].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"')
    return meta, text[marker + len("\n---\n"):]


def _normalize_memory_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in MEMORY_CATEGORY_NAMES:
        return MEMORY_CATEGORY_NAMES[normalized]
    lowered = value.strip().lower()
    if lowered in MEMORY_FILES:
        return lowered
    if lowered.endswith(".md"):
        filename = value.strip().upper().replace(".MD", ".md")
        return MEMORY_FILE_TO_TYPE.get(filename, "")
    return ""


def _linked_promo_id(ctx: WebContext, memory_id: str) -> str:
    for promo in ctx.promotions.list_candidates():
        if memory_id in promo.source_memory_ids:
            return promo.promo_id
    return ""


def _count_by_status(items: list[dict[str, Any]], statuses: list[str]) -> dict[str, int]:
    return {status: sum(1 for item in items if item.get("status") == status) for status in statuses}


def _target_snapshots(ctx: WebContext, review: dict[str, Any]) -> dict[str, str]:
    snapshots = {}
    for target in review.get("target_files", []):
        path = _safe_project_path(ctx, target)
        snapshots[target.replace("\\", "/")] = _read_text(path) if path else ""
    return snapshots


def _safe_project_path(ctx: WebContext, relative_path: str) -> Path | None:
    path = (ctx.project_root / relative_path).resolve()
    try:
        path.relative_to(ctx.project_root.resolve())
    except ValueError:
        return None
    return path


def _next_review_actions(review_id: str, status: str) -> list[str]:
    if not review_id:
        return []
    if status == "pending":
        return [f"/api/reviews/{review_id}", f"/api/reviews/{review_id}/approve", f"/api/reviews/{review_id}/reject"]
    if status == "approved":
        return [f"/api/reviews/{review_id}/patch", f"/api/reviews/{review_id}/apply"]
    return []


def _api_stage(stage: str) -> str:
    return {
        "regression_review": "regression_pending",
        "regression_apply": "regression_pending",
        "skill_review": "skill_patch_pending",
        "skill_apply": "skill_patch_pending",
        "complete": "completed",
    }.get(stage, stage or "regression_required")


def _flow_next_actions(review_id: str, stage: str) -> list[str]:
    if not review_id:
        return []
    if stage in {"regression_pending", "skill_patch_pending"}:
        return [f"/review {review_id}", f"/approve {review_id}", f"/apply {review_id}"]
    return []


def _version_for_review(ctx: WebContext, skill: str, review_id: str) -> str:
    for record in ctx.versions.list_versions(skill):
        if record.get("skill_review_id") == review_id:
            return str(record.get("version", ""))
    return ""


def _version_for_promo(ctx: WebContext, promo_id: str) -> str:
    for record in _all_versions(ctx):
        if record.get("promotion_id") == promo_id:
            return str(record.get("version", ""))
    return ""


def _has_regression_coverage(ctx: WebContext, skill: str, promo_id: str) -> bool:
    path = ctx.skills_dir / skill / "eval" / "cases.yaml"
    if not path.exists():
        return False
    cases = parse_regression_cases(path.read_text(encoding="utf-8"))
    scoped = [case for case in cases if case.get("source_promo_id") == promo_id]
    return any(case.get("must_include") for case in scoped) and any(case.get("must_not_include") for case in scoped)


def _first_review(reviews: list[dict[str, Any]], review_type: str) -> dict[str, Any]:
    for status in ("applied", "approved", "pending", "rejected"):
        for review in reviews:
            if review.get("type") == review_type and review.get("status") == status:
                return review
    return {}


def _next_evolution_action(regression: dict[str, Any], skill_review: dict[str, Any], version: str) -> str:
    if version:
        return "completed"
    if not regression:
        return "create_regression_review"
    if regression.get("status") == "pending":
        return "approve_regression_review"
    if regression.get("status") == "approved":
        return "apply_regression_review"
    if not skill_review:
        return "create_skill_review"
    if skill_review.get("status") == "pending":
        return "approve_skill_review"
    if skill_review.get("status") == "approved":
        return "apply_skill_review"
    return "waiting"


def _handle_chat(ctx: WebContext, message: str, context: dict[str, Any]) -> dict[str, Any]:
    if message.startswith("/"):
        return _handle_command(ctx, message)

    intent = _chat_intent(message)
    used_skill, skill_reason = _route_skill(ctx, message, context, intent)

    if intent == "greeting":
        return _chat_result(
            "answer",
            used_skill,
            skill_reason,
            "\u4f60\u597d\uff01\u6211\u5728\u3002\u4f60\u53ef\u4ee5\u76f4\u63a5\u8ddf\u6211\u804a\uff0c\u4e5f\u53ef\u4ee5\u8ba9\u6211\u5199\u5185\u5bb9\u3001\u770b workspace \u72b6\u6001\u3001\u5904\u7406 skills \u548c reviews\u3002",
        )
    if intent == "weather":
        return _chat_result(
            "answer",
            used_skill,
            skill_reason,
            "\u6211\u53ef\u4ee5\u5e2e\u4f60\u67e5\u5929\u6c14\uff0c\u4f46\u9700\u8981\u4f60\u5148\u544a\u8bc9\u6211\u57ce\u5e02\u6216\u5730\u533a\u3002\u8fd9\u7c7b\u95ee\u9898\u9700\u8981\u5b9e\u65f6\u5929\u6c14\u67e5\u8be2\u5de5\u5177\uff1b\u53ea\u9760\u5f53\u524d workspace \u72b6\u6001\u4e0d\u80fd\u51c6\u786e\u56de\u7b54\u3002",
        )
    if intent == "memory_capture":
        return _capture_learning_memory(ctx, message, used_skill, skill_reason)
    if intent == "list_skills":
        skills = _skills(ctx)
        names = ", ".join(skill["name"] for skill in skills) or "none"
        return _chat_result(
            "skill_result",
            used_skill,
            skill_reason,
            f"Workspace skills: {names}.",
            "No durable memory was captured.",
            data={"skills": skills},
        )
    if intent == "workspace_status":
        return _chat_workspace_status(ctx, context, used_skill, skill_reason)
    if intent == "evolution_status":
        return _chat_evolution_status(ctx, context, used_skill, skill_reason)
    if intent == "generate_regression_review":
        promo = _current_promo(ctx, context)
        if not promo:
            return _chat_result(
                "proposed_action",
                used_skill,
                skill_reason,
                "I could not find a current promotion candidate to generate regression coverage for.",
                "No durable memory was captured.",
                actions=[_action("Open promotions", "GET", "/api/promotions", False)],
            )
        action = _action(
            "Generate or continue regression review",
            "POST",
            f"/api/promotions/{promo['promo_id']}/evolve",
            True,
        )
        return _chat_result(
            "proposed_action",
            used_skill,
            skill_reason,
            (
                f"Ready to generate the next review for {promo['promo_id']}. "
                "This will go through the promotion evolution API and will not modify skill files."
            ),
            "No durable memory was captured.",
            actions=[action],
            data={"promotion": promo},
        )
    if intent == "continue_promo":
        promo = _current_promo(ctx, context)
        if not promo:
            return _chat_result(
                "proposed_action",
                used_skill,
                skill_reason,
                "I could not find a current PROMO. Choose one from Promotions, then ask me to continue it.",
                "No durable memory was captured.",
                actions=[_action("Open promotions", "GET", "/api/promotions", False)],
            )
        return _chat_result(
            "proposed_action",
            used_skill,
            skill_reason,
            f"The controlled next step for {promo['promo_id']} is available.",
            "No durable memory was captured.",
            actions=[
                _action(
                    "Continue promotion flow",
                    "POST",
                    f"/api/promotions/{promo['promo_id']}/evolve",
                    True,
                )
            ],
            data={"promotion": promo},
        )
    if intent == "review_explain":
        return _chat_review_explain(ctx, message, context, used_skill, skill_reason)
    if intent == "approve_review":
        return _chat_review_action(ctx, message, context, used_skill, skill_reason, "approve")
    if intent == "apply_review":
        return _chat_review_action(ctx, message, context, used_skill, skill_reason, "apply")
    if intent == "rollback":
        return _chat_result(
            "approval_required",
            used_skill,
            skill_reason,
            "Rollback must be created through the skill version rollback API after you choose a concrete version.",
            "No durable memory was captured.",
            actions=[_action("Open versions", "GET", "/api/skills", False)],
        )

    answer = _draft_answer(message, intent)
    return _chat_result(
        "skill_result" if used_skill else "answer",
        used_skill,
        skill_reason,
        answer,
        "No durable memory was captured.",
    )


def _chat_result(
    response_type: str,
    used_skill: str | None,
    skill_reason: str,
    output: str,
    memory_note: str = "",
    *,
    actions: list[dict[str, Any]] | None = None,
    data: Any = None,
    memory_record_id: str = "",
) -> dict[str, Any]:
    payload_data = data or {}
    if memory_note and isinstance(payload_data, dict):
        payload_data = {**payload_data, "memory_note": memory_note}
    return {
        "type": response_type,
        "message": output,
        "used_skill": used_skill,
        "why": skill_reason,
        "memory_record_id": memory_record_id,
        "actions": actions or [],
        "data": payload_data,
    }


def _chat_intent(message: str) -> str:
    text = message.lower()
    compact = re.sub(r"[\s\uff01!,.，。？?]+", "", message).lower()
    if compact in {"hi", "hello", "hey", "\u4f60\u597d", "\u55e8", "\u54c8\u55bd"}:
        return "greeting"
    if _looks_like_memory_request(message):
        return "memory_capture"
    if _has_any(message, ["\u5929\u6c14", "weather", "\u4e0b\u96e8", "\u6c14\u6e29", "\u51e0\u5ea6"]):
        return "weather"
    if _has_any(message, ["\u5f53\u524d\u6709\u54ea\u4e9b skills", "\u6709\u54ea\u4e9b skills", "\u6709\u54ea\u4e9b\u6280\u80fd", "\u5f53\u524d\u6280\u80fd"]) or "available skills" in text:
        return "list_skills"
    if _has_any(message, ["\u7cfb\u7edf\u5361\u5728\u54ea", "\u5361\u5728\u54ea", "\u5361\u54ea\u4e00\u6b65", "\u5f53\u524d\u8fdb\u5ea6", "\u7cfb\u7edf\u72b6\u6001", "workspace status"]):
        return "workspace_status"
    if ("self-evolution" in text or "evolution" in text or "\u8fdb\u5316" in message) and _has_any(message, ["\u5361", "\u72b6\u6001", "\u8fdb\u5ea6", "\u54ea\u4e00\u6b65"]):
        return "evolution_status"
    if "regression review" in text or "\u56de\u5f52 review" in message or "\u56de\u5f52\u8bc4\u5ba1" in message:
        return "generate_regression_review"
    if "promo" in text and _has_any(message, ["\u7ee7\u7eed", "\u63a8\u8fdb", "\u4e0b\u4e00\u6b65"]):
        return "continue_promo"
    if "review" in text and (_has_any(message, ["\u6539\u4e86\u4ec0\u4e48", "\u89e3\u91ca", "\u8bf4\u660e"]) or "what changed" in text):
        return "review_explain"
    if re.search(r"\bapprove\b", text) or "\u6279\u51c6" in message or "\u901a\u8fc7\u8fd9\u4e2a review" in message:
        return "approve_review"
    if re.search(r"\bapply\b", text) or "\u5e94\u7528\u8fd9\u4e2a review" in message or "apply \u8fd9\u4e2a review" in text:
        return "apply_review"
    if "rollback" in text or "\u56de\u6eda" in message:
        return "rollback"
    if _has_any(message, ["PRD", "\u6a21\u677f", "\u6574\u7406", "\u66f4\u6b63\u5f0f", "\u5927\u7eb2", "\u8bfb\u4e66\u7b14\u8bb0"]):
        return "writing"
    if _has_any(message, ["\u62a5\u9519", "\u9519\u8bef", "traceback", "exception", "error"]):
        return "explain_error"
    if "self-evolving skill" in text or "\u81ea\u8fdb\u5316 skill" in message:
        return "self_evolving_explain"
    return "general"


def _route_skill(ctx: WebContext, message: str, context: dict[str, Any], intent: str) -> tuple[str | None, str]:
    current = normalize_name(str(context.get("current_skill", "") or ""))
    available = {skill["name"] for skill in _skills(ctx)}
    if intent == "list_skills":
        return None, "Read the workspace skill registry."
    if intent == "workspace_status":
        return "self_improvement", "Read dashboard, promotion, review, and version state."
    if intent in {"greeting", "weather", "general"}:
        return None, "General assistant answer; no workspace skill is needed."
    if current in available and intent in {"memory_capture", "continue_promo", "review_explain", "approve_review", "apply_review"}:
        return current, "The page context names this as the current skill."
    if intent in {"memory_capture", "writing"} or _has_any(message, ["markdown", "\u8bfb\u4e66\u7b14\u8bb0", "PRD", "\u6a21\u677f", "\u5927\u7eb2", "\u6b63\u5f0f"]):
        return _first_available(available, ["markdown_writer", current, "self_improvement"]), "The request is about writing or reusable markdown structure."
    if intent in {"continue_promo", "evolution_status", "generate_regression_review", "approve_review", "apply_review", "review_explain", "rollback"}:
        return "self_improvement", "The request touches promotion, review, memory, version, or self-evolution workflow."
    if _has_any(message, ["\u6587\u4ef6", "\u4fee\u6539", "patch", "diff", "\u7f16\u8f91"]):
        return _first_available(available, ["file_editing", "file_modification", current, "self_improvement"]), "The request is about file editing or patch advice."
    if _has_any(message, ["\u5de5\u5177", "\u547d\u4ee4", "tool", "api", "\u63a5\u53e3"]) or intent == "explain_error":
        return _first_available(available, ["tool_usage", current, "self_improvement"]), "The request is about tools, commands, APIs, or error diagnosis."
    if intent == "self_evolving_explain":
        return "self_improvement", "The request asks about self-evolving skills."
    return None, "General assistant answer; no workspace skill is needed."


def _first_available(available: set[str], candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate and candidate in available:
            return candidate
    return sorted(available)[0] if available else ""


def _has_any(message: str, tokens: list[str]) -> bool:
    lowered = message.lower()
    return any(token.lower() in lowered for token in tokens)


def _looks_like_memory_request(message: str) -> bool:
    text = message.lower()
    return _has_any(
        message,
        ["\u4ee5\u540e", "\u540e\u7eed", "\u8bb0\u4f4f", "\u957f\u671f", "\u9ed8\u8ba4", "\u90fd\u8981", "\u56fa\u5b9a"],
    ) or any(token in text for token in ("from now on", "always", "remember this", "default to"))


def _capture_learning_memory(
    ctx: WebContext,
    message: str,
    used_skill: str,
    skill_reason: str,
) -> dict[str, Any]:
    skill_name = used_skill or "self_improvement"
    title = _memory_title(message)
    content = _memory_content(message, skill_name)
    before_promos = {promo["promo_id"] for promo in _promotions(ctx)}
    result = ctx.skill_memory.record_learning(
        skill_name,
        title,
        content,
        evidence=message,
        priority="medium",
        status="open",
        domain="chat_preference",
        source="chat",
        source_skill="self_improvement",
        attribution_reason="explicit long-term user preference captured from Chat",
        attribution_confidence="high",
        needs_attribution_review=False,
    )
    record_id = _extract_record_id(result, "LRN")
    ctx.promotions = PromotionBrowser(
        skills_dir=ctx.skills_dir,
        global_memory_dir=ctx.global_memory_dir,
        project_root=ctx.project_root,
    )
    after_promos = _promotions(ctx)
    new_promos = [promo for promo in after_promos if promo["promo_id"] not in before_promos]
    actions = [
        _action(
            "Generate promotion candidate",
            "POST",
            f"/api/memories/{record_id}/promote",
            True,
        )
    ] if record_id and not new_promos else []
    if new_promos:
        actions = [
            _action(
                "Continue promotion flow",
                "POST",
                f"/api/promotions/{new_promos[0]['promo_id']}/evolve",
                True,
            )
        ]
    promo_note = f" Promotion candidate: {new_promos[0]['promo_id']}." if new_promos else ""
    return _chat_result(
        "memory_captured",
        used_skill,
        skill_reason,
        f"Captured the preference as a learning signal for {skill_name}.{promo_note}",
        f"Recorded as learning signal {record_id or '(updated existing memory)' }.",
        memory_record_id=record_id,
        actions=actions,
        data={"record_message": result, "new_promotions": new_promos},
    )


def _memory_title(message: str) -> str:
    if "\u8bfb\u4e66\u7b14\u8bb0" in message:
        return "Book note structure preference"
    if "PRD" in message:
        return "PRD structure preference"
    clean = re.sub(r"\s+", " ", message.strip())
    return (clean[:60] + "...") if len(clean) > 60 else clean


def _memory_content(message: str, skill_name: str) -> str:
    extra = ""
    if "\u8bfb\u4e66\u7b14\u8bb0" in message:
        extra = "Reusable default book-note format: book title, core viewpoint, three insights, action checklist."
    if "PRD" in message:
        extra = "Reusable default PRD format preference from the user."
    return "\n".join(item for item in [message.strip(), extra, f"Target skill: {skill_name}"] if item)


def _chat_evolution_status(
    ctx: WebContext,
    context: dict[str, Any],
    used_skill: str | None,
    skill_reason: str,
) -> dict[str, Any]:
    promo = _current_promo(ctx, context)
    if not promo:
        promos = _promotions(ctx)
        pending = [item for item in promos if item.get("status") != "applied"]
        output = (
            f"No current PROMO is selected. Workspace has {len(promos)} promotion candidates, "
            f"{len(pending)} not applied."
        )
        return _chat_result("skill_result", used_skill, skill_reason, output, "No durable memory was captured.", data={"promotions": promos})
    state = _evolution_state_for_promo(ctx, promo["promo_id"])
    next_action = state.get("next_action", "waiting")
    steps = ", ".join(f"{step['name']}={step['status']}" for step in state.get("steps", []))
    output = f"{promo['promo_id']} is at next_action={next_action}. Steps: {steps}."
    return _chat_result("skill_result", used_skill, skill_reason, output, "No durable memory was captured.", data=state)


def _chat_workspace_status(
    ctx: WebContext,
    context: dict[str, Any],
    used_skill: str | None,
    skill_reason: str,
) -> dict[str, Any]:
    reviews = _reviews(ctx)
    promos = _promotions(ctx)
    versions = _all_versions(ctx)
    pending_reviews = [review for review in reviews if review.get("status") == "pending"]
    approved_reviews = [review for review in reviews if review.get("status") == "approved"]
    promo = _current_promo(ctx, context)
    if promo:
        state = _evolution_state_for_promo(ctx, promo["promo_id"])
        next_action = state.get("next_action", "waiting")
        output = (
            f"\u5f53\u524d\u6700\u53ef\u64cd\u4f5c\u7684\u8fdb\u5ea6\u5728 {promo['promo_id']}: "
            f"next_action={next_action}\u3002"
            f"\u5f85\u5ba1 review {len(pending_reviews)} \u4e2a\uff0c"
            f"\u5df2\u6279\u51c6\u5f85 apply review {len(approved_reviews)} \u4e2a\uff0c"
            f"promotion candidates {len(promos)} \u4e2a\uff0c"
            f"\u5df2\u8bb0\u5f55\u7248\u672c {len(versions)} \u4e2a\u3002"
        )
        return _chat_result(
            "skill_result",
            used_skill,
            skill_reason,
            output,
            "No durable memory was captured.",
            data={
                "dashboard": {
                    "pending_reviews": len(pending_reviews),
                    "approved_reviews": len(approved_reviews),
                    "promotions": len(promos),
                    "versions": len(versions),
                },
                "evolution": state,
            },
        )
    output = (
        f"\u5f53\u524d\u6ca1\u6709\u53ef\u63a8\u8fdb\u7684 PROMO\u3002"
        f"\u5f85\u5ba1 review {len(pending_reviews)} \u4e2a\uff0c"
        f"\u5df2\u6279\u51c6\u5f85 apply review {len(approved_reviews)} \u4e2a\uff0c"
        f"promotion candidates {len(promos)} \u4e2a\uff0c"
        f"\u5df2\u8bb0\u5f55\u7248\u672c {len(versions)} \u4e2a\u3002"
    )
    return _chat_result(
        "skill_result",
        used_skill,
        skill_reason,
        output,
        "No durable memory was captured.",
        data={
            "dashboard": {
                "pending_reviews": len(pending_reviews),
                "approved_reviews": len(approved_reviews),
                "promotions": len(promos),
                "versions": len(versions),
            }
        },
    )


def _chat_review_explain(
    ctx: WebContext,
    message: str,
    context: dict[str, Any],
    used_skill: str | None,
    skill_reason: str,
) -> dict[str, Any]:
    review = _current_review(ctx, message, context)
    if not review:
        return _chat_result("error", used_skill, skill_reason, "I could not find a review id in the message or current context.", "No durable memory was captured.")
    patch = _patch_for_review(ctx, review["review_id"])
    output = (
        f"{review['review_id']} is a {review.get('type', '')} review with status={review.get('status', '')}. "
        f"Target files: {', '.join(review.get('target_files', [])) or '(none)'}. "
        f"Proposed change: {review.get('proposed_change', '') or '(none)'}"
    )
    return _chat_result(
        "skill_result",
        used_skill,
        skill_reason,
        output,
        "No durable memory was captured.",
        data={"review": review, "patch": patch},
    )


def _chat_review_action(
    ctx: WebContext,
    message: str,
    context: dict[str, Any],
    used_skill: str | None,
    skill_reason: str,
    action_name: str,
) -> dict[str, Any]:
    review = _current_review(ctx, message, context)
    if not review:
        return _chat_result("approval_required", used_skill, skill_reason, "Choose a review first, or include a REV-xxxxxxxx id.", "No durable memory was captured.")
    if action_name == "approve":
        action = _action("Approve and generate preview", "POST", f"/api/reviews/{review['review_id']}/approve", True)
        output = f"{review['review_id']} can be approved after confirmation. Approval only generates a patch preview."
        return _chat_result("approval_required", used_skill, skill_reason, output, "No durable memory was captured.", actions=[action], data={"review": review})
    patch = _patch_for_review(ctx, review["review_id"])
    action = _action("Apply reviewed change", "POST", f"/api/reviews/{review['review_id']}/apply", True)
    output = (
        f"{review['review_id']} requires explicit confirmation before apply. "
        "The diff preview is included in this response and should be inspected first."
    )
    return _chat_result(
        "approval_required",
        used_skill,
        skill_reason,
        output,
        "No durable memory was captured.",
        actions=[action],
        data={"review": review, "patch": patch},
    )


def _draft_answer(message: str, intent: str) -> str:
    if intent == "writing" and "\u8bfb\u4e66\u7b14\u8bb0" in message:
        return "\n".join(
            [
                "# \u4e66\u540d",
                "",
                "## \u6838\u5fc3\u89c2\u70b9",
                "- ",
                "",
                "## \u4e09\u6761\u542f\u53d1",
                "1. ",
                "2. ",
                "3. ",
                "",
                "## \u884c\u52a8\u6e05\u5355",
                "- [ ] ",
            ]
        )
    if intent == "writing" and "PRD" in message:
        return "\n".join(
            [
                "# PRD \u5927\u7eb2",
                "",
                "## \u80cc\u666f\u4e0e\u76ee\u6807",
                "## \u7528\u6237\u4e0e\u573a\u666f",
                "## F1 \u529f\u80fd\u70b9",
                "## F2 \u529f\u80fd\u70b9",
                "## \u975e\u76ee\u6807",
                "## \u9a8c\u6536\u6807\u51c6",
                "## \u98ce\u9669\u4e0e\u5f00\u653e\u95ee\u9898",
            ]
        )
    if intent == "self_evolving_explain":
        return (
            "A self-evolving skill is a skill that can collect learning signals from repeated corrections, "
            "turn eligible patterns into promotion candidates, pass them through review and regression checks, "
            "and only then update the active skill with a versioned, reversible change."
        )
    if intent == "explain_error":
        return (
            "Paste the exact error text and the operation that triggered it. I will separate the symptom, likely cause, "
            "smallest reproduction, and next verification step."
        )
    if "\u9a8c\u6536" in message:
        return "\u9a8c\u6536\u53ef\u4ee5\u6309\u56db\u5c42\u770b\uff1a\u6838\u5fc3\u8def\u5f84\u80fd\u8dd1\u901a\u3001\u8fb9\u754c\u8f93\u5165\u6709\u63d0\u793a\u3001\u5931\u8d25\u72b6\u6001\u53ef\u6062\u590d\u3001\u5173\u952e\u53d8\u66f4\u6709\u53ef\u56de\u5f52\u7684\u68c0\u67e5\u8bb0\u5f55\u3002"
    if "\u6b63\u5f0f" in message:
        return "\u628a\u539f\u6587\u53d1\u7ed9\u6211\uff0c\u6211\u4f1a\u4fdd\u7559\u610f\u601d\uff0c\u8c03\u6574\u4e3a\u66f4\u6b63\u5f0f\u3001\u6e05\u6670\u3001\u9002\u5408\u4ea4\u4ed8\u6587\u6863\u7684\u8868\u8fbe\u3002"
    return "I can help with writing, explanation, workspace status, skill memory, promotions, reviews, and versioned skill evolution from this Chat entry point."

def _current_promo(ctx: WebContext, context: dict[str, Any]) -> dict[str, Any] | None:
    wanted = str(context.get("current_promo_id", "") or "").strip()
    promos = _promotions(ctx)
    if wanted:
        return next((promo for promo in promos if promo.get("promo_id") == wanted), None)
    actionable = [
        promo for promo in promos
        if promo.get("promotion_decision") == "promote" and promo.get("eligible_target") == "skill_rule"
    ]
    return actionable[0] if actionable else (promos[0] if promos else None)


def _current_review(ctx: WebContext, message: str, context: dict[str, Any]) -> dict[str, Any] | None:
    match = re.search(r"\bREV-[A-Z0-9]{8}\b", message.upper())
    wanted = match.group(0) if match else str(context.get("current_review_id", "") or "").strip()
    if wanted:
        return ctx.review_store.get_review(wanted)
    reviews = _reviews(ctx)
    for status in ("approved", "pending"):
        found = next((review for review in reviews if review.get("status") == status), None)
        if found:
            return found
    return None


def _evolution_state_for_promo(ctx: WebContext, promo_id: str) -> dict[str, Any]:
    promo = ctx.promotions.get_candidate(promo_id)
    reviews_for_promo = [
        review for review in _reviews(ctx)
        if review.get("candidate_id") == promo_id
    ]
    regression = _first_review(reviews_for_promo, "skill.regression_case")
    skill_review = _first_review(reviews_for_promo, "skill.promotion")
    version = _version_for_promo(ctx, promo_id)
    steps = [
        {"name": "memory", "status": "completed"},
        {"name": "promo", "status": "completed"},
        {
            "name": "regression_review",
            "status": regression.get("status", "waiting") if regression else "waiting",
            "review_id": regression.get("review_id", "") if regression else "",
        },
        {
            "name": "skill_promotion_review",
            "status": skill_review.get("status", "waiting") if skill_review else "waiting",
            "review_id": skill_review.get("review_id", "") if skill_review else "",
        },
        {"name": "version", "status": "completed" if version else "waiting", "version": version},
    ]
    return {
        "promo_id": promo_id,
        "target_skill": promo.target_skill if promo else "",
        "steps": steps,
        "next_action": _next_evolution_action(regression, skill_review, version),
    }


def _patch_for_review(ctx: WebContext, review_id: str) -> dict[str, Any]:
    patch_path = ctx.project_root / ".reviews" / "patches" / f"{review_id}.diff"
    if patch_path.exists():
        return {"has_patch": True, "patch_path": _display_path(ctx, patch_path), "patch": patch_path.read_text(encoding="utf-8")}
    review = ctx.review_store.get_review(review_id)
    if review and review.get("status") == "approved":
        try:
            _review, generated = ctx.review_store.approve_review(review_id)
            if generated and Path(generated).exists():
                path = Path(generated)
                return {"has_patch": True, "patch_path": _display_path(ctx, path), "patch": path.read_text(encoding="utf-8")}
        except ValueError:
            pass
    return {"has_patch": False, "patch_path": "", "patch": ""}


def _extract_record_id(text: str, prefix: str) -> str:
    match = re.search(rf"\b{re.escape(prefix)}-[A-Z0-9]{{8}}\b", text)
    return match.group(0) if match else ""


def _action(label: str, method: str, path: str, requires_confirmation: bool) -> dict[str, Any]:
    return {
        "label": label,
        "method": method,
        "path": path,
        "requires_confirmation": requires_confirmation,
    }


def _handle_command(ctx: WebContext, message: str) -> dict[str, Any]:
    parts = message.split()
    command = parts[0]
    if command == "/promotions":
        return _chat_result("tool_result", "self_improvement", "Slash command requested promotion candidates.", "Promotion candidates.", "No durable memory was captured.", data=_promotions(ctx))
    if command == "/reviews":
        return _chat_result("tool_result", "self_improvement", "Slash command requested reviews.", "Reviews.", "No durable memory was captured.", data=[_review_summary(item) for item in _reviews(ctx)])
    if command in {"/evolve-skill", "/evolve"} and len(parts) == 2:
        result = evolve_skill_from_promotion(
            browser=ctx.promotions,
            review_store=ctx.review_store,
            promo_id=parts[1],
            project_root=ctx.project_root,
        )
        return _chat_result(
            "tool_result" if result.ok else "error",
            "self_improvement",
            "Slash command requested the existing promotion evolution flow.",
            result.message,
            "No durable memory was captured.",
            data={"ok": result.ok, "stage": _api_stage(result.stage), "review_id": result.review_id},
        )
    if command == "/approve" and len(parts) == 2:
        review = ctx.review_store.get_review(parts[1])
        if not review:
            return _chat_result("error", "self_improvement", "Slash command requested review approval.", f"Unknown review_id: {parts[1]}", "No durable memory was captured.")
        return _chat_result(
            "approval_required",
            "self_improvement",
            "Slash command requested review approval.",
            f"Confirm approval for {parts[1]}. Approval only creates a patch preview and does not modify target files.",
            "No durable memory was captured.",
            actions=[_action("Approve and generate preview", "POST", f"/api/reviews/{parts[1]}/approve", True)],
            data={"review": review},
        )
    if command == "/apply" and len(parts) == 2:
        current = ctx.review_store.get_review(parts[1])
        if not current:
            return _chat_result("error", "self_improvement", "Slash command requested review apply.", f"Unknown review_id: {parts[1]}", "No durable memory was captured.")
        if current.get("status") != "approved":
            return _chat_result(
                "approval_required",
                "self_improvement",
                "Slash command requested review apply.",
                f"Review {parts[1]} must be approved before apply.",
                "No durable memory was captured.",
                actions=[_action("Approve and generate preview", "POST", f"/api/reviews/{parts[1]}/approve", True)],
                data={"review": current},
            )
        patch = _patch_for_review(ctx, parts[1])
        return _chat_result(
            "approval_required",
            "self_improvement",
            "Slash command requested review apply.",
            f"Confirm apply for {parts[1]} only after inspecting the diff preview.",
            "No durable memory was captured.",
            actions=[_action("Apply reviewed change", "POST", f"/api/reviews/{parts[1]}/apply", True)],
            data={"review": current, "patch": patch},
        )
    if command == "/skill-versions" and len(parts) == 2:
        return _chat_result("tool_result", "self_improvement", "Slash command requested skill versions.", "Skill versions.", "No durable memory was captured.", data=ctx.versions.list_versions(parts[1]))
    return _chat_result(
        "error",
        "self_improvement",
        "Slash command was not recognized.",
        "Unknown command. Supported advanced commands: /promotions, /reviews, /evolve-skill <PROMO>, /approve <REV>, /apply <REV>, /skill-versions <skill>.",
        "No durable memory was captured.",
    )




def _recent_events(ctx: WebContext, limit: int = 50) -> list[dict[str, Any]]:
    path = ctx.project_root / ".audit" / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _display_path(ctx: WebContext, path: Path) -> str:
    try:
        return path.resolve().relative_to(ctx.project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _mtime(path: Path) -> str:
    if not path.exists():
        return ""
    return str(path.stat().st_mtime)


def _parse_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


app = create_app()
