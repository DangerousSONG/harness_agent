import { Eye } from "lucide-react";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import { compact, formatDate, titleize } from "../lib/format";

export default function ReviewsPage({ reviews, actionProps }) {
  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-zinc-950">Reviews</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Approval, preview, apply, and reject actions stay behind the backend review queue.
          </p>
        </div>
        {!reviews?.length ? (
          <EmptyState title="No reviews waiting for approval." />
        ) : (
          <div className="card overflow-hidden">
            <div className="overflow-auto">
              <table className="min-w-full divide-y divide-line text-sm">
                <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase tracking-normal text-zinc-500">
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
                      <th className="whitespace-nowrap px-4 py-3" key={header}>
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-white">
                  {reviews.map((review) => (
                    <tr key={review.review_id} className="align-top">
                      <td className="px-4 py-4 font-semibold">{review.review_id}</td>
                      <td className="px-4 py-4">{titleize(review.type)}</td>
                      <td className="px-4 py-4"><StatusPill status={review.status} /></td>
                      <td className="px-4 py-4">{titleize(review.severity)}</td>
                      <td className="max-w-xs px-4 py-4 text-zinc-600">{compact(review.target_files)}</td>
                      <td className="px-4 py-4">{compact(review.candidate_id)}</td>
                      <td className="px-4 py-4 text-zinc-500">{formatDate(review.created_at)}</td>
                      <td className="px-4 py-4 text-zinc-600">{compact(review.next_actions?.[0], "-")}</td>
                      <td className="px-4 py-4">
                        <div className="flex flex-wrap justify-end gap-2">
                          <button className="secondary-button" onClick={() => actionProps.onDetails(review.review_id)}>
                            <Eye className="h-4 w-4" />
                            Details
                          </button>
                          {review.status === "pending" ? (
                            <button className="secondary-button" onClick={() => actionProps.onApprove(review.review_id)}>
                              Generate Preview
                            </button>
                          ) : null}
                          {review.status === "approved" ? (
                            <button className="primary-button" onClick={() => actionProps.onApply(review.review_id)}>
                              Apply Change
                            </button>
                          ) : null}
                          {review.status === "pending" ? (
                            <button className="danger-button" onClick={() => actionProps.onReject(review.review_id)}>
                              Reject
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
