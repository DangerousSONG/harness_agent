import { Eye, FileText, Hammer, X } from "lucide-react";
import { isValidElement } from "react";
import { compact, severityTone, titleize } from "../lib/format";
import StatusPill from "./StatusPill";

function DetailRow({ label, value }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-3 text-sm">
      <span className="text-zinc-500">{label}</span>
      <span className="font-medium text-zinc-900">
        {isValidElement(value) ? value : compact(value)}
      </span>
    </div>
  );
}

export default function ReviewCard({
  review,
  busy,
  onDetails,
  onApprove,
  onApply,
  onReject,
}) {
  const status = String(review?.status || "").toLowerCase();
  const severity = String(review?.severity || "low");
  const canPreview = status === "pending";
  const canApply = status === "approved";
  const closed = status === "applied" || status === "rejected";
  const tone = severityTone(severity);

  return (
    <article className="rounded-lg border border-amber-100 bg-white p-5 shadow-soft">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-50 text-risk">
              <FileText className="h-4 w-4" />
            </span>
            <h3 className="text-base font-semibold text-zinc-950">
              Human approval required
            </h3>
          </div>
          <p className="mt-2 text-sm text-zinc-600">
            This action may change a long-term Agent asset.
          </p>
        </div>
        <StatusPill status={review?.status || "pending"} />
      </div>

      <div className="mt-5 space-y-3">
        <DetailRow label="Review ID" value={review?.review_id} />
        <DetailRow label="Type" value={titleize(review?.type)} />
        <DetailRow label="Status" value={review?.status} />
        <DetailRow
          label="Severity"
          value={
            <span
              className={
                tone === "danger"
                  ? "text-danger"
                  : tone === "risk"
                    ? "text-risk"
                    : "text-zinc-900"
              }
            >
              {titleize(severity)}
            </span>
          }
        />
        <DetailRow label="Target Asset" value={review?.target_skill} />
        <DetailRow label="Target File" value={review?.target_files} />
        <DetailRow label="Candidate ID / Source" value={review?.candidate_id || review?.source} />
        <DetailRow label="Reason" value={review?.reason} />
      </div>

      <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
        <button className="secondary-button" onClick={onDetails}>
          <Eye className="h-4 w-4" />
          {canApply ? "View Diff" : "Review Details"}
        </button>
        {canPreview ? (
          <button className="secondary-button" onClick={onApprove} disabled={busy}>
            <Hammer className="h-4 w-4" />
            Generate Preview
          </button>
        ) : null}
        {canApply ? (
          <button className="primary-button" onClick={onApply} disabled={busy}>
            Apply Change
          </button>
        ) : null}
        {closed ? (
          <span className="inline-flex items-center rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-600">
            {titleize(status)}
          </span>
        ) : (
          <button className="danger-button" onClick={onReject} disabled={busy || status !== "pending"}>
            <X className="h-4 w-4" />
            Reject
          </button>
        )}
      </div>
    </article>
  );
}
