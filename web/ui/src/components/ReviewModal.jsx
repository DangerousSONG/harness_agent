import { X } from "lucide-react";
import DiffPreview from "./DiffPreview";
import StatusPill from "./StatusPill";
import { compact, titleize } from "../lib/format";

function Field({ label, value }) {
  return (
    <div className="min-w-0">
      <p className="muted-label">{label}</p>
      <p className="mt-1 break-words text-sm font-medium leading-6 text-zinc-900">{compact(value)}</p>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-hairline">
      <h3 className="text-sm font-semibold text-zinc-950">{title}</h3>
      <div className="mt-4">{children}</div>
    </section>
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
      <section className="flex max-h-[90vh] w-full max-w-[940px] flex-col overflow-hidden rounded-xl border border-line bg-zinc-50 shadow-[0_24px_80px_rgba(15,23,42,0.24)]">
        <header className="flex items-start justify-between gap-4 border-b border-line bg-white px-6 py-5">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-zinc-950">Review Details</h2>
              <StatusPill status={review?.status || "loading"} />
            </div>
            <p className="mt-2">
              <span className="mono-badge">{compact(review?.review_id)}</span>
            </p>
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
            <div className="space-y-4">
              <Section title="Overview">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <Field label="Review ID" value={review?.review_id} />
                  <Field label="Type" value={titleize(review?.type)} />
                  <Field label="Status" value={review?.status} />
                  <Field label="Severity" value={review?.severity} />
                  <Field label="Target Files" value={review?.target_files} />
                  <Field label="Candidate ID" value={review?.candidate_id} />
                </div>
              </Section>

              <Section title="Proposed Change">
                <p className="whitespace-pre-wrap break-words text-sm leading-6 text-zinc-800">
                  {compact(review?.proposed_change, "No proposed change was provided.")}
                </p>
              </Section>

              <Section title="Evaluation">
                <div className="grid gap-4 md:grid-cols-2">
                  <Field label="Evaluation Plan" value={review?.evaluation_plan} />
                  <Field
                    label="Regression Coverage Status"
                    value={review?.metadata?.regression_coverage_status || review?.metadata?.coverage_status}
                  />
                </div>
              </Section>

              <Section title="Rollback">
                <p className="whitespace-pre-wrap break-words text-sm leading-6 text-zinc-800">
                  {compact(review?.rollback_plan, "No rollback plan was provided.")}
                </p>
              </Section>

              <Section title="Diff Preview">
                <DiffPreview patch={patch?.patch} />
              </Section>
            </div>
          )}
        </div>

        <footer className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t border-line bg-white/95 px-6 py-4 backdrop-blur">
          {canReject ? (
            <button className="danger-button" onClick={onReject} disabled={busy}>
              Reject
            </button>
          ) : null}
          {canPreview ? (
            <button className="subprimary-button" onClick={onApprove} disabled={busy}>
              Approve Preview
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
