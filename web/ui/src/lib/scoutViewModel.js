// scoutViewModel.js — frontend-only view-model layer over the raw
// Side-Channel API payloads. Translates engineering-grade fields
// (decision / score / tag / reason / edit_ops / cluster_key) into a
// plain-language surface the regular user can navigate. No backend
// changes; raw fields are kept under ``raw`` for the "展开技术细节"
// disclosure panel.
//
// Three classifiers + three mappers:
//   classifyOpportunity / classifyBatch / classifyEdit
//   buildOpportunityView / mapBatchToView / mapEditToView

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

// Strings that must never appear in main copy. If a backend-supplied
// bullet matches any of these, it gets dropped from the user view
// (still preserved under ``raw`` for the technical-detail panel).
const ENGINEERING_NEEDLES = [
  /^tag:/i,
  /^sig:/i,
  /^kw:/i,
  /reduce repetition of pattern/i,
  /\bopp-[0-9a-f]+\b/i,
  /\bsig-[0-9a-f]+\b/i,
  /\bbatch-[0-9a-f]+\b/i,
  /\bedit-[0-9a-f]+\b/i,
  /add\s*→\s*##/i,
  /## memory-derived rules/i,
  /must_not_regress/i,
  /should_improve/i,
  /evidence_quality/i,
  /value_score/i,
  /risk_score/i,
  /testability/i,
  /policy_gate/i,
  /requires_policy_review/i,
  /needs_human_label/i,
];

function isEngineeringText(text) {
  if (typeof text !== "string" || !text.trim()) return true;
  return ENGINEERING_NEEDLES.some((rx) => rx.test(text));
}

function sanitizeBullets(values) {
  if (!Array.isArray(values)) return [];
  return values.filter((v) => !isEngineeringText(v));
}

function stripClusterKey(summary) {
  if (typeof summary !== "string") return "";
  // Drop "sig:foo|bar | …" or "tag:foo|bar | …" prefixes the
  // deterministic summary writer prepends.
  const parts = summary.split(" | ");
  if (parts.length > 1) {
    const head = parts[0].trim();
    if (/^(sig|tag|kw):/i.test(head)) return parts.slice(1).join(" | ").trim();
  }
  return summary;
}

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

// --------------------------------------------------------------- titles

function buildTitle(opp, category) {
  const skill = opp?.target_skill || "未归属 Skill";
  switch (category) {
    case "policy_event":
      return "命中安全/审批策略，需要人工策略审查";
    case "tool_event":
      return `${skill} · 工具或能力配置需要核对`;
    case "needs_label":
      return "需要人工标注归属 Skill";
    case "skill_optimization":
    default:
      return `${skill} · 可考虑沉淀的 Skill 优化`;
  }
}

function describeAffectedObject(signals, fallback) {
  // Try to extract a concrete subject from the first signal's content
  // (file path, tool name, skill name) so the user sees what was hit.
  for (const sig of signals) {
    const content = sig?.content || "";
    const filePath = content.match(/\b(?:tools|skills|web|runtime|harness)\/[A-Za-z0-9_./-]+/);
    if (filePath) return filePath[0];
    const toolMention = content.match(/\b([a-z_]+_(?:file|tool|handler|registry))\b/);
    if (toolMention) return toolMention[1];
  }
  return fallback || "—";
}

// --------------------------------------------------------- what happened

function buildWhatHappenedSkill(opp, signals) {
  const subject = opp?.target_skill || "skill";
  const sample = stripClusterKey(opp?.summary || "") || (signals[0]?.content || "").slice(0, 160);
  if (sample) {
    return `系统发现一组针对 ${subject} 的重复偏好或纠正，证据：${sample.replace(/\s+/g, " ").trim()}`;
  }
  return `系统在 ${subject} 上发现一组可复用的偏好或纠正。`;
}

