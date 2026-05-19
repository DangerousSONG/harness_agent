export function formatDate(value) {
  if (!value) return "-";
  const numeric = Number(value);
  const date = Number.isFinite(numeric) && String(value).length < 14
    ? new Date(numeric * 1000)
    : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function compact(value, fallback = "-") {
  if (Array.isArray(value)) return value.length ? value.join(", ") : fallback;
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

export function titleize(value) {
  return compact(value)
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function nextActionLabel(value) {
  const labels = {
    create_regression_review: "Generate regression coverage review",
    approve_regression_review: "Review and apply regression cases",
    apply_regression_review: "Review and apply regression cases",
    create_skill_review: "Review and apply the approved Skill patch",
    approve_skill_review: "Review and apply the approved Skill patch",
    apply_skill_review: "Review and apply the approved Skill patch",
    completed: "View recorded version",
    waiting: "Waiting for the next reviewable action",
  };
  return labels[value] || titleize(value || "waiting");
}

export function severityTone(value) {
  const normalized = String(value || "").toLowerCase();
  if (["high", "critical", "danger"].includes(normalized)) return "danger";
  if (["medium", "warning"].includes(normalized)) return "risk";
  return "neutral";
}
