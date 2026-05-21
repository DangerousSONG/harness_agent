import {
  Send,
  Paperclip,
  Wrench,
  Brain,
  AlertCircle,
  ShieldCheck,
  Sparkles,
  ChevronDown,
  ChevronRight,
  FileText,
  Route,
  Terminal,
  ClipboardCheck,
  Activity,
  Database,
  Check,
} from "lucide-react";
import { useMemo, useState } from "react";
import ReviewCard from "../components/ReviewCard";
import EmptyState from "../components/EmptyState";
import { formatDate } from "../lib/format";
import StatusPill from "../components/StatusPill";

const TYPE_STYLES = {
  answer: { label: "Answer", icon: Sparkles, className: "bg-zinc-100 text-zinc-700" },
  skill_result: { label: "Skill result", icon: Brain, className: "bg-blue-50 text-appleBlue" },
  memory_captured: { label: "Memory captured", icon: Brain, className: "bg-emerald-50 text-emerald-700" },
  proposed_action: { label: "Proposed action", icon: ShieldCheck, className: "bg-amber-50 text-risk" },
  clarification: { label: "Clarification", icon: Route, className: "bg-blue-50 text-appleBlue" },
  refused: { label: "Refused", icon: ShieldCheck, className: "bg-red-50 text-red-700" },
  review_created: { label: "Review created", icon: ClipboardCheck, className: "bg-amber-50 text-risk" },
  file_result: { label: "File result", icon: FileText, className: "bg-zinc-100 text-zinc-700" },
  command_result: { label: "Command result", icon: Terminal, className: "bg-zinc-100 text-zinc-700" },
  tool_result: { label: "Tool result", icon: Wrench, className: "bg-zinc-100 text-zinc-700" },
  approval_required: { label: "Approval required", icon: ShieldCheck, className: "bg-amber-50 text-risk" },
  error: { label: "Error", icon: AlertCircle, className: "bg-red-50 text-red-700" },
};

