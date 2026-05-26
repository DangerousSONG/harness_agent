import { useState } from "react";
import { useTranslate } from "../lib/i18n.jsx";

export const DEFAULT_PAGE_SIZE = 10;

export function paginate(items, page, pageSize = DEFAULT_PAGE_SIZE) {
  const total = items?.length || 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page || 1), pageCount);
  const start = (safePage - 1) * pageSize;
  return {
    pageItems: (items || []).slice(start, start + pageSize),
    total,
    pageCount,
    page: safePage,
  };
}

export function usePagination() {
  const [page, setPage] = useState(1);
  return [page, setPage];
}

export default function Paginator({ page, pageCount, total, onPage, pageSize = DEFAULT_PAGE_SIZE }) {
  const t = useTranslate();
  if (total <= pageSize) return null;
  return (
    <div className="mt-3 flex items-center justify-between rounded-md border border-line bg-white px-3 py-2 text-xs text-zinc-600">
      <span>
        {t("pagination.range", {
          start: (page - 1) * pageSize + 1,
          end: Math.min(page * pageSize, total),
          total,
        })}
      </span>
      <div className="flex items-center gap-2">
        <button
          className="rounded-md border border-line bg-white px-2 py-1 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => onPage(Math.max(1, page - 1))}
          disabled={page <= 1}
        >
          ←
        </button>
        <span className="font-mono">{page} / {pageCount}</span>
        <button
          className="rounded-md border border-line bg-white px-2 py-1 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => onPage(Math.min(pageCount, page + 1))}
          disabled={page >= pageCount}
        >
          →
        </button>
      </div>
    </div>
  );
}
