import { Boxes, Database, Hammer, Library, MemoryStick, Wrench, X } from "lucide-react";
import { useMemo, useState } from "react";
import EmptyState from "../components/EmptyState";
import { api, getErrorMessage } from "../lib/api";
import { compact } from "../lib/format";

const tabs = [
  { id: "skills", label: "Skills", icon: Boxes },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "memories", label: "Memories", icon: MemoryStick },
  { id: "knowledge", label: "Knowledge Bases", icon: Library },
  { id: "eval", label: "Eval Cases", icon: Hammer },
  { id: "datasets", label: "Datasets", icon: Database },
];

export default function AssetsPage({ skills, tools, memories, knowledgeBases, versions, tab: controlledTab, onTabChange }) {
  const [localTab, setLocalTab] = useState("skills");
  const tab = controlledTab || localTab;
  const setTab = onTabChange || setLocalTab;
  const evalCards = useMemo(
    () => (skills || []).filter((skill) => skill.has_eval_cases),
    [skills],
  );

  return (
    <section className="workbench-section">
      <div className="workbench-container">
        <div className="mb-6">
          <h1 className="page-title">Assets</h1>
          <p className="page-subtitle">
            A read-only entry point for local Agent assets.
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

        {tab === "skills" ? <SkillGrid skills={skills} versions={versions} /> : null}
        {tab === "tools" ? <ToolGrid tools={tools} /> : null}
        {tab === "memories" ? <MemoryGrid memories={memories} /> : null}
        {tab === "knowledge" ? (
          <SimpleList
            items={knowledgeBases}
            empty="This asset type is not implemented yet."
            render={(item) => (
              <AssetCard title={item.kb_id} rows={[["Path", item.path], ["Updated", item.updated_at]]} />
            )}
          />
        ) : null}
        {tab === "eval" ? (
          <SimpleList
            items={evalCards}
            empty="This asset type is not implemented yet."
            render={(skill) => (
              <AssetCard
                title={`${skill.name} eval cases`}
                rows={[["Active source", `skills/${skill.name}/eval/cases.yaml`], ["Latest snapshot", skill.latest_version || "No snapshot"]]}
              />
            )}
          />
        ) : null}
        {tab === "datasets" ? (
          <EmptyState title="This asset type is not implemented yet." detail="TODO: connect a datasets endpoint when the backend exposes one." />
        ) : null}
      </div>
    </section>
  );
}

function SkillGrid({ skills, versions }) {
  if (!skills?.length) return <EmptyState title="No skills found." />;
  return (
    <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
      {skills.map((skill) => (
        <AssetCard
          key={skill.name}
          title={skill.name}
          description={skill.description || "Workspace skill with active source and governance metadata."}
          rows={[
            ["Active source", skill.path || `skills/${skill.name}/SKILL.md`],
            ["Latest snapshot", skill.latest_version || "No snapshot"],
          ]}
          metrics={[
            ["Memory", skill.memory_count],
            ["Promotion", skill.promotion_count],
            ["Version", (versions || []).filter((item) => item.skill === skill.name).length],
          ]}
        />
      ))}
    </div>
  );
}

