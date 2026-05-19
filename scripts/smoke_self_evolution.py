from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.backends.local import LocalReviewStore
from runtime.learning_signal import (
    VERIFICATION_READ_SKIP_RESULT,
    classify_and_record_learning_signal,
)
from runtime.promotion_browser import PromotionBrowser, PromotionCandidateView
from runtime.regression_case_proposal import parse_regression_cases
from runtime.skill_evolution_flow import evolve_skill_from_promotion
from runtime.skill_memory import SkillMemoryManager, normalize_name


BOOK_NOTE_RULE = (
    "When writing book-note style Markdown, prefer the structure: "
    "书名 / 核心观点 / 三条启发 / 行动清单."
)

LEARNING_SAMPLES = [
    "以后 markdown_writer 写读书笔记时，建议使用 书名 / 核心观点 / 三条启发 / 行动清单 的结构。",
    "markdown_writer 遇到读书笔记类 Markdown 时，可以优先按 书名 / 核心观点 / 三条启发 / 行动清单 组织。",
    "读书笔记格式是 markdown_writer 的可复用写作习惯：书名 / 核心观点 / 三条启发 / 行动清单。",
]

ONE_OFF_SAMPLES = [
    "这次写短一点",
    "这次标题换成我的读后感",
    "这次不要太正式",
]

ARTIFACT_PATHS = (
    ".reviews",
    ".skills_memory",
    ".skills_versions",
    "skills/{skill}/memory",
    "skills/{skill}/eval/cases.yaml",
)


class SmokeFailure(AssertionError):
    def __init__(self, step: str, reason: str, paths: list[Path] | None = None):
        super().__init__(reason)
        self.step = step
        self.reason = reason
        self.paths = paths or []


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
    def __init__(self, payloads: list[dict[str, Any]]):
        self.payloads = list(payloads)
        self.calls = 0

    def create(self, **_kwargs: Any) -> FakeResponse:
        self.calls += 1
        if self.payloads:
            payload = self.payloads.pop(0)
        else:
            payload = {
                "should_record": False,
                "record_type": "learning",
                "target_skill": None,
                "reason": "No durable learning signal.",
                "attribution_confidence": "low",
                "title": "No-op",
                "content": "",
            }
        return FakeResponse(json.dumps(payload, ensure_ascii=False))


class FakeChat:
    def __init__(self, payloads: list[dict[str, Any]]):
        self.completions = FakeCompletions(payloads)


class FakeClient:
    def __init__(self, payloads: list[dict[str, Any]]):
        self.chat = FakeChat(payloads)


@dataclass
class SmokeOptions:
    root: Path = ROOT
    skill: str = "markdown_writer"
    clean: bool = False
    keep_artifacts: bool = False
    verbose: bool = False
    restore_skill: bool = True


@dataclass
class ArtifactSnapshot:
    path: Path
    existed: bool
    is_dir: bool = False
    files: dict[Path, bytes] | None = None


@dataclass
class SmokeContext:
    options: SmokeOptions
    skill: str
    root: Path
    manager: SkillMemoryManager
    browser: PromotionBrowser
    review_store: LocalReviewStore
    original_skill_text: str
    original_skill_existed: bool
    artifact_snapshot: list[ArtifactSnapshot]
    promo: PromotionCandidateView | None = None
    regression_review_id: str = ""
    skill_review_id: str = ""
    verification_skip_result: str = ""
    step_results: list[str] | None = None

    def refresh_browser(self) -> None:
        self.browser = PromotionBrowser(
            skills_dir=self.root / "skills",
            global_memory_dir=self.root / ".skills_memory",
            project_root=self.root,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test the SafeHarness self-evolving skill loop.",
    )
    parser.add_argument("--clean", action="store_true", help="clean local artifacts before running")
    parser.add_argument("--skill", default="markdown_writer", help="skill name to test")
    parser.add_argument("--keep-artifacts", action="store_true", help="keep generated artifacts")
    parser.add_argument("--verbose", action="store_true", help="print extra progress details")
    args = parser.parse_args(argv)

    options = SmokeOptions(
        skill=args.skill,
        clean=args.clean,
        keep_artifacts=args.keep_artifacts,
        verbose=args.verbose,
        restore_skill=not args.keep_artifacts,
    )
    return run_cli(options)


