import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, ChevronRight, RefreshCcw, Sparkles, ShieldAlert, ListChecks } from "lucide-react";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { api, getErrorMessage } from "../lib/api";
import { compact, formatDate } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";

const SECTION_KEYS = ["opportunities", "batches", "edits", "rejected"];

export default function SideChannelPage() {
  const t = useTranslate();
  const [section, setSection] = useState("opportunities");
  const [signals, setSignals] = useState([]);
  const [opportunities, setOpportunities] = useState([]);
  const [batches, setBatches] = useState([]);
  const [edits, setEdits] = useState([]);
  const [rejected, setRejected] = useState([]);
  const [selectedOpps, setSelectedOpps] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState({ message: "", tone: "info" });

  const refresh = useCallback(async () => {
    try {
      const [sig, opps, btc, eds, rej] = await Promise.all([
        api.evolutionScoutSignals(),
        api.evolutionScoutOpportunities(),
        api.evolutionScoutBatches(),
        api.evolutionOptimizerEdits(),
        api.evolutionOptimizerRejected(),
      ]);
      setSignals(sig.data || []);
      setOpportunities(opps.data || []);
      setBatches(btc.data || []);
      setEdits(eds.data || []);
      setRejected(rej.data || []);
    } catch (error) {
      setStatus({ message: getErrorMessage(error), tone: "error" });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const runScan = useCallback(async () => {
    setBusy(true);
    try {
      const result = await api.evolutionScoutScan();
      setStatus({
        message: result.message || result.data?.summary || t("side_channel.status.scan_done"),
        tone: "success",
      });
      await refresh();
    } catch (error) {
      setStatus({ message: getErrorMessage(error), tone: "error" });
    } finally {
      setBusy(false);
    }
  }, [refresh, t]);

  const toggleOpp = useCallback((id) => {
    setSelectedOpps((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const createBatch = useCallback(async () => {
    if (!selectedOpps.size) return;
    setBusy(true);
    try {
      const result = await api.evolutionScoutBatchCreate(Array.from(selectedOpps));
      setStatus({ message: result.message, tone: "success" });
      setSelectedOpps(new Set());
      await refresh();
      setSection("batches");
    } catch (error) {
      setStatus({ message: getErrorMessage(error), tone: "error" });
    } finally {
      setBusy(false);
    }
  }, [refresh, selectedOpps]);

  const optimizeBatch = useCallback(
    async (batchId) => {
      setBusy(true);
      try {
        const result = await api.evolutionOptimizerPropose({ batch_id: batchId });
        setStatus({ message: result.message, tone: "success" });
        await refresh();
        setSection("edits");
      } catch (error) {
        setStatus({ message: getErrorMessage(error), tone: "error" });
      } finally {
        setBusy(false);
      }
    },
    [refresh]
  );

  const validateEdit = useCallback(
    async (editId) => {
      setBusy(true);
      try {
        const result = await api.evolutionOptimizerValidate(editId);
        setStatus({ message: result.message, tone: "success" });
        await refresh();
      } catch (error) {
        setStatus({ message: getErrorMessage(error), tone: "error" });
      } finally {
        setBusy(false);
      }
    },
    [refresh]
  );

  const counts = useMemo(
    () => ({
      opportunities: opportunities.length,
      batches: batches.length,
      edits: edits.length,
      rejected: rejected.length,
    }),
    [batches.length, edits.length, opportunities.length, rejected.length]
  );

  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-zinc-950">
              {t("side_channel.title")}
            </h2>
            <p className="mt-1 text-xs text-zinc-500">
              {t("side_channel.subtitle")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="secondary-button"
              onClick={refresh}
              disabled={busy}
              title={t("side_channel.action.refresh")}
            >
              <RefreshCcw className="h-4 w-4" />
              {t("side_channel.action.refresh")}
            </button>
            <button
              className="primary-button"
              onClick={runScan}
              disabled={busy}
            >
              <Activity className="h-4 w-4" />
              {t("side_channel.action.scan")}
            </button>
          </div>
        </header>

        {status.message ? (
          <div
            className={[
              "rounded-lg border px-3 py-2 text-sm",
              status.tone === "error"
                ? "border-rose-200 bg-rose-50/60 text-rose-700"
                : "border-emerald-200 bg-emerald-50/60 text-emerald-700",
            ].join(" ")}
          >
            {status.message}
          </div>
        ) : null}

        <div className="grid gap-2 sm:grid-cols-4">
          <Metric label={t("side_channel.metric.signals")} value={signals.length} icon={ListChecks} />
          <Metric
            label={t("side_channel.metric.opportunities")}
            value={counts.opportunities}
            icon={Sparkles}
          />
          <Metric label={t("side_channel.metric.edits")} value={counts.edits} icon={ChevronRight} />
          <Metric
            label={t("side_channel.metric.rejected")}
            value={counts.rejected}
            icon={ShieldAlert}
          />
        </div>

        <div className="flex flex-wrap gap-2 rounded-lg border border-line bg-white p-1 shadow-hairline">
          {SECTION_KEYS.map((key) => (
            <button
              key={key}
              className={[
                "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition",
                section === key
                  ? "bg-zinc-950 text-white"
                  : "text-zinc-700 hover:bg-zinc-50",
              ].join(" ")}
              onClick={() => setSection(key)}
            >
              {t(`side_channel.tab.${key}`)}
              {counts[key] ? (
                <span
                  className={[
                    "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                    section === key ? "bg-white/20 text-white" : "bg-zinc-100 text-zinc-600",
                  ].join(" ")}
                >
                  {counts[key]}
                </span>
              ) : null}
            </button>
          ))}
        </div>

        {section === "opportunities" ? (
          <OpportunitiesList
            opportunities={opportunities}
            signalsById={Object.fromEntries(signals.map((s) => [s.signal_id, s]))}
            selected={selectedOpps}
            onToggle={toggleOpp}
            onCreateBatch={createBatch}
            busy={busy}
            t={t}
          />
        ) : null}
        {section === "batches" ? (
          <BatchesList
            batches={batches}
            onOptimize={optimizeBatch}
            busy={busy}
            t={t}
          />
        ) : null}
        {section === "edits" ? (
          <EditsList edits={edits} onValidate={validateEdit} busy={busy} t={t} />
        ) : null}
        {section === "rejected" ? <RejectedList items={rejected} t={t} /> : null}
      </div>
    </section>
  );
}

function Metric({ label, value, icon: Icon }) {
  return (
    <div className="section-panel flex items-center justify-between p-3">
      <div>
        <p className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</p>
        <p className="text-xl font-semibold text-zinc-950">{value}</p>
      </div>
      <Icon className="h-5 w-5 text-zinc-400" />
    </div>
  );
}

function OpportunitiesList({ opportunities, signalsById, selected, onToggle, onCreateBatch, busy, t }) {
  if (!opportunities.length) {
    return <EmptyState title={t("side_channel.empty.opportunities")} />;
  }
  const selectedSkill = opportunities.find((opp) => selected.has(opp.opportunity_id))?.target_skill || "";
  return (
    <div className="space-y-3">
      {selected.size ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm">
          <span className="text-zinc-700">
            {t("side_channel.batch.selected", { count: selected.size })}
            {selectedSkill ? (
              <span className="ml-2 text-xs text-zinc-500">
                {t("side_channel.batch.locked_skill")}: <span className="font-mono">{selectedSkill}</span>
              </span>
            ) : null}
          </span>
          <button className="primary-button" onClick={onCreateBatch} disabled={busy}>
            {t("side_channel.action.create_batch")}
          </button>
        </div>
      ) : null}
      {opportunities.map((opp) => {
        const isRejected = opp.decision === "reject";
        const lockedByOtherSkill = Boolean(selectedSkill) && opp.target_skill !== selectedSkill;
        const isDisabled = isRejected || lockedByOtherSkill;
        const disabledReason = isRejected
          ? t("side_channel.disabled.rejected")
          : lockedByOtherSkill
          ? t("side_channel.disabled.cross_skill", { skill: selectedSkill })
          : "";
        return (
        <article
          key={opp.opportunity_id}
          className={[
            "section-panel p-4 transition",
            isDisabled ? "opacity-50" : "",
          ].join(" ")}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-line"
                  checked={selected.has(opp.opportunity_id)}
                  onChange={() => onToggle(opp.opportunity_id)}
                  disabled={isDisabled}
                  title={disabledReason}
                />
                <span className="mono-badge">{opp.opportunity_id}</span>
                <StatusPill status={opp.decision} />
                <span className="text-sm font-semibold text-zinc-900">
                  {compact(opp.target_skill)}
                </span>
                <span className="text-xs text-zinc-500">
                  score=
                  <span className="font-mono">{Number(opp.evolution_score || 0).toFixed(3)}</span>
                </span>
                <span className="text-xs text-zinc-500">priority={opp.priority}</span>
                <span className="text-xs text-zinc-500">risk={opp.risk_level}</span>
              </div>
              <p className="mt-2 line-clamp-2 text-sm text-zinc-600">{compact(opp.summary)}</p>
              <div className="mt-2 rounded-md border border-line bg-zinc-50/60 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                  {t("side_channel.field.reason")}
                </p>
                <p className="mt-1 text-sm leading-relaxed text-zinc-800">
                  {compact(opp.reason)}
                </p>
                {opp.score_breakdown ? (
                  <p className="mt-1.5 font-mono text-[10px] text-zinc-500">
                    {t("side_channel.field.score_breakdown")}: {opp.score_breakdown}
                  </p>
                ) : null}
              </div>
            </div>
          </div>
          <div className="mt-3 grid gap-2 text-xs text-zinc-500 sm:grid-cols-2">
            <Cell
              label={t("side_channel.field.should_improve")}
              values={opp.should_improve || []}
            />
            <Cell
              label={t("side_channel.field.must_not_regress")}
              values={opp.must_not_regress || []}
            />
          </div>
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer text-zinc-500">
              {t("side_channel.field.signals")} ({(opp.signal_ids || []).length})
            </summary>
            <ul className="mt-1 space-y-1">
              {(opp.signal_ids || []).map((id) => {
                const signal = signalsById[id];
                if (!signal) return <li key={id} className="font-mono text-zinc-400">{id}</li>;
                return (
                  <li key={id} className="text-zinc-600">
                    <span className="font-mono">{signal.source_ref}</span>{" "}
                    <span className="text-zinc-400">@</span>{" "}
                    <span className="font-mono text-zinc-500">{signal.source_path}</span>
                    <span className="ml-2 text-zinc-500">{signal.content?.slice(0, 100)}</span>
                  </li>
                );
              })}
            </ul>
          </details>
          {lockedByOtherSkill ? (
            <p className="mt-2 text-[11px] text-zinc-500">
              {disabledReason}
            </p>
          ) : null}
        </article>
      );
      })}
    </div>
  );
}

function BatchesList({ batches, onOptimize, busy, t }) {
  if (!batches.length) {
    return <EmptyState title={t("side_channel.empty.batches")} />;
  }
  return (
    <div className="space-y-3">
      {batches.map((batch) => (
        <article key={batch.batch_id} className="section-panel p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono-badge">{batch.batch_id}</span>
                <span className="text-sm font-semibold text-zinc-900">{batch.target_skill}</span>
                <span className="text-xs text-zinc-500">
                  opportunities={batch.opportunity_ids?.length || 0}
                </span>
                <span className="text-xs text-zinc-500">priority={batch.priority}</span>
                <span className="text-xs text-zinc-500">risk={batch.risk_level}</span>
              </div>
              <p className="mt-2 line-clamp-2 text-sm text-zinc-600">{compact(batch.merged_summary)}</p>
            </div>
            <button
              className="primary-button"
              onClick={() => onOptimize(batch.batch_id)}
              disabled={busy}
            >
              <Sparkles className="h-4 w-4" />
              {t("side_channel.action.optimize")}
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

function EditsList({ edits, onValidate, busy, t }) {
  if (!edits.length) {
    return <EmptyState title={t("side_channel.empty.edits")} />;
  }
  return (
    <div className="space-y-3">
      {edits.map((edit) => (
        <article key={edit.edit_id} className="section-panel p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono-badge">{edit.edit_id}</span>
                <StatusPill status={edit.status} />
                <span className="text-sm font-semibold text-zinc-900">{edit.target_skill}</span>
                {edit.review_id ? (
                  <span className="text-xs text-appleBlue">
                    {t("side_channel.field.review_id")}:
                    <span className="ml-1 font-mono">{edit.review_id}</span>
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-xs text-zinc-500">{compact(edit.rationale)}</p>
              <ul className="mt-2 space-y-1 text-xs">
                {(edit.edit_ops || []).map((op, idx) => (
                  <li key={idx} className="rounded-md border border-line bg-white px-2.5 py-1.5">
                    <span className="font-mono text-zinc-700">{op.op}</span>{" "}
                    <span className="text-zinc-500">→ {op.target_section}</span>
                    <p className="mt-1 line-clamp-2 text-zinc-700">{op.text}</p>
                  </li>
                ))}
              </ul>
            </div>
            {edit.status === "proposed" || edit.status === "validated" ? (
              <button
                className="primary-button"
                onClick={() => onValidate(edit.edit_id)}
                disabled={busy}
              >
                <ChevronRight className="h-4 w-4" />
                {edit.status === "validated"
                  ? t("side_channel.action.submit_review")
                  : t("side_channel.action.validate")}
              </button>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}

function RejectedList({ items, t }) {
  if (!items.length) {
    return <EmptyState title={t("side_channel.empty.rejected")} />;
  }
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <article key={item.edit_id} className="section-panel p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mono-badge">{item.edit_id}</span>
            <span className="text-xs text-rose-700">{compact(item.reject_reason, "—")}</span>
            <span className="ml-auto text-xs text-zinc-500">{formatDate(item.created_at)}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

function Cell({ label, values }) {
  if (!values?.length) {
    return (
      <div className="rounded-md border border-line bg-white px-2.5 py-1.5">
        <p className="text-[10px] uppercase tracking-wide text-zinc-400">{label}</p>
        <p className="mt-0.5 text-xs text-zinc-400">—</p>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-line bg-white px-2.5 py-1.5">
      <p className="text-[10px] uppercase tracking-wide text-zinc-400">{label}</p>
      <ul className="mt-0.5 list-disc space-y-0.5 pl-4">
        {values.map((value, idx) => (
          <li key={idx} className="text-xs text-zinc-700">
            {value}
          </li>
        ))}
      </ul>
    </div>
  );
}