function buildWhatHappenedPolicy(opp, signals) {
  const affected = describeAffectedObject(signals, opp?.target_skill || "");
  if (affected && affected !== "—") {
    return `系统检测到一次涉及 ${affected} 的操作触发了 SafeHarness 的策略/审批规则，已被拦截，未直接执行。`;
  }
  return "系统检测到一次操作触发了 SafeHarness 的策略/审批规则，已被拦截，未直接执行。";
}

function buildWhatHappenedTool(opp, signals) {
  const affected = describeAffectedObject(signals, opp?.target_skill || "tool");
  return `系统在 ${affected} 上发现工具失败或能力缺失的迹象。`;
}

function buildWhatHappenedNeedsLabel(opp) {
  return `系统暂未把这条 cluster 归属到具体的真实 Skill（当前 target_skill="self_improvement"）。`;
}

function buildWhatHappened(opp, signals, category) {
  switch (category) {
    case "policy_event":
      return buildWhatHappenedPolicy(opp, signals);
    case "tool_event":
      return buildWhatHappenedTool(opp, signals);
    case "needs_label":
      return buildWhatHappenedNeedsLabel(opp);
    case "skill_optimization":
    default:
      return buildWhatHappenedSkill(opp, signals);
  }
}

// ----------------------------------------------------- system judgement

function buildJudgement(category) {
  switch (category) {
    case "policy_event":
      return "这是安全策略正常生效的事件，不属于 Skill 优化，**不应直接生成 SKILL.md 补丁**。";
    case "tool_event":
      return "这反映的是工具注册或能力配置的问题，不应通过修改 SKILL.md 来掩盖；建议走人工工具审查。";
    case "needs_label":
      return "未归属到真实 Skill 的 cluster 不允许自动晋升。需要人工把来源 memory 的 Target Skill 标注成真实 skill，下一次扫描才能进入正常审批流程。";
    case "skill_optimization":
    default:
      return "证据可复用、风险较低，适合在补充回归测试后沉淀为 Skill 规则。";
  }
}

// ----------------------------------------------------- recommended action

function buildRecommendedAction(category) {
  switch (category) {
    case "policy_event":
      return "建议进入策略审查，确认当前审批规则是否需要调整。若策略合理，可继续观察或忽略。";
    case "tool_event":
      return "建议走人工工具审查，确认工具配置、权限或注册关系是否需要调整。";
    case "needs_label":
      return "请到来源 memory 把 Target Skill 字段改成真实的 skill 名，再回来重新扫描。";
    case "skill_optimization":
    default:
      return "建议先生成回归测试，再生成 Skill 变更草稿并进入审批。";
  }
}

// ----------------------------------------------------- opportunity view

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
    impactTarget: describeAffectedObject(signals, opp?.target_skill || ""),
    riskLevel,
    riskLabel: LEVEL_LABEL[riskLevel] || riskLevel,
    riskTone: RISK_TONE[riskLevel] || RISK_TONE.low,
    confidence,
    confidenceLabel: LEVEL_LABEL[confidence] || confidence,
    whatHappened: buildWhatHappened(opp, signals, category),
    judgement: buildJudgement(category),
    recommendedAction: buildRecommendedAction(category),
    // Sanitized: drop bullets that smell like engineering output.
    suggestions:
      category === "skill_optimization"
        ? sanitizeBullets(opp?.should_improve || [])
        : [],
    sources: signals.map((s) => ({
      id: s.signal_id,
      sourceRef: s.source_ref,
      sourcePath: s.source_path,
      preview: (s.content || "").slice(0, 160),
    })),
    raw: opp,
  };
}

// ---------------------------------------------------------- batch view

