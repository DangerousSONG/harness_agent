import {
  BotMessageSquare,
  Boxes,
  Check,
  ChevronDown,
  ChevronRight,
  GitCommitHorizontal,
  GitPullRequest,
  Library,
  Monitor,
  Settings,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { nextActionKey, nextActionLabel, titleize } from "../lib/format";
import { useLanguage } from "../lib/i18n.jsx";
import StatusPill from "./StatusPill";

const NAV_TOP = [
  { id: "chat", labelKey: "nav.chat", icon: BotMessageSquare },
  { id: "workspace", labelKey: "nav.workspace", icon: Monitor },
];

const NAV_ASSETS = [
  { id: "assets-library", labelKey: "nav.assets.library", icon: Library },
  { id: "assets-changes", labelKey: "nav.assets.changes", icon: GitCommitHorizontal },
  { id: "assets-governance", labelKey: "nav.assets.governance", icon: GitPullRequest },
];

const NAV_BOTTOM = [{ id: "settings", labelKey: "nav.settings", icon: Settings }];

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
        active && !completed && !failed ? "border-appleBlue bg-appleBlue text-white shadow-[0_0_0_4px_rgba(0,122,255,0.12)]" : "",
        waiting && !active ? "border-zinc-300 bg-white text-zinc-400" : "",
      ].join(" ")}
    >
      {completed ? <Check className="h-3 w-3" /> : active ? "." : ""}
    </span>
  );
}