function Bubble({ role, message, children, time, onAction }) {
  const user = role === "user";
  const typeStyle = TYPE_STYLES[message?.type] || TYPE_STYLES.answer;
  const TypeIcon = typeStyle.icon;
  const actions = message?.actions || [];
  const trace = message?.trace || [];
  const showHeader = !user && message?.type;
  const showSkillMeta = showHeader && message.type !== "answer";
  return (
    <div className={`flex gap-3 ${user ? "justify-end" : "justify-start"}`}>
      {!user ? (
        <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-950 text-xs font-semibold text-white">
          A
        </span>
      ) : null}
      <div className={`${user ? "max-w-[70%] items-end" : "max-w-[78%] items-start"}`}>
        <div
          className={[
            "rounded-lg px-4 py-3 text-sm leading-6",
            user ? "bg-zinc-950 text-white shadow-hairline" : "border border-line bg-white text-zinc-900 shadow-soft",
          ].join(" ")}
        >
          {showHeader ? (
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium ${typeStyle.className}`}>
                <TypeIcon className="h-3.5 w-3.5" />
                {typeStyle.label}
              </span>
              {showSkillMeta && message.used_skill ? (
                <span className="rounded bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-600">
                  {message.used_skill}
                </span>
              ) : null}
              {message.memory_record_id ? (
                <span className="rounded bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
                  {message.memory_record_id}
                </span>
              ) : null}
              {message.intent ? (
                <span className="rounded bg-zinc-50 px-2 py-1 text-xs font-medium text-zinc-500">
                  {displayIntent(message.intent)}
                </span>
              ) : null}
              {message.risk ? (
                <span className="rounded bg-zinc-50 px-2 py-1 text-xs font-medium text-zinc-500">
                  {displayRisk(message.risk)}
                </span>
              ) : null}
            </div>
          ) : null}
          {showSkillMeta && message?.why ? (
            <p className="mb-2 text-xs leading-5 text-zinc-500">{message.why}</p>
          ) : null}
          {!user && trace.length ? <TraceList trace={trace} /> : null}
          <div className={trace.length && !user ? "mt-3 border-t border-line pt-3" : ""}>
            {trace.length && !user ? (
              <p className="muted-label mb-2">Final Result</p>
            ) : null}
            <MarkdownText text={children} />
          </div>
          {!user && message.type === "error" && message.data?.suggested_fix ? (
            <div className="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">
              {message.data.suggested_fix}
            </div>
          ) : null}
          {!user && actions.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {actions.map((action) => (
                <button
                  key={`${action.method}-${action.path}-${action.label}`}
                  type="button"
                  className={
                    action.primary === true || (action.requires_confirmation && action.primary !== false)
                      ? "primary-button"
                      : "secondary-button"
                  }
                  onClick={() => onAction?.(action, message)}
                >
                  {action.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <p className="mt-1 text-xs text-zinc-400">{time || formatDate(new Date().toISOString())}</p>
      </div>
      {user ? (
        <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-200 text-xs font-semibold text-zinc-700">
          U
        </span>
      ) : null}
    </div>
  );
}

const TRACE_ICONS = {
  analyze: Activity,
  reasoning_summary: Activity,
  skill_route: Route,
  tool_call: Wrench,
  command_trace: Terminal,
  file_trace: FileText,
  approval_event: ClipboardCheck,
  final_result: Check,
  next_action: ShieldCheck,
  asset_type: Database,
  asset_route: Route,
  tool_route: Route,
  tool_registry_check: ShieldCheck,
  sources: FileText,
  risk_note: ShieldCheck,
  preflight: ShieldCheck,
  safety_check: ShieldCheck,
  risk_decision: ShieldCheck,
};

const TRACE_LABELS = {
  analyze: "Analyze",
  reasoning_summary: "Analyze",
  skill_route: "Skill route",
  tool_call: "Tool call",
  command_trace: "Bash",
  file_trace: "File",
  approval_event: "Approval",
  final_result: "Final",
  next_action: "Next action",
  asset_type: "Asset type",
  asset_route: "Asset route",
  tool_route: "Tool route",
  tool_registry_check: "Tool registry check",
  sources: "Sources",
  risk_note: "Risk note",
  preflight: "Preflight",
  safety_check: "Safety check",
  risk_decision: "Risk decision",
};

function TraceList({ trace }) {
  const visible = (trace || []).filter((item) => item.type !== "final_result");
  if (!visible.length) return null;
  return (
    <div className="mt-3 space-y-2">
      {visible.map((item, index) => (
        <TraceCard key={`${item.type}-${item.title}-${index}`} item={item} />
      ))}
    </div>
  );
}

function TraceCard({ item }) {
  const [open, setOpen] = useState(false);
  const Icon = TRACE_ICONS[item.type] || Database;
  const label = traceTitle(item);
  const code = traceCode(item);
  const details = traceDetails(item);
  const hasDetails = Boolean(code || details);
  const attention = item.type === "approval_event";
  return (
    <div className={[
      "rounded-lg border shadow-hairline",
      attention ? "border-amber-200 bg-amber-50/60" : "border-line bg-zinc-50/80",
    ].join(" ")}>
      <button
        type="button"
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
        onClick={() => hasDetails && setOpen((value) => !value)}
      >
        <span className={[
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white shadow-hairline",
          attention ? "text-risk" : "text-zinc-600",
        ].join(" ")}>
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-zinc-900">{label}</span>
            {code ? <code className="truncate rounded bg-white px-1.5 py-0.5 text-xs text-zinc-600">{code}</code> : null}
          </div>
          {item.summary ? (
            <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-zinc-500">{item.summary}</p>
          ) : null}
        </div>
        <StatusPill status={item.status || "completed"} />
        {hasDetails ? (
          open ? <ChevronDown className="h-4 w-4 text-zinc-400" /> : <ChevronRight className="h-4 w-4 text-zinc-400" />
        ) : null}
      </button>
      {open ? (
        <div className="border-t border-line px-3 py-3">
          {code ? (
            <pre className="overflow-auto rounded-lg bg-white p-3 font-mono text-xs leading-6 text-zinc-700 shadow-hairline">
              {code}
            </pre>
          ) : null}
          {details ? (
            <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
              {details.map(([key, value]) => (
                <div key={key}>
                  <dt className="muted-label">{key}</dt>
                  <dd className="mt-1 break-words text-zinc-700">{String(value)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function traceTitle(item) {
  if (item.type === "file_trace") {
    const op = String(item.operation || "").toLowerCase();
    if (op === "read") return "Read";
    if (op === "write") return "Write";
    if (op === "write_preview") return "Write preview";
    if (op === "write_review") return "Write review";
    if (op === "edit_preview") return "Edit preview";
  }
  return item.title || TRACE_LABELS[item.type] || "Trace";
}

function traceCode(item) {
  if (item.command) return item.command;
  if (item.path && item.method) return `${item.method} ${item.path}`;
  if (item.path) return item.path;
  if (item.api_path) return item.api_path;
  return "";
}

function traceDetails(item) {
  const keys = [
    "tool_name",
    "skill_name",
    "reason",
    "confidence",
    "operation",
    "review_id",
    "review_type",
    "severity",
    "target_asset",
    "asset_type",
    "target",
    "workspace_scope",
    "secret_scan",
    "existing_file_check",
    "primary_intent",
    "candidate_intents",
    "mode",
    "needs_clarification",
    "risk_labels",
    "requires_realtime_data",
    "requires_disclaimer",
    "source_count",
    "missing",
    "executable",
    "provider_configured",
    "provider_mode",
    "provider",
    "urls",
    "crawl_status",
    "content_length",
    "handler_available",
    "asset_exists",
    "asset_name",
    "risk",
    "preview_content",
    "stdout",
    "stderr",
    "exit_code",
    "started_at",
    "ended_at",
    "duration",
    "suggested_fix",
  ];
  return keys
    .filter((key) => item[key])
    .map((key) => [titleLabel(key), item[key]]);
}

function displayIntent(intent) {
  if (!intent) return "";
  if (typeof intent === "string") return intent;
  return intent.primary || "unknown";
}

function displayRisk(risk) {
  if (!risk) return "";
  if (typeof risk === "string") return risk;
  return risk.level || "safe_read";
}

function titleLabel(value) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function MarkdownText({ text }) {
  const lines = String(text || "").split("\n");
  return (
    <div className="space-y-1">
      {lines.map((line, index) => {
        if (line.startsWith("# ")) {
          return <h2 key={index} className="pt-1 text-base font-semibold text-zinc-950">{line.slice(2)}</h2>;
        }
        if (line.startsWith("## ")) {
          return <h3 key={index} className="pt-2 text-sm font-semibold text-zinc-900">{line.slice(3)}</h3>;
        }
        if (!line.trim()) return <div key={index} className="h-1" />;
        return <p key={index} className="whitespace-pre-wrap break-words text-sm leading-6">{line}</p>;
      })}
    </div>
  );
}

function ToolStatus({ name, status }) {
  const parsed = parseToolName(name);
  return (
    <div className="ml-10 flex max-w-2xl items-center justify-between gap-4 rounded-lg border border-blue-100 bg-white px-4 py-3 shadow-hairline">
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-appleBlue">
          <Wrench className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-normal text-zinc-500">Tool call</p>
          <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2">
            {parsed.method ? (
              <span className="rounded bg-blue-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-appleBlue">
                {parsed.method}
              </span>
            ) : null}
            <code className="truncate text-xs font-semibold text-zinc-700">{parsed.path || parsed.label}</code>
          </div>
        </div>
      </div>
      <StatusPill status={status} />
    </div>
  );
}

function parseToolName(name) {
  const text = String(name || "");
  const match = text.match(/^(GET|POST|PUT|PATCH|DELETE)\s+(.+)$/i);
  if (!match) return { label: text, method: "", path: text };
  return { label: text, method: match[1].toUpperCase(), path: match[2] };
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
  onChatAction,
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
      <div className="border-b border-line bg-white/65 px-6 py-4">
        <h1 className="page-title">Chat</h1>
        <p className="page-subtitle">Conversation, workspace actions, and approval cards in one flow.</p>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-6 py-6">
        <div className="mx-auto max-w-5xl space-y-5">
          {(messages || []).map((message) => (
            message.role === "tool" ? (
              <ToolStatus
                key={message.id}
                name={message.name || message.text}
                status={message.status || "completed"}
              />
            ) : (
              <Bubble
                key={message.id}
                role={message.role}
                message={message}
                time={message.time}
                onAction={onChatAction}
              >
                {message.text}
              </Bubble>
            )
          ))}

          {toolEvents.map((event, index) => (
            <ToolStatus key={`${event.name}-${index}`} name={event.name} status={event.status} />
          ))}

          {activeReviews.map((review) => (
            <div className="ml-0 max-w-3xl md:ml-10" key={review.review_id}>
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
      <form className="border-t border-line bg-white/80 px-6 py-4" onSubmit={submit}>
        <div className="mx-auto flex max-w-5xl items-end gap-3 rounded-lg border border-line bg-white p-3 shadow-soft">
          <button type="button" className="icon-button" aria-label="Attach context">
            <Paperclip className="h-4 w-4" />
          </button>
          <textarea
            className="max-h-36 min-h-12 flex-1 resize-none bg-transparent px-1 py-2 text-sm outline-none placeholder:text-zinc-400"
            placeholder="Ask, write, improve, or run a workspace command…"
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
