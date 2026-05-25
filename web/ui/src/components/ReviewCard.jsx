import { Eye, FileText, Hammer, X } from "lucide-react";
import { isValidElement } from "react";
import { compact, severityTone, titleize } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";
import StatusPill from "./StatusPill";

function DetailRow({ label, value }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 text-sm">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <span className="break-words font-medium text-zinc-900">
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
  const t = useTranslate();
  const status = String(review?.status || "").toLowerCase();
  const severity = String(review?.severity || "low");
  const canPreview = status === "pending";
  const canApply = status === "approved";
  const closed = status === "applied" || status === "rejected";
  const tone = severityTone(severity);

  return (
    <article className="rounded-lg border border-amber-200 bg-white shadow-soft">
      <div className="border-b border-amber-100 bg-amber-50/70 px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-risk shadow-hairline">
                <FileText className="h-4 w-4" />
              </span>
              <h3 className="text-base font-semibold text-zinc-950">
                {t("review.human_required")}
              </h3>
            </div>
            <p className="mt-2 text-sm text-zinc-600">
              {t("review.human_required_sub")}
            </p>
          </div>
          <StatusPill status={review?.status || "pending"} />
        </div>
      </div>

      <div className="space-y-3 px-5 py-4">
        <DetailRow label={t("review.field.review_id")} value={<span className="mono-badge">{review?.review_id}</span>} />
        <DetailRow label={t("review.field.type")} value={titleize(review?.type)} />
        <DetailRow
          label={t("review.field.severity")}
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
        <DetailRow label={t("review.field.target_asset")} value={review?.target_skill} />
        <DetailRow label={t("review.field.target_file")} value={review?.target_files} />
        <DetailRow
          label={t("review.field.candidate_id")}
          value={<span className="mono-badge">{review?.candidate_id || review?.source || "-"}</span>}
        />
        <DetailRow label={t("review.field.reason")} value={review?.reason} />
      </div>

      <div className="flex flex-wrap gap-2 border-t border-line px-5 py-4">
        <button className="secondary-button" onClick={onDetails}>
          <Eye className="h-4 w-4" />
          {canApply ? t("review.action.view_diff") : t("review.action.review_details")}
        </button>
        {canPreview ? (
          <button className="subprimary-button" onClick={onApprove} disabled={busy}>
            <Hammer className="h-4 w-4" />
            {t("review.action.approve_preview")}
          </button>
        ) : null}
        {canApply ? (
          <button className="primary-button" onClick={onApply} disabled={busy}>
            {t("review.action.apply_change")}
          </button>
        ) : null}
        {closed ? (
          <span className="inline-flex items-center rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-600">
            {titleize(status)}
          </span>
        ) : (
          <button className="danger-button" onClick={onReject} disabled={busy || status !== "pending"}>
            <X className="h-4 w-4" />
            {t("review.action.reject")}
          </button>
        )}
      </div>
    </article>
  );
}
