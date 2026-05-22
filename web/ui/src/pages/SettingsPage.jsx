import { useEffect, useState } from "react";
import { Cpu, KeyRound, ShieldCheck, SlidersHorizontal, Save } from "lucide-react";
import { api, getErrorMessage } from "../lib/api";
import { compact } from "../lib/format";

const MODEL_PRESETS = [
  { id: "openai", label: "OpenAI", base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { id: "dashscope", label: "DashScope / Qwen", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  { id: "deepseek", label: "DeepSeek", base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  { id: "moonshot", label: "Moonshot (Kimi)", base_url: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k" },
  { id: "custom", label: "Custom", base_url: "", model: "" },
];

export default function SettingsPage({ dashboard }) {
  const [providers, setProviders] = useState(null);
  const [modelForm, setModelForm] = useState({ model: "", base_url: "", api_key: "" });
  const [loading, setLoading] = useState(true);
  const [savingModel, setSavingModel] = useState(false);
  const [reloadError, setReloadError] = useState("");
  const [modelError, setModelError] = useState("");
  const [modelNotice, setModelNotice] = useState("");
  const [testQuery, setTestQuery] = useState("OpenAI");
  const [testRunning, setTestRunning] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState("");

  async function reload() {
    setLoading(true);
    setReloadError("");
    try {
      const payload = await api.providerSettings();
      setProviders(payload.data);
      setModelForm({
        model: payload.data?.model?.model || "",
        base_url: payload.data?.model?.base_url || "",
        api_key: "",
      });
    } catch (exc) {
      setReloadError(getErrorMessage(exc));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  function applyModelPreset(preset) {
    if (!preset) return;
    setModelForm((prev) => ({
      ...prev,
      base_url: preset.base_url,
      model: preset.model || prev.model,
    }));
  }

  async function handleModelSave(event) {
    event.preventDefault();
    setSavingModel(true);
    setModelError("");
    setModelNotice("");
    const update = {
      model: modelForm.model,
      base_url: modelForm.base_url,
    };
    if (modelForm.api_key.trim()) {
      update.api_key = modelForm.api_key.trim();
    }
    try {
      const payload = await api.saveProviderSettings({ model: update });
      setProviders(payload.data?.providers || providers);
      setModelForm((prev) => ({ ...prev, api_key: "" }));
      const written = payload.data?.written_keys || [];
      setModelNotice(
        written.length
          ? `Saved to ${payload.data?.env_path || ".env"}: ${written.join(", ")}.`
          : "No changes were written.",
      );
    } catch (exc) {
      setModelError(getErrorMessage(exc));
    } finally {
      setSavingModel(false);
    }
  }

  async function handleModelClear() {
    setSavingModel(true);
    setModelError("");
    setModelNotice("");
    try {
      const payload = await api.saveProviderSettings({
        model: { model: "", base_url: "", api_key: "" },
      });
      setProviders(payload.data?.providers || providers);
      setModelForm({ model: "", base_url: "", api_key: "" });
      setModelNotice("Model connection cleared from .env.");
    } catch (exc) {
      setModelError(getErrorMessage(exc));
    } finally {
      setSavingModel(false);
    }
  }

  const searchStatus = providers?.search;
  const modelStatus = providers?.model;
  const inputClass =
    "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-zinc-900 shadow-hairline focus:border-appleBlue focus:outline-none focus:ring-1 focus:ring-appleBlue disabled:opacity-50";

  async function runSearchTest() {
    setTestRunning(true);
    setTestError("");
    setTestResult(null);
    try {
      const payload = await api.testSearchProvider(testQuery);
      setTestResult(payload.data);
    } catch (exc) {
      setTestError(getErrorMessage(exc));
    } finally {
      setTestRunning(false);
    }
  }

  return (
    <section className="workbench-section">
      <div className="workbench-container space-y-5">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">
            Configure realtime providers. Saved values are written to the project <code>.env</code> file and applied to the
            running server immediately. API keys are masked in responses and never returned in plaintext after saving.
          </p>
        </div>

        <div className="grid gap-5 xl:grid-cols-2">
          <SettingsCard
            icon={SlidersHorizontal}
            title="Workspace"
            rows={[
              ["Root", dashboard?.workspace_root || "-"],
              ["Asset counts", formatAssetCounts(dashboard?.asset_counts)],
              ["Pending changes", dashboard?.pending_changes ?? 0],
            ]}
          />
          <SettingsCard
            icon={ShieldCheck}
            title="Safety Policy"
            rows={[
              ["Policy", "default"],
              ["Create route", "preflight + confirmation"],
              ["Rollback", "review required"],
            ]}
          />
        </div>

        <section className="section-panel p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-zinc-50 text-zinc-700">
                <KeyRound className="h-4 w-4" />
              </span>
              <div>
                <h2 className="text-base font-semibold text-zinc-950">Built-in web_search Status</h2>
                <p className="text-xs text-zinc-500">
                  <code>web_search</code> / <code>web_research</code> is a built-in tool. Configure it by editing the project{" "}
                  <code>.env</code>: set <code>SEARCH_PROVIDER=bailian</code> (recommended) plus your{" "}
                  <code>DASHSCOPE_API_KEY</code> or <code>SEARCH_API_KEY</code>. Settings reload automatically on next
                  server start. {reloadError ? <span className="text-rose-600">Status load failed: {reloadError}</span> : null}
                </p>
              </div>
            </div>
            <ProviderBadge
              configured={providers?.search?.configured}
              label={providers?.search?.provider || "not configured"}
            />
          </div>

          {loading ? (
            <div className="mt-4 text-sm text-zinc-500">Loading…</div>
          ) : (
            <>
              <div className="mt-5 grid gap-3 text-xs text-zinc-500 lg:grid-cols-3">
                <StatusRow label="Configured" value={providers?.search?.configured ? "yes" : "no"} />
                <StatusRow label="Provider" value={providers?.search?.provider || "(none)"} />
                <StatusRow
                  label="API key"
                  value={providers?.search?.has_api_key ? providers.search.api_key_masked : "not set"}
                />
              </div>

              <div className="mt-5 border-t border-line pt-4">
                <div className="flex flex-wrap items-end gap-3">
                  <label className="flex-1 min-w-[14rem] space-y-1 text-sm">
                    <span className="block text-xs font-medium text-zinc-600">Test query</span>
                    <input
                      className={inputClass}
                      type="text"
                      value={testQuery}
                      onChange={(event) => setTestQuery(event.target.value)}
                      placeholder="OpenAI"
                      disabled={testRunning}
                    />
                  </label>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={runSearchTest}
                    disabled={testRunning}
                  >
                    {testRunning ? "Testing…" : "Test search now"}
                  </button>
                </div>
                <p className="mt-2 text-xs text-zinc-500">
                  Runs a real search through the configured provider and shows the actual response. Use this to verify your
                  key works end-to-end.
                </p>

                {testError ? (
                  <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                    {testError}
                  </div>
                ) : null}

                {testResult ? (
                  <div className="mt-3 space-y-2">
                    <div className="grid gap-2 text-xs text-zinc-500 lg:grid-cols-3">
                      <StatusRow label="Status" value={testResult.ok ? "ok" : "failed"} />
                      <StatusRow label="Search mode" value={testResult.search_mode || "(unknown)"} />
                      <StatusRow label="Endpoint" value={testResult.endpoint || "(default)"} />
                    </div>
                    {testResult.ok ? (
                      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                        <div className="text-xs font-medium text-emerald-700">
                          {(testResult.result?.results || []).length} result(s) for "{testResult.query}"
                        </div>
                        <ul className="mt-2 space-y-1 text-xs text-zinc-800">
                          {(testResult.result?.results || []).map((item, idx) => (
                            <li key={idx} className="truncate">
                              <span className="font-medium">{item.title || "(no title)"}</span>
                              <span className="text-zinc-500"> — {item.url}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                        <div className="font-medium">error_code: {testResult.result?.error_code || "(unknown)"}</div>
                        <div className="mt-1 break-words">{testResult.result?.message || "No detail."}</div>
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            </>
          )}
        </section>

        <section className="section-panel p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-zinc-50 text-zinc-700">
                <Cpu className="h-4 w-4" />
              </span>
              <div>
                <h2 className="text-base font-semibold text-zinc-950">Model Connection</h2>
                <p className="text-xs text-zinc-500">
                  OpenAI-compatible endpoint used for Chat fallback answers and Markdown summarization. Picking a preset
                  fills in the base URL and a default model name; you still need to provide your own API key.
                </p>
              </div>
            </div>
            <ProviderBadge configured={modelStatus?.configured} label={modelStatus?.model || "no model"} />
          </div>

          {loading ? (
            <div className="mt-4 text-sm text-zinc-500">Loading…</div>
          ) : (
            <form className="mt-5 grid gap-4 lg:grid-cols-2" onSubmit={handleModelSave}>
              <Field label="Preset" hint="Optional: select to autofill base URL and model name.">
                <div className="flex flex-wrap gap-2">
                  {MODEL_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      className="rounded-full border border-line bg-white px-3 py-1 text-xs font-medium text-zinc-700 transition hover:border-zinc-300 hover:bg-zinc-50 disabled:opacity-40"
                      onClick={() => applyModelPreset(preset)}
                      disabled={savingModel}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label="Model" hint="e.g. gpt-4o-mini, qwen-plus, deepseek-chat.">
                <input
                  className={inputClass}
                  type="text"
                  value={modelForm.model}
                  onChange={(event) => setModelForm((prev) => ({ ...prev, model: event.target.value }))}
                  placeholder="gpt-4o-mini"
                  disabled={savingModel}
                />
              </Field>
              <Field label="Base URL" hint="OpenAI-compatible chat completions root. Leave empty to default to https://api.openai.com/v1.">
                <input
                  className={inputClass}
                  type="text"
                  value={modelForm.base_url}
                  onChange={(event) => setModelForm((prev) => ({ ...prev, base_url: event.target.value }))}
                  placeholder="https://api.openai.com/v1"
                  disabled={savingModel}
                />
              </Field>
              <Field
                label="API Key"
                hint={
                  modelStatus?.has_api_key
                    ? `Stored. Current masked value: ${modelStatus.api_key_masked}. Leave empty to keep, type to replace.`
                    : "Stored in .env only. Never returned in plaintext."
                }
              >
                <input
                  className={inputClass}
                  type="password"
                  value={modelForm.api_key}
                  onChange={(event) => setModelForm((prev) => ({ ...prev, api_key: event.target.value }))}
                  placeholder={modelStatus?.has_api_key ? "•••••• (keep existing)" : "sk-..."}
                  disabled={savingModel}
                  autoComplete="off"
                />
              </Field>

              <div className="lg:col-span-2 flex flex-wrap items-center gap-3">
                <button type="submit" className="primary-button inline-flex items-center gap-2" disabled={savingModel}>
                  <Save className="h-4 w-4" />
                  {savingModel ? "Saving…" : "Save to .env"}
                </button>
                <button type="button" className="secondary-button" onClick={handleModelClear} disabled={savingModel}>
                  Clear model connection
                </button>
                {modelNotice ? <span className="text-xs text-emerald-700">{modelNotice}</span> : null}
                {modelError ? <span className="text-xs text-rose-700">{modelError}</span> : null}
              </div>
            </form>
          )}

          <div className="mt-5 grid gap-3 text-xs text-zinc-500 lg:grid-cols-3">
            <StatusRow label="Configured" value={modelStatus?.configured ? "yes" : "no"} />
            <StatusRow label="Model" value={modelStatus?.model || "not set"} />
            <StatusRow label="API key" value={modelStatus?.has_api_key ? modelStatus.api_key_masked : "not set"} />
          </div>
        </section>
      </div>
    </section>
  );
}

function SettingsCard({ icon: Icon, title, rows }) {
  return (
    <section className="section-panel p-5">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-zinc-50 text-zinc-700">
          <Icon className="h-4 w-4" />
        </span>
        <h2 className="text-base font-semibold text-zinc-950">{title}</h2>
      </div>
      <div className="mt-5 space-y-3">
        {rows.map(([label, value]) => (
          <div className="grid grid-cols-[7rem_1fr] gap-3 text-sm" key={label}>
            <span className="text-xs font-medium text-zinc-500">{label}</span>
            <span className="min-w-0 break-words text-right font-semibold text-zinc-900">{compact(value)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Field({ label, hint, children }) {
  return (
    <label className="space-y-1 text-sm">
      <span className="block text-xs font-medium text-zinc-600">{label}</span>
      {children}
      {hint ? <span className="block text-xs text-zinc-500">{hint}</span> : null}
    </label>
  );
}

function StatusRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded border border-line bg-zinc-50 px-3 py-2">
      <span className="font-medium text-zinc-600">{label}</span>
      <span className="font-semibold text-zinc-900">{value}</span>
    </div>
  );
}

function ProviderBadge({ configured, label }) {
  const tone = configured
    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : "bg-amber-50 text-amber-700 border-amber-200";
  return (
    <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${tone}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${configured ? "bg-emerald-500" : "bg-amber-500"}`} />
      {configured ? `configured: ${label}` : `not configured (${label})`}
    </span>
  );
}

function formatAssetCounts(counts) {
  if (!counts) return "-";
  return `skills ${counts.skills || 0}, tools ${counts.tools || 0}, workflows ${counts.workflows || 0}, eval ${counts.eval_cases || 0}`;
}
