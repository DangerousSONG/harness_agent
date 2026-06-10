import { X } from "lucide-react";
import { useEffect } from "react";

// Size scale shared by every modal/dialog on the workbench so the
// "卡片一会儿大一会儿小" feeling is gone. Three tiers cover everything:
//
//   sm  — single-decision confirms (delete? approve?)
//   md  — forms (create skill / tool)
//   lg  — rich detail (asset detail with file viewer)
const SIZE_CLASS = {
  sm: "max-w-md",
  md: "max-w-2xl",
  lg: "max-w-5xl",
};

export default function Modal({
  open,
  onClose,
  size = "md",
  title,
  subtitle,
  children,
  footer,
  closeOnBackdrop = true,
  contentClassName = "",
  bodyClassName = "p-5",
}) {
  // ESC closes; lock body scroll while open.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-[modalFade_0.16s_ease-out]"
      style={{ background: "rgba(9, 9, 11, 0.42)" }}
      onClick={closeOnBackdrop ? onClose : undefined}
    >
      <div
        className={[
          "flex max-h-[88vh] w-full flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-xl",
          "animate-[modalRise_0.18s_ease-out]",
          SIZE_CLASS[size] || SIZE_CLASS.md,
          contentClassName,
        ].join(" ")}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {title || subtitle ? (
          <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
            <div className="min-w-0">
              {title ? (
                <h2 className="text-base font-semibold text-zinc-950">{title}</h2>
              ) : null}
              {subtitle ? (
                <p className="mt-0.5 text-xs leading-relaxed text-zinc-500">{subtitle}</p>
              ) : null}
            </div>
            {onClose ? (
              <button
                className="rounded-full p-1.5 text-zinc-500 transition hover:bg-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-200"
                onClick={onClose}
                aria-label="关闭"
              >
                <X className="h-4 w-4" />
              </button>
            ) : null}
          </header>
        ) : null}
        <div className={["flex-1 overflow-auto", bodyClassName].join(" ")}>{children}</div>
        {footer ? (
          <footer className="flex items-center justify-end gap-2 border-t border-line bg-zinc-50/60 px-5 py-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  );
}
