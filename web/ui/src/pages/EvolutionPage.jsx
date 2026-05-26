import { ArrowRight, Sparkles } from "lucide-react";
import StatusPill from "../components/StatusPill";
import { compact, nextActionKey, nextActionLabel } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";

const STEP_KEYS = {
  memory: "evolution.step.memory",
  promo: "evolution.step.promo",
  regression_review: "evolution.step.regression_review",
  regression_applied: "evolution.step.regression_applied",
  skill_promotion_review: "evolution.step.skill_promotion_review",
  skill_applied: "evolution.step.skill_applied",
  version: "evolution.step.version",
};

export function EvolutionTimeline({
  promoId,
  targetSkill,
  evolutionState,
  currentPromotion,
  onContinue,
  busyPromoId,
}) {
  const t = useTranslate();
  const steps = expandSteps(evolutionState);
  const requiresRegeneration = Boolean(currentPromotion?.requires_regeneration);
  const nextAction = evolutionState?.next_action;
  const nextLabel = requiresRegeneration
    ? t("panel.next_action.regenerate")
    : nextActionKey(nextAction)
      ? t(nextActionKey(nextAction))
      : nextActionLabel(nextAction);
  const busy = busyPromoId === promoId;
  const canContinue = Boolean(promoId) && !busy && nextAction !== "completed";

  return (
    <section className="section-panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-appleBlue">
            <Sparkles className="h-4 w-4" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-zinc-950">{compact(promoId, "—")}</h2>
            <p className="text-xs text-zinc-500">
              {t("promotion.field.target_skill")}: {compact(targetSkill, "—")}
            </p>
          </div>
        </div>
        <button
          className="primary-button"
          disabled={!canContinue}
          onClick={() => promoId && onContinue?.(promoId)}
        >
          {busy ? t("common.working") : requiresRegeneration ? t("panel.next_action.regenerate") : t("evolution.continue")}
        </button>
      </div>

      <p className="mt-3 text-xs text-zinc-500">{nextLabel}</p>

      <div className="mt-4 flex flex-wrap items-stretch gap-2">
        {steps.map((step, index) => (
          <div className="flex items-stretch gap-2" key={step.name}>
            <div className="flex min-w-[7.5rem] flex-col justify-between rounded-lg border border-line bg-zinc-50 px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                {STEP_KEYS[step.name] ? t(STEP_KEYS[step.name]) : step.name}
              </span>
              <div className="mt-1.5 flex items-center justify-between gap-2">
                <StatusPill status={step.status} />
                {step.review_id ? (
                  <span className="truncate font-mono text-[10px] text-zinc-500">{step.review_id}</span>
                ) : null}
              </div>
            </div>
            {index < steps.length - 1 ? (
              <ArrowRight className="h-3.5 w-3.5 shrink-0 self-center text-zinc-300" />
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

export default function EvolutionPage({
  promotions,
  selectedPromoId,
  onSelectPromo,
  evolutionState,
  onContinue,
  currentPromotion,
  busyPromoId,
}) {
  const t = useTranslate();
  const hasPromos = Boolean(promotions?.length);

  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-zinc-950">{t("evolution.title")}</h1>
          </div>
          {hasPromos ? (
            <select
              className="rounded-lg border border-line bg-white px-3 py-2 text-sm"
              value={selectedPromoId || ""}
              onChange={(event) => onSelectPromo(event.target.value)}
            >
              {promotions.map((promo) => (
                <option value={promo.promo_id} key={promo.promo_id}>
                  {promo.promo_id} - {promo.target_skill}
                </option>
              ))}
            </select>
          ) : null}
        </div>
        {hasPromos && currentPromotion ? (
          <EvolutionTimeline
            promoId={selectedPromoId}
            targetSkill={evolutionState?.target_skill || currentPromotion?.target_skill}
            evolutionState={evolutionState}
            currentPromotion={currentPromotion}
            onContinue={onContinue}
            busyPromoId={busyPromoId}
          />
        ) : null}
      </div>
    </section>
  );
}

function expandSteps(state) {
  const raw = state?.steps || [];
  const byName = Object.fromEntries(raw.map((step) => [step.name, step]));
  const regression = byName.regression_review || {};
  const skill = byName.skill_promotion_review || {};
  const regressionApplied = regression.status === "applied" ? "applied" : "waiting";
  const skillApplied = skill.status === "applied" ? "applied" : "waiting";
  return [
    byName.memory || { name: "memory", status: "waiting" },
    byName.promo || { name: "promo", status: "waiting" },
    { name: "regression_review", status: regression.status || "waiting", review_id: regression.review_id },
    { name: "regression_applied", status: regressionApplied, review_id: regression.review_id },
    { name: "skill_promotion_review", status: skill.status || "waiting", review_id: skill.review_id },
    { name: "skill_applied", status: skillApplied, review_id: skill.review_id },
    byName.version || { name: "version", status: "waiting" },
  ];
}
