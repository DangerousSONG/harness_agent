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
}) {
  const [tab, setTab] = useState("snapshot");
  const selected = versions?.find((item) => versionKey(item) === selectedVersionKey);

  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-zinc-950">Versions</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Skill version history is read-only here. Rollback creates a review instead of changing files.
          </p>
        </div>

        {!versions?.length ? (
          <EmptyState title="No recorded skill versions yet." />
        ) : (
          <div className="grid gap-5 lg:grid-cols-[1fr_26rem]">
            <div className="card overflow-hidden">
              <div className="overflow-auto">
                <table className="min-w-full divide-y divide-line text-sm">
                  <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase tracking-normal text-zinc-500">
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
                        <th className="whitespace-nowrap px-4 py-3" key={header}>{header}</th>
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
                          <td className="px-4 py-4 font-semibold">{item.skill}</td>
                          <td className="px-4 py-4">{item.version}</td>
                          <td className="px-4 py-4">{compact(item.promotion_id)}</td>
                          <td className="px-4 py-4">{compact(item.skill_review_id)}</td>
                          <td className="px-4 py-4">{compact(item.regression_review_ids)}</td>
                          <td className="px-4 py-4 text-zinc-500">{formatDate(item.created_at)}</td>
                          <td className="max-w-32 truncate px-4 py-4">{compact(item.base_hash)}</td>
                          <td className="max-w-32 truncate px-4 py-4">{compact(item.new_hash)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <aside className="card flex max-h-[72vh] flex-col overflow-hidden">
              <div className="border-b border-line p-5">
                <h2 className="text-base font-semibold text-zinc-950">
                  {selected ? `${selected.skill} ${selected.version}` : "Version detail"}
                </h2>
                <p className="mt-1 text-sm text-zinc-500">SKILL.md snapshot, patch.diff, eval_result.json</p>
              </div>
              <div className="flex gap-2 border-b border-line px-5 py-3">
                {["snapshot", "patch", "eval"].map((item) => (
                  <button
                    key={item}
                    className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${tab === item ? "bg-zinc-950 text-white" : "text-zinc-600 hover:bg-zinc-100"}`}
                    onClick={() => setTab(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <div className="min-h-0 flex-1 overflow-auto p-5">
                {tab === "snapshot" ? (
                  <pre className="rounded-lg bg-zinc-50 p-4 text-xs leading-6 text-zinc-700">
                    {versionDetail?.snapshot_content || "No SKILL.md snapshot selected."}
                  </pre>
                ) : null}
                {tab === "patch" ? <DiffPreview patch={versionDetail?.patch_content} /> : null}
                {tab === "eval" ? (
                  <pre className="rounded-lg bg-zinc-50 p-4 text-xs leading-6 text-zinc-700">
                    {JSON.stringify(versionDetail?.eval_result || {}, null, 2)}
                  </pre>
                ) : null}
              </div>
              <div className="border-t border-line p-5">
                <button
                  className="secondary-button w-full"
                  disabled={!selected || busyVersionKey === selectedVersionKey}
                  onClick={() => selected && onCreateRollback(selected)}
                >
                  <RotateCcw className="h-4 w-4" />
                  Create Rollback Review
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
