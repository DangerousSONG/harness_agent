import { Boxes, Database, Hammer, Library, MemoryStick, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { compact } from "../lib/format";

const tabs = [
  { id: "skills", label: "Skills", icon: Boxes },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "memories", label: "Memories", icon: MemoryStick },
  { id: "knowledge", label: "Knowledge Bases", icon: Library },
  { id: "eval", label: "Eval Cases", icon: Hammer },
  { id: "datasets", label: "Datasets", icon: Database },
];

export default function AssetsPage({ skills, tools, memories, knowledgeBases, versions }) {
  const [tab, setTab] = useState("skills");
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
  if (!tools?.length) return <EmptyState title="No tools found." />;
  return (
    <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
      {tools.map((tool) => (
        <article className="section-panel p-4" key={tool.name}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-zinc-950">{tool.name}</h2>
              <p className="mt-2 line-clamp-3 text-sm leading-6 text-zinc-500">{tool.description}</p>
            </div>
            <StatusPill status={tool.requires_approval_by_policy ? "approval required" : "available"} />
          </div>
          <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <Metric label="Capability" value={tool.capability} />
            <Metric label="Risk level" value={tool.risk_level} />
            <Metric label="Requires approval" value={tool.requires_approval_by_policy ? "Yes" : "No"} />
          </div>
        </article>
      ))}
    </div>
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

function AssetCard({ title, description, rows, metrics }) {
  return (
    <article className="section-panel p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-zinc-950">{title}</h2>
          {description ? <p className="mt-1 line-clamp-2 text-sm leading-6 text-zinc-500">{description}</p> : null}
        </div>
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

function Metric({ label, value }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-3 text-sm">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <span className="min-w-0 break-words text-right font-semibold text-zinc-900">{compact(value)}</span>
    </div>
  );
}
