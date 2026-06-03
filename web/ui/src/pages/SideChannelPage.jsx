import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  RefreshCcw,
  EyeOff,
  Eye,
  AlertTriangle,
  Wrench,
  UserCheck,
  Sparkles,
  RotateCcw,
} from "lucide-react";
import EmptyState from "../components/EmptyState";
import Paginator, { paginate } from "../components/Paginator";
import { api, getErrorMessage } from "../lib/api";
import { useTranslate } from "../lib/i18n.jsx";
import {
  buildOpportunityView,
  buildEditView,
  CATEGORY_KEYS,
} from "../lib/scoutViewModel.js";

const TAB_KEYS = ["findings", "suggestions", "drafts", "ignored"];

const IGNORE_STORAGE_KEY = "harness.sideChannel.ignored.v1";

function loadIgnored() {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(IGNORE_STORAGE_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}

function saveIgnored(set) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      IGNORE_STORAGE_KEY,
      JSON.stringify(Array.from(set)),
    );
  } catch {
    /* ignore */
  }
}

export default function SideChannelPage() {
  const t = useTranslate();
  const [tab, setTab] = useState("findings");
  const [signals, setSignals] = useState([]);
  const [opportunities, setOpportunities] = useState([]);
  const [batches, setBatches] = useState([]);
  const [edits, setEdits] = useState([]);
  const [rejected, setRejected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState({ message: "", tone: "info" });
  const [pages, setPages] = useState({ findings: 1, suggestions: 1, drafts: 1, ignored: 1 });
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [ignored, setIgnored] = useState(() => loadIgnored());

  const refresh = useCallback(async () => {
    try {
      const [sig, opps, btc, eds, rej] = await Promise.all([
        api.evolutionScoutSignals(),
        api.evolutionScoutOpportunities(),
        api.evolutionScoutBatches(),
        api.evolutionOptimizerEdits(),
        api.evolutionOptimizerRejected(),
      ]);
      setSignals(sig.data || []);
      setOpportunities(opps.data || []);
      setBatches(btc.data || []);
      setEdits(eds.data || []);
      setRejected(rej.data || []);
    } catch (error) {
      setStatus({ message: getErrorMessage(error), tone: "error" });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setPage = useCallback((key, next) => {
    setPages((prev) => ({ ...prev, [key]: next }));
  }, []);

  const switchTab = useCallback((next) => {
    setTab(next);
    setPages((prev) => ({ ...prev, [next]: 1 }));
  }, []);

  const runScan = useCallback(async () => {
    setBusy(true);
    try {
      const result = await api.evolutionScoutScan();
      setStatus({
        message:
          result.message || result.data?.summary || t("side_channel.status.scan_done"),
        tone: "success",
      });
      await refresh();
    } catch (error) {
      setStatus({ message: getErrorMessage(error), tone: "error" });
    } finally {
      setBusy(false);
    }
  }, [refresh, t]);

  const ignoreOpp = useCallback((id, note = "") => {
    setIgnored((prev) => {
      const next = new Set(prev);
      next.add(id);
      saveIgnored(next);
      return next;
    });
    setStatus({ message: note || "已加入忽略列表。", tone: "success" });
  }, []);

  const restoreOpp = useCallback((id) => {
    setIgnored((prev) => {
      const next = new Set(prev);
      next.delete(id);
      saveIgnored(next);
      return next;
    });
    setStatus({ message: "已从忽略列表恢复。", tone: "success" });
  }, []);

  const generateSkillPatch = useCallback(
    async (oppId) => {
      setBusy(true);
      try {
        const batchResult = await api.evolutionScoutBatchCreate([oppId]);
        const batchId = batchResult.data?.batch_id;
        if (!batchId) {
          throw new Error("后端没有返回 batch_id。");
        }
        const editResult = await api.evolutionOptimizerPropose({ batch_id: batchId });
        setStatus({
          message: editResult.message || "已生成变更草稿，请到「变更草稿」核对。",
          tone: "success",
        });
        await refresh();
        setTab("drafts");
      } catch (error) {
        setStatus({ message: getErrorMessage(error), tone: "error" });
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const validateEdit = useCallback(
    async (editId) => {
      setBusy(true);
      try {
        const result = await api.evolutionOptimizerValidate(editId);
        setStatus({ message: result.message, tone: "success" });
        await refresh();
      } catch (error) {
        setStatus({ message: getErrorMessage(error), tone: "error" });
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  const signalsById = useMemo(
    () => Object.fromEntries(signals.map((s) => [s.signal_id, s])),
    [signals],
  );

  const allViews = useMemo(
    () => opportunities.map((opp) => buildOpportunityView(opp, signalsById)),
    [opportunities, signalsById],
  );

  const activeViews = useMemo(
    () => allViews.filter((v) => !ignored.has(v.id)),
    [allViews, ignored],
  );

  const findingViews = useMemo(
    () =>
      activeViews.filter((v) =>
        categoryFilter === "all" ? true : v.category === categoryFilter,
      ),
    [activeViews, categoryFilter],
  );

  const suggestionItems = useMemo(
    () =>
      batches.map((batch) => {
        const memberOpps = (batch.opportunity_ids || [])
          .map((oid) => allViews.find((v) => v.id === oid))
          .filter(Boolean);
        const category =
          memberOpps[0]?.category || "skill_optimization";
        return { batch, memberOpps, category };
      }),
    [batches, allViews],
  );

  const draftViews = useMemo(
    () => edits.map((edit) => buildEditView(edit)).filter(Boolean),
    [edits],
  );

  const ignoredItems = useMemo(() => {
    const localItems = allViews.filter((v) => ignored.has(v.id));
    const rejectedItems = rejected.map((edit) => ({
      kind: "rejected_edit",
      id: edit.edit_id,
      title: `已被验证拒绝的变更草稿：${edit.edit_id}`,
      reason: edit.reject_reason || "—",
      createdAt: edit.created_at,
    }));
    const localItemsShaped = localItems.map((v) => ({
      kind: "local_ignored",
      id: v.id,
      title: v.title,
      reason: "用户手动忽略。",
      view: v,
    }));
    return [...rejectedItems, ...localItemsShaped];
  }, [allViews, ignored, rejected]);

  const counts = useMemo(
    () => ({
      findings: findingViews.length,
      suggestions: suggestionItems.length,
      drafts: draftViews.length,
      ignored: ignoredItems.length,
    }),
    [findingViews.length, suggestionItems.length, draftViews.length, ignoredItems.length],
  );

  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-zinc-950">
              旁路进化 · 问题发现与处理工作台
            </h2>
            <p className="mt-1 text-xs text-zinc-500">
              系统会定期扫描 memory 与 RunTrace，把可能的 skill 改进点、安全/策略事件、工具问题挑出来。
              任何 SKILL.md 修改仍然要走 Review → Approve → Apply。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="secondary-button"
              onClick={refresh}
              disabled={busy}
              title="重新拉取最新数据"
            >
              <RefreshCcw className="h-4 w-4" />
              刷新
            </button>
            <button
              className="primary-button"
              onClick={runScan}
              disabled={busy}
            >
              <Activity className="h-4 w-4" />
              重新扫描
            </button>
          </div>
        </header>

        {status.message ? (
          <div
            className={[
              "rounded-lg border px-3 py-2 text-sm",
              status.tone === "error"
                ? "border-rose-200 bg-rose-50/60 text-rose-700"
                : "border-emerald-200 bg-emerald-50/60 text-emerald-700",
            ].join(" ")}
          >
            {status.message}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 rounded-lg border border-line bg-white p-1 shadow-hairline">
          {TAB_KEYS.map((key) => (
            <button
              key={key}
              className={[
                "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition",
                tab === key
                  ? "bg-zinc-950 text-white"
                  : "text-zinc-700 hover:bg-zinc-50",
              ].join(" ")}
              onClick={() => switchTab(key)}
            >
              {tabLabel(key)}
              {counts[key] ? (
                <span
                  className={[
                    "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                    tab === key ? "bg-white/20 text-white" : "bg-zinc-100 text-zinc-600",
                  ].join(" ")}
                >
                  {counts[key]}
                </span>
              ) : null}
            </button>
          ))}
        </div>

        {tab === "findings" ? (
          <FindingsTab
            views={findingViews}
            allCount={activeViews.length}
            categoryFilter={categoryFilter}
            onCategoryChange={setCategoryFilter}
            page={pages.findings}
            onPage={(n) => setPage("findings", n)}
            onIgnore={(id) => ignoreOpp(id)}
            onGeneratePatch={generateSkillPatch}
            busy={busy}
          />
        ) : null}

        {tab === "suggestions" ? (
          <SuggestionsTab
            items={suggestionItems}
            page={pages.suggestions}
            onPage={(n) => setPage("suggestions", n)}
            onGenerateDraft={async (batchId) => {
              setBusy(true);
              try {
                const result = await api.evolutionOptimizerPropose({ batch_id: batchId });
                setStatus({
                  message: result.message || "已生成变更草稿。",
                  tone: "success",
                });
                await refresh();
                setTab("drafts");
              } catch (error) {
                setStatus({ message: getErrorMessage(error), tone: "error" });
              } finally {
                setBusy(false);
              }
            }}
            busy={busy}
          />
        ) : null}

        {tab === "drafts" ? (
          <DraftsTab
            views={draftViews}
            page={pages.drafts}
            onPage={(n) => setPage("drafts", n)}
            onValidate={validateEdit}
            busy={busy}
          />
        ) : null}

        {tab === "ignored" ? (
          <IgnoredTab
            items={ignoredItems}
            page={pages.ignored}
            onPage={(n) => setPage("ignored", n)}
            onRestore={restoreOpp}
          />
        ) : null}
      </div>
    </section>
  );
}

function tabLabel(key) {
  switch (key) {
    case "findings":
      return "发现的问题";
    case "suggestions":
      return "建议处理";
    case "drafts":
      return "变更草稿";
    case "ignored":
      return "已忽略";
    default:
      return key;
  }
}

// ---------------------------------------------------------- Findings tab

function FindingsTab({
  views,
  allCount,
  categoryFilter,
  onCategoryChange,
  page,
  onPage,
  onIgnore,
  onGeneratePatch,
  busy,
}) {
  if (!allCount) {
    return <EmptyState title="暂无发现。请先运行扫描。" />;
  }
  const { pageItems, total, pageCount, page: safePage } = paginate(views, page);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-white p-2 text-xs">
        <span className="text-zinc-500">按类型筛选：</span>
        {["all", ...CATEGORY_KEYS].map((key) => (
          <button
            key={key}
            className={[
              "rounded-full px-2.5 py-0.5 text-xs font-semibold transition",
              categoryFilter === key
                ? "bg-zinc-950 text-white"
                : "border border-line bg-white text-zinc-600 hover:bg-zinc-50",
            ].join(" ")}
            onClick={() => onCategoryChange(key)}
          >
            {categoryButtonLabel(key)}
          </button>
        ))}
      </div>
      {views.length === 0 ? (
        <EmptyState title="该类型暂无发现。" />
      ) : (
        pageItems.map((view) => (
          <FindingCard
            key={view.id}
            view={view}
            onIgnore={() => onIgnore(view.id)}
            onGeneratePatch={() => onGeneratePatch(view.id)}
            busy={busy}
          />
        ))
      )}
      <Paginator page={safePage} pageCount={pageCount} total={total} onPage={onPage} />
    </div>
  );
}

function categoryButtonLabel(key) {
  switch (key) {
    case "all":
      return "全部";
    case "skill_optimization":
      return "Skill 优化";
    case "policy_event":
      return "策略 / 安全事件";
    case "tool_event":
      return "工具 / 能力问题";
    case "needs_label":
      return "需人工标注";
    default:
      return key;
  }
}

function CategoryIcon({ category, className = "h-4 w-4" }) {
  switch (category) {
    case "policy_event":
      return <AlertTriangle className={className} />;
    case "tool_event":
      return <Wrench className={className} />;
    case "needs_label":
      return <UserCheck className={className} />;
    case "skill_optimization":
    default:
      return <Sparkles className={className} />;
  }
}

function FindingCard({ view, onIgnore, onGeneratePatch, busy }) {
  return (
    <article className="section-panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={[
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                view.categoryTone,
              ].join(" ")}
            >
              <CategoryIcon category={view.category} className="h-3 w-3" />
              {view.categoryLabel}
            </span>
            <span
              className={[
                "rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                view.riskTone,
              ].join(" ")}
            >
              风险：{view.riskLabel}
            </span>
            <span className="rounded-full border border-line bg-white px-2 py-0.5 text-[11px] text-zinc-600">
              可信度：{view.confidenceLabel}
            </span>
            <span className="text-xs text-zinc-500">
              影响对象：<span className="font-medium text-zinc-700">{view.impactTarget}</span>
            </span>
          </div>
          <h3 className="mt-2 text-sm font-semibold text-zinc-950">{view.title}</h3>
          <FactGrid>
            <FactRow label="发生了什么">{view.whatHappened}</FactRow>
            <FactRow label="系统判断">{view.judgement}</FactRow>
            <FactRow label="建议动作">{view.nextStep}</FactRow>
          </FactGrid>
          {view.suggestions.length ? (
            <Bullets label="可以改进的方向" values={view.suggestions} />
          ) : null}
          {view.guardrails.length ? (
            <Bullets label="不允许动" values={view.guardrails} />
          ) : null}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 border-t border-line pt-3">
        <ActionButtons
          category={view.category}
          busy={busy}
          onIgnore={onIgnore}
          onGeneratePatch={onGeneratePatch}
        />
      </div>

      <details className="mt-3 text-xs">
        <summary className="cursor-pointer text-zinc-500">展开调试信息</summary>
        <DebugBlock view={view} />
      </details>
    </article>
  );
}

function ActionButtons({ category, busy, onIgnore, onGeneratePatch }) {
  const ignoreBtn = (
    <button
      key="ignore"
      className="secondary-button"
      onClick={onIgnore}
      disabled={busy}
    >
      <EyeOff className="h-4 w-4" />
      忽略
    </button>
  );
  const observeBtn = (
    <button
      key="observe"
      className="secondary-button"
      onClick={onIgnore}
      disabled={busy}
      title="本次扫描内不再提示，下次扫描出现新证据时仍会重新评估。"
    >
      <Eye className="h-4 w-4" />
      继续观察
    </button>
  );
  switch (category) {
    case "skill_optimization":
      return [
        <button
          key="patch"
          className="primary-button"
          onClick={onGeneratePatch}
          disabled={busy}
        >
          <Sparkles className="h-4 w-4" />
          生成 Skill 补丁
        </button>,
        <button
          key="regression"
          className="secondary-button"
          onClick={() =>
            alert(
              "建议先到 Self-Evolution → 候选 PROMO 用 /evolve-skill 流程为该 skill 补一组正/负回归 case，再回来生成 Skill 补丁。",
            )
          }
          disabled={busy}
        >
          生成回归测试
        </button>,
        ignoreBtn,
      ];
    case "policy_event":
      return [
        <button
          key="policy"
          className="primary-button"
          onClick={() =>
            alert(
              "策略事件需要人工策略审查：可在 Reviews 队列中以 policy_review 标记新建，本工作台不会自动落盘。",
            )
          }
          disabled={busy}
        >
          <AlertTriangle className="h-4 w-4" />
          创建策略审查
        </button>,
        observeBtn,
        ignoreBtn,
      ];
    case "tool_event":
      return [
        <button
          key="tool"
          className="primary-button"
          onClick={() =>
            alert("工具/能力问题应去 Assets → Tools 排查；不能把工具失败硬编码进 skill 规则。")
          }
          disabled={busy}
        >
          <Wrench className="h-4 w-4" />
          创建工具审查
        </button>,
        observeBtn,
        ignoreBtn,
      ];
    case "needs_label":
      return [
        <button
          key="label"
          className="primary-button"
          onClick={() =>
            alert("请到来源 memory（.skills_memory/ 或 skills/<skill>/memory/）把 Target Skill 字段改成真实的 skill 名，再回来重新扫描。")
          }
          disabled={busy}
        >
          <UserCheck className="h-4 w-4" />
          标注归属 Skill
        </button>,
        ignoreBtn,
      ];
    default:
      return [ignoreBtn];
  }
}

function DebugBlock({ view }) {
  const opp = view.raw || {};
  return (
    <div className="mt-2 grid gap-2 rounded-md border border-line bg-zinc-50/60 p-3 text-[11px] text-zinc-600 sm:grid-cols-2">
      <div><b>opportunity_id：</b><span className="font-mono">{opp.opportunity_id}</span></div>
      <div><b>decision：</b><span className="font-mono">{opp.decision}</span></div>
      <div><b>opportunity_type：</b><span className="font-mono">{opp.opportunity_type}</span></div>
      <div><b>priority：</b><span className="font-mono">{opp.priority}</span></div>
      <div><b>value_score：</b><span className="font-mono">{Number(opp.value_score || 0).toFixed(3)}</span></div>
      <div><b>risk_score：</b><span className="font-mono">{Number(opp.risk_score || 0).toFixed(3)}</span></div>
      <div><b>evidence_quality：</b><span className="font-mono">{Number(opp.evidence_quality || 0).toFixed(3)}</span></div>
      <div><b>testability：</b><span className="font-mono">{Number(opp.testability || 0).toFixed(3)}</span></div>
      <div className="sm:col-span-2"><b>score_breakdown：</b><span className="font-mono">{opp.score_breakdown || "—"}</span></div>
      <div className="sm:col-span-2"><b>reason 原文：</b>{opp.reason || "—"}</div>
      {view.sources.length ? (
        <div className="sm:col-span-2">
          <b>来源信号：</b>
          <ul className="mt-1 space-y-1">
            {view.sources.map((s) => (
              <li key={s.id} className="font-mono text-[10.5px]">
                {s.sourceRef} @ {s.sourcePath}
                <span className="ml-2 font-sans text-zinc-500">{s.preview}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------- Suggestions tab

function SuggestionsTab({ items, page, onPage, onGenerateDraft, busy }) {
  if (!items.length) {
    return (
      <EmptyState title="暂无建议处理。需要在「发现的问题」里选择一项点「生成 Skill 补丁」。" />
    );
  }
  const { pageItems, total, pageCount, page: safePage } = paginate(items, page);
  return (
    <div className="space-y-3">
      {pageItems.map(({ batch, memberOpps, category }) => {
        const isSkillCategory = category === "skill_optimization";
        return (
          <article key={batch.batch_id} className="section-panel p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1 rounded-full border border-line bg-zinc-50 px-2 py-0.5 text-[11px] font-semibold text-zinc-700">
                    <CategoryIcon category={category} className="h-3 w-3" />
                    {memberOpps[0]?.categoryLabel || "Skill 优化"}
                  </span>
                  <span className="text-sm font-semibold text-zinc-900">
                    {batch.target_skill}
                  </span>
                  <span className="text-xs text-zinc-500">
                    汇总 {memberOpps.length || batch.opportunity_ids?.length || 0} 条发现
                  </span>
                  <span className="text-xs text-zinc-500">
                    风险：{batch.risk_level || "—"}
                  </span>
                </div>
                <FactGrid>
                  <FactRow label="为什么建议这样改">{batch.merged_summary || "—"}</FactRow>
                  {batch.should_improve?.length ? (
                    <FactRow label="预期改进">
                      <ul className="list-disc space-y-1 pl-5">
                        {batch.should_improve.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </FactRow>
                  ) : null}
                </FactGrid>
              </div>
              {isSkillCategory ? (
                <button
                  className="primary-button"
                  onClick={() => onGenerateDraft(batch.batch_id)}
                  disabled={busy}
                >
                  <Sparkles className="h-4 w-4" />
                  生成变更草稿
                </button>
              ) : (
                <span className="rounded-md border border-amber-200 bg-amber-50/60 px-2 py-1 text-[11px] text-amber-800">
                  非 skill 优化类，不可直接生成 SKILL.md 补丁
                </span>
              )}
            </div>
            <details className="mt-3 text-xs">
              <summary className="cursor-pointer text-zinc-500">展开调试信息</summary>
              <pre className="mt-2 overflow-x-auto rounded-md border border-line bg-zinc-50/60 p-2 text-[10.5px] text-zinc-600">
{JSON.stringify(batch, null, 2)}
              </pre>
            </details>
          </article>
        );
      })}
      <Paginator page={safePage} pageCount={pageCount} total={total} onPage={onPage} />
    </div>
  );
}

// ---------------------------------------------------------- Drafts tab

function DraftsTab({ views, page, onPage, onValidate, busy }) {
  if (!views.length) {
    return <EmptyState title="暂无变更草稿。" />;
  }
  const { pageItems, total, pageCount, page: safePage } = paginate(views, page);
  return (
    <div className="space-y-3">
      {pageItems.map((draft) => (
        <article key={draft.id} className="section-panel p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-zinc-900">
                  {draft.targetSkill}
                </span>
                <span className="rounded-full border border-line bg-white px-2 py-0.5 text-[11px] text-zinc-600">
                  状态：{draft.status}
                </span>
                <span className="rounded-full border border-line bg-white px-2 py-0.5 text-[11px] text-zinc-600">
                  变更类型：{draft.changeKind}
                </span>
                <span className="text-xs text-zinc-500">
                  来源证据：{draft.sourceEvidenceCount} 条
                </span>
                {draft.reviewId ? (
                  <span className="text-xs text-appleBlue">
                    Review：<span className="font-mono">{draft.reviewId}</span>
                  </span>
                ) : null}
              </div>
              <FactGrid>
                <FactRow label="为什么建议这样改">{draft.rationale}</FactRow>
                <FactRow label="期望改进">{draft.expected}</FactRow>
                <FactRow label="风险评估">{draft.risk}</FactRow>
              </FactGrid>
              {draft.proposedRules.length ? (
                <Bullets label="拟新增/修改的规则" values={draft.proposedRules} />
              ) : null}
              {draft.removals.length ? (
                <Bullets label="拟删除的规则" values={draft.removals} />
              ) : null}
              {draft.requiredValidationCases.length ? (
                <Bullets
                  label="需要的回归 case"
                  values={draft.requiredValidationCases}
                />
              ) : null}
            </div>
            {draft.status === "proposed" || draft.status === "validated" ? (
              <button
                className="primary-button"
                onClick={() => onValidate(draft.id)}
                disabled={busy}
              >
                {draft.status === "validated" ? "提交人工审核" : "运行验证"}
              </button>
            ) : null}
          </div>
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer text-zinc-500">
              展开技术细节（原始 diff / edit_ops）
            </summary>
            <ul className="mt-2 space-y-1">
              {(draft.raw.edit_ops || []).map((op, idx) => (
                <li
                  key={idx}
                  className="rounded-md border border-line bg-zinc-50/60 px-2.5 py-1.5"
                >
                  <span className="font-mono text-zinc-700">{op.op}</span>{" "}
                  <span className="text-zinc-500">→ {op.target_section}</span>
                  {op.text ? (
                    <p className="mt-1 whitespace-pre-wrap text-zinc-700">{op.text}</p>
                  ) : null}
                  {op.replace_text ? (
                    <p className="mt-1 whitespace-pre-wrap text-zinc-700">
                      替换为：{op.replace_text}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
            <pre className="mt-2 overflow-x-auto rounded-md border border-line bg-zinc-50/60 p-2 text-[10.5px] text-zinc-600">
{JSON.stringify(draft.raw, null, 2)}
            </pre>
          </details>
        </article>
      ))}
      <Paginator page={safePage} pageCount={pageCount} total={total} onPage={onPage} />
    </div>
  );
}

// ---------------------------------------------------------- Ignored tab

function IgnoredTab({ items, page, onPage, onRestore }) {
  if (!items.length) {
    return <EmptyState title="暂无已忽略的发现。" />;
  }
  const { pageItems, total, pageCount, page: safePage } = paginate(items, page);
  return (
    <div className="space-y-3">
      {pageItems.map((item) => (
        <article key={item.kind + ":" + item.id} className="section-panel p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-semibold text-zinc-900">{item.title}</h3>
              <p className="mt-1 text-xs text-zinc-600">原因：{item.reason}</p>
              {item.kind === "rejected_edit" ? (
                <p className="mt-1 text-[11px] text-zinc-400">
                  系统级拒绝。如需重新评估，请在「发现的问题」里收到新证据后再生成草稿。
                </p>
              ) : null}
            </div>
            {item.kind === "local_ignored" ? (
              <button
                className="secondary-button"
                onClick={() => onRestore(item.id)}
              >
                <RotateCcw className="h-4 w-4" />
                恢复
              </button>
            ) : null}
          </div>
        </article>
      ))}
      <Paginator page={safePage} pageCount={pageCount} total={total} onPage={onPage} />
    </div>
  );
}

// ---------------------------------------------------------- Shared bits

function FactGrid({ children }) {
  return <div className="mt-3 space-y-2 rounded-md border border-line bg-white p-3">{children}</div>;
}

function FactRow({ label, children }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <div className="mt-1 text-sm leading-relaxed text-zinc-800">{children}</div>
    </div>
  );
}

function Bullets({ label, values }) {
  return (
    <div className="mt-2 rounded-md border border-line bg-zinc-50/60 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-zinc-700">
        {values.map((v, idx) => (
          <li key={idx}>{v}</li>
        ))}
      </ul>
    </div>
  );
}