export function mapBatchToView(batch, memberOpps = []) {
  const firstCategory = memberOpps[0]?.category || "skill_optimization";
  const targetSkill = batch?.target_skill || memberOpps[0]?.raw?.target_skill || "—";
  const evidenceCount = (batch?.opportunity_ids || []).length || memberOpps.length;
  const subject =
    firstCategory === "skill_optimization"
      ? targetSkill
      : describeAffectedObject(
          memberOpps.flatMap((m) => m.sources || []).map((s) => ({ content: s.preview })),
          targetSkill,
        );

  const title = (() => {
    switch (firstCategory) {
      case "policy_event":
        return "策略审查草稿：命中安全/审批规则的事件";
      case "tool_event":
        return "工具审查草稿：工具或能力配置问题";
      case "needs_label":
        return "归属待标注草稿：未归属的 cluster";
      case "skill_optimization":
      default:
        return `Skill 变更草稿：${targetSkill}`;
    }
  })();

  const whyClean = (() => {
    switch (firstCategory) {
      case "policy_event":
        return "系统把同一类策略/审批拦截事件汇总成一组待处理项。安全事件不适合作为普通 Skill 规则沉淀。";
      case "tool_event":
        return "系统把同一类工具失败或能力缺失事件汇总成一组待处理项；建议在工具层修复，而不是写进 Skill。";
      case "needs_label":
        return "系统把未归属到具体 Skill 的 cluster 汇总到这里，等待人工标注真实 Target Skill。";
      case "skill_optimization":
      default:
        return `系统在 ${targetSkill} 上汇总了 ${evidenceCount} 条可复用的偏好/纠正证据，预计可沉淀为 Skill 规则。`;
    }
  })();

  const plannedContent = (() => {
    switch (firstCategory) {
      case "policy_event":
        return "**不生成 SKILL.md 补丁。** 建议创建策略审查，确认当前文件修改/工具调用的审批规则是否需要调整。";
      case "tool_event":
        return "**不生成 SKILL.md 补丁。** 建议创建工具审查，检查工具注册、权限或配置。";
      case "needs_label":
        return "**不生成 SKILL.md 补丁。** 请把来源 memory 的 Target Skill 改成真实 skill 名后重新扫描。";
      case "skill_optimization":
      default:
        return "拟生成一份变更草稿，把上述偏好/纠正沉淀为 Skill 规则；草稿仍需走人工审查并通过回归测试。";
    }
  })();

  const reviewRequirements = (() => {
    switch (firstCategory) {
      case "policy_event":
        return [
          "不得绕过 ReviewQueue 审批流程",
          "不得放宽现有的 SafeHarness 安全策略",
          "不得把安全/审批事件写入普通 Skill 规则",
        ];
      case "tool_event":
        return [
          "不得通过修改 SKILL.md 来绕过工具层缺陷",
          "不得放宽工具的默认审批策略",
        ];
      case "needs_label":
        return ["必须先由人工把 Target Skill 标注到真实 skill"];
      case "skill_optimization":
      default:
        return [
          "拟新增的规则必须配套正/负回归 case",
          "草稿仍然必须经过 ReviewQueue 审批与人工 apply",
          "不放宽既有的安全策略",
        ];
    }
  })();

  return {
    id: batch?.batch_id || "",
    category: firstCategory,
    categoryLabel: CATEGORY_LABEL[firstCategory],
    categoryTone: CATEGORY_TONE[firstCategory],
    title,
    targetSubject: subject,
    evidenceCount,
    risk: batch?.risk_level || "—",
    riskLabel: LEVEL_LABEL[batch?.risk_level] || (batch?.risk_level || "—"),
    why: whyClean,
    plannedContent,
    reviewRequirements,
    canGenerateSkillDraft: firstCategory === "skill_optimization",
    raw: batch,
  };
}

// ---------------------------------------------------------- edit view

