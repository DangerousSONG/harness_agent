import { Archive, BookOpen, Boxes, ChevronDown, ChevronRight, GitPullRequest, Hammer, Play, Plus, RotateCcw, Trash2, Workflow, Wrench, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import EmptyState from "../components/EmptyState";
import StatusPill from "../components/StatusPill";
import KnowledgeBasesPage from "./KnowledgeBasesPage";
import AssetCreationDialog from "../components/AssetCreationDialog";
import { api, getErrorMessage } from "../lib/api";
import { compact, formatDate, titleize } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";

const TABS = [
  { id: "skills", labelKey: "assets.tab.skills", icon: Boxes },
  { id: "tools", labelKey: "assets.tab.tools", icon: Wrench },
  { id: "workflows", labelKey: "assets.tab.workflows", icon: Workflow },
  { id: "memories", labelKey: "assets.tab.memories", icon: GitPullRequest },
  { id: "knowledge-bases", labelKey: "assets.tab.knowledge_bases", icon: BookOpen },
  { id: "eval-cases", labelKey: "assets.tab.eval_cases", icon: Hammer },
];

export default function AssetsPage({
  skills,
  tools,
  reviews,
  changes,
  promotions,
  memories,
  knowledgeBases,
  versions,
  tab: controlledTab,
  onTabChange,
  onOpenReview,
  onOpenVersions,
  onAssetCreated,
}) {
  const t = useTranslate();
  const [localTab, setLocalTab] = useState("skills");
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailTab, setDetailTab] = useState("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [creationKind, setCreationKind] = useState(null); // "skill" | "tool" | null
  // pendingAction: {kind: skill|tool, name, action: archive|hard_delete}
  const [pendingAction, setPendingAction] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [toast, setToast] = useState({ tone: "info", message: "" });
  const [archiveOpen, setArchiveOpen] = useState({ skills: false, tools: false });
  const tab = controlledTab || localTab;
  const setTab = onTabChange || setLocalTab;

  const requestArchive = (kind, name) =>
    setPendingAction({ kind, name, action: "archive" });
  const requestHardDelete = (kind, name) =>
    setPendingAction({ kind, name, action: "hard_delete" });
  const cancelPending = () => {
    if (!actionBusy) setPendingAction(null);
  };
  const confirmPending = async () => {
    if (!pendingAction) return;
    setActionBusy(true);
    try {
      const { kind, name, action } = pendingAction;
      let payload;
      if (action === "archive") {
        payload = kind === "skill" ? await api.archiveSkill(name) : await api.archiveTool(name);
      } else {
        payload = kind === "skill" ? await api.hardDeleteSkill(name) : await api.hardDeleteTool(name);
      }
      setToast({
        tone: "success",
        message: payload?.message
          || (action === "archive"
              ? `${name} 已归档，不再被加载或执行。`
              : `${name} 已永久删除。`),
      });
      setPendingAction(null);
      onAssetCreated?.();
    } catch (err) {
      setToast({ tone: "error", message: getErrorMessage(err) });
    } finally {
      setActionBusy(false);
    }
  };

  const restoreAsset = async (kind, name) => {
    setActionBusy(true);
    try {
      const payload = kind === "skill" ? await api.restoreSkill(name) : await api.restoreTool(name);
      setToast({
        tone: "success",
        message: payload?.message || `${name} 已恢复，重新可被加载/执行。`,
      });
      onAssetCreated?.();
    } catch (err) {
      setToast({ tone: "error", message: getErrorMessage(err) });
    } finally {
      setActionBusy(false);
    }
  };

  useEffect(() => {
    if (!toast.message) return;
    const timer = setTimeout(() => setToast({ tone: "info", message: "" }), 3500);
    return () => clearTimeout(timer);
  }, [toast.message]);

  const partitionByArchive = (items) => {
    const active = [];
    const archived = [];
    for (const item of items || []) {
      if (item?.lifecycle_status === "archived") archived.push(item);
      else active.push(item);
    }
    return { active, archived };
  };
  const skillBuckets = useMemo(() => partitionByArchive(skills), [skills]);
  const toolBuckets = useMemo(() => partitionByArchive(tools), [tools]);
  const evalCards = useMemo(
    () => (skills || []).filter((skill) => skill.has_eval_cases),
    [skills],
  );

  async function openAsset(assetType, asset) {
    setSelected({ assetType, asset });
    setDetail(null);
    setDetailTab("overview");
    setError("");
    if (!["skill", "tool"].includes(assetType)) return;
    setLoading(true);
    try {
      if (assetType === "tool") {
        const payload = await api.tool(asset.name);
        setDetail(payload.data);
      } else {
        const [skill, active, evalCases] = await Promise.allSettled([
          api.skill(asset.name),
          api.skillActive(asset.name),
          api.skillEvalCases(asset.name),
        ]);
        setDetail({
          ...(skill.status === "fulfilled" ? skill.value.data : asset),
          files: {
            active: active.status === "fulfilled"
              ? { path: active.value.data.path, exists: true, content: active.value.data.content, status: "present" }
              : { path: `skills/${asset.name}/SKILL.md`, exists: false, content: "", status: "missing" },
            eval_cases: evalCases.status === "fulfilled"
              ? { path: evalCases.value.data.path, exists: Boolean(evalCases.value.data.raw), content: evalCases.value.data.raw, status: evalCases.value.data.raw ? "present" : "missing" }
              : { path: `skills/${asset.name}/eval/cases.yaml`, exists: false, content: "", status: "missing" },
          },
        });
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  const closeDetail = () => {
    setSelected(null);
    setDetail(null);
    setError("");
  };

  return (
    <section className="workbench-section">
      <div className="workbench-container">
        <div className="mb-6">
          <h1 className="page-title">{t("assets.title")}</h1>
          <p className="page-subtitle">{t("assets.subtitle")}</p>
        </div>

        <div className="mb-5 flex flex-wrap gap-2 rounded-lg border border-line bg-white p-1 shadow-hairline">
          {TABS.map((item) => {
            const Icon = item.icon;
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                className={[
                  "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition",
                  active ? "bg-zinc-950 text-white" : "text-zinc-700 hover:bg-zinc-50",
                ].join(" ")}
                onClick={() => setTab(item.id)}
              >
                <Icon className="h-4 w-4" />
                {t(item.labelKey)}
              </button>
            );
          })}
        </div>

        {tab === "skills" ? (
          <>
            <AssetGrid
              items={skillBuckets.active}
              empty={t("assets.skills.empty")}
              leading={
                <CreateEntryCard
                  key="__create_skill__"
                  title="创建 Skill"
                  description="通过自然语言描述能力需求，生成 Skill 草稿并完成系统校验。"
                  onClick={() => setCreationKind("skill")}
                />
              }
              render={(skill) => (
                <AssetCard
                  key={skill.name}
                  title={skill.name}
                  description={skill.description || "暂无描述"}
                  status={assetStatus("skill", skill.name, reviews, skill)}
                  rows={assetRows({
                    assetType: "skill",
                    name: skill.name,
                    currentVersion: skill.latest_version || "active",
                    evalStatus: skill.has_eval_cases ? "present" : "missing",
                    latestChange: latestChange("skill", skill.name, changes),
                    pendingReview: pendingReview("skill", skill.name, reviews),
                  })}
                  metrics={[
                    [t("assets.skills.metric.memory"), skill.memory_count],
                    [t("assets.skills.metric.promo"), skill.promotion_count],
                    [t("assets.skills.metric.versions"), (versions || []).filter((item) => item.skill === skill.name).length],
                  ]}
                  onClick={() => openAsset("skill", skill)}
                  onDelete={() => requestArchive("skill", skill.name)}
                  deleteBusy={actionBusy && pendingAction?.name === skill.name}
                />
              )}
            />
            <ArchiveSection
              kind="skill"
              items={skillBuckets.archived}
              open={archiveOpen.skills}
              onToggle={() => setArchiveOpen({ ...archiveOpen, skills: !archiveOpen.skills })}
              onRestore={(name) => restoreAsset("skill", name)}
              onHardDelete={(name) => requestHardDelete("skill", name)}
              actionBusy={actionBusy}
              pendingName={pendingAction?.name}
            />
          </>
        ) : null}

        {tab === "tools" ? (
          <>
            <AssetGrid
              items={toolBuckets.active}
              empty={t("assets.tools.empty")}
              leading={
                <CreateEntryCard
                  key="__create_tool__"
                  title="注册 Tool"
                  description="注册一个可被 Skill 调用的工具，配置入口、参数和安全策略。"
                  onClick={() => setCreationKind("tool")}
                />
              }
              render={(tool) => (
                <AssetCard
                  key={tool.name}
                  title={tool.name}
                  description={tool.description || "暂无描述"}
                  status={
                    tool.lifecycle_status && tool.lifecycle_status !== "active"
                      ? (LIFECYCLE_LABEL[tool.lifecycle_status] || tool.lifecycle_status)
                      : pendingReview("tool", tool.name, reviews) !== "-"
                        ? assetStatus("tool", tool.name, reviews, tool)
                        : tool.executable ? "executable" : "not executable"
                  }
                  rows={assetRows({
                    assetType: "tool",
                    name: tool.name,
                    currentVersion: tool.status || "draft",
                    evalStatus: tool.eval_cases_count ? `${tool.eval_cases_count} cases` : "missing",
                    latestChange: latestChange("tool", tool.name, changes),
                    pendingReview: pendingReview("tool", tool.name, reviews),
                  })}
                  metrics={[
                    [t("assets.tools.metric.provider"), compact(tool.provider_requirements, t("common.none"))],
                    [t("assets.tools.metric.handler"), tool.handler_available ? t("common.yes") : t("common.no")],
                    [t("assets.tools.metric.executable"), tool.executable ? t("common.yes") : t("common.no")],
                  ]}
                  onClick={() => openAsset("tool", tool)}
                  onDelete={() => requestArchive("tool", tool.name)}
                  deleteBusy={actionBusy && pendingAction?.name === tool.name}
                />
              )}
            />
            <ArchiveSection
              kind="tool"
              items={toolBuckets.archived}
              open={archiveOpen.tools}
              onToggle={() => setArchiveOpen({ ...archiveOpen, tools: !archiveOpen.tools })}
              onRestore={(name) => restoreAsset("tool", name)}
              onHardDelete={(name) => requestHardDelete("tool", name)}
              actionBusy={actionBusy}
              pendingName={pendingAction?.name}
            />
          </>
        ) : null}

        {tab === "workflows" ? (
          <AssetGrid
            items={promotions}
            empty={t("promotions.empty")}
            render={(promo) => (
              <AssetCard
                key={promo.promo_id}
                title={promo.promo_id}
                description={promo.proposed_change_summary || promo.reason || t("assets.workflows.default_desc")}
                status={promo.promotion_decision || promo.status || "proposed"}
                rows={[
                  [t("assets.workflows.metric.target_asset"), promo.target_skill],
                  [t("assets.workflows.metric.source_memory"), compact(promo.source_memory_ids)],
                  [t("assets.workflows.metric.linked_reviews"), compact(promo.linked_reviews)],
                  [t("assets.workflows.metric.linked_version"), compact(promo.linked_version)],
                  [t("assets.workflows.metric.next_action"), promo.requires_regeneration ? t("assets.workflows.next_action.regenerate") : promo.linked_version ? t("assets.workflows.next_action.view_version") : t("assets.workflows.next_action.create_review")],
                ]}
                metrics={[
                  [t("assets.workflows.metric.score"), promo.promotion_score],
                  [t("assets.workflows.metric.eligible"), promo.eligible_target],
                  [t("assets.workflows.metric.schema"), promo.schema_status],
                ]}
                onClick={() => openAsset("workflow", promo)}
              />
            )}
          />
        ) : null}

        {tab === "memories" ? (
          <AssetGrid
            items={memories}
            empty={t("assets.memories.empty")}
            render={(memory) => (
              <AssetCard
                key={memory.memory_id || `${memory.skill}-${memory.type}-${memory.title}`}
                title={memory.title || memory.memory_id || "Memory"}
                description={memory.content || memory.reason || "Recorded asset memory."}
                status={memory.status || memory.type || "recorded"}
                rows={[
                  ["Skill", memory.skill],
                  ["Type", memory.type],
                  ["Memory id", memory.memory_id],
                  ["Updated", formatDate(memory.updated_at || memory.created_at)],
                  ["PROMO", memory.linked_promo_id],
                ]}
                metrics={[
                  ["Priority", memory.priority],
                  ["Occurrences", memory.occurrence_count],
                  ["Review", memory.needs_attribution_review ? "needed" : "none"],
                ]}
                onClick={() => openAsset("memory", memory)}
              >
                <MemoryPromotionProgress progress={memory.promotion_progress} t={t} />
              </AssetCard>
            )}
          />
        ) : null}

        {tab === "knowledge-bases" ? <KnowledgeBasesPage /> : null}

        {tab === "eval-cases" ? (
          <AssetGrid
            items={evalCards}
            empty="No eval cases found."
            render={(skill) => (
              <AssetCard
                key={`${skill.name}-eval`}
                title={`${skill.name} eval cases`}
                description="Regression and acceptance cases connected to this skill asset."
                status={skill.has_eval_cases ? "present" : "missing"}
                rows={[
                  ["Active source", `skills/${skill.name}/eval/cases.yaml`],
                  ["Latest version", skill.latest_version || "No snapshot"],
                  ["Pending review", pendingReview("skill", skill.name, reviews)],
                ]}
                metrics={[
                  ["Asset", skill.name],
                  ["Versions", (versions || []).filter((item) => item.skill === skill.name).length],
                  ["Changes", (changes || []).filter((item) => item.asset_name === skill.name).length],
                ]}
                onClick={() => openAsset("skill", skill)}
              />
            )}
          />
        ) : null}

        {selected ? (
          <AssetDetailModal
            selected={selected}
            detail={detail || selected.asset}
            loading={loading}
            error={error}
            tab={detailTab}
            setTab={setDetailTab}
            reviews={reviews}
            changes={changes}
            versions={versions}
            memories={memories}
            knowledgeBases={knowledgeBases}
            onClose={closeDetail}
            onOpenReview={onOpenReview}
            onOpenVersions={onOpenVersions}
          />
        ) : null}
      </div>
      <AssetCreationDialog
        open={creationKind !== null}
        kind={creationKind}
        onClose={() => setCreationKind(null)}
        onCreated={() => onAssetCreated?.()}
      />
      <DangerConfirmDialog
        target={pendingAction}
        busy={actionBusy}
        onCancel={cancelPending}
        onConfirm={confirmPending}
      />
      {toast.message ? (
        <div
          className={[
            "pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg border px-4 py-3 text-sm shadow-soft",
            toast.tone === "error"
              ? "border-rose-200 bg-rose-50/95 text-rose-700"
              : "border-emerald-200 bg-emerald-50/95 text-emerald-800",
          ].join(" ")}
        >
          {toast.message}
        </div>
      ) : null}
    </section>
  );
}

function DangerConfirmDialog({ target, busy, onCancel, onConfirm }) {
  if (!target) return null;
  const isHard = target.action === "hard_delete";
  const assetLabel = target.kind === "skill" ? "Skill" : "Tool";
  const title = isHard
    ? `永久删除 ${assetLabel}：`
    : `归档 ${assetLabel}：`;
  const detail = isHard ? (
    <>
      <p className="mt-2 text-sm leading-6 text-zinc-700">
        此操作将<span className="font-semibold text-rose-700">永久删除</span>
        资产文件夹，无法恢复。请确认你只想删除这一项。
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-zinc-600">
        <li>
          将移除：
          <span className="font-mono">
            {target.kind === "skill" ? "skills" : "tools"}/{target.name}/
          </span>
        </li>
        <li>不会改动 .reviews / .skills_versions / 审计日志</li>
        <li>不会去触发 ReviewQueue</li>
      </ul>
    </>
  ) : (
    <p className="mt-2 text-sm leading-6 text-zinc-600">
      归档后该资产不会被加载或执行
      {target.kind === "skill"
        ? "（SkillRouter 跳过）"
        : "（ToolRegistry 跳过）"}
      ，文件保留在磁盘。可以在「已归档」列表里恢复或永久删除。
    </p>
  );
  const buttonLabel = isHard ? "确认永久删除" : "确认归档";
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/40 p-4"
      onClick={busy ? undefined : onCancel}
    >
      <div
        className="w-full max-w-md rounded-xl border border-line bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-zinc-950">
          {title}
          <span className="ml-1 font-mono text-rose-700">{target.name}</span>?
        </h3>
        {detail}
        <div className="mt-5 flex justify-end gap-2">
          <button className="secondary-button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button
            className="primary-button"
            style={{ background: isHard ? "#b91c1c" : "#dc2626" }}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "处理中…" : buttonLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function ArchiveSection({
  kind,
  items,
  open,
  onToggle,
  onRestore,
  onHardDelete,
  actionBusy,
  pendingName,
}) {
  const count = items?.length || 0;
  return (
    <div className="mt-6 rounded-xl border border-line bg-zinc-50/60">
      <button
        type="button"
        className="flex w-full items-center justify-between rounded-t-xl px-4 py-3 text-left transition hover:bg-zinc-100"
        onClick={onToggle}
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-zinc-800">
          <Archive className="h-4 w-4" />
          已归档（{count}）
          <span className="ml-1 text-xs font-normal text-zinc-500">
            {count
              ? "已停用的资产留在这里，可以恢复或永久删除"
              : "尚无已归档资产"}
          </span>
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-zinc-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-zinc-500" />
        )}
      </button>
      {open && count ? (
        <div className="grid gap-3 border-t border-line p-4 xl:grid-cols-2 2xl:grid-cols-3">
          {items.map((item) => (
            <ArchivedCard
              key={item.name}
              item={item}
              kind={kind}
              busy={actionBusy && pendingName === item.name}
              onRestore={() => onRestore(item.name)}
              onHardDelete={() => onHardDelete(item.name)}
            />
          ))}
        </div>
      ) : null}
      {open && !count ? (
        <p className="border-t border-line p-4 text-sm text-zinc-500">
          暂无已归档资产。
        </p>
      ) : null}
    </div>
  );
}

function ArchivedCard({ item, kind, busy, onRestore, onHardDelete }) {
  return (
    <article className="rounded-lg border border-line bg-white p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="truncate text-sm font-semibold text-zinc-900">{item.name}</h4>
          <p className="mt-1 line-clamp-2 text-xs text-zinc-500">
            {item.description || "暂无描述"}
          </p>
        </div>
        <StatusPill status="已归档" />
      </div>
      <div className="mt-3 flex gap-2">
        <button
          className="secondary-button flex-1 justify-center"
          onClick={onRestore}
          disabled={busy}
        >
          <RotateCcw className="h-3.5 w-3.5" />
          恢复
        </button>
        <button
          className="secondary-button flex-1 justify-center text-rose-700 hover:bg-rose-50"
          onClick={onHardDelete}
          disabled={busy}
        >
          <Trash2 className="h-3.5 w-3.5" />
          永久删除
        </button>
      </div>
      <p className="mt-2 text-[11px] text-zinc-500">
        路径：<span className="font-mono">{kind === "skill" ? "skills" : "tools"}/{item.name}/</span>
      </p>
    </article>
  );
}

function AssetGrid({ items, empty, render, leading }) {
  if (!items?.length && !leading) return <EmptyState title={empty} />;
  return (
    <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
      {leading}
      {(items || []).map(render)}
    </div>
  );
}

function CreateEntryCard({ title, description, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex h-full min-h-[180px] cursor-pointer flex-col items-start gap-3 rounded-xl border-2 border-dashed border-blue-300 bg-blue-50/40 p-5 text-left transition hover:border-appleBlue hover:bg-blue-50/70"
    >
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-white text-appleBlue ring-1 ring-blue-200 group-hover:ring-appleBlue">
        <Plus className="h-4 w-4" />
      </span>
      <div>
        <p className="text-base font-semibold text-zinc-950">{title}</p>
        <p className="mt-1 text-sm leading-6 text-zinc-600">{description}</p>
      </div>
      <span className="primary-button mt-auto">创建</span>
    </button>
  );
}

function AssetCard({ title, description, status, rows, metrics, children, onClick, onDelete, deleteBusy }) {
  return (
    <article className="section-panel cursor-pointer p-4 transition hover:border-zinc-300" onClick={onClick}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-zinc-950">{title}</h2>
          {description ? <p className="mt-1 line-clamp-2 text-sm leading-6 text-zinc-500">{description}</p> : null}
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={status || "draft"} />
          {onDelete ? (
            <button
              type="button"
              className="rounded-md p-1.5 text-zinc-400 hover:bg-rose-50 hover:text-rose-600"
              title="删除（归档）"
              disabled={deleteBusy}
              onClick={(event) => {
                event.stopPropagation();
                onDelete();
              }}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>
      {children}
      {metrics?.length ? (
        <div className="mt-4 grid grid-cols-3 gap-2">
          {metrics.map(([label, value]) => (
            <div className="rounded-lg border border-line bg-zinc-50 px-3 py-2" key={label}>
              <p className="text-[11px] font-medium text-zinc-500">{label}</p>
              <p className="mt-1 truncate text-sm font-semibold text-zinc-950">{compact(value, "0")}</p>
            </div>
          ))}
        </div>
      ) : null}
      <div className="mt-4 space-y-2.5 border-t border-line pt-4">
        {rows.map(([label, value]) => (
          <Metric label={label} value={value} key={label} />
        ))}
      </div>
    </article>
  );
}

function MemoryPromotionProgress({ progress, t }) {
  if (!progress) return null;
  const { decision, next_step: nextStep, occurrence_count: count, occurrence_threshold: threshold, occurrences_remaining: remaining, promotion_score: score, linked_promo_id: promo } = progress;
  const kind = nextStep?.kind || "waiting_signal";

  const ratio = Math.min(1, Math.max(0, threshold ? count / threshold : 0));
  const widthPercent = Math.round(ratio * 100);

  const tone = (() => {
    if (kind === "ready_to_promote" || kind === "already_promoted") return "emerald";
    if (kind === "rejected") return "rose";
    if (kind === "policy_review_required" || kind === "attribution_review_required") return "amber";
    return "blue";
  })();
  const toneClass = {
    emerald: { bar: "bg-emerald-500", border: "border-emerald-200", bg: "bg-emerald-50/70", text: "text-emerald-800" },
    rose: { bar: "bg-rose-500", border: "border-rose-200", bg: "bg-rose-50/70", text: "text-rose-800" },
    amber: { bar: "bg-amber-500", border: "border-amber-200", bg: "bg-amber-50/70", text: "text-amber-800" },
    blue: { bar: "bg-appleBlue", border: "border-blue-200", bg: "bg-blue-50/60", text: "text-zinc-700" },
  }[tone];

  const headline = (() => {
    if (kind === "already_promoted") return t("memory.progress.already_promoted", { promo });
    if (kind === "ready_to_promote") return t("memory.progress.ready_to_promote");
    if (kind === "rejected") return t("memory.progress.rejected");
    if (kind === "policy_review_required") return t("memory.progress.policy_review");
    if (kind === "attribution_review_required") return t("memory.progress.attribution_required");
    if (kind === "needs_more_occurrences" && remaining === 1) return t("memory.progress.next_one_more");
    if (kind === "needs_more_occurrences") return t("memory.progress.need_more", { remaining, threshold });
    return t("memory.progress.waiting_signal");
  })();

  return (
    <div className={`mt-4 rounded-lg border px-3 py-2.5 ${toneClass.border} ${toneClass.bg}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
          {t("memory.progress.title")}
        </span>
        <span className={`text-[11px] font-semibold ${toneClass.text}`}>
          {t(`memory.decision.${decision || "wait"}`) || decision}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-3">
        <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-white/80">
          <div className={`absolute inset-y-0 left-0 transition-all ${toneClass.bar}`} style={{ width: `${widthPercent}%` }} />
        </div>
        <span className="font-mono text-[11px] font-semibold text-zinc-700">
          {t("memory.progress.occurrences", { count, threshold })}
        </span>
      </div>
      <p className={`mt-2 text-xs leading-5 ${toneClass.text}`}>{headline}</p>
      {score ? (
        <div className="mt-1 text-[11px] text-zinc-500">
          {t("memory.progress.score")}: <span className="font-mono font-semibold text-zinc-700">{score.toFixed(2)}</span>
        </div>
      ) : null}
    </div>
  );
}

function AssetDetailModal({
  selected,
  detail,
  loading,
  error,
  tab,
  setTab,
  reviews,
  changes,
  versions,
  memories,
  onClose,
  onOpenReview,
  onOpenVersions,
}) {
  const assetType = selected.assetType;
  const name = selected.asset.name || selected.asset.target_skill || selected.asset.promo_id;
  const scopedReviews = filterByAsset(reviews, assetType, name);
  const scopedChanges = filterByAsset(changes, assetType, name);
  const scopedVersions = assetType === "skill" ? (versions || []).filter((item) => item.skill === name) : [];
  const scopedMemories = assetType === "skill" ? (memories || []).filter((item) => item.skill === name) : [];
  const tabs = ["overview", "files", "changes", "reviews", "versions", "eval", "memory"];
  const [toolTestInput, setToolTestInput] = useState("");
  const [toolTestResult, setToolTestResult] = useState(null);
  const [toolTestError, setToolTestError] = useState("");

  useEffect(() => {
    if (assetType !== "tool") return;
    setToolTestInput(JSON.stringify(defaultToolTestInputs(detail || selected.asset), null, 2));
    setToolTestResult(null);
    setToolTestError("");
  }, [assetType, name, detail?.name]);

  async function runToolTest() {
    setToolTestError("");
    setToolTestResult(null);
    let inputs = {};
    try {
      inputs = toolTestInput.trim() ? JSON.parse(toolTestInput) : {};
    } catch {
      setToolTestError("Invalid JSON input.");
      return;
    }
    try {
      const payload = await api.runTool(name, inputs);
      setToolTestResult(payload);
    } catch (err) {
      setToolTestError(getErrorMessage(err));
      setToolTestResult(err.payload || null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/30 p-4">
      <div className="max-h-[88vh] w-full max-w-6xl overflow-hidden rounded-lg border border-line bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <p className="muted-label">{titleize(assetType)} Asset</p>
            <h2 className="mt-1 truncate text-lg font-semibold text-zinc-950">{name}</h2>
            <p className="mt-1 text-sm text-zinc-500">{detail.description || selected.asset.description || selected.asset.reason || "SafeHarness asset detail."}</p>
          </div>
          <button className="rounded-md p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="border-b border-line px-5 pt-3">
          <div className="flex flex-wrap gap-2">
            {tabs.map((id) => (
              <button
                key={id}
                className={[
                  "rounded-md px-3 py-2 text-sm font-semibold",
                  tab === id ? "bg-zinc-950 text-white" : "text-zinc-600 hover:bg-zinc-50",
                ].join(" ")}
                onClick={() => setTab(id)}
              >
                {titleize(id)}
              </button>
            ))}
          </div>
        </div>
        <div className="max-h-[62vh] overflow-auto p-5">
          {loading ? <p className="text-sm text-zinc-500">Loading asset details...</p> : null}
          {error ? <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">{error}</p> : null}
          {!loading && tab === "overview" ? (
            <OverviewTab
              detail={detail}
              selected={selected}
              scopedChanges={scopedChanges}
              scopedReviews={scopedReviews}
              scopedVersions={scopedVersions}
              toolTestInput={toolTestInput}
              setToolTestInput={setToolTestInput}
              toolTestResult={toolTestResult}
              toolTestError={toolTestError}
              onRunToolTest={runToolTest}
            />
          ) : null}
          {!loading && tab === "files" ? <FilesTab assetType={assetType} detail={detail} /> : null}
          {!loading && tab === "changes" ? <CompactTable items={scopedChanges} empty="No changes for this asset." kind="changes" /> : null}
          {!loading && tab === "reviews" ? <ReviewList reviews={scopedReviews} onOpenReview={onOpenReview} /> : null}
          {!loading && tab === "versions" ? <VersionList versions={scopedVersions} onOpenVersions={onOpenVersions} /> : null}
          {!loading && tab === "eval" ? <EvalTab assetType={assetType} detail={detail} selected={selected} /> : null}
          {!loading && tab === "memory" ? <MemoryTab assetType={assetType} detail={detail} memories={scopedMemories} /> : null}
        </div>
      </div>
    </div>
  );
}

function OverviewTab({
  detail,
  selected,
  scopedChanges,
  scopedReviews,
  scopedVersions,
  toolTestInput,
  setToolTestInput,
  toolTestResult,
  toolTestError,
  onRunToolTest,
}) {
  const isTool = selected.assetType === "tool";
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-3">
        <Metric label="Asset type" value={selected.assetType} />
        <Metric label="Asset name" value={selected.asset.name || selected.asset.promo_id} />
        <Metric label="Current version" value={detail.latest_version || detail.active_version || detail.status || selected.asset.linked_version || "draft"} />
        <Metric label="Status" value={detail.status || selected.asset.status || selected.asset.promotion_decision || "active"} />
        {isTool ? <Metric label="Asset exists" value={detail.asset_exists ? "yes" : "no"} /> : null}
        {isTool ? <Metric label="Handler" value={detail.handler_available ? "available" : "missing"} /> : null}
        {isTool ? <Metric label="Provider" value={detail.provider_configured ? "configured" : "missing"} /> : null}
        {isTool ? <Metric label="Executable" value={detail.executable ? "yes" : "no"} /> : null}
        {isTool ? <Metric label="Provider reqs" value={compact(detail.provider_requirements, "none")} /> : null}
        {isTool ? <Metric label="Missing" value={compact(detail.missing, "none")} /> : null}
        <Metric label="Latest change" value={scopedChanges[0]?.change_id} />
        <Metric label="Pending review" value={scopedReviews.find((review) => ["pending", "approved"].includes(review.status))?.review_id} />
      </div>
      <div className="space-y-4 self-start">
        <div className="grid grid-cols-3 gap-2">
          <SmallMetric label="Changes" value={scopedChanges.length} />
          <SmallMetric label="Reviews" value={scopedReviews.length} />
          <SmallMetric label="Versions" value={scopedVersions.length} />
        </div>
        {isTool ? (
          <div className="rounded-lg border border-line p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-zinc-950">Test tool</h3>
              <button className="subprimary-button px-3 py-1.5" onClick={onRunToolTest}>
                <Play className="h-4 w-4" />
                Run
              </button>
            </div>
            <textarea
              className="min-h-32 w-full resize-y rounded-md border border-line bg-zinc-50 p-3 font-mono text-xs leading-5 text-zinc-800 outline-none focus:border-zinc-400"
              value={toolTestInput}
              onChange={(event) => setToolTestInput(event.target.value)}
              spellCheck={false}
            />
            {toolTestError ? <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">{toolTestError}</p> : null}
            {toolTestResult ? <DetailBlock title="Result" value={toolTestResult} /> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function FilesTab({ assetType, detail }) {
  if (assetType === "tool") {
    const files = detail.files || {};
    return (
      <div className="space-y-4">
        <FilePanel file={files.schema} fallbackPath={detail.schema_path} />
        <FilePanel file={files.readme} fallbackPath={detail.readme_path} />
        <FilePanel file={files.eval_cases} fallbackPath={detail.eval_cases_path} />
      </div>
    );
  }
  if (assetType === "skill") {
    const files = detail.files || {};
    return (
      <div className="space-y-4">
        <FilePanel file={files.active} fallbackPath={detail.active_file} />
        <FilePanel file={files.eval_cases} fallbackPath={`skills/${detail.name}/eval/cases.yaml`} />
      </div>
    );
  }
  return <EmptyState title="No file-backed view for this asset yet." />;
}

function EvalTab({ assetType, detail, selected }) {
  if (assetType === "tool") return <FilePanel file={detail.files?.eval_cases} fallbackPath={detail.eval_cases_path} />;
  if (assetType === "skill") return <FilePanel file={detail.files?.eval_cases} fallbackPath={`skills/${selected.asset.name}/eval/cases.yaml`} />;
  return <DetailBlock title="Workflow eval status" value={selected.asset.schema_status || "waiting"} />;
}

function MemoryTab({ assetType, detail, memories }) {
  if (assetType === "skill") {
    return (
      <div className="space-y-4">
        <DetailBlock title="Memory summary" value={detail.memory || {}} />
        <CompactTable items={memories} empty="No memory records for this asset." kind="memory" />
      </div>
    );
  }
  return <DetailBlock title="Memory / PROMO source" value={detail.source_memory_ids || detail.linked_promotions || []} />;
}

function ReviewList({ reviews, onOpenReview }) {
  if (!reviews?.length) return <EmptyState title="No reviews for this asset." />;
  return (
    <div className="space-y-3">
      {reviews.map((review) => (
        <div key={review.review_id} className="rounded-lg border border-line p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <span className="mono-badge">{review.review_id}</span>
              <p className="mt-2 text-sm font-semibold text-zinc-950">{titleize(review.type)}</p>
              <p className="mt-1 text-xs text-zinc-500">{compact(review.reason)}</p>
            </div>
            <div className="flex items-center gap-2">
              <StatusPill status={review.status} />
              <button className="secondary-button px-3 py-1.5" onClick={() => onOpenReview?.(review.review_id)}>
                <GitPullRequest className="h-4 w-4" />
                Open
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function VersionList({ versions, onOpenVersions }) {
  if (!versions?.length) return <EmptyState title="No versions for this asset yet." />;
  return (
    <div className="space-y-3">
      {versions.map((version) => (
        <div key={`${version.skill}:${version.version}`} className="rounded-lg border border-line p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <span className="mono-badge">{version.version}</span>
              <p className="mt-2 text-sm font-semibold text-zinc-950">{version.skill}</p>
              <p className="mt-1 text-xs text-zinc-500">{formatDate(version.created_at)}</p>
            </div>
            <button className="subprimary-button px-3 py-1.5" onClick={onOpenVersions}>Open Versions</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function CompactTable({ items, empty, kind }) {
  if (!items?.length) return <EmptyState title={empty} />;
  return (
    <div className="section-panel overflow-hidden shadow-none">
      <div className="divide-y divide-line">
        {items.map((item, index) => (
          <div className="grid gap-3 px-4 py-3 md:grid-cols-[10rem_1fr_8rem_8rem]" key={item.change_id || item.memory_id || index}>
            <span className="mono-badge w-fit">{item.change_id || item.memory_id || item.type}</span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-zinc-950">{item.asset_name || item.title || item.reason || "-"}</span>
              <span className="mt-1 block text-xs text-zinc-500">{kind === "changes" ? `${titleize(item.asset_type)} · ${titleize(item.operation)}` : titleize(item.type)}</span>
            </span>
            <StatusPill status={item.status || item.promotion_decision || "recorded"} />
            <span className="text-xs font-semibold text-zinc-500">{formatDate(item.created_at || item.updated_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DetailBlock({ title, value }) {
  const content = Array.isArray(value)
    ? value.join("\n")
    : typeof value === "object" && value
      ? JSON.stringify(value, null, 2)
      : compact(value);
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase text-zinc-500">{title}</h3>
      <pre className="max-h-56 overflow-auto rounded-md border border-line bg-zinc-50 p-3 text-xs leading-5 text-zinc-800">{content || "missing"}</pre>
    </div>
  );
}

function FilePanel({ file, fallbackPath }) {
  const path = file?.path || fallbackPath || "missing";
  const exists = file?.exists;
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="break-all text-sm font-semibold text-zinc-700">{path}</p>
        <span className="rounded-md border border-line px-2 py-1 text-xs font-semibold text-zinc-500">{exists ? "present" : "missing"}</span>
      </div>
      {exists ? (
        <pre className="max-h-[38vh] overflow-auto rounded-md border border-line bg-zinc-50 p-4 text-xs leading-5 text-zinc-800">{file.content}</pre>
      ) : (
        <div className="rounded-md border border-dashed border-line bg-zinc-50 p-4 text-sm font-semibold text-zinc-500">missing</div>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3 text-sm">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      <span className="min-w-0 break-words text-right font-semibold text-zinc-900">{compact(value)}</span>
    </div>
  );
}

function SmallMetric({ label, value }) {
  return (
    <div className="rounded-lg border border-line bg-zinc-50 px-3 py-2">
      <p className="text-[11px] font-medium text-zinc-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-zinc-950">{compact(value, "0")}</p>
    </div>
  );
}

function defaultToolTestInputs(tool) {
  if (tool?.name === "weather_query" || tool?.capability === "weather_query") {
    return { city: "上海", date: "today", units: "metric", language: "zh-CN" };
  }
  const inputs = tool?.inputs || {};
  if (inputs.city) return { city: "上海", date: "today", units: "metric", language: "zh-CN" };
  if (inputs.query) return { query: "OpenAI API documentation", max_results: 3, language: "zh-CN" };
  if (inputs.path) return { path: "docs/README.md" };
  if (inputs.command) return { command: "git status --short" };
  return {};
}

function assetRows({ assetType, name, currentVersion, evalStatus, latestChange, pendingReview }) {
  return [
    ["Current version", currentVersion],
    ["Status", assetType === "tool" ? "tool asset" : "active asset"],
    ["Latest change", latestChange],
    ["Pending review", pendingReview],
    ["Eval status", evalStatus],
    ["Path", assetType === "tool" ? `tools/${name}/` : `skills/${name}/`],
  ];
}

function latestChange(assetType, name, changes) {
  return filterByAsset(changes, assetType, name)[0]?.change_id || "-";
}

function pendingReview(assetType, name, reviews) {
  return filterByAsset(reviews, assetType, name).find((review) => ["pending", "approved"].includes(review.status))?.review_id || "-";
}

function assetStatus(assetType, name, reviews, asset) {
  // 1) explicit lifecycle marker from the asset-creation pipeline
  const lifecycle = asset?.lifecycle_status;
  if (lifecycle && lifecycle !== "active") {
    return LIFECYCLE_LABEL[lifecycle] || lifecycle;
  }
  // 2) otherwise fall back to the existing pending-review heuristic
  const review = filterByAsset(reviews, assetType, name).find((item) => ["pending", "approved"].includes(item.status));
  return review?.status || "active";
}

const LIFECYCLE_LABEL = {
  draft: "草稿",
  system_check: "系统校验中",
  pending_review: "待审查",
  active: "已上架",
  rejected: "未通过",
  archived: "已归档",
  disabled: "已禁用",
};

function filterByAsset(items, assetType, name) {
  return (items || []).filter((item) => {
    if (item.asset_type && item.asset_type !== assetType) return false;
    if (item.asset_name) return item.asset_name === name;
    if (item.target_skill) return item.target_skill === name;
    if (item.metadata?.tool_name) return item.metadata.tool_name === name;
    return (item.target_files || []).some((path) => String(path).includes(`/${name}/`) || String(path).includes(`\\${name}\\`));
  });
}
