// scoutViewModel.js — frontend-only view-model layer over the raw
// Side-Channel API payloads. Translates engineering-grade fields
// (decision / score / tag / reason) into category + plain-language
// surfaces. No backend changes; raw fields are still available under
// ``raw`` for the "debug" disclosure panel.

const POLICY_PHRASE_NEEDLES = [
  "policy_block",
  "approval_block",
  "tool call blocked",
  "policy enforcement triggered",
  "safeharness policy",
  "protected file",
  "protected_file",
  "policy_candidate",
  "safety",
];

const POLICY_TAGS = new Set([
  "policy_related",
  "policy_candidate",
  "governance_related",
  "security_incident",
  "memory_poisoning",
]);

const TOOL_TAGS = new Set(["tool_failure", "capability_gap"]);

const LEVEL_LABEL = {
  high: "高",
  medium: "中",
  low: "低",
};

const DECISION_JUDGEMENT = {
  promote: "证据足且可测试，建议升级为 skill 规则。",
  request_eval: "价值已达晋升阈值，但还需要更强的可测试性或证据。",
  defer: "暂未达晋升阈值，先观察一段时间。",
  reject: "证据偏弱或风险偏高，本轮不建议沉淀。",
  safety_review: "命中安全/策略标记，需要走人工策略审查，不能直接进入 skill 规则。",
  quarantine: "检测到攻击载荷或被污染的内容，仅做隔离审计。",
};

const DECISION_NEXT_STEP = {
  promote: "为这条机会补一组正/负回归 case，再生成 skill 补丁。",
  request_eval: "先补一组正/负回归 case；测得起来再考虑升级。",
  defer: "继续观察；下一次扫描如果证据累积再评估。",
  reject: "无需行动。如果你有更多上下文，可以恢复后再评估。",
  safety_review: "走人工策略/安全审查；批准后才考虑沉淀为 policy。",
  quarantine: "仅用于审计；禁止把这段内容写进任何 skill 规则。",
};

const CATEGORY_LABEL = {
  skill_optimization: "Skill 优化",
  policy_event: "策略 / 安全事件",
  tool_event: "工具 / 能力问题",
  needs_label: "需人工标注",
  ignored: "已忽略",
};

const CATEGORY_TONE = {
  skill_optimization: "text-emerald-700 bg-emerald-50/60 border-emerald-200",
  policy_event: "text-amber-800 bg-amber-50/60 border-amber-200",
  tool_event: "text-appleBlue bg-blue-50/60 border-blue-200",
  needs_label: "text-indigo-700 bg-indigo-50/60 border-indigo-200",
  ignored: "text-zinc-600 bg-zinc-50 border-line",
};

const RISK_TONE = {
  high: "text-rose-700 bg-rose-50/60 border-rose-200",
  medium: "text-amber-700 bg-amber-50/60 border-amber-200",
  low: "text-zinc-600 bg-zinc-50 border-line",
};

function lowercaseSafe(value) {
  return typeof value === "string" ? value.toLowerCase() : "";
}

function collectSignalsForOpp(opp, signalsById) {
  const ids = opp?.signal_ids || [];
  return ids.map((id) => signalsById?.[id]).filter(Boolean);
}

function hasPolicyMarkers(opp, signals) {
  const reason = lowercaseSafe(opp?.reason);
  if (reason.includes("requires_policy_review=true")) return true;
  if (reason.includes("policy_gate")) return true;
  if (opp?.decision === "quarantine") return true;
  if (opp?.decision === "safety_review") return true;

  for (const signal of signals) {
    if (signal?.quarantined) return true;
    const tags = signal?.tags || [];
    if (tags.some((t) => POLICY_TAGS.has(t))) return true;
    const content = lowercaseSafe(signal?.content);
    if (POLICY_PHRASE_NEEDLES.some((p) => content.includes(p))) return true;
  }
  return false;
}

function hasToolMarkers(opp, signals) {
  if (lowercaseSafe(opp?.target_skill).startsWith("tool")) return true;
  for (const signal of signals) {
    const tags = signal?.tags || [];
    if (tags.some((t) => TOOL_TAGS.has(t))) return true;
  }
  return false;
}

function hasHumanLabelMarker(opp) {
  const reason = lowercaseSafe(opp?.reason);
  if (reason.includes("needs_human_label=true")) return true;
  if (reason.includes("request_human_label")) return true;
  if (opp?.target_skill === "self_improvement") return true;
  return false;
}

