import { useState } from "react";
import { Eye } from "lucide-react";
import EmptyState from "../components/EmptyState";
import Paginator, { paginate } from "../components/Paginator";
import StatusPill from "../components/StatusPill";
import { compact, formatDate, titleize } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";

export default function ReviewsPage({ reviews, actionProps, embedded = false }) {
  const t = useTranslate();
  const [page, setPage] = useState(1);
  const { pageItems, total, pageCount, page: safePage } = paginate(reviews || [], page);
  return (
    <section className="workbench-section">
      <div className="workbench-container">
        {!embedded ? <div className="mb-6">
          <h1 className="page-title">{t("reviews.title")}</h1>
          <p className="page-subtitle">{t("reviews.subtitle")}</p>
        </div> : null}
        {!reviews?.length ? (
          <EmptyState title={t("reviews.empty")} />
        ) : (
          <div className="section-panel overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full table-fixed divide-y divide-line text-sm">
                <colgroup>
                  <col className="w-[9.5rem]" />
                  <col className="w-[10rem]" />
                  <col className="w-[7rem]" />
                  <col className="w-[6rem]" />
                  <col />
                  <col className="w-[10rem]" />
                  <col className="w-[8.5rem]" />
                  <col className="w-[10rem]" />
                  <col className="w-[13rem]" />
                </colgroup>
                <thead className="bg-zinc-50/80 text-left text-[11px] font-semibold uppercase tracking-normal text-zinc-500">
                  <tr>
                    {[
                      "review_id",
                      "type",
                      "status",
                      "severity",
                      "target_files",
                      "candidate_id",
                      "created_at",
                      "next_action",
                      "",
                    ].map((header) => (
                      <th className="px-4 py-3.5" key={header}>
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-white">
                  {pageItems.map((review) => (
                    <tr key={review.review_id} className="align-top transition hover:bg-blue-50/35">
                      <td className="px-4 py-4">
                        <span className="mono-badge">{review.review_id}</span>
                      </td>
                      <td className="break-words px-4 py-4 font-medium text-zinc-900">{titleize(review.type)}</td>
                      <td className="px-4 py-4"><StatusPill status={review.status} /></td>
                      <td className="px-4 py-4 text-zinc-700">{titleize(review.severity)}</td>
                      <td className="break-words px-4 py-4 font-mono text-xs leading-5 text-zinc-600">{compact(review.target_files)}</td>
                      <td className="px-4 py-4">
                        <span className="mono-badge break-all">{compact(review.candidate_id)}</span>
                      </td>
                      <td className="px-4 py-4 text-xs leading-5 text-zinc-500">{formatDate(review.created_at)}</td>
                      <td className="break-words px-4 py-4 font-mono text-xs leading-5 text-zinc-600">{compact(review.next_actions?.[0], "-")}</td>
                      <td className="px-4 py-4">
                        <div className="flex flex-wrap justify-end gap-2">
                          <button className="secondary-button px-3 py-1.5" onClick={() => actionProps.onDetails(review.review_id)}>
                            <Eye className="h-4 w-4" />
                            {t("review.action.review_details")}
                          </button>
                          {review.status === "pending" ? (
                            <button
                              className="subprimary-button px-3 py-1.5"
                              disabled={actionProps.busyReviewId === review.review_id}
                              onClick={() => actionProps.onApprove(review.review_id)}
                            >
                              {actionProps.busyReviewId === review.review_id ? t("common.generating") : t("review.action.generate_preview")}
                            </button>
                          ) : null}
                          {review.status === "approved" ? (
                            <button
                              className="primary-button px-3 py-1.5"
                              disabled={actionProps.busyReviewId === review.review_id}
                              onClick={() => actionProps.onApply(review.review_id)}
                            >
                              {actionProps.busyReviewId === review.review_id ? t("common.applying") : t("review.action.apply_change")}
                            </button>
                          ) : null}
                          {review.status === "pending" ? (
                            <button
                              className="danger-button px-3 py-1.5"
                              disabled={actionProps.busyReviewId === review.review_id}
                              onClick={() => actionProps.onReject(review.review_id)}
                            >
                              {actionProps.busyReviewId === review.review_id ? t("common.rejecting") : t("review.action.reject")}
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Paginator page={safePage} pageCount={pageCount} total={total} onPage={setPage} />
          </div>
        )}
      </div>
    </section>
  );
}
