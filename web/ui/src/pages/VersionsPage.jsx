import { RotateCcw } from "lucide-react";
import { useState } from "react";
import DiffPreview from "../components/DiffPreview";
import EmptyState from "../components/EmptyState";
import { compact, formatDate } from "../lib/format";

export default function VersionsPage({
  versions,
  versionDetail,
  selectedVersionKey,
  onSelectVersion,
  onCreateRollback,
  busyVersionKey,
  embedded = false,
}) {
  const [tab, setTab] = useState("snapshot");
  const selected = versions?.find((item) => versionKey(item) === selectedVersionKey);

  return (
    <section className="workbench-section">
      <div className="workbench-container">
        {!embedded ? <div className="mb-6">
          <h1 className="page-title">Versions</h1>
          <p className="page-subtitle">
            Skill version history is read-only here. Rollback creates a review instead of changing files.
          </p>
        </div> : null}

        {!versions?.length ? (
          <EmptyState title="No recorded skill versions yet." />
        ) : (
          <div className="grid min-h-0 gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(28rem,0.9fr)]">
            <div className="section-panel overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full table-fixed divide-y divide-line text-sm">
                  <colgroup>
                    <col className="w-[9rem]" />
                    <col className="w-[7rem]" />
                    <col className="w-[10rem]" />
                    <col className="w-[10rem]" />
                    <col />
                    <col className="w-[8.5rem]" />
                    <col className="w-[8rem]" />
                    <col className="w-[8rem]" />
                  </colgroup>
                  <thead className="bg-zinc-50/80 text-left text-[11px] font-semibold uppercase tracking-normal text-zinc-500">
                    <tr>
                      {[
                        "skill",
                        "version",
                        "promotion_id",
                        "skill_review_id",
                        "regression_review_ids",
                        "created_at",
                        "base_hash",
                        "new_hash",
                      ].map((header) => (
                        <th className="px-4 py-3.5" key={header}>{header}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line bg-white">
                    {versions.map((item) => {
                      const key = versionKey(item);
                      return (
                        <tr
                          className={`cursor-pointer align-top transition hover:bg-zinc-50 ${key === selectedVersionKey ? "bg-blue-50/40" : ""}`}
                          key={key}
                          onClick={() => onSelectVersion(item)}
                        >
                          <td className="break-words px-4 py-4 font-semibold">{item.skill}</td>
                          <td className="px-4 py-4"><span className="mono-badge">{item.version}</span></td>
                          <td className="px-4 py-4"><span className="mono-badge">{compact(item.promotion_id)}</span></td>
                          <td className="px-4 py-4"><span className="mono-badge">{compact(item.skill_review_id)}</span></td>
                          <td className="break-words px-4 py-4 font-mono text-xs leading-5">{compact(item.regression_review_ids)}</td>
                          <td className="px-4 py-4 text-xs leading-5 text-zinc-500">{formatDate(item.created_at)}</td>
                          <td className="break-all px-4 py-4 font-mono text-xs">{compact(item.base_hash)}</td>
                          <td className="break-all px-4 py-4 font-mono text-xs">{compact(item.new_hash)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <aside className="section-panel flex max-h-[76vh] flex-col overflow-hidden">
              <div className="border-b border-line bg-white p-5">
                <h2 className="text-base font-semibold text-zinc-950">
                  {selected ? `${selected.skill} ${selected.version}` : "Version detail"}
                </h2>
                <p className="mt-1 text-sm text-zinc-500">SKILL.md snapshot, patch.diff, eval_result.json</p>
              </div>
              <div className="flex gap-1 border-b border-line bg-zinc-50 px-3 py-2">
                {["snapshot", "patch", "eval"].map((item) => (
                  <button
                    key={item}
                    className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${tab === item ? "bg-white text-appleBlue shadow-hairline" : "text-zinc-600 hover:bg-white"}`}
                    onClick={() => setTab(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <div className="min-h-0 flex-1 overflow-auto p-5">
                {tab === "snapshot" ? (
                  <pre className="overflow-auto rounded-lg border border-line bg-zinc-50 p-4 font-mono text-xs leading-6 text-zinc-700">
                    {versionDetail?.snapshot_content || "No SKILL.md snapshot selected."}
                  </pre>
                ) : null}
                {tab === "patch" ? <DiffPreview patch={versionDetail?.patch_content} /> : null}
                {tab === "eval" ? (
                  <pre className="overflow-auto rounded-lg border border-line bg-zinc-50 p-4 font-mono text-xs leading-6 text-zinc-700">
                    {JSON.stringify(versionDetail?.eval_result || {}, null, 2)}
                  </pre>
                ) : null}
              </div>
              <div className="border-t border-line p-5">
                <button
                  className="subprimary-button w-full"
                  disabled={!selected || busyVersionKey === selectedVersionKey}
                  onClick={() => selected && onCreateRollback(selected)}
                >
                  <RotateCcw className="h-4 w-4" />
                  {busyVersionKey === selectedVersionKey ? "Creating..." : "Create Rollback Review"}
                </button>
              </div>
            </aside>
          </div>
        )}
      </div>
    </section>
  );
}

export function versionKey(item) {
  return `${item.skill}:${item.version}`;
}