export function classifyOpportunity(opp, signalsById = {}) {
  if (!opp) return "skill_optimization";
  const signals = collectSignalsForOpp(opp, signalsById);
  if (hasPolicyMarkers(opp, signals)) return "policy_event";
  if (hasHumanLabelMarker(opp)) return "needs_label";
  if (hasToolMarkers(opp, signals)) return "tool_event";
  return "skill_optimization";
}

function buildTitle(opp, category) {
  const skill = opp?.target_skill || "未归属 skill";
  switch (category) {
    case "policy_event":
      return `${skill} · 命中策略/安全标记`;
    case "tool_event":
      return `${skill} · 工具或能力问题`;
    case "needs_label":
      return "需要人工标注归属 Skill";
    case "skill_optimization":
    default:
      return `${skill} · 可考虑的 skill 优化`;
  }
}

function buildImpactTarget(opp, category) {
  if (category === "needs_label") return "（未归属，待人工标注）";
  return opp?.target_skill || "—";
}

function buildWhatHappened(opp, signals) {
  if (opp?.summary) {
    // Drop the cluster_key prefix like "sig:foo|bar | " that the
    // deterministic summary writer prepends.
    const parts = opp.summary.split(" | ");
    if (parts.length > 1) return parts.slice(1).join(" | ");
    return opp.summary;
  }
  const firstSignal = signals[0];
  if (firstSignal?.content) return firstSignal.content.slice(0, 200);
  return "（暂无可读摘要）";
}

function buildJudgement(opp) {
  return DECISION_JUDGEMENT[opp?.decision] || opp?.reason || "—";
}

function buildNextStep(opp, category) {
  if (category === "policy_event") return DECISION_NEXT_STEP.safety_review;
  if (category === "tool_event") {
    return "走人工工具/能力审查；不要把工具失败硬编码进 skill 规则。";
  }
  if (category === "needs_label") {
    return "把这条 cluster 的来源 memory 的 Target Skill 标注为真实的 skill，下次扫描就能走正常审批流程。";
  }
  return DECISION_NEXT_STEP[opp?.decision] || "—";
}

export function buildOpportunityView(opp, signalsById = {}) {
  const category = classifyOpportunity(opp, signalsById);
  const signals = collectSignalsForOpp(opp, signalsById);
  const riskLevel = opp?.risk_level || "low";
  const confidence = opp?.confidence || "low";
  return {
    id: opp?.opportunity_id || "",
    category,
    categoryLabel: CATEGORY_LABEL[category],
    categoryTone: CATEGORY_TONE[category],
    title: buildTitle(opp, category),
    impactTarget: buildImpactTarget(opp, category),
    riskLevel,
    riskLabel: LEVEL_LABEL[riskLevel] || riskLevel,
    riskTone: RISK_TONE[riskLevel] || RISK_TONE.low,
    confidence,
    confidenceLabel: LEVEL_LABEL[confidence] || confidence,
    whatHappened: buildWhatHappened(opp, signals),
    judgement: buildJudgement(opp),
    nextStep: buildNextStep(opp, category),
    suggestions: opp?.should_improve || [],
    guardrails: opp?.must_not_regress || [],
    sources: signals.map((s) => ({
      id: s.signal_id,
      sourceRef: s.source_ref,
      sourcePath: s.source_path,
      preview: (s.content || "").slice(0, 160),
    })),
    raw: opp,
  };
}

export function buildEditView(edit) {
  if (!edit) return null;
  const ops = edit.edit_ops || [];
  const proposedRules = ops
    .filter((op) => op.op === "add" || op.op === "replace")
    .map((op) => op.text || op.replace_text || "")
    .filter(Boolean);
  const removals = ops.filter((op) => op.op === "delete").map((op) => op.text || "");
  return {
    id: edit.edit_id,
    status: edit.status,
    targetSkill: edit.target_skill,
    sourceEvidenceCount:
      (edit.source_signal_ids?.length || 0) +
      (edit.source_promo_ids?.length || 0),
    changeKind: proposedRules.length
      ? removals.length
        ? "新增 + 删除规则"
        : "新增规则"
      : removals.length
      ? "删除规则"
      : "修改规则",
    risk: edit.risk_assessment || "—",
    rationale: edit.rationale || "—",
    expected: edit.expected_improvement || "—",
    proposedRules,
    removals,
    requiredValidationCases: edit.required_validation_cases || [],
    reviewId: edit.review_id || "",
    raw: edit,
  };
}

export const CATEGORY_KEYS = [
  "skill_optimization",
  "policy_event",
  "tool_event",
  "needs_label",
];

export { CATEGORY_LABEL, CATEGORY_TONE, LEVEL_LABEL };
