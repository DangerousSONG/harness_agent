import { ShieldCheck } from "lucide-react";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { compact, formatDate, titleize } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";
import ReviewsPage from "./ReviewsPage";
import VersionsPage from "./VersionsPage";

const TABS = [
  { id: "reviews", labelKey: "governance.tab.reviews" },
  { id: "versions", labelKey: "governance.tab.versions" },
  { id: "rollbacks", labelKey: "governance.tab.rollbacks" },
  { id: "safety-checks", labelKey: "governance.tab.safety_checks" },
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
}) {
  const t = useTranslate();
  return (
    <section className="workbench-section">
      <div className="workbench-container">
        <div className="mb-6">
          <h1 className="page-title">{t("governance.title")}</h1>
          <p className="page-subtitle">{t("governance.subtitle")}</p>
        </div>

        <div className="mb-5 flex flex-wrap gap-2 rounded-lg border border-line bg-white p-1 shadow-hairline">
          {TABS.map((item) => (
            <button
              key={item.id}
              className={[
                "rounded-lg px-3 py-2 text-sm font-semibold transition",
                activeTab === item.id ? "bg-zinc-950 text-white" : "text-zinc-700 hover:bg-zinc-50",
              ].join(" ")}
              onClick={() => onTabChange?.(item.id)}
            >
              {t(item.labelKey)}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "reviews" ? <ReviewsPage reviews={reviews} actionProps={actionProps} embedded /> : null}
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
      {activeTab === "rollbacks" ? <Rollbacks reviews={reviews} t={t} /> : null}
      {activeTab === "safety-checks" ? <SafetyChecks reviews={reviews} changes={changes} t={t} /> : null}
    </section>
  );
}

function Rollbacks({ reviews, t }) {
  const rollbackReviews = (reviews || []).filter((review) => {
    const text = JSON.stringify(review).toLowerCase();
    return text.includes("rollback");
  });
  if (!rollbackReviews.length) {
    return (
      <div className="workbench-container">
        <EmptyState title={t("governance.empty.rollbacks")} />
      </div>
    );
  }
  return (
    <div className="workbench-container">
      <div className="section-panel overflow-hidden">
        <div className="divide-y divide-line">
          {rollbackReviews.map((review) => (
            <div className="grid gap-3 px-5 py-4 md:grid-cols-[10rem_1fr_8rem_8rem]" key={review.review_id}>
              <span className="mono-badge w-fit">{review.review_id}</span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-zinc-950">{titleize(review.type)}</span>
                <span className="mt-1 block text-xs text-zinc-500">{compact(review.reason)}</span>
              </span>
              <StatusPill status={review.status} />
              <span className="text-xs font-semibold text-zinc-500">{formatDate(review.created_at)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SafetyChecks({ reviews, changes, t }) {
  const items = [
    {
      label: t("governance.metric.open_high"),
      value: (reviews || []).filter((review) => ["high", "critical"].includes(String(review.severity || "").toLowerCase()) && ["pending", "approved"].includes(review.status)).length,
      status: "tracked",
    },
    {
      label: t("governance.metric.failed_changes"),
      value: (changes || []).filter((change) => ["failed", "rejected", "error"].includes(String(change.status || "").toLowerCase())).length,
      status: "tracked",
    },
    {
      label: t("governance.metric.review_gated"),
      value: (changes || []).filter((change) => Boolean(change.review_id)).length,
      status: "tracked",
    },
  ];
  return (
    <div className="workbench-container">
      <div className="grid gap-4 lg:grid-cols-3">
        {items.map((item) => (
          <section className="section-panel p-5" key={item.label}>
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-zinc-50 text-zinc-700">
                <ShieldCheck className="h-4 w-4" />
              </span>
              <h2 className="text-sm font-semibold text-zinc-950">{item.label}</h2>
            </div>
            <p className="mt-4 text-3xl font-semibold text-zinc-950">{item.value}</p>
            <div className="mt-3">
              <StatusPill status={item.status} />
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
