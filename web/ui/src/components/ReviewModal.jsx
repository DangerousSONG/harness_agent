import { X } from "lucide-react";
import DiffPreview from "./DiffPreview";
import StatusPill from "./StatusPill";
import { compact, titleize } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";

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
  const t = useTranslate();
  if (!open) return null;
  const status = String(review?.status || "").toLowerCase();
  const canPreview = status === "pending";
  const canApply = status === "approved";
  const canReject = status === "pending";
  const emptyPatch = canApply && reviewNeedsPatch(review) && !patch?.has_changes;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-950/20 px-4 py-8 backdrop-blur-sm">
      <section className="flex max-h-[90vh] w-full max-w-[940px] flex-col overflow-hidden rounded-xl border border-line bg-zinc-50 shadow-[0_24px_80px_rgba(15,23,42,0.24)]">
        <header className="flex items-start justify-between gap-4 border-b border-line bg-white px-6 py-5">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-zinc-950">{t("review.action.review_details")}</h2>
              <StatusPill status={review?.status || "loading"} />
            </div>
            <p className="mt-2">
              <span className="mono-badge">{compact(review?.review_id)}</span>
            </p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label={t("review.action.review_details")}>
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="overflow-auto px-6 py-5">
          {loading ? (
            <div className="rounded-lg bg-zinc-50 p-6 text-sm text-zinc-500">
              {t("settings.search.loading")}
            </div>
          ) : (
            <div className="space-y-4">
              <Section title={t("review.modal.overview")}>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <Field label={t("review.field.review_id")} value={review?.review_id} />
                  <Field label={t("review.field.type")} value={titleize(review?.type)} />
                  <Field label={t("review.field.status")} value={review?.status} />
                  <Field label={t("review.field.severity")} value={review?.severity} />
                  <Field label={t("review.field.target_files")} value={review?.target_files} />
                  <Field label={t("review.field.candidate_id")} value={review?.candidate_id} />
                </div>
              </Section>

              <Section title={t("review.modal.proposed_change")}>
                <p className="whitespace-pre-wrap break-words text-sm leading-6 text-zinc-800">
                  {compact(review?.proposed_change, t("review.modal.no_proposed_change"))}
                </p>
              </Section>

              <Section title={t("review.modal.evaluation")}>
                <div className="grid gap-4 md:grid-cols-2">
                  <Field label={t("review.modal.evaluation_plan")} value={review?.evaluation_plan} />
                  <Field
                    label={t("review.modal.regression_coverage")}
                    value={review?.metadata?.regression_coverage_status || review?.metadata?.coverage_status}
                  />
                </div>
              </Section>

              <Section title={t("review.modal.rollback")}>
                <p className="whitespace-pre-wrap break-words text-sm leading-6 text-zinc-800">
                  {compact(review?.rollback_plan, t("review.modal.no_rollback"))}
                </p>
              </Section>

              <Section title={t("review.modal.diff_preview")}>
                <DiffPreview patch={patch?.patch} />
                {emptyPatch ? (
                  <p className="mt-3 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-sm font-medium text-risk">
                    {patch?.apply_blocked_reason || t("review.modal.no_proposed_change")}
                  </p>
                ) : null}
              </Section>
            </div>
          )}
        </div>

        <footer className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t border-line bg-white/95 px-6 py-4 backdrop-blur">
          {canReject ? (
            <button className="danger-button" onClick={onReject} disabled={busy}>
              {t("review.action.reject")}
            </button>
          ) : null}
          {canPreview ? (
            <button className="subprimary-button" onClick={onApprove} disabled={busy}>
              {t("review.action.approve_preview")}
            </button>
          ) : null}
          {emptyPatch ? (
            <button className="subprimary-button" onClick={onApprove} disabled={busy}>
              {t("review.action.generate_preview")}
            </button>
          ) : null}
          {canApply && !emptyPatch ? (
            <button className="primary-button" onClick={onApply} disabled={busy}>
              {t("review.action.apply_change")}
            </button>
          ) : null}
        </footer>
      </section>
    </div>
  );
}

function reviewNeedsPatch(review) {
  const type = review?.type || "";
  const toolName = review?.tool_name || "";
  return ["skill.regression_case", "skill.promotion", "skill.creation", "file.write", "tool.update"].includes(type)
    || ["write_file", "edit_file"].includes(toolName);
}
