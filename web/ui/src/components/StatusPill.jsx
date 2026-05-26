import { Check, Clock, X, AlertTriangle } from "lucide-react";
import { useTranslate } from "../lib/i18n.jsx";

const toneClass = {
  completed: "bg-emerald-50 text-emerald-700 border-emerald-100",
  applied: "bg-emerald-50 text-emerald-700 border-emerald-100",
  approved: "bg-blue-50 text-blue-700 border-blue-100",
  pending: "bg-blue-50 text-blue-700 border-blue-100",
  running: "bg-blue-50 text-blue-700 border-blue-100",
  waiting: "bg-zinc-50 text-zinc-500 border-zinc-200",
  proposed: "bg-zinc-50 text-zinc-500 border-zinc-200",
  rejected: "bg-red-50 text-red-700 border-red-100",
  failed: "bg-red-50 text-red-700 border-red-100",
  blocked: "bg-red-50 text-red-700 border-red-100",
  legacy: "bg-amber-50 text-amber-700 border-amber-100",
  risk: "bg-amber-50 text-amber-700 border-amber-100",
  tracked: "bg-zinc-50 text-zinc-600 border-zinc-200",
};

export default function StatusPill({ status, tone }) {
  const t = useTranslate();
  const normalized = String(status || "waiting").toLowerCase();
  const className = toneClass[tone || normalized] || toneClass.waiting;
  const Icon =
    normalized === "completed" || normalized === "applied"
      ? Check
      : normalized === "rejected" || normalized === "failed" || normalized === "blocked"
        ? X
        : normalized === "risk" || normalized === "legacy"
          ? AlertTriangle
          : Clock;
  // Translate via status.<normalized> with the raw value as fallback so any
  // unknown status string still renders verbatim.
  const key = `status.${normalized}`;
  const translated = t(key);
  const label = translated && translated !== key ? translated : (status || "waiting");
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${className}`}>
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}
