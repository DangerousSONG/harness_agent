import {
  BotMessageSquare,
  Boxes,
  Check,
  GitPullRequest,
  Layers3,
  Monitor,
  Rocket,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { nextActionLabel, titleize } from "../lib/format";
import StatusPill from "./StatusPill";

const nav = [
  { id: "chat", label: "Chat", icon: BotMessageSquare },
  { id: "reviews", label: "Reviews", icon: GitPullRequest },
  { id: "assets", label: "Assets", icon: Boxes },
  { id: "promotions", label: "Promotions", icon: Rocket },
  { id: "evolution", label: "Evolution", icon: Sparkles },
  { id: "versions", label: "Versions", icon: Layers3 },
];

function StepDot({ status, active }) {
  const normalized = String(status || "waiting").toLowerCase();
  const completed = ["completed", "applied"].includes(normalized);
  const failed = ["failed", "rejected"].includes(normalized);
  const waiting = ["waiting", ""].includes(normalized);
  return (
    <span
      className={[
        "relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px]",
        completed ? "border-emerald-500 bg-emerald-500 text-white" : "",
        failed ? "border-danger bg-danger text-white" : "",
        active && !completed && !failed ? "border-appleBlue bg-appleBlue text-white" : "",
        waiting && !active ? "border-zinc-300 bg-white text-zinc-400" : "",
      ].join(" ")}
    >
      {completed ? <Check className="h-3 w-3" /> : active ? "." : ""}
    </span>
  );
}

function ContextPanel({ skills, evolutionState, reviews, onNextAction, nextActionBusy }) {
  const currentSkill =
    skills?.find((skill) => skill.name === evolutionState?.target_skill) || skills?.[0] || null;
  const steps = buildPanelSteps(evolutionState, reviews);
  const nextAction = evolutionState?.next_action || inferNextAction(reviews);

  return (
    <aside className="hidden min-h-0 w-80 shrink-0 overflow-auto border-l border-line bg-white/55 px-4 py-5 xl:block">
      <div className="space-y-4">
        <section className="card p-5">
          <p className="text-sm font-semibold text-zinc-950">1. Current Asset</p>
          <div className="mt-5 space-y-4 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-zinc-500">Asset type:</span>
              <span className="font-semibold">Skill</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-zinc-500">Name:</span>
              <span className="font-semibold">{currentSkill?.name || "-"}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-zinc-500">Active source:</span>
              <span className="text-right font-semibold">
                {currentSkill?.name ? `skills/${currentSkill.name}/SKILL.md` : "-"}
              </span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-zinc-500">Latest snapshot:</span>
              <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-semibold">
                {currentSkill?.latest_version || "No snapshot"}
              </span>
            </div>
          </div>
          <p className="mt-4 text-xs leading-5 text-zinc-500">
            Active source is the runtime current loaded source. Latest snapshot is a version
            record, not the default loaded source.
          </p>
        </section>

        <section className="card p-5">
          <p className="text-sm font-semibold text-zinc-950">2. Evolution Progress</p>
          <div className="relative mt-5 space-y-6">
            <div className="absolute left-2.5 top-2 h-[calc(100%-1rem)] w-px bg-line" />
            {steps.map((step) => (
              <div className="relative flex gap-4" key={step.name}>
                <StepDot status={step.status} active={step.active} />
                <div>
                  <p className="text-sm font-semibold text-zinc-900">{step.label}</p>
                  <div className="mt-2">
                    <StatusPill status={step.status} tone={step.active ? "approved" : undefined} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="card p-5">
          <p className="text-sm font-semibold text-zinc-950">3. Next Action</p>
          <div className="mt-4 flex gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-appleBlue">
              <Sparkles className="h-4 w-4" />
            </span>
            <p className="text-sm leading-6 text-zinc-700">{nextActionLabel(nextAction)}</p>
          </div>
          <button
            className="primary-button mt-5 w-full"
            disabled={!evolutionState?.promo_id || nextAction === "completed" || nextActionBusy}
            onClick={() => onNextAction?.(evolutionState?.promo_id)}
          >
            {nextActionBusy ? "Working..." : nextActionLabel(nextAction)}
          </button>
        </section>
      </div>
    </aside>
  );
}

function buildPanelSteps(evolutionState, reviews) {
  const review = reviews?.find((item) => ["pending", "approved"].includes(item.status));
  const raw = evolutionState?.steps || [];
  const statusFor = (name, fallback) => raw.find((step) => step.name === name)?.status || fallback;
  const skillStatus = statusFor("skill_promotion_review", review?.status || "waiting");
  const regressionStatus = statusFor("regression_review", "waiting");
  const versionStatus = statusFor("version", "waiting");
  const steps = [
    { name: "memory", label: "Memory captured", status: statusFor("memory", review ? "completed" : "waiting") },
    { name: "promo", label: "PROMO generated", status: statusFor("promo", "waiting") },
    { name: "regression", label: "Regression review", status: regressionStatus },
    { name: "skill", label: "Skill patch review", status: skillStatus },
    { name: "version", label: "Version recorded", status: versionStatus },
  ];
  const firstWaiting = steps.findIndex((step) => !["completed", "applied"].includes(step.status));
  return steps.map((step, index) => ({
    ...step,
    active: index === firstWaiting && ["pending", "approved", "waiting"].includes(String(step.status)),
  }));
}

function inferNextAction(reviews) {
  const active = reviews?.find((review) => ["pending", "approved"].includes(review.status));
  if (!active) return "waiting";
  if (active.status === "pending" && active.type === "skill.regression_case") {
    return "approve_regression_review";
  }
  if (active.status === "approved" && active.type === "skill.regression_case") {
    return "apply_regression_review";
  }
  if (active.status === "pending") return "approve_skill_review";
  if (active.status === "approved") return "apply_skill_review";
  return "waiting";
}

export default function AppShell({
  page,
  onPageChange,
  children,
  skills,
  reviews,
  evolutionState,
  onNextAction,
  nextActionBusy,
}) {
  return (
    <div className="flex h-screen overflow-hidden bg-mist text-ink">
      <aside className="hidden w-56 shrink-0 border-r border-line bg-white/70 px-4 py-5 backdrop-blur md:flex md:flex-col">
        <div className="flex items-center gap-3 px-2">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-950 text-white">
            <ShieldCheck className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-semibold leading-4">SafeHarness</p>
            <p className="text-sm font-semibold leading-4">Console</p>
          </div>
        </div>
        <nav className="mt-12 space-y-2">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = page === item.id;
            return (
              <button
                key={item.id}
                className={[
                  "flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm font-semibold transition",
                  active ? "bg-blue-50 text-appleBlue" : "text-zinc-700 hover:bg-zinc-100",
                ].join(" ")}
                onClick={() => onPageChange(item.id)}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className="mt-auto flex items-center gap-3 px-3 py-3 text-sm font-semibold text-zinc-800">
          <Monitor className="h-4 w-4" />
          Local Workspace
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-line bg-white/70 px-4 py-3 md:hidden">
          <div className="flex items-center gap-2 font-semibold">
            <ShieldCheck className="h-5 w-5" />
            SafeHarness Console
          </div>
          <select
            className="rounded-lg border border-line bg-white px-3 py-2 text-sm"
            value={page}
            onChange={(event) => onPageChange(event.target.value)}
          >
            {nav.map((item) => (
              <option value={item.id} key={item.id}>
                {titleize(item.label)}
              </option>
            ))}
          </select>
        </div>
        {children}
      </main>

      <ContextPanel
        skills={skills}
        reviews={reviews}
        evolutionState={evolutionState}
        onNextAction={onNextAction}
        nextActionBusy={nextActionBusy}
      />
    </div>
  );
}
