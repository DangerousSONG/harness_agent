import {
  Check,
  Clock,
  X,
  AlertTriangle,
  ShieldCheck,
  Archive,
  Lock,
  PauseCircle,
  Loader,
} from "lucide-react";
import { useTranslate } from "../lib/i18n.jsx";

// Per-status visual mapping. Keys cover both the original engineering
// vocabulary (pending / approved / failed …) AND the user-facing
// Chinese lifecycle vocabulary (已上架 / 待审查 / 已归档 …) so cards
// across the Assets / Reviews / Side-channel pages render with a
// consistent look without each caller mapping its own labels.
const STATUS_PROFILES = {
  // ---------- engineering vocabulary (legacy callers) ----------
  completed: { tone: "success", icon: Check },
  applied: { tone: "success", icon: Check },
  approved: { tone: "info", icon: Check },
  pending: { tone: "info", icon: Clock },
  running: { tone: "info", icon: Loader },
  waiting: { tone: "muted", icon: Clock },
  proposed: { tone: "muted", icon: Clock },
  validated: { tone: "info", icon: ShieldCheck },
  review_created: { tone: "info", icon: Clock },
  rejected: { tone: "danger", icon: X },
  failed: { tone: "danger", icon: X },
  blocked: { tone: "danger", icon: X },
  legacy: { tone: "warn", icon: AlertTriangle },
  risk: { tone: "warn", icon: AlertTriangle },
  tracked: { tone: "muted", icon: Check },
  executable: { tone: "success", icon: Check },
  "not executable": { tone: "muted", icon: Lock },

  // ---------- user-facing Chinese lifecycle vocabulary ----------
  "已上架": { tone: "success", icon: ShieldCheck },
  "草稿": { tone: "muted", icon: Clock },
  "系统校验中": { tone: "info", icon: Loader },
  "待审查": { tone: "info", icon: Clock },
  "未通过": { tone: "danger", icon: X },
  "已归档": { tone: "muted", icon: Archive },
  "已禁用": { tone: "warn", icon: PauseCircle },
  "active": { tone: "success", icon: ShieldCheck },
  "draft": { tone: "muted", icon: Clock },
  "system_check": { tone: "info", icon: Loader },
  "pending_review": { tone: "info", icon: Clock },
  "archived": { tone: "muted", icon: Archive },
  "disabled": { tone: "warn", icon: PauseCircle },
};

// Tone palette. Softer borders + slightly desaturated backgrounds give
// each badge a calmer, more uniform feel than the previous mix of
// stark borders and bright text.
const TONE_CLASS = {
  success: "bg-emerald-50 text-emerald-700 border-emerald-200/80 ring-emerald-100",
  info: "bg-blue-50 text-blue-700 border-blue-200/80 ring-blue-100",
  warn: "bg-amber-50 text-amber-800 border-amber-200/80 ring-amber-100",
  danger: "bg-rose-50 text-rose-700 border-rose-200/80 ring-rose-100",
  muted: "bg-zinc-50 text-zinc-600 border-zinc-200/80 ring-zinc-100",
};

export default function StatusPill({ status, tone }) {
  const t = useTranslate();
  const raw = String(status || "waiting");
  const normalized = raw.toLowerCase();

  const profile =
    STATUS_PROFILES[raw]
    || STATUS_PROFILES[normalized]
    || STATUS_PROFILES.waiting;

  const resolvedTone = tone || profile.tone;
  const cssClass = TONE_CLASS[resolvedTone] || TONE_CLASS.muted;
  const Icon = profile.icon || Clock;
  const isSpinner = Icon === Loader;

  // Translate via status.<normalized> with the raw value as fallback so
  // any unknown status string still renders verbatim.
  const key = `status.${normalized}`;
  const translated = t(key);
  const label = translated && translated !== key ? translated : raw;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${cssClass}`}
    >
      <Icon className={`h-3.5 w-3.5 ${isSpinner ? "animate-spin" : ""}`} />
      {label}
    </span>
  );
}
