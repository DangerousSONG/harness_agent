import { Boxes, GitPullRequest, Layers3, ShieldCheck, Workflow } from "lucide-react";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { compact, formatDate, titleize } from "../lib/format";

export default function WorkspacePage({
  dashboard,
  skills,
  tools,
  reviews,
  changes,
  versions,
  promotions,
  onNavigate,
}) {
  const assetCounts = dashboard?.asset_counts || {
    skills: skills?.length || 0,
    tools: tools?.length || 0,
    workflows: promotions?.length || 0,
    eval_cases: skills?.filter((skill) => skill.has_eval_cases).length || 0,
  };
  const pendingReviews = reviews?.filter((review) => ["pending", "approved"].includes(review.status)) || [];
  const latestChanges = (changes || []).slice(0, 6);
  const latestVersions = dashboard?.latest_versions?.length ? dashboard.latest_versions : (versions || []).slice(-5).reverse();

  return (
    <section className="workbench-section">
      <div className="workbench-container space-y-5">
        <div>
          <h1 className="page-title">Workspace Overview</h1>
          <p className="page-subtitle">
            Asset → Change → Review → Apply → Version → Rollback, scoped to this local SafeHarness workspace.
          </p>
        </div>

        <section className="section-panel p-5">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(20rem,0.8fr)]">
            <div>
              <p className="muted-label">Workspace root</p>
              <p className="mt-2 break-all font-mono text-sm font-semibold text-zinc-900">{dashboard?.workspace_root || "-"}</p>
              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <StatCard icon={Boxes} label="Skills" value={assetCounts.skills} />
                <StatCard icon={ShieldCheck} label="Tools" value={assetCounts.tools} />
                <StatCard icon={Workflow} label="Workflows" value={assetCounts.workflows} />
                <StatCard icon={Layers3} label="Eval assets" value={assetCounts.eval_cases} />
              </div>
            </div>
            <div className="rounded-lg border border-line bg-zinc-50 p-4">
              <p className="muted-label">Open work</p>
              <div className="mt-4 grid grid-cols-3 gap-2">
                <MiniMetric label="Pending changes" value={dashboard?.pending_changes ?? latestChanges.length} />
                <MiniMetric label="Pending reviews" value={pendingReviews.length} />
                <MiniMetric label="Versions" value={dashboard?.applied_skill_versions ?? versions?.length ?? 0} />
              </div>
              <button className="secondary-button mt-5 w-full" onClick={() => onNavigate?.("changes")}>
                <GitPullRequest className="h-4 w-4" />
                Review Change Queue
              </button>
            </div>
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(24rem,0.9fr)]">
          <section className="section-panel overflow-hidden">
            <PanelHeader title="Latest Changes" action="Open Changes" onAction={() => onNavigate?.("changes")} />
            {!latestChanges.length ? (
              <div className="p-5"><EmptyState title="No changes recorded yet." /></div>
            ) : (
              <div className="divide-y divide-line">
                {latestChanges.map((change) => (
                  <button
                    key={change.change_id}
                    className="grid w-full gap-3 px-5 py-4 text-left transition hover:bg-zinc-50 md:grid-cols-[10rem_1fr_8rem_8rem]"
                    onClick={() => onNavigate?.("changes")}
                  >
                    <span className="mono-badge w-fit">{change.change_id}</span>
                    <span className="min-w-0">
                      <span className="block font-semibold text-zinc-950">{change.asset_name || "-"}</span>
                      <span className="mt-1 block text-xs text-zinc-500">{titleize(change.asset_type)} · {titleize(change.operation)}</span>
                    </span>
                    <StatusPill status={change.status || "waiting"} />
                    <span className="text-xs font-semibold text-zinc-500">{formatDate(change.created_at)}</span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="section-panel overflow-hidden">
            <PanelHeader title="Latest Versions" action="Open Versions" onAction={() => onNavigate?.("versions")} />
            {!latestVersions.length ? (
              <div className="p-5"><EmptyState title="No versions recorded yet." /></div>
            ) : (
              <div className="divide-y divide-line">
                {latestVersions.map((version) => (
                  <div key={`${version.skill}:${version.version}`} className="px-5 py-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-zinc-950">{version.skill}</p>
                        <p className="mt-1 text-xs text-zinc-500">{formatDate(version.created_at)}</p>
                      </div>
                      <span className="mono-badge">{version.version}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <MiniMetric label="Review" value={compact(version.skill_review_id)} />
                      <MiniMetric label="PROMO" value={compact(version.promotion_id)} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </section>
  );
}

function StatCard({ icon: Icon, label, value }) {
  return (
    <div className="rounded-lg border border-line bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-zinc-600">{label}</p>
        <Icon className="h-4 w-4 text-zinc-400" />
      </div>
      <p className="mt-3 text-2xl font-semibold text-zinc-950">{value ?? 0}</p>
    </div>
  );
}

function MiniMetric({ label, value }) {
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2">
      <p className="text-[11px] font-medium text-zinc-500">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-zinc-950">{compact(value, "0")}</p>
    </div>
  );
}

function PanelHeader({ title, action, onAction }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
      <h2 className="text-base font-semibold text-zinc-950">{title}</h2>
      <button className="secondary-button px-3 py-1.5" onClick={onAction}>{action}</button>
    </div>
  );
}
