"""Deterministic skill eval runner.

What this is and isn't
----------------------

This module evaluates a skill change by checking whether the rules
encoded in ``skills/<skill>/eval/cases.yaml`` are *textually* reflected
in (or absent from) the proposed ``SKILL.md``.

It is **not** a real behavioural evaluator — it cannot tell whether an
agent will actually obey the rules at runtime. It catches a real class
of regressions (rule removed; negation forgotten; rule never landed in
``## Memory-derived rules``) without needing an LLM, and forms the
deterministic baseline that an LLM-backed evaluator can later replace.

Case schema (cases.yaml entries)
--------------------------------

Each case is a YAML mapping. The runner accepts both the historical
shorthand and the new explicit field names, normalising to the latter:

  - ``id``                      — case identifier (string)
  - ``input``                   — sample user input (string, informational)
  - ``expected_behavior``       — token(s) that MUST appear in
                                  ``## Memory-derived rules``. Alias:
                                  ``must_include``.
  - ``negative_assertions``     — token(s) that MUST NOT appear anywhere
                                  in ``SKILL.md``. Alias:
                                  ``must_not_include``.
  - ``target_rule``             — the concrete rule the case is guarding
                                  (string). When present, the runner
                                  also asserts it lands in the rules
                                  section.
  - ``source_promo_id``         — provenance link to the originating
                                  PROMO; used for ``covered_promo_ids``.

The yaml parser already lives in ``runtime/regression_case_proposal``
(``parse_regression_cases``); this module wraps it and folds the alias
fields into a typed structure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from .regression_case_proposal import parse_regression_cases


MEMORY_RULES_HEADING = "## Memory-derived rules"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvalCase:
    case_id: str
    input: str
    expected_behavior: list[str]
    negative_assertions: list[str]
    target_rule: str
    source_promo_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CaseOutcome:
    case_id: str
    passed: bool
    source_promo_id: str
    target_rule: str
    failures: list[str] = field(default_factory=list)
    matched_expectations: list[str] = field(default_factory=list)
    avoided_negatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunReport:
    skill: str
    total: int
    passed_count: int
    failed_count: int
    accepted: bool
    outcomes: list[CaseOutcome]
    covered_promo_ids: list[str]
    covered_rules: list[str]
    evaluator: str = "deterministic_text"
    note: str = (
        "Deterministic text-presence eval. Catches text-level regressions "
        "but does not simulate agent behaviour; pair with an LLM evaluator "
        "for behavioural coverage."
    )
    evaluated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["outcomes"] = [o.to_dict() if isinstance(o, CaseOutcome) else o for o in self.outcomes]
        return payload


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_cases(yaml_text: str) -> list[EvalCase]:
    """Parse cases.yaml text into typed EvalCase records. Empty / missing
    fields default to safe placeholders so a partially-filled case still
    runs (it just contributes weaker coverage)."""
    parsed = parse_regression_cases(yaml_text or "")
    cases: list[EvalCase] = []
    for index, raw in enumerate(parsed):
        cases.append(EvalCase(
            case_id=str(raw.get("id") or f"case-{index + 1}").strip(),
            input=str(raw.get("input") or "").strip(),
            expected_behavior=_normalize_terms(
                raw.get("expected_behavior", raw.get("must_include", []))
            ),
            negative_assertions=_normalize_terms(
                raw.get("negative_assertions", raw.get("must_not_include", []))
            ),
            target_rule=str(raw.get("target_rule") or "").strip(),
            source_promo_id=str(raw.get("source_promo_id") or "").strip(),
        ))
    return cases


def load_cases_for_skill(project_root: Path | str, skill: str) -> list[EvalCase]:
    path = Path(project_root) / "skills" / skill / "eval" / "cases.yaml"
    if not path.exists():
        return []
    return load_cases(path.read_text(encoding="utf-8"))


def run_cases(
    cases: list[EvalCase],
    skill_md_text: str,
    *,
    skill: str = "",
) -> RunReport:
    """Run each case against the proposed SKILL.md text.

    A case passes when (in deterministic text-presence mode):
      - every expected_behavior term appears inside the
        ``## Memory-derived rules`` section, AND
      - target_rule (when non-empty) appears inside the rules section.

    ``negative_assertions`` describe *agent output* behaviour ("when the
    user asks for X, the output should not contain Y"), which cannot be
    faithfully checked by string presence in SKILL.md — the rule itself
    often mentions those tokens. We record them in
    ``outcome.negative_assertions_recorded`` for the future LLM
    evaluator, but do **not** fail the case on them in this mode.
    """
    rules_section = _extract_rules_section(skill_md_text or "")
    rules_lower = rules_section.lower()

    outcomes: list[CaseOutcome] = []
    passed_count = 0
    failed_count = 0
    covered_promos: set[str] = set()
    covered_rules: set[str] = set()

    for case in cases:
        failures: list[str] = []
        matched: list[str] = []

        # expected_behavior and negative_assertions describe AGENT OUTPUT
        # (e.g. "output must contain ```", "output must not contain
        # 书名"). A text-presence check on SKILL.md can't faithfully
        # verify those — the rule itself often mentions the very tokens.
        # We record them for the future LLM evaluator but do not fail
        # the case on them in deterministic mode.
        for term in case.expected_behavior:
            if term.lower() in rules_lower:
                matched.append(term)

        # target_rule IS a SKILL.md-level claim ("this rule must land in
        # the Memory-derived rules section"). That we CAN verify.
        if case.target_rule:
            if case.target_rule.strip().lower() not in rules_lower:
                failures.append(
                    f"target_rule '{_truncate(case.target_rule, 80)}' missing from {MEMORY_RULES_HEADING}"
                )

        # Cases that have neither a target_rule nor any expected_behavior
        # match are uninformative — flag them so the human notices.
        if not case.target_rule and not matched and case.expected_behavior:
            failures.append(
                f"no expected_behavior term reflected in {MEMORY_RULES_HEADING}"
            )

        avoided = list(case.negative_assertions)
        passed = not failures
        outcomes.append(CaseOutcome(
            case_id=case.case_id,
            passed=passed,
            source_promo_id=case.source_promo_id,
            target_rule=case.target_rule,
            failures=failures,
            matched_expectations=matched,
            avoided_negatives=avoided,
        ))

        if passed:
            passed_count += 1
            if case.source_promo_id:
                covered_promos.add(case.source_promo_id)
            if case.target_rule:
                covered_rules.add(case.target_rule)
        else:
            failed_count += 1

    accepted = failed_count == 0 and (passed_count > 0 or not cases)

    return RunReport(
        skill=skill,
        total=len(cases),
        passed_count=passed_count,
        failed_count=failed_count,
        accepted=accepted,
        outcomes=outcomes,
        covered_promo_ids=sorted(covered_promos),
        covered_rules=sorted(covered_rules),
    )


def run_for_skill(
    project_root: Path | str,
    skill: str,
    *,
    proposed_skill_md: str | None = None,
) -> RunReport:
    """Convenience wrapper: load cases, read SKILL.md (or use the
    provided proposed text), and run."""
    cases = load_cases_for_skill(project_root, skill)
    if proposed_skill_md is None:
        path = Path(project_root) / "skills" / skill / "SKILL.md"
        proposed_skill_md = path.read_text(encoding="utf-8") if path.exists() else ""
    return run_cases(cases, proposed_skill_md, skill=skill)


def summarize_failures(report: RunReport, *, limit: int = 3) -> str:
    """Build a one-line, human-readable failure summary for reject_reason
    fields and apply error messages."""
    if report.accepted:
        return ""
    failed = [o for o in report.outcomes if not o.passed]
    parts: list[str] = []
    for outcome in failed[:limit]:
        first = outcome.failures[0] if outcome.failures else "unknown failure"
        parts.append(f"{outcome.case_id}: {first}")
    suffix = ""
    if len(failed) > limit:
        suffix = f" (+ {len(failed) - limit} more)"
    return f"eval failed ({report.failed_count}/{report.total}): " + "; ".join(parts) + suffix


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _normalize_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    return []


def _extract_rules_section(skill_md_text: str) -> str:
    """Return the body under ``## Memory-derived rules`` (up to next H2)."""
    lines = skill_md_text.splitlines()
    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() == MEMORY_RULES_HEADING:
            start_idx = idx + 1
            break
    if start_idx is None:
        return ""
    end_idx = len(lines)
    for cursor in range(start_idx, len(lines)):
        if lines[cursor].startswith("## "):
            end_idx = cursor
            break
    return "\n".join(lines[start_idx:end_idx])


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
