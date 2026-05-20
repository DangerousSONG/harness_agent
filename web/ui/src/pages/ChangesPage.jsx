import { ArrowRight, Eye } from "lucide-react";
import { useMemo } from "react";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { compact, formatDate, titleize } from "../lib/format";

const tabs = [
  { id: "proposed", label: "Proposed" },
  { id: "review-required", label: "Review Required" },
  { id: "applied", label: "Applied" },
  { id: "failed", label: "Failed" },
  { id: "archived", label: "Archived" },
];

export default function ChangesPage({ changes, activeTab = "proposed", onTabChange, onOpenReview, onOpenVersions }) {
  const visibleChanges = useMemo(
    () => (changes || []).filter((change) => changeMatchesTab(change, activeTab)),
    [changes, activeTab],
  );
  return (
    <section className="workbench-section">
      <div className="workbench-container">
        <div className="mb-6">
          <h1 className="page-title">Assets / Changes</h1>
          <p className="page-subtitle">
            Proposed and applied asset changes, including Create route outputs and Evolve route PROMO upgrades.
          </p>
        </div>

        <div className="mb-5 flex flex-wrap gap-2 rounded-lg border border-line bg-white p-1 shadow-hairline">
          {tabs.map((item) => (
            <button
              key={item.id}
              className={[
                "rounded-lg px-3 py-2 text-sm font-semibold transition",
                activeTab === item.id ? "bg-zinc-950 text-white" : "text-zinc-700 hover:bg-zinc-50",
              ].join(" ")}
              onClick={() => onTabChange?.(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {!visibleChanges?.length ? (
          <EmptyState title="No changes found." />
        ) : (
          <div className="section-panel overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full table-fixed divide-y divide-line text-sm">
                <colgroup>
                  <col className="w-[10rem]" />
                  <col className="w-[8rem]" />
                  <col className="w-[12rem]" />
                  <col className="w-[8rem]" />
                  <col className="w-[7rem]" />
                  <col className="w-[8rem]" />
                  <col className="w-[10rem]" />
                  <col className="w-[9rem]" />
                  <col className="w-[12rem]" />
                  <col />
                </colgroup>
                <thead className="bg-zinc-50/80 text-left text-[11px] font-semibold uppercase text-zinc-500">
                  <tr>
                    {[
                      "change_id",
                      "asset_type",
                      "asset_name",
                      "operation",
                      "risk",
                      "status",
                      "review_id",
                      "version_id",
                      "next_action",
                      "",
                    ].map((header) => (
                      <th className="px-4 py-3.5" key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-white">
                  {visibleChanges.map((change) => (
                    <tr key={`${change.source}:${change.change_id}`} className="align-top transition hover:bg-blue-50/35">
                      <td className="px-4 py-4"><span className="mono-badge break-all">{change.change_id}</span></td>
                      <td className="px-4 py-4 font-semibold text-zinc-700">{titleize(change.asset_type)}</td>
                      <td className="break-words px-4 py-4 font-semibold text-zinc-950">{compact(change.asset_name)}</td>
                      <td className="px-4 py-4">{titleize(change.operation)}</td>
                      <td className="px-4 py-4">{titleize(change.risk)}</td>
                      <td className="px-4 py-4"><StatusPill status={change.status} /></td>
                      <td className="px-4 py-4"><span className="mono-badge break-all">{compact(change.review_id)}</span></td>
                      <td className="px-4 py-4"><span className="mono-badge break-all">{compact(change.version_id)}</span></td>
                      <td className="break-words px-4 py-4 font-mono text-xs text-zinc-600">{compact(change.next_action)}</td>
                      <td className="px-4 py-4">
                        <div className="flex flex-wrap justify-end gap-2">
                          {change.review_id ? (
                            <button className="secondary-button px-3 py-1.5" onClick={() => onOpenReview?.(change.review_id)}>
                              <Eye className="h-4 w-4" />
                              Review
                            </button>
                          ) : null}
                          {change.version_id ? (
                            <button className="subprimary-button px-3 py-1.5" onClick={() => onOpenVersions?.()}>
                              <ArrowRight className="h-4 w-4" />
                              Version
                            </button>
                          ) : null}
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

function changeMatchesTab(change, tab) {
  const status = String(change?.status || "").toLowerCase();
  const nextAction = String(change?.next_action || "").toLowerCase();
  const hasReview = Boolean(change?.review_id);
  const hasVersion = Boolean(change?.version_id);
  if (tab === "applied") return hasVersion || ["applied", "completed"].includes(status);
  if (tab === "failed") return ["failed", "rejected", "error"].includes(status);
  if (tab === "archived") return ["archived", "legacy"].includes(status);
  if (tab === "review-required") {
    return !hasVersion && (hasReview || ["pending", "approved", "review_required"].includes(status) || nextAction.includes("review"));
  }
  return !hasVersion && !["failed", "rejected", "error", "archived", "legacy", "applied", "completed"].includes(status);
}
