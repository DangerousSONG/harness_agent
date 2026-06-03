import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCcw } from "lucide-react";
import EmptyState from "../components/EmptyState";
import Paginator, { paginate } from "../components/Paginator";
import { api, getErrorMessage } from "../lib/api";
import { compact, formatDate } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";

const OUTCOME_TONE = {
  success: "text-emerald-700 bg-emerald-50/60 border-emerald-200",
  failure: "text-rose-700 bg-rose-50/60 border-rose-200",
  blocked: "text-amber-800 bg-amber-50/60 border-amber-200",
  partial: "text-appleBlue bg-blue-50/60 border-blue-200",
  unknown: "text-zinc-600 bg-zinc-50 border-line",
};

const FAILURE_TONE = {
  environment: "text-amber-800 bg-amber-50/60",
  tool_failure: "text-rose-700 bg-rose-50/60",
  policy_block: "text-rose-700 bg-rose-50/60",
  rule_not_applied: "text-appleBlue bg-blue-50/60",
  skill_gap: "text-appleBlue bg-blue-50/60",
  bad_skill_selection: "text-appleBlue bg-blue-50/60",
  bad_retrieval: "text-appleBlue bg-blue-50/60",
  "": "text-zinc-500",
};

const OUTCOME_FILTERS = ["", "success", "failure", "blocked", "partial", "unknown"];