def run_cli(options: SmokeOptions) -> int:
    try:
        result = run_smoke(options)
    except SmokeFailure as failure:
        print(f"[FAIL] {failure.step}")
        print(f"Reason: {failure.reason}")
        if failure.paths:
            print("Paths:")
            for path in failure.paths:
                print(f"- {path}")
        return 1
    except Exception as exc:
        print("[FAIL] unexpected smoke test error")
        print(f"Reason: {exc}")
        return 1

    for line in result.step_results or []:
        print(line)
    if options.keep_artifacts:
        print("Artifacts kept:")
        for path in artifact_paths(result.root, result.skill):
            print(f"- {path}")
    print("Smoke test passed: SafeHarness self-evolving skill loop is healthy.")
    return 0


def run_smoke(options: SmokeOptions) -> SmokeContext:
    root = options.root.resolve()
    skill = normalize_name(options.skill or "markdown_writer")
    assert_project_root(root)

    skill_file = root / "skills" / skill / "SKILL.md"
    original_skill_existed = skill_file.exists()
    original_skill_text = skill_file.read_text(encoding="utf-8") if original_skill_existed else ""

    artifact_snapshot = snapshot_artifacts(root, skill)
    if options.clean:
        clean_artifacts(root, skill)
    ensure_minimal_skill(root, skill)

    if not original_skill_existed:
        original_skill_text = (root / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")

    ctx = SmokeContext(
        options=options,
        skill=skill,
        root=root,
        manager=SkillMemoryManager(root / "skills", root / ".skills_memory"),
        browser=PromotionBrowser(
            skills_dir=root / "skills",
            global_memory_dir=root / ".skills_memory",
            project_root=root,
        ),
        review_store=LocalReviewStore(root / ".reviews", root),
        original_skill_text=original_skill_text,
        original_skill_existed=original_skill_existed,
        artifact_snapshot=artifact_snapshot,
        step_results=[],
    )

    steps: list[tuple[str, Callable[[SmokeContext], None]]] = [
        ("record learning and generate PROMO", step_record_learning),
        ("create regression review", step_create_regression_review),
        ("apply regression cases", step_apply_regression_cases),
        ("create skill promotion review", step_create_skill_promotion_review),
        ("approve skill patch preview", step_approve_skill_patch_preview),
        ("apply skill patch and record version", step_apply_skill_patch_and_record_version),
        ("evolve-skill idempotency", step_evolve_skill_idempotency),
        ("policy_candidate blocked from SKILL.md", step_policy_candidate_blocked),
        ("one-off preferences not promoted", step_one_off_preferences_not_promoted),
        ("verification read_file skipped", step_verification_read_file_skipped),
    ]

    try:
        for step_name, step_func in steps:
            step_func(ctx)
            ctx.step_results.append(f"[PASS] {step_name}")
    except SmokeFailure:
        raise
    except Exception as exc:
        raise SmokeFailure("unexpected smoke step error", str(exc)) from exc
    finally:
        if not options.keep_artifacts:
            restore_skill_file(skill_file, original_skill_existed, original_skill_text)
            clean_artifacts(root, skill)
            if not options.clean:
                restore_artifacts(ctx.artifact_snapshot, root)

    return ctx


def assert_project_root(root: Path) -> None:
    required = [root / "docs" / "CHANGELOG.md", root / "runtime", root / "harness"]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise SmokeFailure(
            "startup checks",
            "Current directory does not look like the project root.",
            missing,
        )


def ensure_minimal_skill(root: Path, skill: str) -> None:
    skill_dir = root / "skills" / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        skill_file.write_text(
            "\n".join(
                [
                    "---",
                    f"name: {skill}",
                    "description: Minimal test skill for self-evolution smoke validation.",
                    "---",
                    "",
                    f"# {skill}",
                    "",
                    "Write clear Markdown for the requested task.",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def restore_skill_file(skill_file: Path, existed: bool, original_text: str) -> None:
    if existed:
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(original_text, encoding="utf-8")
    elif skill_file.exists():
        skill_file.unlink()


def clean_artifacts(root: Path, skill: str) -> None:
    for path in artifact_paths(root, skill):
        safe_remove(path, root)


def artifact_paths(root: Path, skill: str) -> list[Path]:
    return [root / item.format(skill=skill) for item in ARTIFACT_PATHS]


def safe_remove(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise SmokeFailure("cleanup", "Refusing to remove a path outside the project root.", [path])
    if not resolved_path.exists():
        return
    if resolved_path.is_dir():
        shutil.rmtree(resolved_path)
    else:
        resolved_path.unlink()


def snapshot_artifacts(root: Path, skill: str) -> list[ArtifactSnapshot]:
    snapshots: list[ArtifactSnapshot] = []
    for path in artifact_paths(root, skill):
        resolved = path.resolve()
        if not resolved.exists():
            snapshots.append(ArtifactSnapshot(path=path, existed=False))
            continue
        if resolved.is_dir():
            files = {
                file.relative_to(resolved): file.read_bytes()
                for file in sorted(resolved.rglob("*"))
                if file.is_file()
            }
            snapshots.append(ArtifactSnapshot(path=path, existed=True, is_dir=True, files=files))
        else:
            snapshots.append(ArtifactSnapshot(path=path, existed=True, files={Path("."): resolved.read_bytes()}))
    return snapshots


def restore_artifacts(snapshots: list[ArtifactSnapshot], root: Path) -> None:
    for snapshot in snapshots:
        if not snapshot.existed:
            continue
        path = snapshot.path
        safe_remove(path, root)
        if snapshot.is_dir:
            for relative, content in (snapshot.files or {}).items():
                target = path / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            content = (snapshot.files or {}).get(Path("."), b"")
            path.write_bytes(content)


def step_record_learning(ctx: SmokeContext) -> None:
    client = FakeClient(
        [
            {
                "should_record": True,
                "record_type": "learning",
                "target_skill": ctx.skill,
                "reason": "User repeatedly gave a durable book-note Markdown structure.",
                "attribution_confidence": "high",
                "title": "Book note fixed structure",
                "content": sample,
            }
            for sample in LEARNING_SAMPLES
        ]
    )

    for sample in LEARNING_SAMPLES:
        classify_and_record_learning_signal(
            client=client,
            model="smoke-fake-classifier",
            skill_memory=ctx.manager,
            raw_content=sample,
            conversation_context=[{"role": "user", "content": sample}],
            latest_tool_events=[],
            latest_llm_messages=[],
            explicit_skill_name=ctx.skill,
        )

    learning_path = ctx.root / "skills" / ctx.skill / "memory" / "LEARNINGS.md"
    learning_text = read_text(learning_path)
    require(
        max_occurrence_count(learning_text) >= 3,
        "LEARNINGS.md did not reach occurrence_count >= 3.",
        "record learning and generate PROMO",
        [learning_path],
    )

    ctx.refresh_browser()
    promo = first_matching_promo(ctx, source_type="learning", target_skill=ctx.skill)
    require(promo is not None, "No PROMO was generated from learning memory.", "record learning and generate PROMO")
    assert promo is not None
    ctx.promo = promo
    require(promo.target_skill == ctx.skill, "PROMO target_skill is wrong.", "record learning and generate PROMO")
    require(promo.source_memory_type == "learning", "PROMO source_memory_type is not learning.", "record learning and generate PROMO")
    require(float(promo.promotion_score) > 0, "PROMO promotion_score is not positive.", "record learning and generate PROMO")
    require(promo.promotion_decision == "promote", "PROMO promotion_decision is not promote.", "record learning and generate PROMO")
    require(promo.eligible_target == "skill_rule", "PROMO eligible_target is not skill_rule.", "record learning and generate PROMO")


def step_create_regression_review(ctx: SmokeContext) -> None:
    promo = require_promo(ctx)
    cases_file = ctx.root / "skills" / ctx.skill / "eval" / "cases.yaml"
    cases_before = read_text(cases_file)
    result = evolve_skill_from_promotion(
        browser=ctx.browser,
        review_store=ctx.review_store,
        promo_id=promo.promo_id,
        project_root=ctx.root,
    )
    require(result.ok, result.message, "create regression review")
    ctx.regression_review_id = result.review_id
    review = get_review(ctx, result.review_id, "create regression review")
    require(review["type"] == "skill.regression_case", "review type is not skill.regression_case.", "create regression review")
    require(review["candidate_id"] == promo.promo_id, "review candidate_id does not match PROMO.", "create regression review")
    require(review["target_files"] == [f"skills/{ctx.skill}/eval/cases.yaml"], "regression review target_files is wrong.", "create regression review")
    require(review["status"] == "pending", "regression review status is not pending.", "create regression review")
    require(read_text(cases_file) == cases_before, "evolve-skill modified eval/cases.yaml before apply.", "create regression review", [cases_file])


def step_apply_regression_cases(ctx: SmokeContext) -> None:
    review = approve_and_preview(ctx, ctx.regression_review_id, "apply regression cases")
    require(review["status"] == "approved", "regression review was not approved.", "apply regression cases")
    applied, _message = ctx.review_store.apply_review(ctx.regression_review_id)
    require(applied["status"] == "applied", "regression review was not applied.", "apply regression cases")

    promo = require_promo(ctx)
    cases_path = ctx.root / "skills" / ctx.skill / "eval" / "cases.yaml"
    cases_text = read_text(cases_path)
    cases = [
        case for case in parse_regression_cases(cases_text)
        if case.get("source_promo_id") == promo.promo_id
    ]
    positives = [case for case in cases if case.get("must_include")]
    negatives = [case for case in cases if case.get("must_not_include")]
    expected_terms = ["书名", "核心观点", "三条启发", "行动清单"]
    require(cases_path.exists(), "cases.yaml was not created.", "apply regression cases", [cases_path])
    require(f"source_promo_id: \"{promo.promo_id}\"" in cases_text, "cases.yaml missing source_promo_id.", "apply regression cases", [cases_path])
    require(positives, "cases.yaml has no positive case.", "apply regression cases", [cases_path])
    require(negatives, "cases.yaml has no negative case.", "apply regression cases", [cases_path])
    require(all(term in positives[0].get("must_include", []) for term in expected_terms), "positive case missing required must_include terms.", "apply regression cases", [cases_path])
    require(all(term in negatives[0].get("must_not_include", []) for term in expected_terms), "negative case missing required must_not_include terms.", "apply regression cases", [cases_path])


def step_create_skill_promotion_review(ctx: SmokeContext) -> None:
    promo = require_promo(ctx)
    skill_file = ctx.root / "skills" / ctx.skill / "SKILL.md"
    before = read_text(skill_file)
    result = evolve_skill_from_promotion(
        browser=ctx.browser,
        review_store=ctx.review_store,
        promo_id=promo.promo_id,
        project_root=ctx.root,
    )
    require(result.ok, result.message, "create skill promotion review")
    ctx.skill_review_id = result.review_id
    review = get_review(ctx, result.review_id, "create skill promotion review")
    forbidden = [
        "Based on repeated safety or policy signals",
        "before changing any policy",
        "bypass approval",
        "disable safety",
    ]
    require(review["type"] == "skill.promotion", "review type is not skill.promotion.", "create skill promotion review")
    require(review["candidate_id"] == promo.promo_id, "skill review candidate_id does not match PROMO.", "create skill promotion review")
    require(review["target_files"] == [f"skills/{ctx.skill}/SKILL.md"], "skill review target_files is wrong.", "create skill promotion review")
    require(review["status"] == "pending", "skill review status is not pending.", "create skill promotion review")
    require(review["proposed_change"] == BOOK_NOTE_RULE, "proposed_change is not the concrete book-note rule.", "create skill promotion review")
    require(not any(text in review["proposed_change"] for text in forbidden), "proposed_change contains forbidden safety-policy template text.", "create skill promotion review")
    require(read_text(skill_file) == before, "evolve-skill modified SKILL.md before apply.", "create skill promotion review", [skill_file])


def step_approve_skill_patch_preview(ctx: SmokeContext) -> None:
    skill_file = ctx.root / "skills" / ctx.skill / "SKILL.md"
    before = read_text(skill_file)
    review = approve_and_preview(ctx, ctx.skill_review_id, "approve skill patch preview")
    patch_path = ctx.root / ".reviews" / "patches" / f"{ctx.skill_review_id}.diff"
    patch_text = read_text(patch_path)
    require(review["status"] == "approved", "skill review was not approved.", "approve skill patch preview")
    require(patch_path.exists(), "skill patch preview was not written.", "approve skill patch preview", [patch_path])
    require(f"--- skills/{ctx.skill}/SKILL.md" in patch_text, "patch preview does not target SKILL.md.", "approve skill patch preview", [patch_path])
    require("eval/cases.yaml" not in patch_text and ".skills_memory" not in patch_text, "patch preview points to unexpected files.", "approve skill patch preview", [patch_path])
    require("Memory-derived rules" in patch_text, "patch preview missing Memory-derived rules.", "approve skill patch preview", [patch_path])
    require(read_text(skill_file) == before, "approve modified SKILL.md before apply.", "approve skill patch preview", [skill_file])


def step_apply_skill_patch_and_record_version(ctx: SmokeContext) -> None:
    promo = require_promo(ctx)
    applied, _message = ctx.review_store.apply_review(ctx.skill_review_id)
    require(applied["status"] == "applied", "skill review was not applied.", "apply skill patch and record version")

    skill_file = ctx.root / "skills" / ctx.skill / "SKILL.md"
    skill_text = read_text(skill_file)
    versions_file = ctx.root / ".skills_versions" / ctx.skill / "versions.jsonl"
    version_dir = ctx.root / ".skills_versions" / ctx.skill / "v0.1.1"
    expected_terms = ["book-note", "书名", "核心观点", "三条启发", "行动清单"]
    require("Memory-derived rules" in skill_text, "SKILL.md missing Memory-derived rules.", "apply skill patch and record version", [skill_file])
    require(all(term in skill_text for term in expected_terms), "SKILL.md missing promoted book-note rule terms.", "apply skill patch and record version", [skill_file])
    require(versions_file.exists(), "versions.jsonl was not created.", "apply skill patch and record version", [versions_file])
    require((version_dir / "SKILL.md").exists(), "version snapshot SKILL.md missing.", "apply skill patch and record version", [version_dir / "SKILL.md"])
    require((version_dir / "patch.diff").exists(), "version patch.diff missing.", "apply skill patch and record version", [version_dir / "patch.diff"])
    require((version_dir / "eval_result.json").exists(), "version eval_result.json missing.", "apply skill patch and record version", [version_dir / "eval_result.json"])
    records = read_jsonl(versions_file)
    require(records, "versions.jsonl contains no records.", "apply skill patch and record version", [versions_file])
    record = records[-1]
    require(record.get("promotion_id") == promo.promo_id, "version record promotion_id is wrong.", "apply skill patch and record version", [versions_file])
    require(record.get("skill_review_id") == ctx.skill_review_id, "version record skill_review_id is wrong.", "apply skill patch and record version", [versions_file])
    require(ctx.regression_review_id in record.get("regression_review_ids", []), "version record regression_review_ids is missing regression review.", "apply skill patch and record version", [versions_file])
    require(record.get("base_hash") != record.get("new_hash"), "version record base_hash equals new_hash.", "apply skill patch and record version", [versions_file])


def step_evolve_skill_idempotency(ctx: SmokeContext) -> None:
    promo = require_promo(ctx)
    before_reviews = review_counts(ctx)
    result = evolve_skill_from_promotion(
        browser=ctx.browser,
        review_store=ctx.review_store,
        promo_id=promo.promo_id,
        project_root=ctx.root,
    )
    after_reviews = review_counts(ctx)
    require(result.ok, result.message, "evolve-skill idempotency")
    require(result.stage == "complete", "evolve-skill did not return complete after apply.", "evolve-skill idempotency")
    require("already applied" in result.message.lower() or "completed" in result.message.lower(), "idempotent result did not report already applied/completed.", "evolve-skill idempotency")
    require(ctx.skill_review_id in result.message or result.review_id == ctx.skill_review_id, "idempotent result did not link applied review_id.", "evolve-skill idempotency")
    require(after_reviews == before_reviews, "idempotent evolve-skill created a new review.", "evolve-skill idempotency")


def step_policy_candidate_blocked(ctx: SmokeContext) -> None:
    for _ in range(3):
        ctx.manager.record_policy_candidate(
            ctx.skill,
            "Policy review only",
            "Repeated SafeHarness policy signal should route to policy_review, not SKILL.md.",
            source="smoke",
        )
    ctx.refresh_browser()
    policy_promos = [
        promo for promo in ctx.browser.list_candidates()
        if promo.source_memory_type == "policy_candidate"
    ]
    require(policy_promos, "No policy_candidate PROMO was generated.", "policy_candidate blocked from SKILL.md")
    policy_promo = policy_promos[-1]
    before_skill_reviews = count_reviews(ctx, "skill.promotion")
    result = evolve_skill_from_promotion(
        browser=ctx.browser,
        review_store=ctx.review_store,
        promo_id=policy_promo.promo_id,
        project_root=ctx.root,
    )
    after_skill_reviews = count_reviews(ctx, "skill.promotion")
    require(not result.ok, "policy_candidate was accepted into skill evolution.", "policy_candidate blocked from SKILL.md")
    require(
        policy_promo.eligible_target == "policy_review" or policy_promo.promotion_decision == "policy_review",
        "policy_candidate PROMO is not routed to policy_review.",
        "policy_candidate blocked from SKILL.md",
    )
    require(after_skill_reviews == before_skill_reviews, "policy_candidate created a skill.promotion review.", "policy_candidate blocked from SKILL.md")


def step_one_off_preferences_not_promoted(ctx: SmokeContext) -> None:
    before_skill_rule_promos = {
        promo.promo_id
        for promo in ctx.browser.list_candidates()
        if promo.eligible_target == "skill_rule"
    }
    for sample in ONE_OFF_SAMPLES:
        ctx.manager.record_learning(
            ctx.skill,
            "One-off preference",
            sample,
            source="smoke_one_off",
        )
    ctx.refresh_browser()
    after_skill_rule_promos = {
        promo.promo_id
        for promo in ctx.browser.list_candidates()
        if promo.eligible_target == "skill_rule"
    }
    new_skill_rule_promos = after_skill_rule_promos - before_skill_rule_promos
    learning_text = read_text(ctx.root / "skills" / ctx.skill / "memory" / "LEARNINGS.md")
    require(not new_skill_rule_promos, "one-off preferences generated a skill_rule PROMO.", "one-off preferences not promoted")
    require("One-off preference" in learning_text and "- Promotion Decision: wait" in learning_text, "one-off preference record did not remain wait/reject.", "one-off preferences not promoted")


def step_verification_read_file_skipped(ctx: SmokeContext) -> None:
    before_learning = read_text(ctx.root / "skills" / ctx.skill / "memory" / "LEARNINGS.md")
    before_promos = read_text(ctx.root / ".skills_memory" / "PROMOTION_CANDIDATES.md")
    events = [
        {"tool": "read_file", "arguments": {"path": ".reviews/patches/REV.diff"}, "status": "ok"},
        {"tool": "read_file", "arguments": {"path": f"skills/{ctx.skill}/SKILL.md"}, "status": "ok"},
        {"tool": "read_file", "arguments": {"path": f"skills/{ctx.skill}/eval/cases.yaml"}, "status": "ok"},
        {"tool": "read_file", "arguments": {"path": ".skills_versions/markdown_writer/v0.1.1/SKILL.md"}, "status": "ok"},
        {"tool": "bash", "arguments": {"command": f"Get-Content skills/{ctx.skill}/SKILL.md"}, "status": "ok"},
        {"tool": "bash", "arguments": {"command": "Select-String -Path .skills_versions/markdown_writer/versions.jsonl -Pattern v0.1.1"}, "status": "ok"},
    ]
    client = FakeClient(
        [
            {
                "should_record": True,
                "record_type": "learning",
                "target_skill": ctx.skill,
                "reason": "This should be skipped.",
                "attribution_confidence": "high",
                "title": "Bad verification learning",
                "content": "Verification reads should not create learning.",
            }
        ]
    )
    result = classify_and_record_learning_signal(
        client=client,
        model="smoke-fake-classifier",
        skill_memory=ctx.manager,
        raw_content="verification reads",
        latest_tool_events=events,
        latest_llm_messages=[],
    )
    ctx.verification_skip_result = str(result.get("record_result", ""))
    after_learning = read_text(ctx.root / "skills" / ctx.skill / "memory" / "LEARNINGS.md")
    after_promos = read_text(ctx.root / ".skills_memory" / "PROMOTION_CANDIDATES.md")
    require(ctx.verification_skip_result == VERIFICATION_READ_SKIP_RESULT, "verification read did not return skipped result.", "verification read_file skipped")
    require(client.chat.completions.calls == 0, "verification read called the classifier.", "verification read_file skipped")
    require(after_learning == before_learning, "verification read added LEARNINGS.md content.", "verification read_file skipped")
    require(after_promos == before_promos, "verification read generated a new PROMO.", "verification read_file skipped")


def approve_and_preview(ctx: SmokeContext, review_id: str, step: str) -> dict[str, Any]:
    try:
        review, patch_path = ctx.review_store.approve_review(review_id)
    except ValueError as exc:
        raise SmokeFailure(step, str(exc)) from exc
    require(patch_path, "approve did not create a patch preview.", step)
    require(Path(patch_path).exists(), "patch preview path does not exist.", step, [Path(patch_path)])
    return review


def require_promo(ctx: SmokeContext) -> PromotionCandidateView:
    if ctx.promo is None:
        raise SmokeFailure("internal smoke state", "PROMO was not recorded in context.")
    return ctx.promo


def first_matching_promo(
    ctx: SmokeContext,
    *,
    source_type: str,
    target_skill: str,
) -> PromotionCandidateView | None:
    for promo in ctx.browser.list_candidates():
        if promo.source_memory_type == source_type and promo.target_skill == target_skill:
            return promo
    return None


def get_review(ctx: SmokeContext, review_id: str, step: str) -> dict[str, Any]:
    review = ctx.review_store.get_review(review_id)
    require(review is not None, f"Unknown review_id: {review_id}", step)
    return review or {}


def count_reviews(ctx: SmokeContext, review_type: str) -> int:
    return sum(1 for review in ctx.review_store.list_reviews(None) if review.get("type") == review_type)


def review_counts(ctx: SmokeContext) -> dict[str, int]:
    counts: dict[str, int] = {}
    for review in ctx.review_store.list_reviews(None):
        key = f"{review.get('type')}:{review.get('status')}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in read_text(path).splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def max_occurrence_count(text: str) -> int:
    counts = []
    for line in text.splitlines():
        if not line.startswith("- Occurrence Count:"):
            continue
        try:
            counts.append(int(line.split(":", 1)[1].strip()))
        except ValueError:
            continue
    return max(counts, default=0)


def require(condition: bool, reason: str, step: str, paths: list[Path] | None = None) -> None:
    if not condition:
        raise SmokeFailure(step, reason, paths)


if __name__ == "__main__":
    raise SystemExit(main())
