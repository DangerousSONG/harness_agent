import { Boxes, GitPullRequest, Hammer, Play, Workflow, Wrench, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { api, getErrorMessage } from "../lib/api";
import { compact, formatDate, titleize } from "../lib/format";

const tabs = [
  { id: "skills", label: "Skills", icon: Boxes },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "workflows", label: "Workflows", icon: Workflow },
  { id: "memories", label: "Memories", icon: GitPullRequest },
  { id: "eval-cases", label: "Eval Cases", icon: Hammer },
];

export default function AssetsPage({
  skills,
  tools,
  reviews,
  changes,
  promotions,
  memories,
  knowledgeBases,
  versions,
  tab: controlledTab,
  onTabChange,
  onOpenReview,
  onOpenVersions,
}) {
  const [localTab, setLocalTab] = useState("skills");
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailTab, setDetailTab] = useState("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const tab = controlledTab || localTab;
  const setTab = onTabChange || setLocalTab;
  const evalCards = useMemo(
    () => (skills || []).filter((skill) => skill.has_eval_cases),
    [skills],
  );

  async function openAsset(assetType, asset) {
    setSelected({ assetType, asset });
    setDetail(null);
    setDetailTab("overview");
    setError("");
    if (!["skill", "tool"].includes(assetType)) return;
    setLoading(true);
    try {
      if (assetType === "tool") {
        const payload = await api.tool(asset.name);
        setDetail(payload.data);
      } else {
        const [skill, active, evalCases] = await Promise.allSettled([
          api.skill(asset.name),
          api.skillActive(asset.name),
          api.skillEvalCases(asset.name),
        ]);
        setDetail({
          ...(skill.status === "fulfilled" ? skill.value.data : asset),
          files: {
            active: active.status === "fulfilled"
              ? { path: active.value.data.path, exists: true, content: active.value.data.content, status: "present" }
              : { path: `skills/${asset.name}/SKILL.md`, exists: false, content: "", status: "missing" },
            eval_cases: evalCases.status === "fulfilled"
              ? { path: evalCases.value.data.path, exists: Boolean(evalCases.value.data.raw), content: evalCases.value.data.raw, status: evalCases.value.data.raw ? "present" : "missing" }
              : { path: `skills/${asset.name}/eval/cases.yaml`, exists: false, content: "", status: "missing" },
          },
        });
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const closeDetail = () => {
    setSelected(null);
    setDetail(null);
    setError("");
  };

  return (
    <section className="workbench-section">
      <div className="workbench-container">
        <div className="mb-6">
          <h1 className="page-title">Assets</h1>
          <p className="page-subtitle">
            Versionable agent assets grouped by Skills, Tools, Workflows, and Eval Cases.
          </p>
        </div>

        <div className="mb-5 flex flex-wrap gap-2 rounded-lg border border-line bg-white p-1 shadow-hairline">
          {tabs.map((item) => {
            const Icon = item.icon;
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                className={[
                  "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition",
                  active ? "bg-zinc-950 text-white" : "text-zinc-700 hover:bg-zinc-50",
                ].join(" ")}
                onClick={() => setTab(item.id)}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            );
          })}
        </div>

        {tab === "skills" ? (
          <AssetGrid
            items={skills}
            empty="No skills found."
            render={(skill) => (
              <AssetCard
                key={skill.name}
                title={skill.name}
                description={skill.description || "Workspace skill with active source and governance metadata."}
                status={assetStatus("skill", skill.name, reviews)}
                rows={assetRows({
                  assetType: "skill",
                  name: skill.name,
                  currentVersion: skill.latest_version || "active",
                  evalStatus: skill.has_eval_cases ? "present" : "missing",
                  latestChange: latestChange("skill", skill.name, changes),
                  pendingReview: pendingReview("skill", skill.name, reviews),
                })}
                metrics={[
                  ["Memory", skill.memory_count],
                  ["PROMO", skill.promotion_count],
                  ["Versions", (versions || []).filter((item) => item.skill === skill.name).length],
                ]}
                onClick={() => openAsset("skill", skill)}
              />
            )}
          />
        ) : null}

        {tab === "tools" ? (
          <AssetGrid
            items={tools}
            empty="No tools found."
            render={(tool) => (
              <AssetCard
                key={tool.name}
                title={tool.name}
                description={tool.description || "Workspace tool asset."}
                status={pendingReview("tool", tool.name, reviews) !== "-" ? assetStatus("tool", tool.name, reviews) : tool.executable ? "executable" : "not executable"}
                rows={assetRows({
                  assetType: "tool",
                  name: tool.name,
                  currentVersion: tool.status || "draft",
                  evalStatus: tool.eval_cases_count ? `${tool.eval_cases_count} cases` : "missing",
                  latestChange: latestChange("tool", tool.name, changes),
                  pendingReview: pendingReview("tool", tool.name, reviews),
                })}
                metrics={[
                  ["Provider", compact(tool.provider_requirements, "none")],
                  ["Handler", tool.handler_available ? "yes" : "no"],
                  ["Executable", tool.executable ? "yes" : "no"],
                ]}
                onClick={() => openAsset("tool", tool)}
              />
            )}
          />
        ) : null}

        {tab === "workflows" ? (
          <AssetGrid
            items={promotions}
            empty="No workflow/PROMO sources found."
            render={(promo) => (
              <AssetCard
                key={promo.promo_id}
                title={promo.promo_id}
                description={promo.proposed_change_summary || promo.reason || "PROMO-backed evolution workflow."}
                status={promo.promotion_decision || promo.status || "proposed"}
                rows={[
                  ["Target asset", promo.target_skill],
                  ["Source memory", compact(promo.source_memory_ids)],
                  ["Linked reviews", compact(promo.linked_reviews)],
                  ["Linked version", compact(promo.linked_version)],
                  ["Next action", promo.requires_regeneration ? "regenerate" : promo.linked_version ? "view version" : "create review"],
                ]}
                metrics={[
                  ["Score", promo.promotion_score],
                  ["Eligible", promo.eligible_target],
                  ["Schema", promo.schema_status],
                ]}
                onClick={() => openAsset("workflow", promo)}
              />
            )}
          />
        ) : null}

        {tab === "memories" ? (
          <AssetGrid
            items={memories}
            empty="No memories found."
            render={(memory) => (
              <AssetCard
                key={memory.memory_id || `${memory.skill}-${memory.type}-${memory.title}`}
                title={memory.title || memory.memory_id || "Memory"}
                description={memory.content || memory.reason || "Recorded asset memory."}
                status={memory.status || memory.type || "recorded"}
                rows={[
                  ["Skill", memory.skill],
                  ["Type", memory.type],
                  ["Memory id", memory.memory_id],
                  ["Updated", formatDate(memory.updated_at || memory.created_at)],
                  ["PROMO", memory.linked_promo_id],
                ]}
                metrics={[
                  ["Priority", memory.priority],
                  ["Occurrences", memory.occurrence_count],
                  ["Review", memory.needs_attribution_review ? "needed" : "none"],
                ]}
                onClick={() => openAsset("memory", memory)}
              />
            )}
          />
        ) : null}

        {tab === "eval-cases" ? (
          <AssetGrid
            items={evalCards}
            empty="No eval cases found."
            render={(skill) => (
              <AssetCard
                key={`${skill.name}-eval`}
                title={`${skill.name} eval cases`}
                description="Regression and acceptance cases connected to this skill asset."
                status={skill.has_eval_cases ? "present" : "missing"}
                rows={[
                  ["Active source", `skills/${skill.name}/eval/cases.yaml`],
                  ["Latest version", skill.latest_version || "No snapshot"],
                  ["Pending review", pendingReview("skill", skill.name, reviews)],
                ]}
                metrics={[
                  ["Asset", skill.name],
                  ["Versions", (versions || []).filter((item) => item.skill === skill.name).length],
                  ["Changes", (changes || []).filter((item) => item.asset_name === skill.name).length],
                ]}
                onClick={() => openAsset("skill", skill)}
              />
            )}
          />
        ) : null}

        {selected ? (
          <AssetDetailModal
            selected={selected}
            detail={detail || selected.asset}
            loading={loading}
            error={error}
            tab={detailTab}
            setTab={setDetailTab}
            reviews={reviews}
            changes={changes}
            versions={versions}
            memories={memories}
            knowledgeBases={knowledgeBases}
            onClose={closeDetail}
            onOpenReview={onOpenReview}
            onOpenVersions={onOpenVersions}
          />
        ) : null}
      </div>
    </section>
  );
}

function AssetGrid({ items, empty, render }) {
  if (!items?.length) return <EmptyState title={empty} />;
  return <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">{items.map(render)}</div>;
}

function AssetCard({ title, description, status, rows, metrics, onClick }) {
  return (
    <article className="section-panel cursor-pointer p-4 transition hover:border-zinc-300" onClick={onClick}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-zinc-950">{title}</h2>
          {description ? <p className="mt-1 line-clamp-2 text-sm leading-6 text-zinc-500">{description}</p> : null}
        </div>
        <StatusPill status={status || "draft"} />
      </div>
      {metrics?.length ? (
        <div className="mt-4 grid grid-cols-3 gap-2">
          {metrics.map(([label, value]) => (
            <div className="rounded-lg border border-line bg-zinc-50 px-3 py-2" key={label}>
              <p className="text-[11px] font-medium text-zinc-500">{label}</p>
              <p className="mt-1 truncate text-sm font-semibold text-zinc-950">{compact(value, "0")}</p>
            </div>
          ))}
        </div>
      ) : null}
      <div className="mt-4 space-y-2.5 border-t border-line pt-4">
        {rows.map(([label, value]) => (
          <Metric label={label} value={value} key={label} />
        ))}
      </div>
    </article>
  );
}

function AssetDetailModal({
  selected,
  detail,
  loading,
  error,
  tab,
  setTab,
  reviews,
  changes,
  versions,
  memories,
  onClose,
  onOpenReview,
  onOpenVersions,
}) {
  const assetType = selected.assetType;
  const name = selected.asset.name || selected.asset.target_skill || selected.asset.promo_id;
  const scopedReviews = filterByAsset(reviews, assetType, name);
  const scopedChanges = filterByAsset(changes, assetType, name);
  const scopedVersions = assetType === "skill" ? (versions || []).filter((item) => item.skill === name) : [];
  const scopedMemories = assetType === "skill" ? (memories || []).filter((item) => item.skill === name) : [];
  const tabs = ["overview", "files", "changes", "reviews", "versions", "eval", "memory"];
  const [toolTestInput, setToolTestInput] = useState("");
  const [toolTestResult, setToolTestResult] = useState(null);
  const [toolTestError, setToolTestError] = useState("");

  useEffect(() => {
    if (assetType !== "tool") return;
    setToolTestInput(JSON.stringify(defaultToolTestInputs(detail || selected.asset), null, 2));
    setToolTestResult(null);
    setToolTestError("");
  }, [assetType, name, detail?.name]);

  async function runToolTest() {
    setToolTestError("");
    setToolTestResult(null);
    let inputs = {};
    try {
      inputs = toolTestInput.trim() ? JSON.parse(toolTestInput) : {};
    } catch {
      setToolTestError("Invalid JSON input.");
      return;
    }
    try {
      const payload = await api.runTool(name, inputs);
      setToolTestResult(payload);
    } catch (err) {
      setToolTestError(getErrorMessage(err));
      setToolTestResult(err.payload || null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/30 p-4">
      <div className="max-h-[88vh] w-full max-w-6xl overflow-hidden rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <p className="muted-label">{titleize(assetType)} Asset</p>
            <h2 className="mt-1 truncate text-lg font-semibold text-zinc-950">{name}</h2>
            <p className="mt-1 text-sm text-zinc-500">{detail.description || selected.asset.description || selected.asset.reason || "SafeHarness asset detail."}</p>
          </div>
          <button className="rounded-md p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="border-b border-line px-5 pt-3">
          <div className="flex flex-wrap gap-2">
            {tabs.map((id) => (
              <button
                key={id}
                className={[
                  "rounded-md px-3 py-2 text-sm font-semibold",
                  tab === id ? "bg-zinc-950 text-white" : "text-zinc-600 hover:bg-zinc-50",
                ].join(" ")}
                onClick={() => setTab(id)}
              >
                {titleize(id)}
              </button>
            ))}
          </div>
        </div>
        <div className="max-h-[62vh] overflow-auto p-5">
          {loading ? <p className="text-sm text-zinc-500">Loading asset details...</p> : null}
          {error ? <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">{error}</p> : null}
          {!loading && tab === "overview" ? (
            <OverviewTab
              detail={detail}
              selected={selected}
              scopedChanges={scopedChanges}
              scopedReviews={scopedReviews}
              scopedVersions={scopedVersions}
              toolTestInput={toolTestInput}
              setToolTestInput={setToolTestInput}
              toolTestResult={toolTestResult}
              toolTestError={toolTestError}
              onRunToolTest={runToolTest}
            />
          ) : null}
          {!loading && tab === "files" ? <FilesTab assetType={assetType} detail={detail} /> : null}
          {!loading && tab === "changes" ? <CompactTable items={scopedChanges} empty="No changes for this asset." kind="changes" /> : null}
          {!loading && tab === "reviews" ? <ReviewList reviews={scopedReviews} onOpenReview={onOpenReview} /> : null}
          {!loading && tab === "versions" ? <VersionList versions={scopedVersions} onOpenVersions={onOpenVersions} /> : null}
          {!loading && tab === "eval" ? <EvalTab assetType={assetType} detail={detail} selected={selected} /> : null}
          {!loading && tab === "memory" ? <MemoryTab assetType={assetType} detail={detail} memories={scopedMemories} /> : null}
        </div>
      </div>
    </div>
  );
}

function OverviewTab({
  detail,
  selected,
  scopedChanges,
  scopedReviews,
  scopedVersions,
  toolTestInput,
  setToolTestInput,
  toolTestResult,
  toolTestError,
  onRunToolTest,
}) {
  const isTool = selected.assetType === "tool";
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-3">
        <Metric label="Asset type" value={selected.assetType} />
        <Metric label="Asset name" value={selected.asset.name || selected.asset.promo_id} />
        <Metric label="Current version" value={detail.latest_version || detail.active_version || detail.status || selected.asset.linked_version || "draft"} />
        <Metric label="Status" value={detail.status || selected.asset.status || selected.asset.promotion_decision || "active"} />
        {isTool ? <Metric label="Asset exists" value={detail.asset_exists ? "yes" : "no"} /> : null}
        {isTool ? <Metric label="Handler" value={detail.handler_available ? "available" : "missing"} /> : null}
        {isTool ? <Metric label="Provider" value={detail.provider_configured ? "configured" : "missing"} /> : null}
        {isTool ? <Metric label="Executable" value={detail.executable ? "yes" : "no"} /> : null}
        {isTool ? <Metric label="Provider reqs" value={compact(detail.provider_requirements, "none")} /> : null}
        {isTool ? <Metric label="Missing" value={compact(detail.missing, "none")} /> : null}
        <Metric label="Latest change" value={scopedChanges[0]?.change_id} />
        <Metric label="Pending review" value={scopedReviews.find((review) => ["pending", "approved"].includes(review.status))?.review_id} />
      </div>
      <div className="space-y-4 self-start">
        <div className="grid grid-cols-3 gap-2">
          <SmallMetric label="Changes" value={scopedChanges.length} />
          <SmallMetric label="Reviews" value={scopedReviews.length} />
          <SmallMetric label="Versions" value={scopedVersions.length} />
        </div>
        {isTool ? (
          <div className="rounded-lg border border-line p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-zinc-950">Test tool</h3>
              <button className="subprimary-button px-3 py-1.5" onClick={onRunToolTest}>
                <Play className="h-4 w-4" />
                Run
              </button>
            </div>
            <textarea
              className="min-h-32 w-full resize-y rounded-md border border-line bg-zinc-50 p-3 font-mono text-xs leading-5 text-zinc-800 outline-none focus:border-zinc-400"
              value={toolTestInput}
              onChange={(event) => setToolTestInput(event.target.value)}
              spellCheck={false}
            />
            {toolTestError ? <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">{toolTestError}</p> : null}
            {toolTestResult ? <DetailBlock title="Result" value={toolTestResult} /> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function FilesTab({ assetType, detail }) {
  if (assetType === "tool") {
    const files = detail.files || {};
    return (
      <div className="space-y-4">
        <FilePanel file={files.schema} fallbackPath={detail.schema_path} />
        <FilePanel file={files.readme} fallbackPath={detail.readme_path} />
        <FilePanel file={files.eval_cases} fallbackPath={detail.eval_cases_path} />
      </div>
    );
  }
  if (assetType === "skill") {
    const files = detail.files || {};
    return (
      <div className="space-y-4">
        <FilePanel file={files.active} fallbackPath={detail.active_file} />
        <FilePanel file={files.eval_cases} fallbackPath={`skills/${detail.name}/eval/cases.yaml`} />
      </div>
    );
  }
  return <EmptyState title="No file-backed view for this asset yet." />;
}

function EvalTab({ assetType, detail, selected }) {
  if (assetType === "tool") return <FilePanel file={detail.files?.eval_cases} fallbackPath={detail.eval_cases_path} />;
  if (assetType === "skill") return <FilePanel file={detail.files?.eval_cases} fallbackPath={`skills/${selected.asset.name}/eval/cases.yaml`} />;
  return <DetailBlock title="Workflow eval status" value={selected.asset.schema_status || "waiting"} />;
}

function MemoryTab({ assetType, detail, memories }) {
  if (assetType === "skill") {
    return (
      <div className="space-y-4">
        <DetailBlock title="Memory summary" value={detail.memory || {}} />
        <CompactTable items={memories} empty="No memory records for this asset." kind="memory" />
      </div>
    );
  }
  return <DetailBlock title="Memory / PROMO source" value={detail.source_memory_ids || detail.linked_promotions || []} />;
}

function ReviewList({ reviews, onOpenReview }) {
  if (!reviews?.length) return <EmptyState title="No reviews for this asset." />;
  return (
    <div className="space-y-3">
      {reviews.map((review) => (
        <div key={review.review_id} className="rounded-lg border border-line p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <span className="mono-badge">{review.review_id}</span>
              <p className="mt-2 text-sm font-semibold text-zinc-950">{titleize(review.type)}</p>
              <p className="mt-1 text-xs text-zinc-500">{compact(review.reason)}</p>
            </div>
            <div className="flex items-center gap-2">
              <StatusPill status={review.status} />
              <button className="secondary-button px-3 py-1.5" onClick={() => onOpenReview?.(review.review_id)}>
                <GitPullRequest className="h-4 w-4" />
                Open
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function VersionList({ versions, onOpenVersions }) {
  if (!versions?.length) return <EmptyState title="No versions for this asset yet." />;
  return (
    <div className="space-y-3">
      {versions.map((version) => (
        <div key={`${version.skill}:${version.version}`} className="rounded-lg border border-line p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className="mono-badge">{version.version}</span>
              <p className="mt-2 text-sm font-semibold text-zinc-950">{version.skill}</p>
              <p className="mt-1 text-xs text-zinc-500">{formatDate(version.created_at)}</p>
            </div>
            <button className="subprimary-button px-3 py-1.5" onClick={onOpenVersions}>Open Versions</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function CompactTable({ items, empty, kind }) {
  if (!items?.length) return <EmptyState title={empty} />;
  return (
    <div className="section-panel overflow-hidden shadow-none">
      <div className="divide-y divide-line">
        {items.map((item, index) => (
          <div className="grid gap-3 px-4 py-3 md:grid-cols-[10rem_1fr_8rem_8rem]" key={item.change_id || item.memory_id || index}>
            <span className="mono-badge w-fit">{item.change_id || item.memory_id || item.type}</span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-zinc-950">{item.asset_name || item.title || item.reason || "-"}</span>
              <span className="mt-1 block text-xs text-zinc-500">{kind === "changes" ? `${titleize(item.asset_type)} · ${titleize(item.operation)}` : titleize(item.type)}</span>
            </span>
            <StatusPill status={item.status || item.promotion_decision || "recorded"} />
            <span className="text-xs font-semibold text-zinc-500">{formatDate(item.created_at || item.updated_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DetailBlock({ title, value }) {
  const content = Array.isArray(value)
    ? value.join("\n")
    : typeof value === "object" && value
      ? JSON.stringify(value, null, 2)
      : compact(value);
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase text-zinc-500">{title}</h3>
      <pre className="max-h-56 overflow-auto rounded-md border border-line bg-zinc-50 p-3 text-xs leading-5 text-zinc-800">{content || "missing"}</pre>
    </div>
  );
}

function FilePanel({ file, fallbackPath }) {
  const path = file?.path || fallbackPath || "missing";
  const exists = file?.exists;
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="break-all text-sm font-semibold text-zinc-700">{path}</p>
        <span className="rounded-md border border-line px-2 py-1 text-xs font-semibold text-zinc-500">{exists ? "present" : "missing"}</span>
      </div>
      {exists ? (
        <pre className="max-h-[38vh] overflow-auto rounded-md border border-line bg-zinc-50 p-4 text-xs leading-5 text-zinc-800">{file.content}</pre>
      ) : (
        <div className="rounded-md border border-dashed border-line bg-zinc-50 p-4 text-sm font-semibold text-zinc-500">missing</div>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3 text-sm">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <span className="min-w-0 break-words text-right font-semibold text-zinc-900">{compact(value)}</span>
    </div>
  );
}

function SmallMetric({ label, value }) {
  return (
    <div className="rounded-lg border border-line bg-zinc-50 px-3 py-2">
      <p className="text-[11px] font-medium text-zinc-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-zinc-950">{compact(value, "0")}</p>
    </div>
  );
}

function defaultToolTestInputs(tool) {
  if (tool?.name === "weather_query" || tool?.capability === "weather_query") {
    return { city: "上海", date: "today", units: "metric", language: "zh-CN" };
  }
  const inputs = tool?.inputs || {};
  if (inputs.city) return { city: "上海", date: "today", units: "metric", language: "zh-CN" };
  if (inputs.query) return { query: "OpenAI API documentation", max_results: 3, language: "zh-CN" };
  if (inputs.path) return { path: "docs/README.md" };
  if (inputs.command) return { command: "git status --short" };
  return {};
}

function assetRows({ assetType, name, currentVersion, evalStatus, latestChange, pendingReview }) {
  return [
    ["Current version", currentVersion],
    ["Status", assetType === "tool" ? "tool asset" : "active asset"],
    ["Latest change", latestChange],
    ["Pending review", pendingReview],
    ["Eval status", evalStatus],
    ["Path", assetType === "tool" ? `tools/${name}/` : `skills/${name}/`],
  ];
}

function latestChange(assetType, name, changes) {
  return filterByAsset(changes, assetType, name)[0]?.change_id || "-";
}

function pendingReview(assetType, name, reviews) {
  return filterByAsset(reviews, assetType, name).find((review) => ["pending", "approved"].includes(review.status))?.review_id || "-";
}

function assetStatus(assetType, name, reviews) {
  const review = filterByAsset(reviews, assetType, name).find((item) => ["pending", "approved"].includes(item.status));
  return review?.status || "active";
}

function filterByAsset(items, assetType, name) {
  return (items || []).filter((item) => {
    if (item.asset_type && item.asset_type !== assetType) return false;
    if (item.asset_name) return item.asset_name === name;
    if (item.target_skill) return item.target_skill === name;
    if (item.metadata?.tool_name) return item.metadata.tool_name === name;
    return (item.target_files || []).some((path) => String(path).includes(`/${name}/`) || String(path).includes(`\\${name}\\`));
  });
}
