import { X } from "lucide-react";
import { compact } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";
import StatusPill from "./StatusPill";

function Row({ label, value }) {
  return (
    <div>
      <p className="muted-label">{label}</p>
      <p className="mt-1 text-sm leading-6 text-zinc-800">{compact(value)}</p>
    </div>
  );
}

export default function PromotionModal({
  open,
  promotion,
  loading,
  onClose,
  onEvolve,
  onRegenerate,
  busy,
}) {
  const t = useTranslate();
  if (!open) return null;
  const missingFields = promotion?.missing_fields || [];
  const requiresRegeneration = Boolean(promotion?.requires_regeneration || missingFields.length);
  const missing = (field) => `Missing ${field}`;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-950/20 px-4 py-8 backdrop-blur-sm">
      <section className="card flex max-h-[86vh] w-full max-w-2xl flex-col overflow-hidden">
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-zinc-950">{t("promotions.title")}</h2>
              {promotion?.status ? <StatusPill status={promotion.status} /> : null}
            </div>
            <p className="mt-1 text-sm text-zinc-500">{compact(promotion?.promo_id)}</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label={t("common.cancel")}>
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="overflow-auto px-6 py-5">
          {loading ? (
            <div className="rounded-lg bg-zinc-50 p-6 text-sm text-zinc-500">
              {t("settings.search.loading")}
            </div>
          ) : (
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <Row label={t("promotion.field.target_skill")} value={promotion?.target_skill} />
                <Row label={t("promotion.field.source_memory_type")} value={promotion?.source_memory_type} />
                <Row label={t("promotion.field.occurrence_count")} value={promotion?.occurrence_count} />
                <Row
                  label={t("promotion.field.promotion_score")}
                  value={missingFields.includes("promotion_score") ? missing("promotion_score") : promotion?.promotion_score}
                />
                <Row
                  label={t("promotion.field.promotion_decision")}
                  value={missingFields.includes("promotion_decision") ? missing("promotion_decision") : promotion?.promotion_decision}
                />
                <Row
                  label={t("promotion.field.eligible_target")}
                  value={missingFields.includes("eligible_target") ? missing("eligible_target") : promotion?.eligible_target}
                />
              </div>
              {requiresRegeneration ? (
                <div className="rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
                  {t("panel.next_action.regenerate_hint")}
                </div>
              ) : null}
              <Row label={t("promotion.field.summary")} value={promotion?.summary} />
              <Row label={t("promotion.field.proposed_change")} value={promotion?.proposed_change} />
              <Row label={t("promotion.field.evaluation_plan")} value={promotion?.evaluation_plan} />
              <Row label={t("promotion.field.rollback_plan")} value={promotion?.rollback_plan} />
              <Row label={t("promotion.field.source_memory")} value={promotion?.source_memory} />
            </div>
          )}
        </div>

        <footer className="flex justify-end gap-2 border-t border-line bg-white px-6 py-4">
          <button className="secondary-button" onClick={onClose}>{t("common.cancel")}</button>
          <button
            className="primary-button"
            disabled={!promotion?.promo_id || busy}
            onClick={() =>
              requiresRegeneration
                ? onRegenerate(promotion.promo_id)
                : onEvolve(promotion.promo_id)
            }
          >
            {busy
              ? t("common.working")
              : requiresRegeneration
                ? t("panel.next_action.regenerate")
                : t("common.evolve")}
          </button>
        </footer>
      </section>
    </div>
  );
}
