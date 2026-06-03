"""SkillOptimizer: bounded edit proposals + deterministic validation gate.

The Optimizer is the only writer in the side-channel pipeline. Even
then, it never modifies SKILL.md, ReviewQueue records, evaluator
configuration, or regression cases directly. It can:

1. Create a ``SkillEditProposal`` in ``.evolution/skill_edits/<id>.json``
   with ``edit_ops`` constrained to add/replace/delete on
   ``## Memory-derived rules``.
2. Run a deterministic ``ValidationGate`` whose result is written to
   ``.evolution/validation_results/<id>.json``. Failures go to
   ``.evolution/rejected_edits/<edit_id>.json`` and do **not** create a
   ReviewQueue item.
3. On successful validation, create a ReviewQueue item of type
   ``skill.bounded_edit`` so the human can approve and apply. The actual
   write to ``skills/<skill>/SKILL.md`` is performed by ReviewQueue.apply
   only after the human approves.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .evolution_scout import detect_policy_gate
from .evolution_stores import (
    EvolutionStores,
    RejectedEdit,
    SkillEditProposal,
    ValidationResult,
    validate_edit_ops,
)


@dataclass
class OptimizerResult:
    ok: bool
    message: str
    edit_id: str = ""
    review_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "edit_id": self.edit_id,
            "review_id": self.review_id,
        }


class SkillOptimizer:
    """Produces bounded edits. Never touches SKILL.md directly."""

    def __init__(
        self,
        *,
        project_root: Path | str,
        stores: EvolutionStores,
        review_store,
        validation_gate: "ValidationGate | None" = None,
        bullet_writer: Any = None,
        decision_store: Any = None,
    ):
        self.project_root = Path(project_root)
        self.stores = stores
        self.review_store = review_store
        self.validation_gate = validation_gate or ValidationGate()
        self.bullet_writer = bullet_writer
        if decision_store is None:
            from .scout_decisions import ScoutDecisionStore
            decision_store = ScoutDecisionStore(self.project_root)
        self.decision_store = decision_store

    def _record_scout_outcome(
        self,
        opportunities: list[dict[str, Any]],
        status: str,
        details: dict[str, Any],
    ) -> None:
        for opp in opportunities:
            opp_id = opp.get("opportunity_id")
            if not opp_id:
                continue
            self.decision_store.record_outcome(opp_id, status, details)

    def _record_scout_outcome_by_ids(
        self,
        opportunity_ids: list[str],
        status: str,
        details: dict[str, Any],
    ) -> None:
        for opp_id in opportunity_ids:
            if not opp_id:
                continue
            self.decision_store.record_outcome(opp_id, status, details)

    def propose(
        self,
        *,
        batch_id: str = "",
        opportunity_id: str = "",
    ) -> OptimizerResult:
        if not batch_id and not opportunity_id:
            return OptimizerResult(False, "either batch_id or opportunity_id is required")

        if batch_id:
            batch = self.stores.batches.get(batch_id)
            if not batch:
                return OptimizerResult(False, f"unknown batch_id: {batch_id}")
            opportunities = [
                self.stores.opportunities.get(opp_id) for opp_id in batch["opportunity_ids"]
            ]
            opportunities = [opp for opp in opportunities if opp]
            target_skill = batch["target_skill"]
            source_batch_id = batch_id
            source_promo_ids = list(batch.get("promo_ids") or [])
        else:
            opp = self.stores.opportunities.get(opportunity_id)
            if not opp:
                return OptimizerResult(False, f"unknown opportunity_id: {opportunity_id}")
            opportunities = [opp]
            target_skill = opp["target_skill"]
            source_batch_id = ""
            source_promo_ids = list(opp.get("related_promo_ids") or [])

        if not opportunities:
            return OptimizerResult(False, "no opportunities to propose from")

        if any(opp.get("decision") == "reject" for opp in opportunities):
            return OptimizerResult(
                False,
                "refusing to optimize: at least one opportunity has decision=reject",
            )

        blocked_decisions = {"quarantine", "safety_review"}
        for opp in opportunities:
            if opp.get("decision") in blocked_decisions:
                return OptimizerResult(
                    False,
                    f"refusing to optimize: opportunity decision='{opp.get('decision')}' "
                    "is not eligible for bounded edit (memory poisoning or safety incident).",
                )

        signal_ids: list[str] = []
        for opp in opportunities:
            signal_ids.extend(opp.get("signal_ids", []))
        if not signal_ids:
            return OptimizerResult(
                False,
                "refusing to optimize: opportunities have no source signal references",
            )

        # Defence-in-depth: even if a normal opportunity sneaks in a
        # quarantined signal via some future code path, refuse.
        for signal_id in set(signal_ids):
            signal = self.stores.signals.get(signal_id)
            if signal and signal.get("quarantined"):
                return OptimizerResult(
                    False,
                    f"refusing to optimize: signal {signal_id} is quarantined "
                    f"(attack_type={signal.get('attack_type', 'unknown')}).",
                )

        # Defence-in-depth #2: scan each opportunity's actual tag set +
        # source signal content for the same policy / approval /
        # SafeHarness markers the Scout's policy_gate uses. Even if a
        # decision somehow reached us as promote / request_eval / defer
        # while still carrying policy_block / approval_block /
        # Tool Call Blocked / Policy Enforcement Triggered / SafeHarness
        # policy / protected file / safety markers in its tags or
        # member content, we refuse here and steer to policy_review /
        # tool_review. ``requires_policy_review=true`` is surfaced in
        # the message so the UI / CLI can route accordingly.
        for opp in opportunities:
            members: list[dict[str, Any]] = []
            for signal_id in opp.get("signal_ids", []):
                signal = self.stores.signals.get(signal_id)
                if signal:
                    members.append(signal)
            tag_set: set[str] = set()
            for member in members:
                for tag in (member.get("tags") or []):
                    bare = str(tag).split(":", 1)[0]
                    if bare:
                        tag_set.add(bare)
            triggered, reasons = detect_policy_gate(members, tag_set)
            if triggered:
                joined = ", ".join(reasons) or "policy_gate=True"
                return OptimizerResult(
                    False,
                    f"refusing to optimize: opportunity '{opp.get('opportunity_id')}' "
                    f"carries policy / approval / SafeHarness markers ({joined}). "
                    "requires_policy_review=true — route to policy_review / tool_review "
                    "instead of skill.bounded_edit / skill.promotion.",
                )

        edit_ops = _build_edit_ops(opportunities, self.stores)
        if self.bullet_writer is not None:
            llm_bullets = self._llm_bullets(opportunities)
            if llm_bullets:
                edit_ops = [
                    {"op": "add", "target_section": "## Memory-derived rules", "text": bullet}
                    for bullet in llm_bullets[:3]
                ]
        ok, reason = validate_edit_ops(edit_ops)
        if not ok:
            return OptimizerResult(False, f"refused: {reason}")

        rationale = _rationale_text(opportunities)
        expected = "; ".join(
            line for opp in opportunities for line in (opp.get("should_improve") or [])
        )[:500]
        risk_assessment = _risk_text(opportunities)
        required_validation = sorted({
            line for opp in opportunities for line in (opp.get("must_not_regress") or [])
        })

        edit = SkillEditProposal.new(
            target_skill=target_skill,
            source_batch_id=source_batch_id,
            source_opportunity_ids=[opp["opportunity_id"] for opp in opportunities],
            source_signal_ids=sorted(set(signal_ids)),
            source_promo_ids=sorted(set(source_promo_ids)),
            edit_ops=edit_ops,
            rationale=rationale,
            expected_improvement=expected,
            risk_assessment=risk_assessment,
            required_validation_cases=required_validation,
        )
        stored = self.stores.skill_edits.save(edit)
        self._record_scout_outcome(
            opportunities,
            "optimizer_proposed",
            {"edit_id": stored["edit_id"]},
        )
        return OptimizerResult(
            True,
            f"Created skill edit {stored['edit_id']}. No SKILL.md file was modified.",
            edit_id=stored["edit_id"],
        )

    def validate(self, edit_id: str) -> OptimizerResult:
        edit = self.stores.skill_edits.get(edit_id)
        if not edit:
            return OptimizerResult(False, f"unknown edit_id: {edit_id}")
        if edit.get("status") == "review_created":
            return OptimizerResult(
                True,
                f"Edit {edit_id} already created review {edit.get('review_id', '')}.",
                edit_id=edit_id,
                review_id=edit.get("review_id", ""),
            )

        ok, reason = validate_edit_ops(edit.get("edit_ops", []))
        if not ok:
            self._reject(edit, reason, train=0.0, validation=0.0, regression=0.0)
            return OptimizerResult(False, f"validation failed: {reason}", edit_id=edit_id)

        result = self.validation_gate.evaluate(edit, project_root=self.project_root)
        record = ValidationResult.new(
            edit_id=edit_id,
            train_score=result["train_score"],
            validation_score=result["validation_score"],
            regression_score=result["regression_score"],
            accepted=result["accepted"],
            reject_reason=result.get("reject_reason", ""),
        )
        self.stores.validation_results.save(record)

        if not result["accepted"]:
            self._reject(
                edit,
                result.get("reject_reason", "validation failed"),
                train=result["train_score"],
                validation=result["validation_score"],
                regression=result["regression_score"],
                validation_id=record.validation_id,
            )
            return OptimizerResult(
                False,
                f"validation failed: {result.get('reject_reason', 'validation gate rejected the edit')}",
                edit_id=edit_id,
            )

        self.stores.skill_edits.update(edit_id, status="validated")
        return OptimizerResult(True, f"Edit {edit_id} passed validation.", edit_id=edit_id)

    def submit_review(self, edit_id: str) -> OptimizerResult:
        edit = self.stores.skill_edits.get(edit_id)
        if not edit:
            return OptimizerResult(False, f"unknown edit_id: {edit_id}")
        if edit.get("status") != "validated":
            return OptimizerResult(
                False,
                f"edit {edit_id} status is '{edit.get('status')}'; must be 'validated' before submit",
                edit_id=edit_id,
            )

        target_file = f"skills/{edit['target_skill']}/SKILL.md"
        review_fields = {
            "type": "skill.bounded_edit",
            "source": "skill_optimizer",
            "candidate_id": edit_id,
            "target_skill": edit["target_skill"],
            "target_files": [target_file],
            "severity": "medium",
            "reason": edit.get("rationale", "")[:400] or "bounded edit from skill optimizer",
            "proposed_change": _proposed_change_text(edit),
            "evaluation_plan": (
                f"Review edit_ops; run skills/{edit['target_skill']}/eval/cases.yaml if present; "
                "verify diff stays inside '## Memory-derived rules'."
            ),
            "rollback_plan": "revert the SKILL.md patch via /rollback-skill or git",
            "status": "pending",
            "metadata": {
                "source_edit_id": edit_id,
                "source_batch_id": edit.get("source_batch_id", ""),
                "source_opportunity_ids": edit.get("source_opportunity_ids", []),
                "source_signal_ids": edit.get("source_signal_ids", []),
                "source_promo_ids": edit.get("source_promo_ids", []),
                "edit_ops": edit.get("edit_ops", []),
                "expected_improvement": edit.get("expected_improvement", ""),
                "required_validation_cases": edit.get("required_validation_cases", []),
            },
        }
        item = self.review_store.create_review(**review_fields)
        review_id = item.get("review_id", "")
        self.stores.skill_edits.update(edit_id, status="review_created", review_id=review_id)
        self._record_scout_outcome_by_ids(
            edit.get("source_opportunity_ids") or [],
            "review_created",
            {"review_id": review_id, "edit_id": edit_id},
        )
        return OptimizerResult(
            True,
            f"Created review {review_id} for edit {edit_id}. SKILL.md not modified.",
            edit_id=edit_id,
            review_id=review_id,
        )

    def _llm_bullets(self, opportunities: list[dict[str, Any]]) -> list[str]:
        if self.bullet_writer is None or not opportunities:
            return []
        signals: list[dict[str, Any]] = []
        for opp in opportunities:
            for signal_id in opp.get("signal_ids", []):
                signal = self.stores.signals.get(signal_id)
                if signal:
                    signals.append(signal)
        try:
            return self.bullet_writer.write(opportunities[0], signals)
        except Exception:
            return []

    def _reject(
        self,
        edit: dict[str, Any],
        reason: str,
        *,
        train: float,
        validation: float,
        regression: float,
        validation_id: str = "",
    ) -> None:
        rejected = RejectedEdit(
            edit_id=edit["edit_id"],
            validation_id=validation_id,
            reject_reason=reason,
            edit_snapshot={
                **edit,
                "scores": {
                    "train": train,
                    "validation": validation,
                    "regression": regression,
                },
            },
        )
        self.stores.rejected_edits.save(rejected)
        self.stores.skill_edits.update(
            edit["edit_id"], status="rejected", review_id=""
        )


class ValidationGate:
    """Deterministic, no-LLM validation gate for the MVP.

    The interface is intentionally narrow so that a real LLM-backed gate
    can replace this without changing the Optimizer call site. The
    implementation reads the on-disk SKILL.md and any
    ``skills/<skill>/eval/cases.yaml`` to compute simple scores.
    """

    def __init__(
        self,
        *,
        train_evaluator: Callable[[dict[str, Any], Path], float] | None = None,
        regression_evaluator: Callable[[dict[str, Any], Path], float] | None = None,
        min_validation_score: float = 0.5,
        min_regression_score: float = 0.5,
    ):
        self.train_evaluator = train_evaluator
        self.regression_evaluator = regression_evaluator
        self.min_validation_score = min_validation_score
        self.min_regression_score = min_regression_score

    def evaluate(
        self,
        edit: dict[str, Any],
        *,
        project_root: Path,
    ) -> dict[str, Any]:
        from .evolution_stores import apply_edit_ops_to_text
        from .skill_eval_runner import (
            load_cases_for_skill,
            run_cases,
            summarize_failures,
        )

        train = self.train_evaluator(edit, project_root) if self.train_evaluator else 0.6
        target_skill = str(edit.get("target_skill", ""))
        skill_path = Path(project_root) / "skills" / target_skill / "SKILL.md"
        base_text = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
        try:
            proposed_text = apply_edit_ops_to_text(base_text, edit.get("edit_ops") or [])
        except Exception:
            proposed_text = base_text
        cases = load_cases_for_skill(project_root, target_skill)
        report = run_cases(cases, proposed_text, skill=target_skill)

        # validation_score = pass ratio of the eval cases (1.0 when no
        # cases are defined yet, so the gate doesn't block a freshly
        # seeded skill).
        validation_score = (
            report.passed_count / report.total if report.total > 0 else 1.0
        )

        if self.regression_evaluator is not None:
            regression = self.regression_evaluator(edit, project_root)
        else:
            # Keep the dangerous-word guard so unsafe phrases inside
            # cases.yaml still drag the regression score to 0.
            regression = _default_regression_score(edit, project_root)
            if report.accepted:
                # Lift toward 1.0 when eval is clean, so the gate only
                # blocks when the cases.yaml says it should.
                regression = max(regression, 0.75)

        accepted = (
            report.accepted
            and validation_score >= self.min_validation_score
            and regression >= self.min_regression_score
        )
        reject_reason = ""
        if not accepted:
            if not report.accepted:
                reject_reason = summarize_failures(report)
            elif regression < self.min_regression_score:
                reject_reason = f"regression_score {regression:.2f} below threshold"
            else:
                reject_reason = f"validation_score {validation_score:.2f} below threshold"
        return {
            "train_score": float(train),
            "validation_score": float(validation_score),
            "regression_score": float(regression),
            "accepted": accepted,
            "reject_reason": reject_reason,
            "eval_report": report.to_dict(),
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _build_edit_ops(
    opportunities: list[dict[str, Any]],
    stores: EvolutionStores,
) -> list[dict[str, Any]]:
    bullets: list[str] = []
    seen: set[str] = set()
    for opp in opportunities:
        for line in opp.get("should_improve") or []:
            bullet = line.strip()
            if bullet and bullet not in seen:
                seen.add(bullet)
                bullets.append(bullet)
        summary = (opp.get("summary") or "").split("|", 1)[-1].strip()
        if summary:
            short = summary.split(".")[0][:160].strip()
            if short and short not in seen:
                seen.add(short)
                bullets.append(short)
    if not bullets:
        bullets.append("apply lessons from recent learning signals")
    return [
        {"op": "add", "target_section": "## Memory-derived rules", "text": bullet}
        for bullet in bullets[:3]
    ]


def _rationale_text(opportunities: list[dict[str, Any]]) -> str:
    parts = []
    for opp in opportunities:
        parts.append(
            f"{opp['opportunity_id']} (score={opp.get('evolution_score', 0):.2f}, "
            f"signals={len(opp.get('signal_ids', []))})"
        )
    return "; ".join(parts)[:1000]


def _risk_text(opportunities: list[dict[str, Any]]) -> str:
    risks = sorted({opp.get("risk_level", "low") for opp in opportunities})
    must_not = sorted({
        line for opp in opportunities for line in (opp.get("must_not_regress") or [])
    })
    body = f"risk_levels={','.join(risks)}"
    if must_not:
        body += " | must_not_regress=" + "; ".join(must_not)
    return body[:500]


def _proposed_change_text(edit: dict[str, Any]) -> str:
    lines = ["Bounded edit:"]
    for op in edit.get("edit_ops", []):
        lines.append(
            f"- {op.get('op', '?')} :: {op.get('text', '').strip()[:200]}"
        )
    return "\n".join(lines)


def _default_regression_score(edit: dict[str, Any], project_root: Path) -> float:
    target_skill = edit.get("target_skill", "")
    eval_path = project_root / "skills" / target_skill / "eval" / "cases.yaml"
    if not eval_path.exists():
        return 0.6
    raw = eval_path.read_text(encoding="utf-8").lower()
    new_bullets = [
        str(op.get("text", "")).lower() for op in edit.get("edit_ops", [])
    ]
    must_not_terms = ("disable safety", "bypass approval", "ignore previous")
    if any(term in bullet for bullet in new_bullets for term in must_not_terms):
        return 0.0
    if "cases:" in raw and "[]" not in raw:
        return 0.75
    return 0.6


def _default_validation_score(edit: dict[str, Any], project_root: Path) -> float:
    target_skill = edit.get("target_skill", "")
    skill_path = project_root / "skills" / target_skill / "SKILL.md"
    if not skill_path.exists():
        return 0.0
    skill_text = skill_path.read_text(encoding="utf-8").lower()
    score = 0.5
    for op in edit.get("edit_ops", []):
        text = str(op.get("text", "")).strip().lower()
        if not text:
            continue
        if text in skill_text:
            score -= 0.05  # duplicate
        else:
            score += 0.1
    return max(0.0, min(1.0, score))
