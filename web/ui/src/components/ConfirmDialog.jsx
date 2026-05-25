import { AlertTriangle } from "lucide-react";
import DiffPreview from "./DiffPreview";
import { useTranslate } from "../lib/i18n.jsx";

export default function ConfirmDialog({
  open,
  title,
  message,
  patch,
  busy,
  confirmLabel,
  confirmDisabled = false,
  onCancel,
  onConfirm,
}) {
  const t = useTranslate();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/20 px-4 backdrop-blur-sm">
      <div className="card max-h-[88vh] w-full max-w-2xl overflow-auto p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-50 text-risk">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-zinc-950">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">{message}</p>
          </div>
        </div>
        {patch ? (
          <div className="mt-5">
            <p className="muted-label mb-2">{t("review.modal.diff_preview")}</p>
            <DiffPreview patch={patch} />
          </div>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <button className="secondary-button" onClick={onCancel} disabled={busy}>
            {t("common.cancel")}
          </button>
          <button className="primary-button" onClick={onConfirm} disabled={busy || confirmDisabled}>
            {confirmLabel || t("common.continue")}
          </button>
        </div>
      </div>
    </div>
  );
}
