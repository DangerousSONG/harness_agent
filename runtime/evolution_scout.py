"""EvolutionScout: structured four-stage judge over memory + PROMOs.

Pipeline:

  scan()
   ├── extract raw memory records
   ├── ① hard filter / quarantine
   │       attack patterns → quarantined signal (redacted, attack_type set)
   │       defended security reports → security_incident tag, normal signal
   ├── classify tags (9-class taxonomy, not just a coarse 'safety' flag)
   ├── ② cluster by semantic key (across skills), then pick target_skill
   │       from observed_skill distribution; cross-skill ⇒ high transferability
   ├── ③ evidence_quality / value_score / risk_score per cluster
   ├── ④ decision matrix
   │       quarantine · safety_review · promote · request_eval · defer · reject
   └── persist opportunities (refreshing existing on re-scan)

The Optimizer rejects any opportunity whose signals carry
`quarantined=True`, so attack content can never reach SKILL.md even if
a human accidentally clicks Optimize on a security-related row.
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
from .scout_decisions import ScoutDecisionStore


# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------

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

# Attack patterns that MUST quarantine the signal. Each pattern triggers a
# specific attack_type so the human reviewer knows what they're looking at.
ATTACK_PATTERNS: dict[str, tuple[str, ...]] = {
    "prompt_injection": (
        "ignore previous instructions",
        "ignore the system prompt",
        "you are now",
        "from now on you will act as",
        "忽略以上指令",
        "忽略 safeharness",
    ),
    "approval_bypass": (
        "bypass approval",
        "bypass policy",
        "skip the review",
        "skip approval",
        "绕过审批",
        "跳过审批",
        "无需审批",
    ),
    "safety_disable": (
        "disable safety",
        "turn off safety",
        "ignore safety",
        "disable safeharness",
        "关闭安全",
        "禁用安全",
    ),
    "secret_exfiltration": (
        "send this secret",
        "exfiltrate",
        "leak the api key",
        "post the token to",
        "把 api key 发",
    ),
}

# Phrases that indicate the memory is REPORTING a defended security event
# (not attempting one). When present alongside attack phrases, we lean
# toward security_incident instead of full quarantine.
DEFENDED_INCIDENT_MARKERS = (
    "blocked", "rejected", "denied", "stopped", "prevented",
    "require_approval", "审批拦截", "已拦截", "已被拒绝", "需要审批",
)

# Tag taxonomy. A signal can carry multiple tags. memory_poisoning and
# user_correction are set programmatically, not via keywords.
TAG_LEXICON: dict[str, tuple[str, ...]] = {
    "security_incident": (
        "attack", "exploit", "malicious", "credential", "secret leak",
        "exfiltrate", "data breach", "未授权", "凭据泄漏", "凭据泄露",
    ),
    "governance_related": (
        "审批", "审核", "approval", "approve", "reviewqueue", "review queue",
        "policy gate", "审计",
    ),
    "policy_related": (
        "policy", "策略", "guideline", "标准", "规范",
    ),
    "rollback_related": (
        "rollback", "revert", "回滚", "回退", "撤销",
    ),
    "tool_failure": (
        "traceback", "exception", "failed", "error code", "stack trace",
        "报错", "失败", "异常",
    ),
    "format_preference": (
        "markdown", "yaml", "json", "csv", "format", "structure",
        "格式", "结构", "排版", "template", "模板",
    ),
    "capability_gap": (
        "missing capability", "not supported", "cannot", "unable to",
        "support for", "feature request", "需要支持", "增加支持",
    ),
}

CORRECTION_PHRASES: tuple[tuple[str, float], ...] = (
    ("以后", 0.9),
    ("固定", 0.9),
    ("默认", 0.8),
    ("不要再", 0.95),
    ("可复用", 0.7),
    ("always", 0.9),
    ("never", 0.9),
    ("from now on", 0.95),
    ("default to", 0.8),
    ("reusable", 0.7),
    ("must not", 0.85),
)

CROSS_CUTTING_TAGS = {"format_preference", "capability_gap", "tool_failure", "governance_related"}
META_TAGS = {"error", "learning", "feature_request", "policy_candidate", "regression_test", "promo"}

# ---- feature extraction lexicons (for normalized_problem_signature) ----

ACTION_LEXICON: dict[str, tuple[str, ...]] = {
    "edit": ("edit", "modify", "change ", "更改", "修改"),
    "read": ("read", "open ", "查看", "读取"),
    "write": ("write", "create ", "生成", "写入"),
    "run": ("run ", "execute", "运行", "执行"),
    "load": ("load_skill", "load skill", "加载"),
    "delete": ("delete", "remove ", "删除"),
    "parse": ("parse", "解析"),
    "format": ("format", "格式化", "排版"),
}

ERROR_TYPE_LEXICON: dict[str, tuple[str, ...]] = {
    "policy_block": ("blocked by policy", "policy that requires approval", "policy requirement", "requires approval", "审批拦截", "策略拦截"),
    "parse_error": ("parse", "traceback", "syntaxerror", "json", "解析失败", "语法错误"),
    "timeout": ("timeout", "timed out", "超时"),
    "missing_capability": ("not supported", "missing capability", "unable to", "cannot ", "不支持", "缺少能力"),
    "permission": ("permission denied", "permission", "denied", "权限"),
    "not_found": ("not found", "no such", "找不到", "不存在"),
}

ARTIFACT_LEXICON: tuple[tuple[str, str], ...] = (
    ("eval_file", ("eval/cases", "cases.yaml")),
    ("skill_file", ("skill.md", "skills/")),
    ("tool_file", ("tools/", "tool.yaml")),
    ("env_file", (".env", "dotenv")),
    ("config_file", (".yaml", ".yml", ".toml", ".ini", "config")),
    ("doc_file", (".md", "readme", "docs/")),
)

CORRECTION_PATTERN_LEXICON: dict[str, tuple[str, ...]] = {
    "prohibition": ("不要再", "never", "must not", "禁止"),
    "default": ("默认", "default", "always", "from now on", "以后"),
    "structure": ("结构", "structure", "格式", "format", "模板", "template"),
    "naming": ("命名", "naming", "name it"),
}

SAFETY_TYPE_LEXICON: dict[str, tuple[str, ...]] = {
    "secret_leak": ("secret", "credential", "api key", "api_key", "token", "凭据", "密钥", "泄漏", "泄露"),
    "approval_block": ("approval", "审批", "reviewqueue", "review queue", "require_approval"),
    "injection": ("ignore previous", "injection", "prompt injection", "注入"),
    "policy_violation": ("policy violation", "违规", "policy gate"),
}


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    new_signal_ids: list[str]
    new_opportunity_ids: list[str]
    skipped_signal_count: int = 0
    quarantined_signal_count: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "new_signal_ids": self.new_signal_ids,
            "new_opportunity_ids": self.new_opportunity_ids,
            "skipped_signal_count": self.skipped_signal_count,
            "quarantined_signal_count": self.quarantined_signal_count,
            "summary": self.summary,
        }


class EvolutionScout:
    """Read-only scout. LLM enrichment optional and never authoritative."""

    def __init__(
        self,
        *,
        project_root: Path | str,
        stores: EvolutionStores,
        promotions: PromotionBrowser,
        llm_enricher: Any = None,
        decision_store: ScoutDecisionStore | None = None,
    ):
        self.project_root = Path(project_root)
        self.stores = stores
        self.promotions = promotions
        self.llm_enricher = llm_enricher
        self.decision_store = decision_store or ScoutDecisionStore(self.project_root)

    # ---- scan -----------------------------------------------------------

    def scan(self) -> ScanResult:
        existing_signals = {self._signal_key(s): s for s in self.stores.signals.list()}
        new_signals: list[dict[str, Any]] = []
        quarantined_count = 0

        # Stage 1: extract + classify each memory record, including
        # quarantine for attack content.
        for record in self._iter_memory_records():
            extracted = self._classify_signal(record)
            key = self._signal_key(extracted)
            if extracted.get("quarantined"):
                quarantined_count += 1
            if key in existing_signals:
                signal_id = existing_signals[key]["signal_id"]
                extracted["signal_id"] = signal_id
                if "created_at" in existing_signals[key]:
                    extracted["created_at"] = existing_signals[key]["created_at"]
                self.stores.signals.save(LearningSignal(**extracted))
                continue
            signal = LearningSignal.new(**extracted)
            stored = self.stores.signals.save(signal)
            new_signals.append(stored)
            existing_signals[key] = stored

        for promo in self.promotions.list_candidates():
            promo_signal = self._signal_from_promo(promo.to_dict())
            if not promo_signal:
                continue
            key = self._signal_key(promo_signal)
            if key in existing_signals:
                signal_id = existing_signals[key]["signal_id"]
                promo_signal["signal_id"] = signal_id
                if "created_at" in existing_signals[key]:
                    promo_signal["created_at"] = existing_signals[key]["created_at"]
                self.stores.signals.save(LearningSignal(**promo_signal))
                continue
            signal = LearningSignal.new(**promo_signal)
            stored = self.stores.signals.save(signal)
            new_signals.append(stored)
            existing_signals[key] = stored

        # Stage 2: cluster all signals (quarantine bucket is segregated).
        all_signals = self.stores.signals.list()
        opportunities = self._cluster_into_opportunities(all_signals)

        # Persist opportunities, refreshing existing on re-scan.
        existing_opp_by_key: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
        for opp in self.stores.opportunities.list():
            k = (opp.get("target_skill", ""), tuple(sorted(opp.get("signal_ids", []))))
            existing_opp_by_key[k] = opp

        new_opp_ids: list[str] = []
        refreshed = 0
        for opp in opportunities:
            k = (opp.target_skill, tuple(sorted(opp.signal_ids)))
            existing = existing_opp_by_key.get(k)
            if existing is not None:
                opp.opportunity_id = existing["opportunity_id"]
                if existing.get("created_at"):
                    opp.created_at = existing["created_at"]
                self.stores.opportunities.save(opp)
                refreshed += 1
            else:
                stored = self.stores.opportunities.save(opp)
                new_opp_ids.append(stored["opportunity_id"])
            # Decision log AFTER the opportunity_id is finalised. The
            # store decides whether to append (material change) or
            # idempotently no-op.
            payload = getattr(opp, "_decision_payload", None)
            if payload:
                self.decision_store.record_decision(
                    opportunity_id=opp.opportunity_id,
                    **payload,
                )

        parts = [
            f"scanned: signals_new={len(new_signals)}",
            f"opportunities_new={len(new_opp_ids)}",
        ]
        if refreshed:
            parts.append(f"opportunities_refreshed={refreshed}")
        parts.append(f"quarantined={quarantined_count}")
        return ScanResult(
            new_signal_ids=[s["signal_id"] for s in new_signals],
            new_opportunity_ids=new_opp_ids,
            skipped_signal_count=0,
            quarantined_signal_count=quarantined_count,
            summary=" ".join(parts),
        )

    def create_batch(self, opportunity_ids: list[str]) -> dict[str, Any]:
        from .evolution_stores import PromotionBatch

        if not opportunity_ids:
            raise ValueError("opportunity_ids is required")
        opportunities = [self.stores.opportunities.get(oid) for oid in opportunity_ids]
        missing = [oid for oid, opp in zip(opportunity_ids, opportunities) if opp is None]
        if missing:
            raise ValueError(f"unknown opportunity_ids: {missing}")
        target_skills = {opp["target_skill"] for opp in opportunities}
        if len(target_skills) > 1:
            raise ValueError(f"cannot batch opportunities across skills: {sorted(target_skills)}")
        target_skill = next(iter(target_skills))
        promo_ids: list[str] = []
        for opp in opportunities:
            promo_ids.extend(opp.get("related_promo_ids", []))
        risk = _max_rank([opp["risk_level"] for opp in opportunities], order=("low", "medium", "high"))
        priority = _max_rank([opp["priority"] for opp in opportunities], order=("low", "medium", "high"))
        should = []
        must = []
        for opp in opportunities:
            should.extend(opp.get("should_improve") or [])
            must.extend(opp.get("must_not_regress") or [])
        batch = PromotionBatch.new(
            target_skill=target_skill,
            opportunity_ids=opportunity_ids,
            promo_ids=sorted(set(promo_ids)),
            merged_summary="; ".join(opp.get("summary", "") for opp in opportunities)[:500],
            priority=priority,
            risk_level=risk,
            should_improve=sorted(set(should)),
            must_not_regress=sorted(set(must)),
            recommended_next_action="run /skill-optimize",
        )
        return self.stores.batches.save(batch)

    # ---- Stage 1: signal classification ---------------------------------

    def _classify_signal(self, record: dict[str, Any]) -> dict[str, Any]:
        content = record["content"]
        attack_type = _detect_attack(content)
        defended = bool(attack_type) and _looks_defended(content, record)
        quarantined = bool(attack_type) and not defended
        redacted_content = _redact_attack(content) if quarantined else content

        tags = _detect_tags(content, record["source_type"])
        if quarantined:
            tags.add("memory_poisoning")
            tags.add(f"attack:{attack_type}")
        elif attack_type and defended:
            tags.add("security_incident")
            tags.add(f"defended:{attack_type}")

        strength = _correction_strength(content)
        if strength >= 0.7:
            tags.add("user_correction")

        features = _extract_features(
            redacted_content,
            source_type=record["source_type"],
            tags=tags,
            attack_type=attack_type,
        )

        return {
            "source_type": record["source_type"],
            "source_path": record["source_path"],
            "source_ref": record["source_ref"],
            "observed_skill": record["observed_skill"],
            "content": redacted_content[:1500],
            "tags": sorted(tags),
            "frequency": record["frequency"],
            "severity": record["severity"],
            "quarantined": quarantined,
            "attack_type": attack_type if quarantined else "",
            "redacted": quarantined,
            "correction_strength": strength,
            "features": features,
        }

    def _signal_from_promo(self, promo: dict[str, Any]) -> dict[str, Any] | None:
        promo_id = promo.get("promo_id") or ""
        if not promo_id:
            return None
        summary = promo.get("summary") or promo.get("proposed_change") or ""
        if not summary.strip():
            return None
        record = {
            "source_type": "promo",
            "source_path": ".skills_memory/PROMOTION_CANDIDATES.md",
            "source_ref": promo_id,
            "observed_skill": promo.get("target_skill") or "self_improvement",
            "content": summary[:1500],
            "frequency": int(promo.get("occurrence_count") or 1),
            "severity": "medium",
        }
        return self._classify_signal(record)

    # ---- Stage 2: clustering --------------------------------------------

    def _cluster_into_opportunities(
        self,
        signals: list[dict[str, Any]],
    ) -> list[EvolutionOpportunity]:
        # Quarantined signals are clustered per attack_type and never mix
        # with normal signals.
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for signal in signals:
            if signal.get("quarantined"):
                key = ("__quarantine__", signal.get("attack_type", "unknown"))
            else:
                key = ("normal", self._cluster_key(signal))
            groups[key].append(signal)

        opportunities: list[EvolutionOpportunity] = []
        for (bucket, cluster_key), members in groups.items():
            if bucket == "__quarantine__":
                opp = self._quarantine_opportunity(cluster_key, members)
            else:
                opp = self._normal_opportunity(cluster_key, members)
            if self.llm_enricher is not None and not members[0].get("quarantined"):
                self._enrich_opportunity(opp, members)
            opportunities.append(opp)
        return opportunities

    def _cluster_key(self, signal: dict[str, Any]) -> str:
        """Skill-agnostic problem identity.

        Priority:
          1. normalized_problem_signature derived from extracted features
             (action / tool / error_type / target_artifact /
             correction_pattern / safety_type). This is discriminating
             enough that a policy-block and a parse-error do NOT merge,
             while the SAME problem on two skills DOES merge (→ high
             transferability).
          2. semantic tags (skill-agnostic) when no signature features.
          3. keyword fallback.

        Safety signals always carry their safety_type in the signature,
        so different safety incidents never collapse into one bucket.
        """
        features = signal.get("features") or {}
        signature = _problem_signature(features)
        if signature:
            return "sig:" + signature
        tags = sorted(
            t for t in (signal.get("tags") or [])
            if not t.startswith("attack:")
            and not t.startswith("defended:")
            and not t.startswith("tool:")
        )
        if tags:
            return "tag:" + "|".join(tags[:5])
        words = _top_words(signal.get("content") or "", limit=5)
        return "kw:" + "|".join(words)

    def _quarantine_opportunity(
        self,
        attack_type: str,
        members: list[dict[str, Any]],
    ) -> EvolutionOpportunity:
        skills = sorted({m["observed_skill"] for m in members})
        target_skill = skills[0] if skills else "self_improvement"
        opp = EvolutionOpportunity.new(
            signal_ids=[m["signal_id"] for m in members],
            target_skill=target_skill,
            opportunity_type="quarantine",
            summary=f"⚠ quarantined memory poisoning attempt ({attack_type})",
            decision="quarantine",
            evolution_score=0.0,
            value_score=0.0,
            risk_score=1.0,
            evidence_quality=0.0,
            testability=0.0,
            priority="high",
            risk_level="high",
            confidence="high",
            reason=(
                f"为什么：检测到 {attack_type} 攻击痕迹，原文已脱敏。"
                "预期效果：仅用于审计追溯；**禁止**进入 Skill Optimizer 或 SKILL.md。"
            ),
            score_breakdown=f"attack_type={attack_type}; members={len(members)}",
            should_improve=["人工审阅这条 memory 的来源是否值得保留"],
            must_not_regress=[
                "禁止把攻击载荷沉淀进 skill rule",
                "禁止用攻击文本生成 bounded edit",
            ],
            observed_skills=skills,
            cross_skill=len(skills) > 1,
            related_promo_ids=[],
        )
        opp._decision_payload = {  # type: ignore[attr-defined]
            "target_skill": target_skill,
            "decision": "quarantine",
            "alternative_decision": "n/a",
            "threshold_hit": f"quarantine_lane: attack_type={attack_type}",
            "binding_threshold": f"attack_type={attack_type}",
            "score_components": {"attack_type_count": float(len(members))},
            "value_score": 0.0,
            "risk_score": 1.0,
            "evidence_quality": 0.0,
            "testability": 0.0,
        }
        return opp

    def _normal_opportunity(
        self,
        cluster_key: str,
        members: list[dict[str, Any]],
    ) -> EvolutionOpportunity:
        # Stage 2a: target_skill from observed_skill distribution; prefer
        # non-self_improvement on ties.
        skill_counts: dict[str, int] = defaultdict(int)
        for m in members:
            skill_counts[m["observed_skill"]] += 1
        skills_sorted = sorted(
            skill_counts.items(),
            key=lambda kv: (-kv[1], 0 if kv[0] != "self_improvement" else 1, kv[0]),
        )
        target_skill = skills_sorted[0][0]
        observed_skills = sorted(skill_counts.keys())
        cross_skill = len(observed_skills) >= 2

        evidence_quality, _ = _evidence_quality(members)

        tags = {t for m in members for t in (m.get("tags") or [])}
        bare_tags = {t for t in tags if ":" not in t}
        frequency_sum = sum(int(m.get("frequency", 1)) for m in members)

        has_security = "security_incident" in bare_tags
        has_governance = "governance_related" in bare_tags or "policy_related" in bare_tags
        has_cross_cutting = bool(bare_tags & CROSS_CUTTING_TAGS)
        has_promo_evidence = any(m.get("source_type") == "promo" for m in members)

        components = {
            "frequency": min(1.0, frequency_sum / 5.0),
            "transferability": _transferability(observed_skills, has_cross_cutting),
            "impact": _impact(has_security, frequency_sum),
            "skill_confidence": _skill_confidence(observed_skills, target_skill),
            "testability": _testability(members, bare_tags, has_promo_evidence),
            "safety_gain": 1.0 if has_security else 0.0,
            "regression_risk": 0.3 if has_promo_evidence else 0.4,
            "overfitting_risk": _overfitting_risk(members, frequency_sum),
            "policy_risk": 0.5 if has_governance and not has_promo_evidence else 0.15,
            "scope_risk": 0.55 if "capability_gap" in bare_tags else 0.30,
            "cost_increase": 0.10,
            "uncertainty": 0.30 if evidence_quality < 0.5 else 0.15,
            "evidence_quality": evidence_quality,
        }

        value_score = _value_score(components)
        risk_score = _risk_score(components)

        (
            decision, opp_type, priority, risk_level, confidence,
            threshold_hit, binding_threshold, alternative_decision,
        ) = _decide_explained(
            value=value_score,
            risk=risk_score,
            evidence=evidence_quality,
            testability=components["testability"],
            overfitting=components["overfitting_risk"],
            has_security=has_security,
            has_cross_cutting=has_cross_cutting,
            target_skill=target_skill,
            frequency_sum=frequency_sum,
        )

        should_improve = _derive_should_improve(bare_tags, members, target_skill)
        must_not_regress = _derive_must_not_regress(bare_tags, has_security)

        reason = _reason_text(
            decision=decision,
            value=value_score,
            risk=risk_score,
            evidence=evidence_quality,
            testability=components["testability"],
            members=members,
            target_skill=target_skill,
            cross_skill=cross_skill,
        )
        breakdown = _score_breakdown(decision, components, value_score, risk_score, evidence_quality)
        related_promos = sorted({m["source_ref"] for m in members if m["source_type"] == "promo"})

        opp = EvolutionOpportunity.new(
            signal_ids=[m["signal_id"] for m in members],
            target_skill=target_skill,
            opportunity_type=opp_type,
            summary=_summary_text(members, cluster_key),
            decision=decision,
            evolution_score=round(value_score, 4),  # backward-compat alias
            value_score=round(value_score, 4),
            risk_score=round(risk_score, 4),
            evidence_quality=round(evidence_quality, 4),
            testability=round(components["testability"], 4),
            priority=priority,
            risk_level=risk_level,
            confidence=confidence,
            reason=reason,
            score_breakdown=breakdown,
            should_improve=should_improve,
            must_not_regress=must_not_regress,
            observed_skills=observed_skills,
            cross_skill=cross_skill,
            related_promo_ids=related_promos,
        )
        decision_payload = {
            "target_skill": target_skill,
            "decision": decision,
            "alternative_decision": alternative_decision,
            "threshold_hit": threshold_hit,
            "binding_threshold": binding_threshold,
            "score_components": dict(components),
            "value_score": value_score,
            "risk_score": risk_score,
            "evidence_quality": evidence_quality,
            "testability": components["testability"],
        }
        opp._decision_payload = decision_payload  # type: ignore[attr-defined]
        return opp

    def _enrich_opportunity(
        self,
        opp: EvolutionOpportunity,
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
        opp.must_not_regress = sorted(set(opp.must_not_regress) | set(result.must_not_regress))

    # ---- raw memory iteration -------------------------------------------

    def _iter_memory_records(self):
        for path in self._memory_files():
            text = path.read_text(encoding="utf-8")
            for record in _parse_id_records(text):
                source_ref = record["record_id"]
                observed_skill = (
                    self._skill_from_path(path)
                    or record["fields"].get("Target Skill", "")
                )
                source_type, classification = self._classify_path(path)
                content_lines = [record["title"], record["details"]]
                content = "\n".join(line for line in content_lines if line).strip()
                yield {
                    "source_type": source_type,
                    "source_path": self._rel(path),
                    "source_ref": source_ref,
                    "observed_skill": observed_skill or "self_improvement",
                    "content": content[:1500],
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
                p = global_dir / name
                if p.exists():
                    files.append(p)
        skills_dir = self.project_root / "skills"
        if skills_dir.exists():
            for skill_path in sorted(skills_dir.iterdir()):
                memory_dir = skill_path / "memory"
                if not memory_dir.exists():
                    continue
                for name in SKILL_MEMORY_FILES:
                    p = memory_dir / name
                    if p.exists():
                        files.append(p)
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


# ---------------------------------------------------------------------------
# Stage 1 helpers — attack detection + tag classification
# ---------------------------------------------------------------------------


def _detect_attack(content: str) -> str:
    lowered = content.lower()
    for attack_type, patterns in ATTACK_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in lowered:
                return attack_type
    return ""


def _looks_defended(content: str, record: dict[str, Any]) -> bool:
    lowered = content.lower()
    source = str(record.get("source_type", ""))
    if source == "error" or source.endswith(".error") or "error" in source:
        if any(marker in lowered for marker in DEFENDED_INCIDENT_MARKERS):
            return True
    return False


def _redact_attack(content: str) -> str:
    redacted = content
    for attack_type, patterns in ATTACK_PATTERNS.items():
        for pattern in patterns:
            redacted = re.sub(
                re.escape(pattern),
                f"[REDACTED_ATTACK:{attack_type}]",
                redacted,
                flags=re.IGNORECASE,
            )
    return redacted


def _detect_tags(content: str, source_type: str) -> set[str]:
    lowered = content.lower()
    tags: set[str] = set()
    base = source_type.replace("skill_memory.", "").replace("global_", "")
    if base:
        tags.add(base)
    for tag, words in TAG_LEXICON.items():
        if not words:
            continue
        if any(w.lower() in lowered for w in words):
            tags.add(tag)
    for tool in ("read_file", "edit_file", "write_file", "load_skill", "bash"):
        if tool in lowered:
            tags.add(f"tool:{tool}")
    return tags


def _correction_strength(content: str) -> float:
    lowered = content.lower()
    strengths = [strength for phrase, strength in CORRECTION_PHRASES if phrase.lower() in lowered]
    return max(strengths, default=0.0)


def _first_lexicon_match(lowered: str, lexicon: dict[str, tuple[str, ...]]) -> str:
    for label, needles in lexicon.items():
        if any(n in lowered for n in needles):
            return label
    return ""


def _extract_features(
    content: str,
    *,
    source_type: str,
    tags: set[str],
    attack_type: str = "",
) -> dict[str, str]:
    """Pull a small, skill-agnostic feature set out of the memory text.

    These features drive the normalized_problem_signature so that
    different *kinds* of problem cluster apart even when their coarse
    tags coincide.
    """
    lowered = content.lower()
    features: dict[str, str] = {}

    action = _first_lexicon_match(lowered, ACTION_LEXICON)
    if action:
        features["action"] = action

    for tool in ("edit_file", "read_file", "write_file", "load_skill", "bash"):
        if tool in lowered:
            features["tool"] = tool
            break

    is_error = source_type.endswith("error") or "tool_failure" in tags
    if is_error:
        error_type = _first_lexicon_match(lowered, ERROR_TYPE_LEXICON)
        features["error_type"] = error_type or "unknown_error"

    artifact = ""
    for label, needles in ARTIFACT_LEXICON:
        if any(n in lowered for n in needles):
            artifact = label
            break
    if artifact:
        features["target_artifact"] = artifact

    if "user_correction" in tags or "format_preference" in tags:
        pattern = _first_lexicon_match(lowered, CORRECTION_PATTERN_LEXICON)
        if pattern:
            features["correction_pattern"] = pattern

    # Safety type — derived for any security-tinged signal so different
    # safety incidents bucket separately. Prefer the concrete attack_type
    # (from quarantine / defended detection) when present.
    if attack_type:
        features["safety_type"] = {
            "approval_bypass": "approval_block",
            "secret_exfiltration": "secret_leak",
            "prompt_injection": "injection",
            "safety_disable": "policy_violation",
        }.get(attack_type, attack_type)
    elif tags & {"security_incident", "governance_related", "policy_related"}:
        safety_type = _first_lexicon_match(lowered, SAFETY_TYPE_LEXICON)
        if safety_type:
            features["safety_type"] = safety_type

    return features


def _problem_signature(features: dict[str, str]) -> str:
    """Stable, ordered signature string from extracted features. Empty
    when no discriminating feature was found (caller falls back to
    tags / keywords)."""
    order = ("safety_type", "error_type", "action", "tool", "target_artifact", "correction_pattern")
    parts = [f"{key[:4]}:{features[key]}" for key in order if features.get(key)]
    return "|".join(parts)


# ---------------------------------------------------------------------------
# Stage 3 helpers — evidence_quality / value_score / risk_score / testability
# ---------------------------------------------------------------------------


def _evidence_quality(members: list[dict[str, Any]]) -> tuple[float, dict[str, float]]:
    type_score = {
        "promo": 1.0,
        "error": 0.8,
        "skill_memory.error": 0.8,
        "global_error": 0.8,
        "learning": 0.7,
        "skill_memory.learning": 0.7,
        "global_learning": 0.6,
        "feature_request": 0.6,
        "global_feature_request": 0.6,
        "policy_candidate": 0.6,
        "regression_test": 0.7,
    }
    reliabilities = [type_score.get(m.get("source_type", ""), 0.5) for m in members]
    source_reliability = sum(reliabilities) / len(reliabilities)

    distinct = len({(m["source_path"], m["source_ref"]) for m in members})
    distinct_occurrence = min(1.0, distinct / 3.0)

    human_correction = max(
        (float(m.get("correction_strength", 0.0)) for m in members), default=0.0,
    )

    has_tool_failure = any("tool_failure" in (m.get("tags") or []) for m in members)
    failure_reproducibility = (
        0.8 if has_tool_failure and distinct >= 2
        else (0.5 if has_tool_failure else 0.3)
    )

    trace_support = (
        0.7 if any(any(t.startswith("tool:") for t in (m.get("tags") or [])) for m in members)
        else 0.3
    )

    breakdown = {
        "source_reliability": source_reliability,
        "distinct_occurrence": distinct_occurrence,
        "human_correction": human_correction,
        "failure_reproducibility": failure_reproducibility,
        "trace_support": trace_support,
    }
    weighted = (
        0.30 * source_reliability
        + 0.25 * distinct_occurrence
        + 0.25 * human_correction
        + 0.10 * failure_reproducibility
        + 0.10 * trace_support
    )
    return min(1.0, max(0.0, weighted)), breakdown


def _value_score(c: dict[str, float]) -> float:
    return min(
        1.0,
        max(
            0.0,
            0.25 * c["evidence_quality"]
            + 0.15 * c["frequency"]
            + 0.15 * c["transferability"]
            + 0.15 * c["impact"]
            + 0.10 * c["skill_confidence"]
            + 0.15 * c["testability"]
            + 0.05 * c["safety_gain"],
        ),
    )


def _risk_score(c: dict[str, float]) -> float:
    return min(
        1.0,
        max(
            0.0,
            0.25 * c["regression_risk"]
            + 0.20 * c["overfitting_risk"]
            + 0.20 * c["policy_risk"]
            + 0.15 * c["scope_risk"]
            + 0.10 * c["cost_increase"]
            + 0.10 * c["uncertainty"],
        ),
    )


def _testability(
    members: list[dict[str, Any]],
    tags: set[str],
    has_promo: bool,
) -> float:
    """Composite of 5 sub-signals, each contributing up to its weight.

    Weights chosen so a strong user_correction on a format_preference
    cluster reliably clears the 0.70 promote threshold, while a weak
    cluster (only meta tags) stays well below.
    """
    score = 0.0
    non_meta = tags - META_TAGS
    if non_meta:
        score += 0.20  # has should_improve
    if {"security_incident", "governance_related", "policy_related"} & tags:
        score += 0.15  # concrete must_not_regress
    correction = max(
        (float(m.get("correction_strength", 0.0)) for m in members), default=0.0,
    )
    score += 0.30 * correction  # human-correction strength
    if tags & {"format_preference", "capability_gap"}:
        score += 0.25  # judgeable output (format / capability)
    if "tool_failure" in tags and len(members) >= 2:
        score += 0.20  # reproducible negative case from tool failure
    if has_promo:
        score += 0.10  # existing PROMO already encodes a judgeable rule
    return min(1.0, score)


def _transferability(observed_skills: list[str], has_cross_cutting: bool) -> float:
    if len(observed_skills) >= 3:
        return 1.0
    if len(observed_skills) == 2:
        return 0.85
    return 0.65 if has_cross_cutting else 0.40


def _impact(has_security: bool, frequency_sum: int) -> float:
    if has_security:
        return 1.0
    return min(1.0, 0.3 + 0.15 * frequency_sum)


def _skill_confidence(observed_skills: list[str], target_skill: str) -> float:
    if target_skill == "self_improvement":
        return 0.4
    non_self = [s for s in observed_skills if s != "self_improvement"]
    return 1.0 if len(non_self) == len(observed_skills) else 0.7


def _overfitting_risk(members: list[dict[str, Any]], frequency_sum: int) -> float:
    if frequency_sum <= 1:
        return 0.6
    one_time = any(
        m.get("severity") == "low"
        and "user_correction" not in (m.get("tags") or [])
        for m in members
    )
    if one_time and frequency_sum < 3:
        return 0.5
    return 0.2


# ---------------------------------------------------------------------------
# Stage 4 — decision matrix
# ---------------------------------------------------------------------------


def _decide(
    *,
    value: float,
    risk: float,
    evidence: float,
    testability: float,
    overfitting: float,
    has_security: bool,
    has_cross_cutting: bool,
    target_skill: str,
    frequency_sum: int,
) -> tuple[str, str, str, str, str]:
    decision, opp_type, priority, risk_level, confidence, _, _, _ = _decide_explained(
        value=value,
        risk=risk,
        evidence=evidence,
        testability=testability,
        overfitting=overfitting,
        has_security=has_security,
        has_cross_cutting=has_cross_cutting,
        target_skill=target_skill,
        frequency_sum=frequency_sum,
    )
    return decision, opp_type, priority, risk_level, confidence


def _decide_explained(
    *,
    value: float,
    risk: float,
    evidence: float,
    testability: float,
    overfitting: float,
    has_security: bool,
    has_cross_cutting: bool,
    target_skill: str,
    frequency_sum: int,
) -> tuple[str, str, str, str, str, str, str, str]:
    """Same matrix as ``_decide`` but also returns
    ``threshold_hit`` (the rule that fired),
    ``binding_threshold`` (the tightest inequality), and
    ``alternative_decision`` (what would fire if the binding bound were
    just barely missed). Used to feed ScoutDecisionStore."""
    if has_security:
        return (
            "safety_review", "safety_review", "high", "high", "medium",
            "security_lane: contains security_incident tag",
            "security_incident=True",
            "promote (if not security)",
        )

    # self_improvement gate: an unattributed self_improvement cluster
    # never auto-promotes. The only way to promote is for a human to
    # re-attribute the source memory to a real skill (then the next scan
    # picks that skill as target_skill and this gate no longer applies).
    if target_skill == "self_improvement":
        if value >= 0.55:
            return (
                "request_eval", "request_eval", "medium", "medium", "low",
                "self_improvement_gate: needs human target_skill attribution before promote",
                "target_skill=self_improvement",
                "promote (after human attribution)",
            )
        return (
            "defer", "defer", "low", "low", "low",
            "self_improvement_gate: low value + unattributed",
            "target_skill=self_improvement",
            "request_eval (after human attribution)",
        )

    if value >= 0.60 and risk <= 0.35 and testability >= 0.70:
        priority = "high" if has_cross_cutting or value >= 0.75 else "medium"
        binding = _tightest_promote_binding(value, risk, testability)
        return (
            "promote", "promote", priority, "medium", "medium",
            "promote_lane: value>=0.60 ∧ risk<=0.35 ∧ testability>=0.70",
            binding,
            "request_eval",
        )

    if value >= 0.55 and (testability < 0.70 or risk > 0.35):
        binding = f"testability={testability:.2f}<0.70" if testability < 0.70 else f"risk={risk:.2f}>0.35"
        return (
            "request_eval", "request_eval", "medium", "medium", "low",
            "request_eval_lane: value>=0.55 but testability or risk fails",
            binding,
            "promote",
        )

    if value >= 0.40 and evidence < 0.50:
        return (
            "defer", "defer", "low", "low", "low",
            "defer_lane: value>=0.40 but evidence<0.50",
            f"evidence={evidence:.2f}<0.50",
            "request_eval",
        )

    if overfitting >= 0.5 and frequency_sum < 3:
        return (
            "reject", "defer", "low", "low", "low",
            "reject_lane: overfitting>=0.5 ∧ frequency<3",
            f"overfitting={overfitting:.2f}∧Σf={frequency_sum}",
            "defer",
        )

    if target_skill == "self_improvement" and not has_security:
        return (
            "defer", "defer", "low", "low", "low",
            "defer_lane: target_skill==self_improvement",
            "target_skill=self_improvement",
            "promote (if attributed to a real skill)",
        )

    if value >= 0.30:
        return (
            "defer", "defer", "low", "low", "low",
            "defer_lane: value>=0.30",
            f"value={value:.2f}∈[0.30,0.55)",
            "request_eval",
        )

    return (
        "reject", "defer", "low", "low", "low",
        "reject_lane: value<0.30",
        f"value={value:.2f}<0.30",
        "defer",
    )


def _tightest_promote_binding(value: float, risk: float, testability: float) -> str:
    """Return whichever of the three promote thresholds is currently
    closest to flipping. Lets the decision log explain *why* this row
    fired and where the marginal score sits."""
    distances = {
        f"value={value:.2f}>=0.60": value - 0.60,
        f"risk={risk:.2f}<=0.35": 0.35 - risk,
        f"testability={testability:.2f}>=0.70": testability - 0.70,
    }
    return min(distances.items(), key=lambda kv: kv[1])[0]


# ---------------------------------------------------------------------------
# Narrative
# ---------------------------------------------------------------------------


def _reason_text(
    *,
    decision: str,
    value: float,
    risk: float,
    evidence: float,
    testability: float,
    members: list[dict[str, Any]],
    target_skill: str,
    cross_skill: bool,
) -> str:
    skill_label = f"`{target_skill}`" if target_skill else "目标 skill"
    frequency = sum(int(m.get("frequency", 1)) for m in members)
    if decision == "promote":
        why = (
            f"{skill_label} 的证据足（value={value:.2f}, evidence={evidence:.2f}），"
            f"风险可控（risk={risk:.2f}），且可测试（testability={testability:.2f}）。"
        )
        if cross_skill:
            why += " 同类问题跨多个 skill，可迁移性高。"
        effect = "升级后预期固化为 SKILL.md 的 Memory-derived rules，减少同类问题的纠正成本。"
    elif decision == "request_eval":
        why = f"价值评估 {value:.2f} 已达晋升阈值，但 testability={testability:.2f} 或 risk={risk:.2f} 不达标。"
        effect = "建议先补一组 positive + negative regression case 再考虑升级。"
    elif decision == "safety_review":
        why = "信号涉及安全/审批事件（命中 security_incident 标签），不能直接进入 skill rule。"
        effect = "走人工 safety review；批准后才考虑沉淀为 policy 规则。"
    elif decision == "quarantine":
        why = "检测到攻击载荷（prompt injection / approval bypass / safety disable / secret exfiltration），原文已脱敏。"
        effect = "仅用于审计；不进入任何 Optimizer 提案。"
    elif decision == "defer":
        if evidence < 0.5:
            why = f"价值 {value:.2f} 中等，但证据质量 {evidence:.2f} 偏低（缺重复出现或强纠正）。"
        else:
            why = f"价值 {value:.2f} 介于观察区间（0.30..0.55），暂未达晋升阈值。"
        effect = "保留观察，下次扫描如果证据累积再评估。"
    else:  # reject
        why = (
            f"价值 {value:.2f} 偏低，证据 {evidence:.2f}，frequency={frequency}。"
            "更像一次性偏好或低质量信号。"
        )
        effect = "不进入 skill rules，避免污染长期规则集。"
    return f"为什么：{why} 预期效果：{effect}"


def _score_breakdown(
    decision: str,
    c: dict[str, float],
    value: float,
    risk: float,
    evidence: float,
) -> str:
    return (
        f"decision={decision}; value={value:.2f}; risk={risk:.2f}; "
        f"evidence={evidence:.2f}; testability={c['testability']:.2f}; "
        f"frequency={c['frequency']:.2f}; transferability={c['transferability']:.2f}; "
        f"impact={c['impact']:.2f}; skill_confidence={c['skill_confidence']:.2f}; "
        f"policy_risk={c['policy_risk']:.2f}; overfitting={c['overfitting_risk']:.2f}"
    )


# ---------------------------------------------------------------------------
# Derived fields, summary, parsing
# ---------------------------------------------------------------------------


def _derive_should_improve(
    tags: set[str],
    members: list[dict[str, Any]],
    target_skill: str,
) -> list[str]:
    out: list[str] = []
    skill_label = target_skill or "目标 skill"
    if "tool_failure" in tags:
        out.append(f"减少 {skill_label} 在类似输入下重复抛同一类错误")
    if "format_preference" in tags:
        out.append(f"把用户偏好的格式/结构固化到 {skill_label} 的 Memory-derived rules")
    if "capability_gap" in tags:
        out.append(f"覆盖 {skill_label} 目前缺失的能力调用方式")
    if "rollback_related" in tags:
        out.append("识别并避免触发版本回滚的输入模式")
    if "governance_related" in tags or "policy_related" in tags:
        out.append("不要把审批/治理细节硬编码进 skill；走 policy review")
    if any(m.get("source_type") == "promo" for m in members):
        out.append("把已有 PROMO 候选合并审查，避免碎片化升级")
    if not out:
        non_meta = sorted(tags - META_TAGS)
        out = [f"梳理重复模式 '{tag}'" for tag in non_meta[:3]] or ["梳理本聚类中的重复经验"]
    return out[:5]


def _derive_must_not_regress(tags: set[str], has_security: bool) -> list[str]:
    out = ["不放宽既有的安全策略", "不绕过 ReviewQueue 审批"]
    if has_security or "memory_poisoning" in tags:
        out.append("保留 safety_gain 相关断言不被覆盖")
    if "governance_related" in tags or "policy_related" in tags:
        out.append("不把治理/审批 phrasing 写进 SKILL.md 的可执行规则")
    if "rollback_related" in tags:
        out.append("不破坏现有的 rollback 路径")
    return out


def _summary_text(members: list[dict[str, Any]], cluster_key: str) -> str:
    sample = members[0]["content"][:160].replace("\n", " ").strip()
    return f"{cluster_key} | {sample}"


def _max_rank(values: list[str], order: tuple[str, ...]) -> str:
    seen = [v for v in values if v in order]
    if not seen:
        return order[0]
    return max(seen, key=lambda v: order.index(v))


def _parse_id_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("## ")]
    starts.append(len(lines))
    for cursor in range(len(starts) - 1):
        block = lines[starts[cursor]:starts[cursor + 1]]
        if not block:
            continue
        match = ID_HEADING_RE.match(block[0])
        if not match:
            continue
        record_id = match.group(1)
        title = (match.group(2) or "").strip()
        fields: dict[str, str] = {}
        details: list[str] = []
        in_details = False
        for line in block[1:]:
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
        records.append({
            "record_id": record_id,
            "title": title,
            "fields": fields,
            "details": "\n".join(details).strip(),
        })
    return records


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _top_words(content: str, limit: int) -> list[str]:
    seen: dict[str, int] = defaultdict(int)
    for word in WORD_RE.findall(content.lower()):
        if len(word) < 3:
            continue
        seen[word] += 1
    ordered = sorted(seen.items(), key=lambda item: (-item[1], item[0]))
    return [w for w, _ in ordered[:limit]]
