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
import { useEffect, useMemo, useState } from "react";
import ReviewCard from "../components/ReviewCard";
import EmptyState from "../components/EmptyState";
import MarkdownText from "../components/MarkdownText";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";
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
  const t = useTranslate();
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
            <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px] leading-4">
              <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium ${typeStyle.className}`}>
                <TypeIcon className="h-3 w-3" />
                {typeStyle.label}
              </span>
              {showSkillMeta && message.used_skill ? (
                <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-medium text-zinc-600">
                  {message.used_skill}
                </span>
              ) : null}
              {message.memory_record_id ? (
                <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-medium text-emerald-700">
                  {message.memory_record_id}
                </span>
              ) : null}
              {message.intent ? (
                <span className="rounded px-1.5 py-0.5 font-medium text-zinc-400">
                  {displayIntent(message.intent)}
                </span>
              ) : null}
              {message.risk ? (
                <span className="rounded px-1.5 py-0.5 font-medium text-zinc-400">
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
              <p className="muted-label mb-2">{t("chat.final_result")}</p>
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
  task_mode: Route,
  capability_check: ShieldCheck,
  decision: ShieldCheck,
  search: Activity,
  crawl: Database,
  summarize: FileText,
  model_call: Brain,
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
  task_mode: "Task mode",
  capability_check: "Capability check",
  decision: "Decision",
  search: "Search",
  crawl: "Crawl",
  summarize: "Summarize",
  model_call: "Model call",
};

function TraceList({ trace }) {
  const t = useTranslate();
  const [showAll, setShowAll] = useState(false);
  // next_action items are already rendered as buttons inside the bubble.
  const items = (trace || []).filter(
    (item) => item.type !== "final_result" && item.type !== "next_action",
  );
  if (!items.length) return null;
  const essential = items.filter(
    (item) => item.essential || item.status === "failed" || item.status === "blocked",
  );
  const visible = showAll ? items : essential;
  const hiddenCount = items.length - visible.length;
  if (!visible.length && !hiddenCount) return null;
  return (
    <div className="mt-3 space-y-2">
      {visible.map((item, index) => (
        <TraceCard key={`${item.type}-${item.title}-${index}`} item={item} />
      ))}
      {hiddenCount > 0 ? (
        <button
          type="button"
          className="text-xs text-zinc-500 hover:text-zinc-800 underline-offset-2 hover:underline"
          onClick={() => setShowAll(true)}
        >
          {t("chat.show_all_steps", { total: items.length, hidden: hiddenCount })}
        </button>
      ) : showAll && essential.length && essential.length < items.length ? (
        <button
          type="button"
          className="text-xs text-zinc-500 hover:text-zinc-800 underline-offset-2 hover:underline"
          onClick={() => setShowAll(false)}
        >
          {t("chat.hide_internal_steps")}
        </button>
      ) : null}
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

function ToolStatus({ name, status }) {
  const t = useTranslate();
  const parsed = parseToolName(name);
  const displayName = parsed.path || parsed.label || name;
  return (
    <div className="ml-10 inline-flex max-w-2xl items-center gap-3 rounded-full border border-line bg-white py-1.5 pl-1.5 pr-3 shadow-hairline">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-50 text-appleBlue">
        <Wrench className="h-3.5 w-3.5" />
      </span>
      <div className="flex min-w-0 items-center gap-2">
        <span className="text-xs font-semibold text-zinc-600">{t("trace.tool_call")}:</span>
        {parsed.method ? (
          <span className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-appleBlue">
            {parsed.method}
          </span>
        ) : null}
        <code className="truncate text-xs font-medium text-zinc-900">{displayName}</code>
      </div>
      <span className="ml-auto shrink-0">
        <StatusPill status={status} />
      </span>
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
  const t = useTranslate();
  const activeReviews = useMemo(
    () => (reviews || []).filter((review) => ["pending", "approved"].includes(review.status)),
    [reviews],
  );

  const [draft, setDraft] = useState("");
  const value = input ?? draft;
  const setValue = onInput ?? setDraft;
  const [kbList, setKbList] = useState([]);
  const [selectedKbIds, setSelectedKbIds] = useState([]);
  const [showKbPicker, setShowKbPicker] = useState(false);

  useEffect(() => {
    api.knowledgeBases().then((result) => setKbList(result.data || [])).catch(() => {});
  }, []);

  const toggleKb = (id) => {
    setSelectedKbIds((prev) => {
      if (prev.includes(id)) return prev.filter((item) => item !== id);
      if (prev.length >= 3) return prev;
      return [...prev, id];
    });
  };

  function submit(event) {
    event.preventDefault();
    const message = value.trim();
    if (!message) return;
    const context = selectedKbIds.length ? { kb_ids: selectedKbIds } : undefined;
    onSend(message, context);
    setValue("");
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-line bg-white/65 px-6 py-4">
        <h1 className="page-title">{t("chat.title")}</h1>
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
        <div className="mx-auto max-w-5xl">
          {selectedKbIds.length || showKbPicker ? (
            <div className="mb-2 flex flex-wrap items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-xs">
              <span className="font-semibold text-zinc-600">{t("chat.kb.label")}:</span>
              {selectedKbIds.map((id) => {
                const kb = kbList.find((item) => item.kb_id === id);
                return (
                  <span
                    key={id}
                    className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-appleBlue"
                  >
                    {kb?.name || id}
                    <button
                      type="button"
                      onClick={() => toggleKb(id)}
                      className="text-appleBlue hover:text-blue-700"
                      aria-label="Remove"
                    >
                      ×
                    </button>
                  </span>
                );
              })}
              <span className="text-zinc-400">{selectedKbIds.length}/3</span>
              <button
                type="button"
                className="ml-auto text-zinc-500 hover:text-zinc-800"
                onClick={() => setShowKbPicker((prev) => !prev)}
              >
                {showKbPicker ? t("chat.kb.close_picker") : t("chat.kb.add_more")}
              </button>
            </div>
          ) : null}

          {showKbPicker ? (
            <div className="mb-2 max-h-40 overflow-auto rounded-lg border border-line bg-white p-2 text-xs">
              {!kbList.length ? (
                <p className="text-zinc-500">{t("chat.kb.empty")}</p>
              ) : (
                kbList.map((kb) => {
                  const checked = selectedKbIds.includes(kb.kb_id);
                  const disabled = !checked && selectedKbIds.length >= 3;
                  return (
                    <label
                      key={kb.kb_id}
                      className={[
                        "flex items-center gap-2 rounded px-2 py-1",
                        disabled ? "opacity-40" : "hover:bg-zinc-50",
                      ].join(" ")}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={() => toggleKb(kb.kb_id)}
                      />
                      <span className="font-semibold text-zinc-900">{kb.name}</span>
                      <span className="font-mono text-[10px] text-zinc-500">{kb.kb_id}</span>
                      <span className="ml-auto text-[10px] text-zinc-500">
                        {kb.file_count} files
                      </span>
                    </label>
                  );
                })
              )}
            </div>
          ) : null}
        </div>
        <div className="mx-auto flex max-w-5xl items-end gap-2 rounded-2xl border border-line bg-white p-2.5 shadow-hairline focus-within:border-zinc-300 focus-within:shadow-soft">
          <button
            type="button"
            className={[
              "inline-flex h-9 items-center gap-1.5 rounded-full border px-2.5 text-xs font-semibold transition",
              selectedKbIds.length || showKbPicker
                ? "border-appleBlue/30 bg-blue-50 text-appleBlue"
                : "border-line bg-white text-zinc-600 hover:bg-zinc-50",
            ].join(" ")}
            onClick={() => setShowKbPicker((prev) => !prev)}
            title={t("chat.kb.button_title")}
          >
            <Paperclip className="h-3.5 w-3.5" />
            {t("chat.kb.label")} {selectedKbIds.length}/3
          </button>
          <textarea
            className="max-h-36 min-h-9 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm leading-6 outline-none placeholder:text-zinc-400"
            placeholder={t("chat.placeholder")}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button className="primary-button h-9 w-9 rounded-full px-0" type="submit" disabled={sending}>
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-2 text-center text-[11px] text-zinc-400">
          SafeHarness Console — Local First, Always in Control.
        </p>
      </form>
    </section>
  );
}