function ContextPanel({
  skills,
  evolutionState,
  reviews,
  currentPromotion,
  onNextAction,
  nextActionBusy,
  flowActive,
  onClose,
}) {
  const { t } = useLanguage();
  const currentSkill =
    skills?.find((skill) => skill.name === evolutionState?.target_skill) || skills?.[0] || null;
  const steps = buildPanelSteps(evolutionState, reviews, t);
  const nextAction = evolutionState?.next_action || inferNextAction(reviews);
  const requiresRegeneration = Boolean(currentPromotion?.requires_regeneration);
  const nextKey = nextActionKey(nextAction);
  const actionLabel = requiresRegeneration
    ? t("panel.next_action.regenerate")
    : nextKey
      ? t(nextKey)
      : nextActionLabel(nextAction);

  return (
    <aside className="hidden min-h-0 w-72 shrink-0 overflow-auto border-l border-line bg-white/70 px-3 py-4 xl:block 2xl:w-80">
      <div className="space-y-3">
        {onClose && !flowActive ? (
          <div className="flex justify-end">
            <button
              type="button"
              className="icon-button h-7 w-7"
              onClick={onClose}
              aria-label={t("common.cancel")}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : null}
        <section className="section-panel p-4">
          <p className="muted-label">{t("panel.current_asset")}</p>
          <div className="mt-4 space-y-3 text-sm">
            <div>
              <span className="text-xs font-medium text-zinc-500">{t("panel.asset_type")}</span>
              <p className="mt-1 font-semibold text-zinc-950">{t("panel.asset_type.skill")}</p>
            </div>
            <div>
              <span className="text-xs font-medium text-zinc-500">{t("panel.name")}</span>
              <p className="mt-1 font-semibold text-zinc-950">{currentSkill?.name || "-"}</p>
            </div>
            <div>
              <span className="text-xs font-medium text-zinc-500">{t("panel.active_source")}</span>
              <p className="mt-1 break-words font-mono text-xs font-semibold leading-5 text-zinc-800">
                {currentSkill?.name ? `skills/${currentSkill.name}/SKILL.md` : "-"}
              </p>
            </div>
            <div>
              <span className="text-xs font-medium text-zinc-500">{t("panel.latest_snapshot")}</span>
              <div className="mt-1">
                <span className="mono-badge">{currentSkill?.latest_version || t("panel.no_snapshot")}</span>
              </div>
            </div>
          </div>
        </section>

        <section className="section-panel p-4">
          <p className="muted-label">{t("panel.skill_evolution_progress")}</p>
          <div className="relative mt-5 space-y-5">
            <div className="absolute left-2.5 top-2 h-[calc(100%-1rem)] w-px bg-line" />
            {steps.map((step) => (
              <div
                className={[
                  "relative flex gap-3 rounded-lg px-1 py-1",
                  step.active ? "bg-blue-50/70" : "",
                ].join(" ")}
                key={step.name}
              >
                <StepDot status={step.status} active={step.active} />
                <div className="min-w-0">
                  <p className={["text-sm font-semibold", step.active ? "text-appleBlue" : "text-zinc-900"].join(" ")}>
                    {step.label}
                  </p>
                  <div className="mt-1.5">
                    <StatusPill status={step.status} tone={step.active ? "approved" : undefined} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="section-panel p-4">
          <p className="muted-label">{t("panel.next_action")}</p>
          <p className="mt-3 text-sm font-semibold leading-6 text-zinc-900">{actionLabel}</p>
          {requiresRegeneration ? (
            <div className="mt-4 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
              {t("panel.next_action.regenerate_hint")}
            </div>
          ) : null}
          <button
            className="primary-button mt-5 w-full"
            disabled={
              !currentPromotion?.promo_id
              || (!requiresRegeneration && nextAction === "completed")
              || nextActionBusy
            }
            onClick={() => onNextAction?.(currentPromotion?.promo_id)}
          >
            {nextActionBusy ? t("panel.next_action.working") : actionLabel}
          </button>
        </section>
      </div>
    </aside>
  );
}

function buildPanelSteps(evolutionState, reviews, t) {
  const review = reviews?.find((item) => ["pending", "approved"].includes(item.status));
  const raw = evolutionState?.steps || [];
  const statusFor = (name, fallback) => raw.find((step) => step.name === name)?.status || fallback;
  const skillStatus = statusFor("skill_promotion_review", review?.status || "waiting");
  const regressionStatus = statusFor("regression_review", "waiting");
  const versionStatus = statusFor("version", "waiting");
  const steps = [
    { name: "memory", label: t("step.memory"), status: statusFor("memory", review ? "completed" : "waiting") },
    { name: "promo", label: t("step.promo"), status: statusFor("promo", "waiting") },
    { name: "regression", label: t("step.regression"), status: regressionStatus },
    { name: "skill", label: t("step.skill"), status: skillStatus },
    { name: "version", label: t("step.version"), status: versionStatus },
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

function LanguageToggle() {
  const { language, setLanguage } = useLanguage();
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-line text-xs font-semibold">
      <button
        type="button"
        className={[
          "px-2 py-1 transition",
          language === "en" ? "bg-zinc-900 text-white" : "bg-white text-zinc-600 hover:bg-zinc-100",
        ].join(" ")}
        onClick={() => setLanguage("en")}
      >
        EN
      </button>
      <button
        type="button"
        className={[
          "px-2 py-1 transition",
          language === "zh" ? "bg-zinc-900 text-white" : "bg-white text-zinc-600 hover:bg-zinc-100",
        ].join(" ")}
        onClick={() => setLanguage("zh")}
      >
        中
      </button>
    </div>
  );
}

export default function AppShell({
  page,
  onPageChange,
  children,
  skills,
  reviews,
  evolutionState,
  currentPromotion,
  onNextAction,
  nextActionBusy,
}) {
  const { t } = useLanguage();
  const assetsActive = page.startsWith("assets-");
  const [assetsOpen, setAssetsOpen] = useState(true);
  const mobileNav = [...NAV_TOP, ...NAV_ASSETS, ...NAV_BOTTOM];
  return (
    <div className="flex h-screen overflow-hidden bg-mist text-ink">
      <aside className="hidden w-56 shrink-0 border-r border-line bg-white/70 px-4 py-5 backdrop-blur md:flex md:flex-col">
        <div className="flex items-center gap-3 px-2">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-950 text-white">
            <ShieldCheck className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-semibold leading-4">{t("app.brand_line_1")}</p>
            <p className="text-sm font-semibold leading-4">{t("app.brand_line_2")}</p>
          </div>
        </div>
        <nav className="mt-12 space-y-2">
          {NAV_TOP.map((item) => {
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
                {t(item.labelKey)}
              </button>
            );
          })}
          <div>
            <button
              className={[
                "flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm font-semibold transition",
                assetsActive ? "bg-blue-50 text-appleBlue" : "text-zinc-700 hover:bg-zinc-100",
              ].join(" ")}
              onClick={() => {
                setAssetsOpen((open) => !open);
                if (!assetsActive) onPageChange("assets-library");
              }}
            >
              <Boxes className="h-4 w-4" />
              <span className="flex-1">{t("nav.assets")}</span>
              <ChevronDown className={["h-4 w-4 transition", assetsOpen ? "rotate-180" : ""].join(" ")} />
            </button>
            {assetsOpen ? (
              <div className="mt-1 space-y-1 pl-5">
                {NAV_ASSETS.map((item) => {
                  const Icon = item.icon;
                  const active = page === item.id;
                  return (
                    <button
                      key={item.id}
                      className={[
                        "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-semibold transition",
                        active ? "bg-white text-appleBlue shadow-hairline" : "text-zinc-600 hover:bg-zinc-100",
                      ].join(" ")}
                      onClick={() => onPageChange(item.id)}
                    >
                      <Icon className="h-4 w-4" />
                      {t(item.labelKey)}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
          {NAV_BOTTOM.map((item) => {
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
                {t(item.labelKey)}
              </button>
            );
          })}
        </nav>
        <div className="mt-auto space-y-3 px-3 py-3 text-sm font-semibold text-zinc-800">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-medium text-zinc-500">{t("app.language")}</span>
            <LanguageToggle />
          </div>
          <div className="flex items-center gap-3">
            <Monitor className="h-4 w-4" />
            {t("app.local_workspace")}
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-line bg-white/70 px-4 py-3 md:hidden">
          <div className="flex items-center gap-2 font-semibold">
            <ShieldCheck className="h-5 w-5" />
            {t("app.brand_line_1")} {t("app.brand_line_2")}
          </div>
          <div className="flex items-center gap-2">
            <LanguageToggle />
            <select
              className="rounded-lg border border-line bg-white px-3 py-2 text-sm"
              value={page}
              onChange={(event) => onPageChange(event.target.value)}
            >
              {mobileNav.map((item) => (
                <option value={item.id} key={item.id}>
                  {titleize(t(item.labelKey))}
                </option>
              ))}
            </select>
          </div>
        </div>
        {children}
      </main>

      <EvolutionPanelSlot
        skills={skills}
        reviews={reviews}
        evolutionState={evolutionState}
        currentPromotion={currentPromotion}
        onNextAction={onNextAction}
        nextActionBusy={nextActionBusy}
      />
    </div>
  );
}

function evolutionFlowActive({ reviews, evolutionState, currentPromotion }) {
  const hasActiveReview = (reviews || []).some((review) =>
    ["pending", "approved"].includes(String(review?.status || "").toLowerCase()),
  );
  if (hasActiveReview) return true;
  if (currentPromotion?.promo_id) return true;
  const steps = evolutionState?.steps || [];
  return steps.some((step) => {
    const status = String(step?.status || "").toLowerCase();
    return status && status !== "waiting";
  });
}

function EvolutionPanelSlot({
  skills,
  reviews,
  evolutionState,
  currentPromotion,
  onNextAction,
  nextActionBusy,
}) {
  const { t } = useLanguage();
  const flowActive = evolutionFlowActive({ reviews, evolutionState, currentPromotion });
  const [manualOpen, setManualOpen] = useState(false);

  useEffect(() => {
    if (flowActive) setManualOpen(true);
  }, [flowActive]);

  const visible = flowActive || manualOpen;

  if (!visible) {
    return (
      <div className="hidden xl:flex">
        <button
          type="button"
          className="m-3 flex h-9 items-center gap-2 self-start rounded-full border border-line bg-white px-3 text-xs font-semibold text-zinc-600 shadow-hairline transition hover:border-zinc-300 hover:bg-zinc-50"
          onClick={() => setManualOpen(true)}
          aria-label={t("panel.skill_evolution_progress")}
        >
          <Sparkles className="h-3.5 w-3.5 text-appleBlue" />
          <span className="hidden 2xl:inline">{t("panel.skill_evolution_progress")}</span>
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  return (
    <ContextPanel
      skills={skills}
      reviews={reviews}
      evolutionState={evolutionState}
      currentPromotion={currentPromotion}
      onNextAction={onNextAction}
      nextActionBusy={nextActionBusy}
      flowActive={flowActive}
      onClose={() => setManualOpen(false)}
    />
  );
}
