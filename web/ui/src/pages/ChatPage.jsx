import { Send, Paperclip, Wrench, Check } from "lucide-react";
import { useMemo, useState } from "react";
import ReviewCard from "../components/ReviewCard";
import EmptyState from "../components/EmptyState";
import { formatDate } from "../lib/format";

function Bubble({ role, children, time }) {
  const user = role === "user";
  return (
    <div className={`flex gap-3 ${user ? "justify-end" : "justify-start"}`}>
      {!user ? (
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-950 text-xs font-semibold text-white">
          A
        </span>
      ) : null}
      <div className={`max-w-xl ${user ? "items-end" : "items-start"}`}>
        <div
          className={[
            "rounded-lg px-4 py-3 text-sm leading-6 shadow-hairline",
            user ? "bg-zinc-950 text-white" : "border border-line bg-white text-zinc-900",
          ].join(" ")}
        >
          {children}
        </div>
        <p className="mt-1 text-xs text-zinc-400">{time || formatDate(new Date().toISOString())}</p>
      </div>
      {user ? (
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-200 text-xs font-semibold text-zinc-700">
          U
        </span>
      ) : null}
    </div>
  );
}

function ToolStatus({ name, status }) {
  return (
    <div className="ml-12 flex max-w-md items-center justify-between rounded-lg border border-line bg-white px-4 py-3 shadow-hairline">
      <div className="flex items-center gap-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-appleBlue">
          <Wrench className="h-4 w-4" />
        </span>
        <span className="text-sm text-zinc-700">Tool call: {name}</span>
      </div>
      <span className="flex items-center gap-1 text-xs font-medium text-emerald-600">
        <Check className="h-3.5 w-3.5" />
        {status}
      </span>
    </div>
  );
}

export default function ChatPage({
  reviews,
  dashboard,
  messages,
  onSend,
  sending,
  input,
  onInput,
  actionProps,
}) {
  const activeReviews = useMemo(
    () => (reviews || []).filter((review) => ["pending", "approved"].includes(review.status)),
    [reviews],
  );
  const toolEvents = useMemo(() => {
    const events = dashboard?.recent_events || [];
    return events
      .map((event) => ({
        name: event.tool || event.target || event.event || "safeharness",
        status: event.decision?.action || event.decision || "completed",
      }))
      .slice(-2);
  }, [dashboard]);

  const [draft, setDraft] = useState("");
  const value = input ?? draft;
  const setValue = onInput ?? setDraft;

  function submit(event) {
    event.preventDefault();
    const message = value.trim();
    if (!message) return;
    onSend(message);
    setValue("");
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-line bg-white/55 px-5 py-4">
        <h1 className="text-lg font-semibold text-zinc-950">Chat</h1>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-5 py-6">
        <div className="mx-auto max-w-3xl space-y-5">
          {(messages || []).map((message) => (
            <Bubble key={message.id} role={message.role} time={message.time}>
              {message.text}
            </Bubble>
          ))}

          {toolEvents.map((event, index) => (
            <ToolStatus key={`${event.name}-${index}`} name={event.name} status={event.status} />
          ))}

          {activeReviews.map((review) => (
            <div className="ml-0 md:ml-12" key={review.review_id}>
              <ReviewCard
                review={review}
                busy={actionProps.busyReviewId === review.review_id}
                onDetails={() => actionProps.onDetails(review.review_id)}
                onApprove={() => actionProps.onApprove(review.review_id)}
                onApply={() => actionProps.onApply(review.review_id)}
                onReject={() => actionProps.onReject(review.review_id)}
              />
            </div>
          ))}

          {!messages?.length && !activeReviews.length ? (
            <EmptyState title="SafeHarness Console is ready." detail="Agent review cards will appear here automatically when approval is required." />
          ) : null}
        </div>
      </div>
      <form className="border-t border-line bg-white/70 px-5 py-4" onSubmit={submit}>
        <div className="mx-auto flex max-w-3xl items-end gap-3 rounded-lg border border-line bg-white p-3 shadow-soft">
          <button type="button" className="icon-button" aria-label="Attach context">
            <Paperclip className="h-4 w-4" />
          </button>
          <textarea
            className="max-h-36 min-h-12 flex-1 resize-none bg-transparent px-1 py-2 text-sm outline-none placeholder:text-zinc-400"
            placeholder="Message Agent..."
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button className="primary-button h-10 w-10 px-0" type="submit" disabled={sending}>
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-3 text-center text-xs text-zinc-400">
          SafeHarness Console - Local First, Always in Control.
        </p>
      </form>
    </section>
  );
}
