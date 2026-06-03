import { useMemo, useState } from "react";
import { ShieldCheck } from "lucide-react";
import StatusPill from "../components/StatusPill";
import { useTranslate } from "../lib/i18n.jsx";
import { EvolutionTimeline } from "./EvolutionPage";
import PromotionsPage from "./PromotionsPage";
import ReviewsPage from "./ReviewsPage";
import RunsPage from "./RunsPage";
import SideChannelPage from "./SideChannelPage";
import VersionsPage from "./VersionsPage";

const TABS = [
  { id: "promotions", labelKey: "governance.tab.promotions" },
  { id: "reviews", labelKey: "governance.tab.reviews" },
  { id: "versions", labelKey: "governance.tab.versions" },
  { id: "side-channel", labelKey: "governance.tab.side_channel" },
  { id: "runs", labelKey: "governance.tab.runs" },
];

const REVIEW_FILTERS = [
  { id: "all", labelKey: "governance.review_filter.all" },
  { id: "rollback", labelKey: "governance.review_filter.rollback" },
  { id: "high", labelKey: "governance.review_filter.high_severity" },
];

export default function GovernancePage({
  activeTab,
  onTabChange,
  reviews,
  actionProps,
  versions,
  versionDetail,
  selectedVersionKey,
  onSelectVersion,
  onCreateRollback,
  busyVersionKey,
  changes,
  promotions,
  busyPromoId,
  onViewPromotion,
  onEvolvePromotion,
  onRegeneratePromotion,
  onFastTrackPromotion,
  selectedPromoId,
  currentPromotion,
  evolutionState,
  onContinueEvolution,
}) {
  const t = useTranslate();
  const [reviewFilter, setReviewFilter] = useState("all");

  const tabCounts = {
    promotions: (promotions || []).length,
    reviews: (reviews || []).filter((item) => ["pending", "approved"].includes(item.status)).length,
    versions: (versions || []).length,
  };

  const metrics = useMemo(() => [
    {
      label: t("governance.metric.open_high"),
      value: (reviews || []).filter(
        (review) =>
          ["high", "critical"].includes(String(review.severity || "").toLowerCase()) &&
          ["pending", "approved"].includes(review.status),
      ).length,
    },
    {
      label: t("governance.metric.failed_changes"),
      value: (changes || []).filter((change) =>
        ["failed", "rejected", "error"].includes(String(change.status || "").toLowerCase()),
      ).length,
    },
    {
      label: t("governance.metric.review_gated"),
      value: (changes || []).filter((change) => Boolean(change.review_id)).length,
    },
  ], [reviews, changes, t]);

  const filteredReviews = useMemo(() => {
    if (reviewFilter === "rollback") {
      return (reviews || []).filter((review) => {
        const text = JSON.stringify(review).toLowerCase();
        return text.includes("rollback");
      });
    }
    if (reviewFilter === "high") {
      return (reviews || []).filter((review) =>
        ["high", "critical"].includes(String(review.severity || "").toLowerCase()),
      );
    }
    return reviews;
  }, [reviews, reviewFilter]);

  return (
    <section className="workbench-section">
      <div className="workbench-container">
        <div className="mb-5">
          <h1 className="page-title">{t("governance.title.self_evolution")}</h1>
          <p className="page-subtitle">{t("governance.subtitle.self_evolution")}</p>
        </div>

        <div className="mb-5 grid gap-3 sm:grid-cols-3">
          {metrics.map((item) => (
            <section className="section-panel flex items-center justify-between p-4" key={item.label}>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-zinc-500">{item.label}</p>
                <p className="mt-1 text-2xl font-semibold text-zinc-950">{item.value}</p>
              </div>
              <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-zinc-50 text-zinc-700">
                <ShieldCheck className="h-4 w-4" />
              </span>
            </section>
          ))}
        </div>

        <div className="mb-5 flex flex-wrap gap-2 rounded-lg border border-line bg-white p-1 shadow-hairline">
          {TABS.map((item) => {
            const count = tabCounts[item.id];
            return (
              <button
                key={item.id}
                className={[
                  "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition",
                  activeTab === item.id ? "bg-zinc-950 text-white" : "text-zinc-700 hover:bg-zinc-50",
                ].join(" ")}
                onClick={() => onTabChange?.(item.id)}
              >
                {t(item.labelKey)}
                {typeof count === "number" && count > 0 ? (
                  <span
                    className={[
                      "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                      activeTab === item.id ? "bg-white/20 text-white" : "bg-zinc-100 text-zinc-600",
                    ].join(" ")}
                  >
                    {count}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      {activeTab === "promotions" ? (
        <div className="workbench-container space-y-3 px-6">
          {selectedPromoId && currentPromotion ? (
            <EvolutionTimeline
              promoId={selectedPromoId}
              targetSkill={evolutionState?.target_skill || currentPromotion?.target_skill}
              evolutionState={evolutionState}
              currentPromotion={currentPromotion}
              onContinue={onContinueEvolution}
              busyPromoId={busyPromoId}
            />
          ) : null}
          <PromotionsPage
            promotions={promotions}
            busyPromoId={busyPromoId}
            onView={onViewPromotion}
            onEvolve={onEvolvePromotion}
            onRegenerate={onRegeneratePromotion}
            onFastTrack={onFastTrackPromotion}
          />
        </div>
      ) : null}

      {activeTab === "reviews" ? (
        <div className="workbench-container px-6">
          <div className="mb-3 inline-flex gap-1 rounded-lg border border-line bg-white p-1 shadow-hairline">
            {REVIEW_FILTERS.map((filter) => (
              <button
                key={filter.id}
                className={[
                  "rounded-md px-3 py-1.5 text-xs font-semibold transition",
                  reviewFilter === filter.id
                    ? "bg-zinc-950 text-white"
                    : "text-zinc-600 hover:bg-zinc-50",
                ].join(" ")}
                onClick={() => setReviewFilter(filter.id)}
              >
                {t(filter.labelKey)}
              </button>
            ))}
          </div>
          <ReviewsPage reviews={filteredReviews} actionProps={actionProps} embedded />
        </div>
      ) : null}

      {activeTab === "versions" ? (
        <VersionsPage
          versions={versions}
          versionDetail={versionDetail}
          selectedVersionKey={selectedVersionKey}
          onSelectVersion={onSelectVersion}
          onCreateRollback={onCreateRollback}
          busyVersionKey={busyVersionKey}
          embedded
        />
      ) : null}

      {activeTab === "side-channel" ? (
        <div className="workbench-container">
          <SideChannelPage />
        </div>
      ) : null}

      {activeTab === "runs" ? (
        <div className="workbench-container">
          <RunsPage />
        </div>
      ) : null}
    </section>
  );
}
