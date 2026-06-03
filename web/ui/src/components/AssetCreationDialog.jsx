import { useEffect, useMemo, useState } from "react";
import { X, Sparkles, FileText, Github, Folder } from "lucide-react";
import { api, getErrorMessage } from "../lib/api";

// Method picker on the left side of the dialog. NL + blank are
// enabled; Git import and local folder are visible but disabled.
const METHODS = [
  { id: "nl", label: "自然语言创建", icon: Sparkles, enabled: true },
  { id: "blank", label: "空白资产", icon: FileText, enabled: true },
  { id: "git", label: "Git 导入", icon: Github, enabled: false, note: "即将支持" },
  { id: "local", label: "本地文件夹", icon: Folder, enabled: false, note: "即将支持" },
];

const STATUS_FLOW = [
  { id: "submitting", label: "创建中" },
  { id: "checking", label: "系统校验中" },
  { id: "settled", label: "完成" },
];

const HIGH_RISK_PERMISSIONS = new Set(["write_file", "shell", "high_risk"]);
const POLICY_OPTIONS = ["allow", "require_approval", "block"];
const PERMISSION_OPTIONS = ["read_only", "write_file", "network", "shell", "high_risk"];
const ENTRY_TYPE_OPTIONS = [
  { value: "python_function", label: "Python 函数" },
  { value: "http_api", label: "HTTP API" },
  { value: "shell_command", label: "Shell 命令" },
  { value: "mcp_tool", label: "MCP Tool" },
];

const LIFECYCLE_USER_LABEL = {
  active: "已上架",
  draft: "草稿",
  system_check: "系统校验中",
  pending_review: "待审查",
  rejected: "未通过",
  archived: "已归档",
  disabled: "已禁用",
};