function ToolGrid({ tools }) {
  const [selectedTool, setSelectedTool] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailTab, setDetailTab] = useState("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const openDetail = async (tool) => {
    setSelectedTool(tool);
    setDetail(tool);
    setDetailTab("overview");
    setError("");
    setLoading(true);
    try {
      const payload = await api.tool(tool.name);
      setDetail(payload.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  if (!tools?.length) return <EmptyState title="No tools found." />;
  return (
    <>
      <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
        {tools.map((tool) => (
          <AssetCard
            key={tool.name}
            title={tool.name}
            description={tool.description || "Workspace tool asset."}
            rows={[
              ["Capability", tool.capability],
              ["Provider requirements", tool.provider_requirements],
              ["Eval cases", tool.eval_cases_count ?? 0],
              ["Status", tool.status || (tool.handler_available ? "registered" : "draft")],
              ["Schema path", tool.schema_path || "tools/schemas.py"],
            ]}
            metrics={[
              ["Risk", tool.risk_level || "medium"],
              ["Handler", tool.handler_available ? "Yes" : "No"],
              ["Approval", tool.requires_approval_by_policy ? "Yes" : "No"],
            ]}
            onClick={() => openDetail(tool)}
            action={
              <button
                className="rounded-md border border-line px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
                onClick={(event) => {
                  event.stopPropagation();
                  openDetail(tool);
                }}
              >
                Details
              </button>
            }
          />
        ))}
      </div>
      {selectedTool ? (
        <ToolDetailModal
          tool={detail || selectedTool}
          loading={loading}
          error={error}
          tab={detailTab}
          setTab={setDetailTab}
          onClose={() => setSelectedTool(null)}
        />
      ) : null}
    </>
  );
}

function MemoryGrid({ memories }) {
  if (!memories?.length) return <EmptyState title="This asset type is not implemented yet." />;
  return (
    <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
      {memories.map((memory) => (
        <AssetCard
          key={memory.memory_id}
          title={memory.title}
          description={memory.details}
          rows={[
            ["Skill", memory.skill],
            ["Type", memory.type],
            ["Occurrence count", memory.occurrence_count],
            ["Linked PROMO", memory.linked_promo_id],
          ]}
        />
      ))}
    </div>
  );
}

function SimpleList({ items, empty, render }) {
  if (!items?.length) return <EmptyState title={empty} />;
  return <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">{items.map(render)}</div>;
}

function AssetCard({ title, description, rows, metrics, action, onClick }) {
  return (
    <article className={["section-panel p-4", onClick ? "cursor-pointer transition hover:border-zinc-300" : ""].join(" ")} onClick={onClick}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-zinc-950">{title}</h2>
          {description ? <p className="mt-1 line-clamp-2 text-sm leading-6 text-zinc-500">{description}</p> : null}
        </div>
        {action}
      </div>
      {metrics?.length ? (
        <div className="mt-4 grid grid-cols-3 gap-2">
          {metrics.map(([label, value]) => (
            <div className="rounded-lg border border-line bg-zinc-50 px-3 py-2" key={label}>
              <p className="text-[11px] font-medium text-zinc-500">{label}</p>
              <p className="mt-1 text-sm font-semibold text-zinc-950">{compact(value, "0")}</p>
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

function ToolDetailModal({ tool, loading, error, tab, setTab, onClose }) {
  const tabs = [
    ["overview", "Overview"],
    ["schema", "Schema"],
    ["readme", "README"],
    ["eval", "Eval Cases"],
  ];
  const files = tool.files || {};
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/30 p-4">
      <div className="max-h-[86vh] w-full max-w-5xl overflow-hidden rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold text-zinc-950">{tool.name}</h2>
            <p className="mt-1 text-sm text-zinc-500">{tool.description || "Workspace tool asset."}</p>
          </div>
          <button className="rounded-md p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="border-b border-line px-5 pt-3">
          <div className="flex flex-wrap gap-2">
            {tabs.map(([id, label]) => (
              <button
                key={id}
                className={[
                  "rounded-md px-3 py-2 text-sm font-semibold",
                  tab === id ? "bg-zinc-950 text-white" : "text-zinc-600 hover:bg-zinc-50",
                ].join(" ")}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="max-h-[62vh] overflow-auto p-5">
          {loading ? <p className="text-sm text-zinc-500">Loading tool details...</p> : null}
          {error ? <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">{error}</p> : null}
          {!loading && tab === "overview" ? <ToolOverview tool={tool} /> : null}
          {!loading && tab === "schema" ? <FilePanel file={files.schema} fallbackPath={tool.schema_path} /> : null}
          {!loading && tab === "readme" ? <FilePanel file={files.readme} fallbackPath={tool.readme_path} /> : null}
          {!loading && tab === "eval" ? <FilePanel file={files.eval_cases} fallbackPath={tool.eval_cases_path} /> : null}
        </div>
      </div>
    </div>
  );
}

function ToolOverview({ tool }) {
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-3">
        <Metric label="Tool name" value={tool.name} />
        <Metric label="Description" value={tool.description} />
        <Metric label="Schema path" value={tool.schema_path} />
        <Metric label="README path" value={tool.readme_path} />
        <Metric label="Eval path" value={tool.eval_cases_path} />
        <Metric label="Provider requirements" value={tool.provider_requirements} />
        <Metric label="Last modified" value={tool.last_modified} />
      </div>
      <div className="space-y-4">
        <DetailBlock title="Inputs" value={tool.inputs} />
        <DetailBlock title="Outputs" value={tool.outputs} />
        <DetailBlock title="Safety rules" value={tool.safety} />
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
        <pre className="max-h-[48vh] overflow-auto rounded-md border border-line bg-zinc-50 p-4 text-xs leading-5 text-zinc-800">{file.content}</pre>
      ) : (
        <div className="rounded-md border border-dashed border-line bg-zinc-50 p-4 text-sm font-semibold text-zinc-500">missing</div>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-3 text-sm">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <span className="min-w-0 break-words text-right font-semibold text-zinc-900">{compact(value)}</span>
    </div>
  );
}
