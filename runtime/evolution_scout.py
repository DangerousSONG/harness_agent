"""EvolutionScout: read-only signal extraction + opportunity scoring.

Scout responsibilities (per the side-channel evolution spec):

- Read-only: scans memory/errors/learnings/feature_requests/PROMO records.
- Decides which experience is worth evolving, which skill to prioritize,
  which PROMOs to batch.
- Never modifies SKILL.md, ReviewQueue, regression cases, evaluator,
  scorer, or the existing skill_memory record files. The only thing it
  writes to disk is the side-channel JSON stores under ``.evolution/``.

Each opportunity must trace back to at least one signal, and each signal
must trace back to a concrete source_path:source_ref so that the human
reviewer can verify provenance.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .evolution_stores import (
    EvolutionOpportunity,
    EvolutionStores,
    LearningSignal,
)
from .promotion_browser import PromotionBrowser


WORD_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]+")
ID_HEADING_RE = re.compile(r"^##\s+([A-Z]+-[A-Z0-9]+)\s*(?:-\s*(.*))?$")

DEFAULT_GLOBAL_FILES = {
    "GLOBAL_LEARNINGS.md": ("global_learning", "learning"),
    "GLOBAL_ERRORS.md": ("global_error", "error"),
    "GLOBAL_FEATURE_REQUESTS.md": ("global_feature_request", "feature_request"),
}

SKILL_MEMORY_FILES = {
    "LEARNINGS.md": "learning",
    "ERRORS.md": "error",
    "FEATURE_REQUESTS.md": "feature_request",
    "POLICY_CANDIDATES.md": "policy_candidate",
    "REGRESSION_TESTS.md": "regression_test",
}

UNSAFE_HINTS = (
    "ignore previous instructions",
    "disable safety",
    "bypass approval",
    "bypass policy",
    "system administrator",
    "send this secret",
)

SAFETY_HINTS = (
    "leak",
    "secret",
    "credential",
    "approval",
    "safety",
    "policy",
    "rollback",
    "回退",
    "审批",
)


@dataclass
class ScanResult:
    new_signal_ids: list[str]
    new_opportunity_ids: list[str]
    skipped_signal_count: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "new_signal_ids": self.new_signal_ids,
            "new_opportunity_ids": self.new_opportunity_ids,
            "skipped_signal_count": self.skipped_signal_count,
            "summary": self.summary,
        }


class EvolutionScout:
    """Read-only scout. LLM enrichment is opt-in; the deterministic
    decision/score path is always authoritative."""

    def __init__(
        self,
        *,
        project_root: Path | str,
        stores: EvolutionStores,
        promotions: PromotionBrowser,
        llm_enricher: Any = None,
    ):
        self.project_root = Path(project_root)
        self.stores = stores
        self.promotions = promotions
        self.llm_enricher = llm_enricher

    def scan(self) -> ScanResult:
        existing_signals = {self._signal_key(s): s for s in self.stores.signals.list()}
        new_signals: list[dict[str, Any]] = []
        skipped = 0

        for record in self._iter_memory_records():
            if self._is_unsafe(record["content"]):
                skipped += 1
                continue
            signal = LearningSignal.new(
                source_type=record["source_type"],
                source_path=record["source_path"],
                source_ref=record["source_ref"],
                observed_skill=record["observed_skill"],
                content=record["content"],
                tags=record["tags"],
                frequency=record["frequency"],
                severity=record["severity"],
            )
            key = self._signal_key(signal.to_dict())
            if key in existing_signals:
                continue
            stored = self.stores.signals.save(signal)
            new_signals.append(stored)
            existing_signals[key] = stored

        for promo in self.promotions.list_candidates():
            promo_signal = self._signal_from_promo(promo.to_dict())
            if not promo_signal:
                continue
            key = self._signal_key(promo_signal)
            if key in existing_signals:
                continue
            signal = LearningSignal.new(**promo_signal)
            stored = self.stores.signals.save(signal)
            new_signals.append(stored)
            existing_signals[key] = stored

        all_signals = self.stores.signals.list()
        opportunities = self._cluster_into_opportunities(all_signals)

        existing_opp_keys = {
            (opp.get("target_skill", ""), tuple(sorted(opp.get("signal_ids", []))))
            for opp in self.stores.opportunities.list()
        }
        new_opportunities: list[str] = []
        for opp in opportunities:
            key = (opp.target_skill, tuple(sorted(opp.signal_ids)))
            if key in existing_opp_keys:
                continue
            stored = self.stores.opportunities.save(opp)
            new_opportunities.append(stored["opportunity_id"])
            existing_opp_keys.add(key)

        summary = (
            f"scanned: signals_new={len(new_signals)} "
            f"opportunities_new={len(new_opportunities)} "
            f"unsafe_skipped={skipped}"
        )
        return ScanResult(
            new_signal_ids=[s["signal_id"] for s in new_signals],
            new_opportunity_ids=new_opportunities,
            skipped_signal_count=skipped,
            summary=summary,
        )

    def create_batch(
        self,
        opportunity_ids: list[str],
    ) -> dict[str, Any]:
        from .evolution_stores import PromotionBatch  # local import to keep module lean

        if not opportunity_ids:
            raise ValueError("opportunity_ids is required")
        opportunities = [
            self.stores.opportunities.get(opp_id) for opp_id in opportunity_ids
        ]
        missing = [
            opp_id for opp_id, payload in zip(opportunity_ids, opportunities)
            if payload is None
        ]
        if missing:
            raise ValueError(f"unknown opportunity_ids: {missing}")

        target_skills = {opp["target_skill"] for opp in opportunities}
        if len(target_skills) > 1:
            raise ValueError(
                f"cannot batch opportunities across skills: {sorted(target_skills)}"
            )

        target_skill = next(iter(target_skills))
        promo_ids: list[str] = []
        for opp in opportunities:
            promo_ids.extend(opp.get("related_promo_ids", []))

        risk = _max_rank(
            [opp["risk_level"] for opp in opportunities],
            order=("low", "medium", "high"),
        )
        priority = _max_rank(
            [opp["priority"] for opp in opportunities],
            order=("low", "medium", "high"),
        )
        should_improve: list[str] = []
        must_not_regress: list[str] = []
        for opp in opportunities:
            should_improve.extend(opp.get("should_improve") or [])
            must_not_regress.extend(opp.get("must_not_regress") or [])

        batch = PromotionBatch.new(
            target_skill=target_skill,
            opportunity_ids=opportunity_ids,
            promo_ids=sorted(set(promo_ids)),
            merged_summary="; ".join(opp.get("summary", "") for opp in opportunities)[:500],
            priority=priority,
            risk_level=risk,
            should_improve=sorted(set(should_improve)),
            must_not_regress=sorted(set(must_not_regress)),
            recommended_next_action="run /skill-optimize",
        )
        return self.stores.batches.save(batch)

    def _iter_memory_records(self):
        for path in self._memory_files():
            text = path.read_text(encoding="utf-8")
            for record in _parse_id_records(text):
                source_ref = record["record_id"]
                observed_skill = self._skill_from_path(path) or record["fields"].get("Target Skill", "")
                source_type, classification = self._classify_path(path)
                content_lines = [record["title"], record["details"]]
                content = "\n".join(line for line in content_lines if line).strip()
                yield {
                    "source_type": source_type,
                    "source_path": self._rel(path),
                    "source_ref": source_ref,
                    "observed_skill": observed_skill or "self_improvement",
                    "content": content[:1500],
                    "tags": _tagify(content, classification),
                    "frequency": _safe_int(record["fields"].get("Occurrence Count", "1"), 1),
                    "severity": (
                        record["fields"].get("Priority", "")
                        or record["fields"].get("Severity", "")
                        or ("high" if classification == "error" else "medium")
                    ).lower(),
                }

    def _memory_files(self) -> list[Path]:
        files: list[Path] = []
        global_dir = self.project_root / ".skills_memory"
        if global_dir.exists():
            for name in DEFAULT_GLOBAL_FILES:
                path = global_dir / name
                if path.exists():
                    files.append(path)
        skills_dir = self.project_root / "skills"
        if skills_dir.exists():
            for skill_path in sorted(skills_dir.iterdir()):
                memory_dir = skill_path / "memory"
                if not memory_dir.exists():
                    continue
                for name in SKILL_MEMORY_FILES:
                    path = memory_dir / name
                    if path.exists():
                        files.append(path)
        return files

    def _classify_path(self, path: Path) -> tuple[str, str]:
        if path.name in DEFAULT_GLOBAL_FILES:
            return DEFAULT_GLOBAL_FILES[path.name]
        kind = SKILL_MEMORY_FILES.get(path.name, "learning")
        return f"skill_memory.{kind}", kind

    def _skill_from_path(self, path: Path) -> str:
        parts = path.parts
        if "skills" in parts:
            idx = parts.index("skills")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return ""

    def _rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.project_root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    def _signal_key(self, signal: dict[str, Any]) -> str:
        return f"{signal.get('source_path', '')}::{signal.get('source_ref', '')}"

    def _is_unsafe(self, content: str) -> bool:
        lowered = content.lower()
        return any(hint in lowered for hint in UNSAFE_HINTS)

    def _signal_from_promo(self, promo: dict[str, Any]) -> dict[str, Any] | None:
        promo_id = promo.get("promo_id") or ""
        if not promo_id:
            return None
        summary = promo.get("summary") or promo.get("proposed_change") or ""
        if not summary.strip():
            return None
        return {
            "source_type": "promo",
            "source_path": ".skills_memory/PROMOTION_CANDIDATES.md",
            "source_ref": promo_id,
            "observed_skill": promo.get("target_skill") or "self_improvement",
            "content": summary[:1500],
            "tags": _tagify(summary, "promo") + ["promo"],
            "frequency": int(promo.get("occurrence_count") or 1),
            "severity": "medium",
        }

    def _cluster_into_opportunities(
        self,
        signals: list[dict[str, Any]],
    ) -> list[EvolutionOpportunity]:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for signal in signals:
            cluster_key = self._cluster_key(signal)
            groups[(signal["observed_skill"], cluster_key)].append(signal)

        opportunities: list[EvolutionOpportunity] = []
        for (skill, cluster_key), members in groups.items():
            score, components = _evolution_score(members)
            decision, opp_type, priority, risk, confidence = _make_decision(
                members, score, components
            )
            reason = _reason_text(decision, components, members, target_skill=skill)
            score_breakdown = _score_breakdown(decision, components, members)
            should_improve = _derive_should_improve(members, decision=decision, target_skill=skill)
            must_not_regress = _derive_must_not_regress(members)
            related_promos = sorted(
                {s["source_ref"] for s in members if s["source_type"] == "promo"}
            )
            opp = EvolutionOpportunity.new(
                signal_ids=[s["signal_id"] for s in members],
                target_skill=skill,
                opportunity_type=opp_type,
                summary=_summary_text(members, cluster_key),
                decision=decision,
                evolution_score=round(score, 4),
                priority=priority,
                risk_level=risk,
                confidence=confidence,
                reason=reason,
                score_breakdown=score_breakdown,
                should_improve=should_improve,
                must_not_regress=must_not_regress,
                related_promo_ids=related_promos,
            )
            if self.llm_enricher is not None:
                self._enrich_opportunity(opp, members)
            opportunities.append(opp)
        return opportunities

    def _enrich_opportunity(
        self,
        opp: "EvolutionOpportunity",
        signals: list[dict[str, Any]],
    ) -> None:
        try:
            result = self.llm_enricher.enrich(opp.to_dict(), signals)
        except Exception:
            return
        if not getattr(result, "used_llm", False):
            return
        if result.reason:
            opp.reason = result.reason + " | " + opp.reason
        if result.should_improve:
            opp.should_improve = result.should_improve
        # must_not_regress is always merged with the deterministic floor.
        opp.must_not_regress = sorted(
            set(opp.must_not_regress) | set(result.must_not_regress)
        )

    def _cluster_key(self, signal: dict[str, Any]) -> str:
        tokens = sorted(set(signal.get("tags") or []))[:5]
        if tokens:
            return "tag:" + "|".join(tokens)
        words = _top_words(signal.get("content") or "", limit=5)
        return "kw:" + "|".join(words)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_id_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    lines = text.splitlines()
    starts: list[int] = []
    for idx, line in enumerate(lines):
        if line.startswith("## "):
            starts.append(idx)
    starts.append(len(lines))
    for cursor in range(len(starts) - 1):
        block_lines = lines[starts[cursor]: starts[cursor + 1]]
        if not block_lines:
            continue
        match = ID_HEADING_RE.match(block_lines[0])
        if not match:
            continue
        record_id = match.group(1)
        title = (match.group(2) or "").strip()
        fields: dict[str, str] = {}
        details: list[str] = []
        in_details = False
        for line in block_lines[1:]:
            stripped = line.strip()
            if stripped.startswith("### Details"):
                in_details = True
                continue
            if stripped.startswith("### "):
                in_details = False
                continue
            if not in_details and stripped.startswith("- ") and ":" in stripped:
                key, _, value = stripped[2:].partition(":")
                fields[key.strip()] = value.strip()
            elif in_details:
                details.append(line)
        records.append(
            {
                "record_id": record_id,
                "title": title,
                "fields": fields,
                "details": "\n".join(details).strip(),
            }
        )
    return records


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _tagify(content: str, classification: str) -> list[str]:
    lowered = content.lower()
    tags: list[str] = [classification]
    for marker in ("read_file", "edit_file", "write_file", "load_skill", "weather", "json", "markdown"):
        if marker in lowered:
            tags.append(marker)
    if any(hint in lowered for hint in SAFETY_HINTS):
        tags.append("safety")
    if "rollback" in lowered or "回退" in lowered:
        tags.append("rollback")
    return sorted(set(tags))


def _top_words(content: str, limit: int) -> list[str]:
    seen: dict[str, int] = defaultdict(int)
    for word in WORD_RE.findall(content.lower()):
        if len(word) < 3:
            continue
        seen[word] += 1
    ordered = sorted(seen.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ordered[:limit]]


def _evolution_score(members: list[dict[str, Any]]) -> tuple[float, dict[str, float]]:
    frequency = sum(int(s.get("frequency", 1)) for s in members)
    transferability = 1.0 if len({s["observed_skill"] for s in members}) > 1 else 0.6
    safety = any("safety" in (s.get("tags") or []) for s in members)
    impact = 1.0 if safety else min(1.0, 0.3 + 0.15 * frequency)
    skill_confidence = 1.0 if all(s["observed_skill"] != "self_improvement" for s in members) else 0.5
    has_promo = any(s.get("source_type") == "promo" for s in members)
    testability = 0.8 if has_promo else 0.5
    safety_gain = 1.0 if safety else 0.0
    regression_risk = 0.3 if has_promo else 0.4
    overfitting_risk = 0.5 if frequency <= 1 else 0.2
    cost_increase = 0.1

    components = {
        "frequency": min(1.0, frequency / 5.0),
        "transferability": transferability,
        "impact": impact,
        "skill_confidence": skill_confidence,
        "testability": testability,
        "safety_gain": safety_gain,
        "regression_risk": regression_risk,
        "overfitting_risk": overfitting_risk,
        "cost_increase": cost_increase,
    }
    score = (
        0.20 * components["frequency"]
        + 0.20 * components["transferability"]
        + 0.20 * components["impact"]
        + 0.15 * components["skill_confidence"]
        + 0.15 * components["testability"]
        + 0.10 * components["safety_gain"]
        - 0.15 * components["regression_risk"]
        - 0.10 * components["overfitting_risk"]
        - 0.10 * components["cost_increase"]
    )
    return score, components


def _make_decision(
    members: list[dict[str, Any]],
    score: float,
    components: dict[str, float],
) -> tuple[str, str, str, str, str]:
    safety = components["safety_gain"] > 0
    has_promo = any(s.get("source_type") == "promo" for s in members)
    frequency = sum(int(s.get("frequency", 1)) for s in members)
    only_self_improvement = all(s["observed_skill"] == "self_improvement" for s in members)

    if only_self_improvement and not safety:
        return ("defer", "defer", "low", "low", "low")
    if safety and components["skill_confidence"] >= 0.5:
        return ("promote", "safety_gain", "high", "medium", "medium")
    if score >= 0.45 and frequency >= 2:
        return ("promote", "promote", "medium", "medium", "medium")
    if score >= 0.45 and frequency < 2 and not has_promo:
        return ("request_eval", "request_eval", "medium", "medium", "low")
    if score >= 0.30:
        return ("defer", "defer", "low", "low", "low")
    return ("reject", "defer", "low", "low", "low")


def _reason_text(
    decision: str,
    components: dict[str, float],
    members: list[dict[str, Any]],
    *,
    target_skill: str = "",
) -> str:
    """Return a Chinese narrative explaining *why* this needs evolution and
    *what* the expected outcome is. The technical score breakdown lives in
    a separate ``score_breakdown`` field for audit, so this stays readable.
    """
    frequency = sum(int(s.get("frequency", 1)) for s in members)
    has_safety = components.get("safety_gain", 0) > 0
    has_promo = any(s.get("source_type") == "promo" for s in members)
    cross_skill = components.get("transferability", 0) >= 1.0
    skill_label = f"`{target_skill}`" if target_skill else "目标 skill"

    if decision == "promote" and has_safety:
        why = f"信号涉及安全策略或审批被拒事件，{skill_label} 在类似场景下需要主动避让而不是事后拦截。"
        effect = "升级后预期能减少重复触发 ReviewQueue 审批，缩短人工介入路径，同时保留既有安全护栏。"
    elif decision == "promote" and frequency >= 2:
        why = f"这条经验在 {skill_label} 已重复出现 {frequency} 次，属于稳定可复用的模式。"
        effect = "升级后预期把它固化进 SKILL.md 的 Memory-derived rules，减少同类问题再次发生时的纠正成本。"
    elif decision == "promote" and cross_skill:
        why = f"信号跨多个 skill 出现，说明这是通用经验而不是个例。"
        effect = "升级后预期能让相关 skill 共享这条规则，避免逐个修改。"
    elif decision == "promote":
        why = f"评分高于晋升阈值（≥0.45），且 {skill_label} 的归属置信度足够。"
        effect = "升级后预期把这条经验固化为 skill 规则。"
    elif decision == "request_eval":
        why = "评分达到晋升阈值但证据只有 1 次出现，且没有现成的 PROMO 来佐证可测试性。"
        effect = "建议先补一组 regression case（positive + negative），覆盖建立后再考虑升级。"
    elif decision == "defer":
        if all(s.get("observed_skill") == "self_improvement" for s in members):
            why = "信号全部归属在 self_improvement，缺少明确的目标 skill，不适合直接升级。"
        else:
            why = "评分介于观察区间（0.30–0.45），证据强度尚不足以做出升级判断。"
        effect = "保留观察，等待新的同类信号出现，或人工标注归属后再评估。"
    else:  # reject
        why = "评分低于观察阈值（<0.30），且不属于 safety 事件，更像是一次性偏好或低质量信号。"
        effect = "不进入 skill rules，避免污染长期规则集。"

    return f"为什么：{why} 预期效果：{effect}"


def _score_breakdown(decision: str, components: dict[str, float], members: list[dict[str, Any]]) -> str:
    """Technical breakdown kept alongside the human-readable reason."""
    frequency = sum(int(s.get("frequency", 1)) for s in members)
    parts = [
        f"decision={decision}",
        f"frequency={frequency}",
        f"transferability={components['transferability']:.2f}",
        f"impact={components['impact']:.2f}",
        f"safety_gain={components['safety_gain']:.2f}",
        f"skill_confidence={components['skill_confidence']:.2f}",
        f"testability={components['testability']:.2f}",
    ]
    return "; ".join(parts)


def _derive_should_improve(
    members: list[dict[str, Any]],
    *,
    decision: str = "",
    target_skill: str = "",
) -> list[str]:
    """Build a context-aware list of 'what we want this evolution to fix'.

    Falls back to the old tag-based phrasing when we cannot derive
    something more specific from the signal source types.
    """
    skill_label = target_skill or "目标 skill"
    tags = {tag for signal in members for tag in (signal.get("tags") or [])}
    source_types = {signal.get("source_type") for signal in members}
    out: list[str] = []

    if "safety" in tags:
        out.append(f"让 {skill_label} 在触发安全策略前主动停止，减少 ReviewQueue 反复打断")
    if any("error" in (st or "") for st in source_types):
        out.append(f"减少 {skill_label} 在类似输入下重复抛同一种错误")
    if any("feature_request" in (st or "") for st in source_types):
        out.append(f"覆盖 {skill_label} 现在缺失的能力调用方式")
    if any(st == "promo" for st in source_types):
        out.append("把已有 PROMO 候选合并审查，避免碎片化升级")
    if "rollback" in tags:
        out.append("识别并避免触发版本回滚的输入模式")

    if not out:
        # Fall back to the old tag-based phrasing for unusual clusters.
        out = sorted(
            {
                f"减少 '{tag}' 模式的重复出现"
                for tag in tags
                if tag not in {"error", "learning", "feature_request", "promo"}
            }
        )

    return out[:5]


def _derive_must_not_regress(members: list[dict[str, Any]]) -> list[str]:
    out = ["不放宽既有的安全策略", "不绕过 ReviewQueue 审批"]
    if any("safety" in (s.get("tags") or []) for s in members):
        out.append("保留 safety_gain 相关的断言不被覆盖")
    return out


def _summary_text(members: list[dict[str, Any]], cluster_key: str) -> str:
    sample = members[0]["content"][:160].replace("\n", " ").strip()
    return f"{cluster_key} | {sample}"


def _max_rank(values: list[str], order: tuple[str, ...]) -> str:
    seen = [value for value in values if value in order]
    if not seen:
        return order[0]
    return max(seen, key=lambda value: order.index(value))
