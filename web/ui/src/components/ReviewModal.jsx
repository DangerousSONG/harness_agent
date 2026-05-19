import { X } from "lucide-react";
import DiffPreview from "./DiffPreview";
import StatusPill from "./StatusPill";
import { compact, titleize } from "../lib/format";

function Field({ label, value }) {
  return (
    <div>
      <p className="muted-label">{label}</p>
      <p className="mt-1 text-sm font-medium leading-6 text-zinc-900">{compact(value)}</p>
    </div>
  );
}

export default function ReviewModal({
  open,
  review,
  patch,
  loading,
  busy,
  onClose,
  onApprove,
  onApply,
  onReject,
}) {
  if (!open) return null;
  const status = String(review?.status || "").toLowerCase();
  const canPreview = status === "pending";
  const canApply = status === "approved";
  const canReject = status === "pending";

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-950/20 px-4 py-8 backdrop-blur-sm">
      <section className="card flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden">
        <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-zinc-950">Review Details</h2>
              <StatusPill status={review?.status || "loading"} />
            </div>
            <p className="mt-1 text-sm text-zinc-500">{compact(review?.review_id)}</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close review details">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="overflow-auto px-6 py-5">
          {loading ? (
            <div className="rounded-lg bg-zinc-50 p-6 text-sm text-zinc-500">
              Loading review details...
            </div>
          ) : (
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <Field label="Review ID" value={review?.review_id} />
                <Field label="Type" value={titleize(review?.type)} />
                <Field label="Status" value={review?.status} />
                <Field label="Severity" value={review?.severity} />
                <Field label="Target Files" value={review?.target_files} />
                <Field label="Candidate ID" value={review?.candidate_id} />
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Proposed Change" value={review?.proposed_change} />
                <Field
                  label="Regression Coverage Status"
                  value={review?.metadata?.regression_coverage_status || review?.metadata?.coverage_status}
                />
                <Field label="Evaluation Plan" value={review?.evaluation_plan} />
                <Field label="Rollback Plan" value={review?.rollback_plan} />
              </div>

              <div>
                <p className="muted-label mb-2">Diff Preview</p>
                <DiffPreview patch={patch?.patch} />
              </div>
            </div>
          )}
        </div>

        <footer className="flex flex-wrap justify-end gap-2 border-t border-line bg-white px-6 py-4">
          {canReject ? (
            <button className="danger-button" onClick={onReject} disabled={busy}>
              Reject
            </button>
          ) : null}
          {canPreview ? (
            <button className="secondary-button" onClick={onApprove} disabled={busy}>
              Generate Preview
            </button>
          ) : null}
          {canApply ? (
            <button className="primary-button" onClick={onApply} disabled={busy}>
              Apply Change
            </button>
          ) : null}
        </footer>
      </section>
    </div>
  );
}
