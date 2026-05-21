import { KeyRound, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { compact } from "../lib/format";

export default function SettingsPage({ dashboard }) {
  return (
    <section className="workbench-section">
      <div className="workbench-container space-y-5">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">
            Read-only workspace configuration summary. Mutating safety or connection settings should go through review.
          </p>
        </div>

        <div className="grid gap-5 xl:grid-cols-3">
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
            icon={KeyRound}
            title="Model Connection"
            rows={[
              ["Provider", "OpenAI-compatible runtime"],
              ["API key", "Environment only"],
              ["Secrets", "Never stored in assets, reviews, or eval cases"],
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
          <SettingsCard
            icon={KeyRound}
            title="Realtime Providers"
            rows={[
              ["Search", providerStatus(dashboard?.providers?.search)],
              ["Finance", providerStatus(dashboard?.providers?.finance)],
              ["Weather", providerStatus(dashboard?.providers?.weather)],
            ]}
          />
        </div>
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

function formatAssetCounts(counts) {
  if (!counts) return "-";
  return `skills ${counts.skills || 0}, tools ${counts.tools || 0}, workflows ${counts.workflows || 0}, eval ${counts.eval_cases || 0}`;
}

function providerStatus(provider) {
  if (!provider) return "not configured";
  const state = provider.configured ? "configured" : "not configured";
  return provider.provider ? `${state}: ${provider.provider}` : state;
}
