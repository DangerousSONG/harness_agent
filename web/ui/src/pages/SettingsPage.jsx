import { useEffect, useState } from "react";
import { Cpu, KeyRound, ShieldCheck, SlidersHorizontal, Save } from "lucide-react";
import { api, getErrorMessage } from "../lib/api";
import { compact } from "../lib/format";

const SEARCH_PROVIDER_OPTIONS = [
  { value: "", label: "Not configured (no-key DuckDuckGo fallback)" },
  { value: "bailian", label: "Bailian / DashScope WebSearch (MCP)" },
  { value: "bing", label: "Bing Web Search (no adapter yet)" },
  { value: "serper", label: "Serper / Google (no adapter yet)" },
  { value: "brave", label: "Brave Search (no adapter yet)" },
  { value: "tavily", label: "Tavily (no adapter yet)" },
];

const SEARCH_PROVIDER_HINTS = {
  bailian:
    "百炼 / DashScope: get the API key at bailian.console.aliyun.com (Manage → API-KEY). Endpoint is the MCP WebSearch URL; tool name defaults to 'WebSearch' (override with SEARCH_TOOL_NAME if needed).",
  bing: "Bing adapter is not wired up yet; the key will be saved but search will fall back to DuckDuckGo.",
  serper: "Serper adapter is not wired up yet; the key will be saved but search will fall back to DuckDuckGo.",
  brave: "Brave adapter is not wired up yet; the key will be saved but search will fall back to DuckDuckGo.",
  tavily: "Tavily adapter is not wired up yet; the key will be saved but search will fall back to DuckDuckGo.",
};

