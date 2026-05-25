import { Eye, Rocket } from "lucide-react";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { compact } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";

export default function PromotionsPage({ promotions, busyPromoId, onView, onEvolve, onRegenerate }) {
  const t = useTranslate();
  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-zinc-950">{t("promotions.title")}</h1>
        </div>
        {!promotions?.length ? (
          <EmptyState title={t("promotions.empty")} />
        ) : (
          <div className="card overflow-hidden">
            <div className="overflow-auto">
              <table className="min-w-full divide-y divide-line text-sm">
                <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase tracking-normal text-zinc-500">
                  <tr>
                    {[
                      "promo_id",
                      "target_skill",
                      "source_memory_type",
                      "occurrence_count",
                      "promotion_score",
                      "promotion_decision",
                      "eligible_target",
                      "status",
                      "",
                    ].map((header) => (
                      <th className="whitespace-nowrap px-4 py-3" key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-white">
                  {promotions.map((promo) => (
                    <tr key={promo.promo_id}>
                      <td className="px-4 py-4 font-semibold">{promo.promo_id}</td>
                      <td className="px-4 py-4">{compact(promo.target_skill)}</td>
                      <td className="px-4 py-4">{compact(promo.source_memory_type)}</td>
                      <td className="px-4 py-4">{compact(promo.occurrence_count)}</td>
                      <td className="px-4 py-4">{compact(promo.promotion_score)}</td>
                      <td className="px-4 py-4">{compact(promo.promotion_decision)}</td>
                      <td className="px-4 py-4">{compact(promo.eligible_target)}</td>
                      <td className="px-4 py-4"><StatusPill status={promo.status} /></td>
                      <td className="px-4 py-4">
                        <div className="flex justify-end gap-2">
                          <button className="secondary-button" onClick={() => onView(promo.promo_id)}>
                            <Eye className="h-4 w-4" />
                            {t("review.action.review_details")}
                          </button>
                          <button
                            className="primary-button"
                            disabled={busyPromoId === promo.promo_id}
                            onClick={() =>
                              promo.requires_regeneration
                                ? onRegenerate(promo.promo_id)
                                : onEvolve(promo.promo_id)
                            }
                          >
                            <Rocket className="h-4 w-4" />
                            {promo.requires_regeneration ? t("common.regenerate") : t("common.evolve")}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
