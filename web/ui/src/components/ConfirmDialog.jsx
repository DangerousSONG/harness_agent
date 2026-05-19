import { AlertTriangle } from "lucide-react";

export default function ConfirmDialog({ open, title, message, busy, onCancel, onConfirm }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/20 px-4 backdrop-blur-sm">
      <div className="card w-full max-w-sm p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-50 text-risk">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-zinc-950">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">{message}</p>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button className="secondary-button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className="primary-button" onClick={onConfirm} disabled={busy}>
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
