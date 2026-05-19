import { X } from "lucide-react";
import { compact } from "../lib/format";
import StatusPill from "./StatusPill";

function Row({ label, value }) {
  return (
    <div>
      <p className="muted-label">{label}</p>
      <p className="mt-1 text-sm leading-6 text-zinc-800">{compact(value)}</p>
    </div>
  );
}

export default function PromotionModal({ open, promotion, loading, onClose, onEvolve, busy }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-950/20 px-4 py-8 backdrop-blur-sm">
      <section className="card flex max-h-[86vh] w-full max-w-2xl flex-col overflow-hidden">
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-zinc-950">Promotion Candidate</h2>
              {promotion?.status ? <StatusPill status={promotion.status} /> : null}
            </div>
            <p className="mt-1 text-sm text-zinc-500">{compact(promotion?.promo_id)}</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close promotion detail">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="overflow-auto px-6 py-5">
          {loading ? (
            <div className="rounded-lg bg-zinc-50 p-6 text-sm text-zinc-500">
              Loading promotion...
            </div>
          ) : (
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <Row label="Target Skill" value={promotion?.target_skill} />
                <Row label="Source Memory Type" value={promotion?.source_memory_type} />
                <Row label="Occurrence Count" value={promotion?.occurrence_count} />
                <Row label="Promotion Score" value={promotion?.promotion_score} />
                <Row label="Promotion Decision" value={promotion?.promotion_decision} />
                <Row label="Eligible Target" value={promotion?.eligible_target} />
              </div>
              <Row label="Summary" value={promotion?.summary} />
              <Row label="Proposed Change" value={promotion?.proposed_change} />
              <Row label="Evaluation Plan" value={promotion?.evaluation_plan} />
              <Row label="Rollback Plan" value={promotion?.rollback_plan} />
              <Row label="Source Memory" value={promotion?.source_memory} />
            </div>
          )}
        </div>

        <footer className="flex justify-end gap-2 border-t border-line bg-white px-6 py-4">
          <button className="secondary-button" onClick={onClose}>Close</button>
          <button
            className="primary-button"
            disabled={!promotion?.promo_id || busy}
            onClick={() => onEvolve(promotion.promo_id)}
          >
            {busy ? "Evolving..." : "Evolve"}
          </button>
        </footer>
      </section>
    </div>
  );
}