export function mapEditToView(edit, signalsById = {}, oppsById = {}) {
  if (!edit) return null;

  const sourceOppIds = edit.source_opportunity_ids || [];
  const memberOpps = sourceOppIds
    .map((oid) => oppsById[oid])
    .filter(Boolean)
    .map((opp) => buildOpportunityView(opp, signalsById));
  const category = memberOpps[0]?.category || "skill_optimization";

  const ops = edit.edit_ops || [];
  const proposedRules = ops
    .filter((op) => op.op === "add" || op.op === "replace")
    .map((op) => (op.text || op.replace_text || "").trim())
    .filter(Boolean);
  const removals = ops
    .filter((op) => op.op === "delete")
    .map((op) => (op.text || "").trim())
    .filter(Boolean);

  const title = (() => {
    switch (category) {
      case "policy_event":
        return "策略审查草稿";
      case "tool_event":
        return "工具审查草稿";
      case "needs_label":
        return "归属待标注草稿";
      case "skill_optimization":
      default:
        return `Skill 变更草稿：${edit.target_skill}`;
    }
  })();

  const why = (() => {
    if (category === "policy_event") {
      return "系统发现一组与安全/审批策略相关的事件。这类问题不应该通过修改 SKILL.md 来处理，应该进入策略审查。";
    }
    if (category === "tool_event") {
      return "系统发现一组与工具/能力相关的事件。这类问题应该在工具层处理，而不是通过 SKILL.md。";
    }
    if (category === "needs_label") {
      return "本草稿对应的 cluster 还没有归属到真实 Skill，先不应自动晋升。";
    }
    return (
      sanitizeBullets([edit.rationale]).join(" ")
      || "系统在该 skill 上汇总了若干可复用的偏好/纠正证据，建议作为 Skill 规则沉淀。"
    );
  })();

  const plannedContent = (() => {
    if (category === "policy_event") {
      return "**不生成 SKILL.md 补丁。** 建议进入策略审查，确认审批规则是否需要调整。";
    }
    if (category === "tool_event") {
      return "**不生成 SKILL.md 补丁。** 建议进入工具审查，检查工具注册、权限或配置。";
    }
    if (category === "needs_label") {
      return "**不生成 SKILL.md 补丁。** 请把来源 memory 的 Target Skill 改成真实 skill 名后重新扫描。";
    }
    return proposedRules.length
      ? `拟新增/修改 ${proposedRules.length} 条规则到 ${edit.target_skill} 的 SKILL.md（已限定在 "## Memory-derived rules" 节内）。`
      : "暂无可读规则，请展开技术细节查看 edit_ops。";
  })();

  const reviewRequirements = (() => {
    if (category === "policy_event") {
      return [
        "不得绕过 ReviewQueue",
        "不得放宽现有的 SafeHarness 安全策略",
        "不得把安全事件写入普通 Skill 规则",
      ];
    }
    if (category === "tool_event") {
      return [
        "不得通过 SKILL.md 掩盖工具层缺陷",
        "不得放宽工具的默认审批策略",
      ];
    }
    if (category === "needs_label") {
      return ["先由人工把 Target Skill 标注到真实 skill"];
    }
    return [
      "新增规则必须配套正/负回归 case",
      "草稿必须经过 ReviewQueue 审批与人工 apply",
      "不放宽既有的安全策略",
    ];
  })();

  return {
    id: edit.edit_id,
    category,
    categoryLabel: CATEGORY_LABEL[category],
    categoryTone: CATEGORY_TONE[category],
    title,
    targetSubject: edit.target_skill || memberOpps[0]?.impactTarget || "—",
    status: edit.status,
    statusLabel: STATUS_LABEL[edit.status] || edit.status,
    sourceEvidenceCount:
      (edit.source_signal_ids?.length || 0) + (edit.source_promo_ids?.length || 0),
    why,
    plannedContent,
    proposedRules: category === "skill_optimization" ? proposedRules : [],
    removals: category === "skill_optimization" ? removals : [],
    reviewRequirements,
    reviewId: edit.review_id || "",
    canValidate: category === "skill_optimization"
      && (edit.status === "proposed" || edit.status === "validated"),
    raw: edit,
  };
}

const STATUS_LABEL = {
  proposed: "待审查",
  validated: "已通过验证",
  rejected: "已拒绝",
  review_created: "已创建审查",
  applied: "已应用",
};

export const CATEGORY_KEYS = [
  "skill_optimization",
  "policy_event",
  "tool_event",
  "needs_label",
];

export { CATEGORY_LABEL, CATEGORY_TONE, LEVEL_LABEL };

// Back-compat alias used by an earlier version of the page.
export const buildEditView = mapEditToView;