export default function AssetCreationDialog({ open, kind, onClose, onCreated }) {
  const [method, setMethod] = useState("nl");
  const [stage, setStage] = useState("idle"); // idle | submitting | checking | settled
  const [result, setResult] = useState(null); // { ok, lifecycle_status, message, name }
  const [error, setError] = useState("");
  const [form, setForm] = useState(blankForm(kind));

  useEffect(() => {
    if (open) {
      setMethod("nl");
      setStage("idle");
      setResult(null);
      setError("");
      setForm(blankForm(kind));
    }
  }, [open, kind]);

  if (!open) return null;

  const isSkill = kind === "skill";
  const title = isSkill ? "创建 Skill" : "注册 Tool";

  const handleSubmit = async () => {
    setError("");
    const validation = validateForm(kind, method, form);
    if (validation) {
      setError(validation);
      return;
    }
    setStage("submitting");
    // Give the user a beat of visual feedback for "系统校验中" before
    // we report the verdict (server roundtrip is usually < 100ms).
    await sleep(120);
    setStage("checking");
    try {
      const payload = await callCreate(kind, method, form);
      setStage("settled");
      const lifecycle =
        payload?.data?.lifecycle_status
        || (payload?.data?.review_id ? "pending_review" : "active");
      const name =
        payload?.data?.skill_name
        || payload?.data?.tool_name
        || form.name
        || "";
      setResult({
        ok: true,
        lifecycle_status: lifecycle,
        message: payload?.message || "",
        name,
        review_id: payload?.data?.review_id || "",
      });
      onCreated?.();
    } catch (err) {
      setStage("settled");
      // The "rejected" lifecycle is sent as ok:false from the server.
      const apiPayload = err?.payload || {};
      setResult({
        ok: false,
        lifecycle_status: apiPayload?.data?.lifecycle_status || "rejected",
        message: apiPayload?.message || getErrorMessage(err),
        name: form.name || "",
      });
    }
  };

  const closeDialog = () => {
    if (stage === "submitting" || stage === "checking") return;
    onClose?.();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/40 p-4"
      onClick={closeDialog}
    >
      <div
        className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-line bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-zinc-950">{title}</h2>
            <p className="mt-0.5 text-xs text-zinc-500">
              选择创建方式，填写信息后点击「创建」。系统会自动完成校验和上架流转。
            </p>
          </div>
          <button
            className="rounded-full p-1.5 text-zinc-500 hover:bg-zinc-100"
            onClick={closeDialog}
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="grid flex-1 grid-cols-[14rem_minmax(0,1fr)] overflow-hidden">
          {/* Method picker */}
          <aside className="border-r border-line bg-zinc-50/60 p-3 text-sm">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
              创建方式
            </p>
            <ul className="space-y-1">
              {METHODS.map((m) => {
                const Icon = m.icon;
                const active = method === m.id;
                return (
                  <li key={m.id}>
                    <button
                      className={[
                        "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition",
                        !m.enabled
                          ? "cursor-not-allowed text-zinc-400"
                          : active
                            ? "bg-zinc-950 text-white"
                            : "text-zinc-700 hover:bg-white",
                      ].join(" ")}
                      onClick={() => m.enabled && setMethod(m.id)}
                      disabled={!m.enabled}
                    >
                      <Icon className="h-4 w-4" />
                      <span className="flex-1">{m.label}</span>
                      {!m.enabled ? (
                        <span className="rounded-full bg-zinc-200 px-1.5 py-0.5 text-[10px] text-zinc-600">
                          {m.note}
                        </span>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          {/* Form area */}
          <div className="overflow-auto p-5">
            {stage === "idle" ? (
              <FormBody
                kind={kind}
                method={method}
                form={form}
                onChange={(next) => setForm({ ...form, ...next })}
              />
            ) : (
              <StatusBody stage={stage} result={result} />
            )}
          </div>
        </div>

        <footer className="flex items-center justify-between border-t border-line bg-zinc-50/60 px-5 py-3">
          <p className="text-xs text-rose-600">{error}</p>
          <div className="flex gap-2">
            <button
              className="secondary-button"
              onClick={closeDialog}
              disabled={stage === "submitting" || stage === "checking"}
            >
              {stage === "settled" && result ? "完成" : "取消"}
            </button>
            {stage === "idle" ? (
              <button className="primary-button" onClick={handleSubmit}>
                创建
              </button>
            ) : null}
            {stage === "settled" && !result?.ok ? (
              <button
                className="primary-button"
                onClick={() => {
                  setStage("idle");
                  setResult(null);
                }}
              >
                返回修改
              </button>
            ) : null}
          </div>
        </footer>
      </div>
    </div>
  );
}

// ------------------------------------------------------------- form body

function FormBody({ kind, method, form, onChange }) {
  if (kind === "skill") {
    return method === "nl" ? (
      <SkillNlForm form={form} onChange={onChange} />
    ) : (
      <SkillBlankForm form={form} onChange={onChange} />
    );
  }
  return method === "nl" ? (
    <ToolNlForm form={form} onChange={onChange} />
  ) : (
    <ToolBlankForm form={form} onChange={onChange} />
  );
}

function SkillNlForm({ form, onChange }) {
  return (
    <div className="space-y-4">
      <FieldText
        label="资产名称（可选）"
        placeholder="不填则系统自动生成"
        value={form.name}
        onChange={(v) => onChange({ name: v })}
      />
      <FieldTextArea
        label="资产需求"
        placeholder="用中文描述你希望这个 Skill 能做什么，比如 “写读书笔记，输出固定结构的 markdown 报告”。"
        value={form.description}
        onChange={(v) => onChange({ description: v })}
      />
      <FieldSelect
        label="可见性"
        value={form.visibility}
        onChange={(v) => onChange({ visibility: v })}
        options={[
          { value: "workspace", label: "工作区内可见" },
          { value: "private", label: "仅自己可见" },
        ]}
      />
    </div>
  );
}

function SkillBlankForm({ form, onChange }) {
  return (
    <div className="space-y-4">
      <FieldText
        label="Skill 名称"
        placeholder="例如 markdown_writer"
        value={form.name}
        onChange={(v) => onChange({ name: v })}
      />
      <FieldTextArea
        label="描述"
        placeholder="简要描述这个 Skill 的能力。"
        value={form.description}
        onChange={(v) => onChange({ description: v })}
      />
      <FieldText
        label="标签（逗号分隔）"
        placeholder="例如 writing, markdown"
        value={form.tags}
        onChange={(v) => onChange({ tags: v })}
      />
      <FieldSelect
        label="可见性"
        value={form.visibility}
        onChange={(v) => onChange({ visibility: v })}
        options={[
          { value: "workspace", label: "工作区内可见" },
          { value: "private", label: "仅自己可见" },
        ]}
      />
    </div>
  );
}

function ToolNlForm({ form, onChange }) {
  return (
    <div className="space-y-4">
      <FieldText
        label="Tool 名称（可选）"
        placeholder="不填则系统自动生成"
        value={form.name}
        onChange={(v) => onChange({ name: v })}
      />
      <FieldTextArea
        label="Tool 需求"
        placeholder="用中文描述工具能力，比如 “查询天气，输入城市，返回温度和天气状况”。"
        value={form.description}
        onChange={(v) => onChange({ description: v })}
      />
      <div className="grid grid-cols-2 gap-3">
        <FieldSelect
          label="权限级别"
          value={form.permission}
          onChange={(v) => onChange({ permission: v })}
          options={PERMISSION_OPTIONS.map((p) => ({ value: p, label: p }))}
        />
        <FieldSelect
          label="默认策略"
          value={form.default_policy}
          onChange={(v) => onChange({ default_policy: v })}
          options={POLICY_OPTIONS.map((p) => ({ value: p, label: p }))}
        />
      </div>
      <PolicyWarning form={form} />
    </div>
  );
}

function ToolBlankForm({ form, onChange }) {
  return (
    <div className="space-y-4">
      <FieldText
        label="Tool 名称"
        placeholder="例如 weather_query"
        value={form.name}
        onChange={(v) => onChange({ name: v })}
      />
      <FieldTextArea
        label="描述"
        placeholder="简要描述工具能力。"
        value={form.description}
        onChange={(v) => onChange({ description: v })}
      />
      <div className="grid grid-cols-2 gap-3">
        <FieldSelect
          label="入口类型"
          value={form.entry_type}
          onChange={(v) => onChange({ entry_type: v })}
          options={ENTRY_TYPE_OPTIONS}
        />
        <FieldText
          label="入口地址 / 函数路径"
          placeholder="例如 tools.weather.query / https://…"
          value={form.entry_path}
          onChange={(v) => onChange({ entry_path: v })}
        />
      </div>
      <FieldTextArea
        label="参数 Schema（JSON）"
        placeholder='例如 {"city": {"type": "string"}}'
        value={form.inputs_schema}
        onChange={(v) => onChange({ inputs_schema: v })}
        rows={4}
      />
      <div className="grid grid-cols-2 gap-3">
        <FieldSelect
          label="权限级别"
          value={form.permission}
          onChange={(v) => onChange({ permission: v })}
          options={PERMISSION_OPTIONS.map((p) => ({ value: p, label: p }))}
        />
        <FieldSelect
          label="默认策略"
          value={form.default_policy}
          onChange={(v) => onChange({ default_policy: v })}
          options={POLICY_OPTIONS.map((p) => ({ value: p, label: p }))}
        />
      </div>
      <PolicyWarning form={form} />
    </div>
  );
}

function PolicyWarning({ form }) {
  if (
    HIGH_RISK_PERMISSIONS.has(form.permission)
    && form.default_policy === "allow"
  ) {
    return (
      <p className="rounded-md border border-rose-200 bg-rose-50/60 px-3 py-2 text-xs text-rose-700">
        该权限级别不能使用直接允许策略，请选择 require_approval 或 block。
      </p>
    );
  }
  return null;
}

// ----------------------------------------------------------- status body

function StatusBody({ stage, result }) {
  return (
    <div className="space-y-4">
      <ol className="grid grid-cols-3 gap-2">
        {STATUS_FLOW.map((step, idx) => {
          const reached = stageIndex(stage) >= idx || (stage === "settled" && idx <= 2);
          return (
            <li
              key={step.id}
              className={[
                "rounded-lg border px-3 py-2 text-center text-xs font-semibold",
                reached
                  ? "border-emerald-200 bg-emerald-50/60 text-emerald-800"
                  : "border-line bg-zinc-50 text-zinc-500",
              ].join(" ")}
            >
              {idx + 1}. {step.label}
            </li>
          );
        })}
      </ol>

      {stage !== "settled" ? (
        <p className="text-center text-sm text-zinc-600">
          {stage === "submitting" ? "正在提交资产草稿…" : "系统正在自动校验…"}
        </p>
      ) : result ? (
        <ResultPanel result={result} />
      ) : null}
    </div>
  );
}

function ResultPanel({ result }) {
  const status = result.lifecycle_status;
  const tone =
    status === "active"
      ? "border-emerald-200 bg-emerald-50/60 text-emerald-900"
      : status === "rejected"
        ? "border-rose-200 bg-rose-50/60 text-rose-800"
        : "border-amber-200 bg-amber-50/60 text-amber-900";
  const headline = headlineFor(status);
  return (
    <div className={`rounded-lg border px-4 py-3 ${tone}`}>
      <p className="text-sm font-semibold">{headline}</p>
      {result.name ? (
        <p className="mt-1 text-xs">
          资产：<span className="font-mono">{result.name}</span> · 状态：
          <span className="font-medium">
            {LIFECYCLE_USER_LABEL[status] || status}
          </span>
        </p>
      ) : null}
      {status === "pending_review" && result.review_id ? (
        <p className="mt-1 text-xs text-zinc-600">
          已生成审查项：<span className="font-mono">{result.review_id}</span>
        </p>
      ) : null}
      {result.message ? (
        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">
          {result.message}
        </p>
      ) : null}
    </div>
  );
}

function headlineFor(status) {
  if (status === "active") return "创建成功，资产已上架。";
  if (status === "pending_review") return "资产已创建，系统校验后进入审查，审查通过后将自动上架。";
  if (status === "rejected") return "创建未通过，请调整资产配置后重试。";
  return "已提交，处理中。";
}

// ------------------------------------------------------------ controls

function FieldText({ label, value, onChange, placeholder }) {
  return (
    <label className="block text-sm">
      <span className="text-xs font-medium text-zinc-600">{label}</span>
      <input
        className="mt-1 w-full rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function FieldTextArea({ label, value, onChange, placeholder, rows = 5 }) {
  return (
    <label className="block text-sm">
      <span className="text-xs font-medium text-zinc-600">{label}</span>
      <textarea
        className="mt-1 w-full rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
        value={value}
        placeholder={placeholder}
        rows={rows}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function FieldSelect({ label, value, onChange, options }) {
  return (
    <label className="block text-sm">
      <span className="text-xs font-medium text-zinc-600">{label}</span>
      <select
        className="mt-1 w-full rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-zinc-400"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

// ------------------------------------------------------------- helpers

function blankForm(kind) {
  if (kind === "skill") {
    return {
      name: "",
      description: "",
      tags: "",
      visibility: "workspace",
    };
  }
  return {
    name: "",
    description: "",
    entry_type: "python_function",
    entry_path: "",
    inputs_schema: "",
    permission: "read_only",
    default_policy: "require_approval",
  };
}

function validateForm(kind, method, form) {
  const description = (form.description || "").trim();
  if (method !== "nl" && !(form.name || "").trim()) {
    return kind === "skill" ? "请填写 Skill 名称。" : "请填写 Tool 名称。";
  }
  if (method === "nl" && !description) {
    return kind === "skill"
      ? "请描述这个 Skill 的能力需求。"
      : "请描述这个 Tool 的能力需求。";
  }
  if (kind === "tool") {
    if (
      HIGH_RISK_PERMISSIONS.has(form.permission)
      && form.default_policy === "allow"
    ) {
      return "该权限级别不能使用直接允许策略，请选择 require_approval 或 block。";
    }
    if (method === "blank" && form.inputs_schema) {
      try {
        const parsed = JSON.parse(form.inputs_schema);
        if (typeof parsed !== "object" || Array.isArray(parsed)) {
          return "参数 Schema 必须是 JSON 对象。";
        }
      } catch {
        return "参数 Schema 不是合法的 JSON。";
      }
    }
  }
  return "";
}

function stageIndex(stage) {
  if (stage === "submitting") return 0;
  if (stage === "checking") return 1;
  if (stage === "settled") return 2;
  return -1;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function callCreate(kind, method, form) {
  if (kind === "skill") {
    const body = {
      skill_name: (form.name || "").trim() || guessSkillName(form.description),
      description: (form.description || "").trim(),
    };
    if (method === "blank") {
      body.metadata = {
        tags: parseTags(form.tags),
        visibility: form.visibility,
      };
    }
    return api.proposeSkill(body);
  }
  const toolName = (form.name || "").trim() || guessToolName(form.description);
  const body = {
    tool_name: toolName,
    description: (form.description || "").trim(),
    confirmed: true,
  };
  if (method === "blank") {
    body.files = [
      {
        path: `tools/${toolName}/tool.yaml`,
        content: composeToolYaml(toolName, form),
      },
    ];
  }
  return api.createTool(body);
}

function parseTags(raw) {
  return (raw || "")
    .split(/[,，]/)
    .map((t) => t.trim())
    .filter(Boolean);
}

function guessSkillName(description) {
  const text = (description || "").toLowerCase().trim();
  if (!text) return `skill_${Date.now().toString(36)}`;
  const m = text.match(/[a-z][a-z0-9_]{2,30}/);
  return m ? m[0] : `skill_${Date.now().toString(36)}`;
}

function guessToolName(description) {
  const text = (description || "").toLowerCase().trim();
  if (!text) return `tool_${Date.now().toString(36)}`;
  const m = text.match(/[a-z][a-z0-9_]{2,30}/);
  return m ? m[0] : `tool_${Date.now().toString(36)}`;
}

function composeToolYaml(toolName, form) {
  const lines = [
    `name: ${toolName}`,
    `description: ${(form.description || "").replace(/\n/g, " ").trim()}`,
    `entry_type: ${mapEntryType(form.entry_type)}`,
  ];
  if (form.entry_path) lines.push(`entry_path: ${form.entry_path}`);
  lines.push(`permissions:`);
  lines.push(`  - ${form.permission}`);
  lines.push(`default_policy: ${form.default_policy}`);
  if (form.inputs_schema) {
    lines.push(`inputs: ${form.inputs_schema}`);
  }
  return lines.join("\n") + "\n";
}

function mapEntryType(value) {
  switch (value) {
    case "python_function":
      return "python_function";
    case "http_api":
      return "http_get";
    case "shell_command":
      return "shell";
    case "mcp_tool":
      return "mcp_tool";
    default:
      return value || "python_function";
  }
}
