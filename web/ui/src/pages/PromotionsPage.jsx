import { useState } from "react";
import { Eye, Rocket, RefreshCcw, Zap } from "lucide-react";
import EmptyState from "../components/EmptyState";
import Paginator, { paginate } from "../components/Paginator";
import StatusPill from "../components/StatusPill";
import { compact } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";

const STATUS_TONE = {
  applied: { border: "border-emerald-200", bg: "bg-emerald-50/60", text: "text-emerald-700", dot: "bg-emerald-500" },
  ready: { border: "border-blue-200", bg: "bg-blue-50/60", text: "text-appleBlue", dot: "bg-appleBlue" },
  in_flight: { border: "border-blue-200", bg: "bg-blue-50/60", text: "text-appleBlue", dot: "bg-appleBlue" },
  legacy: { border: "border-amber-200", bg: "bg-amber-50/60", text: "text-amber-800", dot: "bg-amber-500" },
  waiting_for_signal: { border: "border-amber-200", bg: "bg-amber-50/60", text: "text-amber-800", dot: "bg-amber-500" },
  policy_review_required: { border: "border-amber-200", bg: "bg-amber-50/60", text: "text-amber-800", dot: "bg-amber-500" },
  rejected: { border: "border-rose-200", bg: "bg-rose-50/60", text: "text-rose-700", dot: "bg-rose-500" },
  wrong_eligible_target: { border: "border-rose-200", bg: "bg-rose-50/60", text: "text-rose-700", dot: "bg-rose-500" },
  dangling_source: { border: "border-rose-200", bg: "bg-rose-50/60", text: "text-rose-700", dot: "bg-rose-500" },
  unknown: { border: "border-line", bg: "bg-zinc-50", text: "text-zinc-600", dot: "bg-zinc-400" },
};

export default function PromotionsPage({ promotions, busyPromoId, onView, onEvolve, onRegenerate, onFastTrack }) {
  const t = useTranslate();
  const [page, setPage] = useState(1);
  const { pageItems, total, pageCount, page: safePage } = paginate(promotions || [], page);
  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-6xl space-y-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-950">{t("promotions.title")}</h1>
        </div>
        {!promotions?.length ? (
          <EmptyState title={t("promotions.empty")} />
        ) : (
          <div className="space-y-3">
            {pageItems.map((promo) => (
              <PromotionRow
                key={promo.promo_id}
                promo={promo}
                t={t}
                busy={busyPromoId === promo.promo_id}
                onView={onView}
                onEvolve={onEvolve}
                onRegenerate={onRegenerate}
                onFastTrack={onFastTrack}
              />
            ))}
            <Paginator page={safePage} pageCount={pageCount} total={total} onPage={setPage} />
          </div>
        )}
      </div>
    </section>
  );
}

function PromotionRow({ promo, t, busy, onView, onEvolve, onRegenerate, onFastTrack }) {
  const classification = promo.status_classification || { kind: "unknown", fix: { kind: "none" } };
  const kind = classification.kind || "unknown";
  const tone = STATUS_TONE[kind] || STATUS_TONE.unknown;
  const summary = renderStatusSummary(classification, t);
  const fix = classification.fix || { kind: "none" };

  return (
    <article className="section-panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mono-badge">{promo.promo_id}</span>
            <StatusPill status={promo.status} />
            <span className="text-sm font-semibold text-zinc-900">{compact(promo.target_skill)}</span>
          </div>
          <p className="mt-2 line-clamp-2 text-sm text-zinc-600">
            {compact(promo.summary || promo.proposed_change, "—")}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <button className="secondary-button" onClick={() => onView(promo.promo_id)}>
            <Eye className="h-4 w-4" />
            {t("review.action.review_details")}
          </button>
          {fix.kind === "regenerate" ? (
            <button className="primary-button" disabled={busy} onClick={() => onRegenerate(promo.promo_id)}>
              <RefreshCcw className="h-4 w-4" />
              {t("promotions.fix.regenerate")}
            </button>
          ) : null}
          {fix.kind === "evolve" && onFastTrack ? (
            <button
              className="subprimary-button"
              disabled={busy}
              onClick={() => {
                if (window.confirm(t("promotions.fast_track.confirm_body", { promo: promo.promo_id, skill: promo.target_skill }))) {
                  onFastTrack(promo.promo_id);
                }
              }}
              title={t("promotions.fast_track.confirm_title")}
            >
              <Zap className="h-4 w-4" />
              {t("promotions.fix.fast_track")}
            </button>
          ) : null}
          {fix.kind === "evolve" ? (
            <button className="primary-button" disabled={busy} onClick={() => onEvolve(promo.promo_id)}>
              <Rocket className="h-4 w-4" />
              {t("promotions.fix.evolve")}
            </button>
          ) : null}
        </div>
      </div>

      <div className={`mt-3 flex items-start gap-3 rounded-lg border px-3 py-2.5 ${tone.border} ${tone.bg}`}>
        <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot}`} />
        <div className="min-w-0 flex-1">
          <p className={`text-sm font-medium ${tone.text}`}>{summary}</p>
          {classification.field ? (
            <p className="mt-1 text-[11px] text-zinc-500">
              <span className="font-mono">{classification.field}</span>
              {" · "}
              {t("promotions.field.actual")}: <span className="font-mono">{compact(classification.actual, "—")}</span>
              {" · "}
              {t("promotions.field.expected")}: <span className="font-mono">{compact(classification.expected, "—")}</span>
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-3 grid gap-2 text-xs text-zinc-500 sm:grid-cols-4">
        <Cell label="source_memory_type" value={promo.source_memory_type} />
        <Cell label="occurrence_count" value={promo.occurrence_count} />
        <Cell label="promotion_score" value={promo.promotion_score} />
        <Cell label="eligible_target" value={promo.eligible_target} />
      </div>
    </article>
  );
}

function Cell({ label, value }) {
  return (
    <div className="rounded-md border border-line bg-white px-2.5 py-1.5">
      <p className="text-[10px] font-medium uppercase tracking-wide text-zinc-400">{label}</p>
      <p className="mt-0.5 truncate font-mono text-xs font-semibold text-zinc-700">{compact(value, "—")}</p>
    </div>
  );
}

function renderStatusSummary(classification, t) {
  const kind = classification.kind || "unknown";
  const key = `promotions.status.${kind}`;
  const params = {
    fields: String(classification.field || ""),
    actual: String(classification.actual || ""),
    expected: String(classification.expected || ""),
  };
  const translated = t(key, params);
  if (translated && translated !== key) return translated;
  return classification.summary || kind;
}