const MODEL_PRESETS = [
  { id: "openai", label: "OpenAI", base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { id: "dashscope", label: "DashScope / Qwen", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  { id: "deepseek", label: "DeepSeek", base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  { id: "moonshot", label: "Moonshot (Kimi)", base_url: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k" },
  { id: "custom", label: "Custom", base_url: "", model: "" },
];

export default function SettingsPage({ dashboard }) {
  const [providers, setProviders] = useState(null);
  const [searchForm, setSearchForm] = useState({ provider: "", api_key: "", api_key_env: "", mock_results: "" });
  const [modelForm, setModelForm] = useState({ model: "", base_url: "", api_key: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingModel, setSavingModel] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [modelError, setModelError] = useState("");
  const [modelNotice, setModelNotice] = useState("");

  async function reload() {
    setLoading(true);
    setError("");
    try {
      const payload = await api.providerSettings();
      setProviders(payload.data);
      setSearchForm({
        provider: payload.data?.search?.provider || "",
        api_key: "",
        api_key_env: payload.data?.search?.api_key_env || "",
        mock_results: "",
      });
      setModelForm({
        model: payload.data?.model?.model || "",
        base_url: payload.data?.model?.base_url || "",
        api_key: "",
      });
    } catch (exc) {
      setError(getErrorMessage(exc));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    const update = { provider: searchForm.provider };
    if (searchForm.api_key.trim()) {
      update.api_key = searchForm.api_key.trim();
    }
    if (searchForm.api_key_env.trim()) {
      update.api_key_env = searchForm.api_key_env.trim();
    }
    if (searchForm.mock_results.trim()) {
      update.mock_results = searchForm.mock_results.trim();
    }
    try {
      const payload = await api.saveProviderSettings({ search: update });
      setProviders(payload.data?.providers || providers);
      setSearchForm((prev) => ({ ...prev, api_key: "" }));
      const written = payload.data?.written_keys || [];
      setNotice(
        written.length
          ? `Saved to ${payload.data?.env_path || ".env"}: ${written.join(", ")}.`
          : "No changes were written.",
      );
    } catch (exc) {
      setError(getErrorMessage(exc));
    } finally {
      setSaving(false);
    }
  }

  async function handleClear() {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = await api.saveProviderSettings({
        search: { provider: "", api_key: "", api_key_env: "", mock_results: "" },
      });
      setProviders(payload.data?.providers || providers);
      setSearchForm({ provider: "", api_key: "", api_key_env: "", mock_results: "" });
      setNotice("Search provider configuration removed from .env.");
    } catch (exc) {
      setError(getErrorMessage(exc));
    } finally {
      setSaving(false);
    }
  }

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
                <h2 className="text-base font-semibold text-zinc-950">Realtime Search Provider</h2>
                <p className="text-xs text-zinc-500">
                  Used by Chat for realtime queries. Without a configured provider the runtime falls back to a no-key
                  DuckDuckGo search before crawl4ai.
                </p>
              </div>
            </div>
            <ProviderBadge configured={searchStatus?.configured} label={searchStatus?.provider || "no-key fallback"} />
          </div>

          {loading ? (
            <div className="mt-4 text-sm text-zinc-500">Loading…</div>
          ) : (
            <form className="mt-5 grid gap-4 lg:grid-cols-2" onSubmit={handleSave}>
              <Field label="Provider" hint={SEARCH_PROVIDER_HINTS[searchForm.provider] || ""}>
                <select
                  className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-zinc-900 shadow-hairline focus:border-appleBlue focus:outline-none focus:ring-1 focus:ring-appleBlue disabled:opacity-50"
                  value={searchForm.provider}
                  onChange={(event) => setSearchForm((prev) => ({ ...prev, provider: event.target.value }))}
                  disabled={saving}
                >
                  {SEARCH_PROVIDER_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                label="API Key"
                hint={
                  searchStatus?.has_api_key
                    ? `Stored. Current masked value: ${searchStatus.api_key_masked}. Leave empty to keep, type to replace.`
                    : "Stored in .env only. Leave empty to skip if you only need provider switching."
                }
              >
                <input
                  className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-zinc-900 shadow-hairline focus:border-appleBlue focus:outline-none focus:ring-1 focus:ring-appleBlue disabled:opacity-50"
                  type="password"
                  value={searchForm.api_key}
                  onChange={(event) => setSearchForm((prev) => ({ ...prev, api_key: event.target.value }))}
                  placeholder={searchStatus?.has_api_key ? "•••••• (keep existing)" : "sk-..."}
                  disabled={saving}
                  autoComplete="off"
                />
              </Field>
              <Field
                label="API Key Env (optional)"
                hint="If you prefer to keep the key in another env var, name it here and leave API Key empty."
              >
                <input
                  className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-zinc-900 shadow-hairline focus:border-appleBlue focus:outline-none focus:ring-1 focus:ring-appleBlue disabled:opacity-50"
                  type="text"
                  value={searchForm.api_key_env}
                  onChange={(event) => setSearchForm((prev) => ({ ...prev, api_key_env: event.target.value }))}
                  placeholder="BING_SEARCH_API_KEY"
                  disabled={saving}
                />
              </Field>
              <Field
                label="Mock results (optional)"
                hint="JSON array of search results. Useful for tests; takes precedence over provider/key."
              >
                <input
                  className="w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-zinc-900 shadow-hairline focus:border-appleBlue focus:outline-none focus:ring-1 focus:ring-appleBlue disabled:opacity-50"
                  type="text"
                  value={searchForm.mock_results}
                  onChange={(event) => setSearchForm((prev) => ({ ...prev, mock_results: event.target.value }))}
                  placeholder='[{"title":"...","url":"https://..."}]'
                  disabled={saving}
                />
              </Field>

              <div className="lg:col-span-2 flex flex-wrap items-center gap-3">
                <button type="submit" className="primary-button inline-flex items-center gap-2" disabled={saving}>
                  <Save className="h-4 w-4" />
                  {saving ? "Saving…" : "Save to .env"}
                </button>
                <button type="button" className="secondary-button" onClick={handleClear} disabled={saving}>
                  Clear search provider
                </button>
                {notice ? <span className="text-xs text-emerald-700">{notice}</span> : null}
                {error ? <span className="text-xs text-rose-700">{error}</span> : null}
              </div>
            </form>
          )}

          <div className="mt-5 grid gap-3 text-xs text-zinc-500 lg:grid-cols-3">
            <StatusRow label="Configured" value={searchStatus?.configured ? "yes" : "no"} />
            <StatusRow label="Provider" value={searchStatus?.provider || "(no-key fallback)"} />
            <StatusRow label="API key" value={searchStatus?.has_api_key ? searchStatus.api_key_masked : "not set"} />
          </div>
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