export default function RunsPage() {
  const t = useTranslate();
  const [rows, setRows] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [detail, setDetail] = useState(null);
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [intentFilter, setIntentFilter] = useState("");
  const [emitFilter, setEmitFilter] = useState("any");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 50 };
      if (outcomeFilter) params.outcome = outcomeFilter;
      if (intentFilter.trim()) params.intent = intentFilter.trim();
      if (emitFilter !== "any") params.should_emit = emitFilter === "true";
      const result = await api.runs(params);
      setRows(result.data || []);
      setError("");
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [outcomeFilter, intentFilter, emitFilter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedRunId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    api.run(selectedRunId).then((result) => {
      if (!cancelled) setDetail(result.data || null);
    }).catch((caught) => {
      if (!cancelled) setError(getErrorMessage(caught));
    });
    return () => { cancelled = true; };
  }, [selectedRunId]);

  const { pageItems, total, pageCount, page: safePage } = useMemo(
    () => paginate(rows, page),
    [rows, page]
  );

  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-zinc-950">{t("runs.title")}</h2>
            <p className="mt-1 text-xs text-zinc-500">{t("runs.subtitle")}</p>
          </div>
          <button className="secondary-button" onClick={refresh} disabled={loading}>
            <RefreshCcw className="h-4 w-4" />
            {t("runs.action.refresh")}
          </button>
        </header>

        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-white p-3 text-xs">
          <span className="text-zinc-500">{t("runs.filter.outcome")}:</span>
          {OUTCOME_FILTERS.map((value) => (
            <button
              key={value || "all"}
              className={[
                "rounded-full px-2.5 py-0.5 text-xs font-semibold transition",
                outcomeFilter === value
                  ? "bg-zinc-950 text-white"
                  : "border border-line bg-white text-zinc-600 hover:bg-zinc-50",
              ].join(" ")}
              onClick={() => setOutcomeFilter(value)}
            >
              {value || t("runs.filter.all")}
            </button>
          ))}
          <span className="ml-3 text-zinc-500">{t("runs.filter.intent")}:</span>
          <input
            className="rounded-md border border-line px-2 py-1 text-xs"
            placeholder="general_chat"
            value={intentFilter}
            onChange={(e) => setIntentFilter(e.target.value)}
          />
          <span className="ml-3 text-zinc-500">{t("runs.filter.should_emit")}:</span>
          <select
            className="rounded-md border border-line bg-white px-2 py-1 text-xs"
            value={emitFilter}
            onChange={(e) => setEmitFilter(e.target.value)}
          >
            <option value="any">{t("runs.filter.any")}</option>
            <option value="true">true</option>
            <option value="false">false</option>
          </select>
        </div>

        {error ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50/60 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        ) : null}

        {!rows.length ? (
          <EmptyState title={t("runs.empty")} />
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(22rem,0.95fr)]">
            <div className="section-panel overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full table-fixed divide-y divide-line text-xs">
                  <colgroup>
                    <col className="w-[8.5rem]" />
                    <col className="w-[10rem]" />
                    <col />
                    <col className="w-[9rem]" />
                    <col className="w-[7rem]" />
                    <col className="w-[9rem]" />
                    <col className="w-[5rem]" />
                  </colgroup>
                  <thead className="bg-zinc-50/80 text-left text-[11px] font-semibold uppercase tracking-normal text-zinc-500">
                    <tr>
                      <th className="px-3 py-2.5">run_id</th>
                      <th className="px-3 py-2.5">created_at</th>
                      <th className="px-3 py-2.5">intent</th>
                      <th className="px-3 py-2.5">selected_skill</th>
                      <th className="px-3 py-2.5">outcome</th>
                      <th className="px-3 py-2.5">primary_failure</th>
                      <th className="px-3 py-2.5">emit?</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line bg-white">
                    {pageItems.map((row) => (
                      <tr
                        key={row.run_id}
                        className={[
                          "cursor-pointer align-top transition hover:bg-zinc-50",
                          selectedRunId === row.run_id ? "bg-blue-50/40" : "",
                        ].join(" ")}
                        onClick={() => setSelectedRunId(row.run_id)}
                      >
                        <td className="px-3 py-2"><span className="mono-badge text-[10px]">{row.run_id}</span></td>
                        <td className="px-3 py-2 text-zinc-500">{formatDate(row.created_at)}</td>
                        <td className="px-3 py-2"><span className="font-mono text-[11px] text-zinc-700">{compact(row.intent, "—")}</span></td>
                        <td className="px-3 py-2"><span className="font-mono text-[11px] text-zinc-700">{compact(row.selected_skill, "—")}</span></td>
                        <td className="px-3 py-2">
                          <span className={["rounded-full border px-2 py-0.5 text-[10px] font-semibold", OUTCOME_TONE[row.outcome] || OUTCOME_TONE.unknown].join(" ")}>
                            {row.outcome}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          {row.primary_failure_source ? (
                            <span className={["rounded-md px-2 py-0.5 text-[10px] font-semibold", FAILURE_TONE[row.primary_failure_source] || FAILURE_TONE[""]].join(" ")}>
                              {row.primary_failure_source}
                            </span>
                          ) : (
                            <span className="text-zinc-400">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-center font-mono text-[11px]">
                          {row.should_emit_learning_signal ? (
                            <span className="text-emerald-700">✓</span>
                          ) : (
                            <span className="text-zinc-400">✗</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Paginator page={safePage} pageCount={pageCount} total={total} onPage={setPage} />
            </div>

            <aside className="section-panel flex max-h-[78vh] flex-col overflow-hidden">
              <div className="border-b border-line bg-white p-4">
                <h3 className="text-sm font-semibold text-zinc-950">
                  {detail?.run_id || t("runs.detail.placeholder_title")}
                </h3>
                <p className="mt-1 text-xs text-zinc-500">
                  {detail
                    ? t("runs.detail.subtitle", { outcome: detail.outcome })
                    : t("runs.detail.placeholder")}
                </p>
              </div>
              <div className="overflow-auto p-4">
                {detail ? (
                  <pre className="whitespace-pre-wrap break-words font-mono text-[10.5px] leading-relaxed text-zinc-800">
                    {JSON.stringify(detail, null, 2)}
                  </pre>
                ) : (
                  <p className="text-xs text-zinc-500">{t("runs.detail.placeholder")}</p>
                )}
              </div>
            </aside>
          </div>
        )}
      </div>
    </section>
  );
}
