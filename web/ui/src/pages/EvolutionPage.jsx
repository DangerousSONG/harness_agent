import { ArrowRight, Sparkles } from "lucide-react";
import EmptyState from "../components/EmptyState";
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
  const steps = expandSteps(evolutionState);
  const requiresRegeneration = Boolean(currentPromotion?.requires_regeneration);
  const candidateMissing = Boolean(selectedPromoId && hasPromos && !currentPromotion);

  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
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

        {!hasPromos ? (
          <EmptyState title={t("evolution.no_candidates")} />
        ) : candidateMissing ? (
          <EmptyState
            title={t("evolution.not_found")}
            detail={t("evolution.not_found_detail")}
          />
        ) : (
          <div className="grid gap-5 lg:grid-cols-[1fr_18rem]">
            <section className="card p-6">
              <div className="flex flex-wrap items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-appleBlue">
                  <Sparkles className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-base font-semibold text-zinc-950">
                    {compact(evolutionState?.promo_id || selectedPromoId)}
                  </h2>
                  <p className="text-sm text-zinc-500">
                    {t("promotion.field.target_skill")}: {compact(evolutionState?.target_skill)}
                  </p>
                </div>
              </div>

              <div className="mt-8 space-y-4">
                {steps.map((step, index) => (
                  <div className="flex items-center gap-4" key={step.name}>
                    <div className="flex min-w-0 flex-1 items-center gap-4 rounded-lg border border-line bg-zinc-50 px-4 py-3">
                      <span className="text-sm font-semibold text-zinc-950">{STEP_KEYS[step.name] ? t(STEP_KEYS[step.name]) : step.name}</span>
                      <div className="ml-auto">
                        <StatusPill status={step.status} />
                      </div>
                    </div>
                    {index < steps.length - 1 ? <ArrowRight className="h-4 w-4 shrink-0 text-zinc-300" /> : null}
                  </div>
                ))}
              </div>
            </section>

            <aside className="card p-5">
              <p className="text-sm font-semibold text-zinc-950">{t("panel.next_action")}</p>
              <p className="mt-3 text-sm leading-6 text-zinc-600">
                {requiresRegeneration
                  ? t("panel.next_action.regenerate")
                  : nextActionKey(evolutionState?.next_action)
                    ? t(nextActionKey(evolutionState?.next_action))
                    : nextActionLabel(evolutionState?.next_action)}
              </p>
              <button
                className="primary-button mt-5 w-full"
                disabled={!selectedPromoId || busyPromoId === selectedPromoId}
                onClick={() => onContinue(selectedPromoId)}
              >
                {busyPromoId === selectedPromoId
                  ? t("common.working")
                  : requiresRegeneration
                    ? t("panel.next_action.regenerate")
                    : t("evolution.continue")}
              </button>
              <div className="mt-5 space-y-2 text-xs text-zinc-500">
                {steps.map((step) => (
                  <p key={`${step.name}-review`}>
                    {STEP_KEYS[step.name] ? t(STEP_KEYS[step.name]) : step.name}: {compact(step.review_id || step.version || step.status)}
                  </p>
                ))}
              </div>
            </aside>
          </div>
        )}
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
