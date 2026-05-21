import { useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "./components/AppShell";
import ConfirmDialog from "./components/ConfirmDialog";
import PromotionModal from "./components/PromotionModal";
import ReviewModal from "./components/ReviewModal";
import { api, getErrorMessage } from "./lib/api";
import { formatDate } from "./lib/format";
import AssetsPage from "./pages/AssetsPage";
import ChangesPage from "./pages/ChangesPage";
import ChatPage from "./pages/ChatPage";
import GovernancePage from "./pages/GovernancePage";
import SettingsPage from "./pages/SettingsPage";
import { versionKey } from "./pages/VersionsPage";
import WorkspacePage from "./pages/WorkspacePage";

const initialMessages = [
  {
    id: "hello",
    role: "agent",
    text: "SafeHarness Console is ready. I will surface approval cards here when the backend creates a review.",
    time: formatDate(new Date().toISOString()),
  },
];

export default function App() {
  const initialRoute = routeFromLocation();
  const [page, setPageState] = useState(initialRoute.page);
  const [assetTab, setAssetTab] = useState(initialRoute.assetTab || "skills");
  const [changesTab, setChangesTabState] = useState(initialRoute.changesTab || "proposed");
  const [governanceTab, setGovernanceTabState] = useState(initialRoute.governanceTab || "reviews");
  const [dashboard, setDashboard] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [promotions, setPromotions] = useState([]);
  const [skills, setSkills] = useState([]);
  const [tools, setTools] = useState([]);
  const [memories, setMemories] = useState([]);
  const [knowledgeBases, setKnowledgeBases] = useState([]);
  const [versions, setVersions] = useState([]);
  const [changes, setChanges] = useState([]);
  const [messages, setMessages] = useState(initialMessages);
  const [selectedPromoId, setSelectedPromoId] = useState("");
  const [evolutionState, setEvolutionState] = useState(null);
  const [selectedReviewId, setSelectedReviewId] = useState("");
  const [reviewDetail, setReviewDetail] = useState(null);
  const [reviewPatch, setReviewPatch] = useState(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);
  const [busyReviewId, setBusyReviewId] = useState("");
  const [busyPromoId, setBusyPromoId] = useState("");
  const [selectedPromotion, setSelectedPromotion] = useState(null);
  const [promotionLoading, setPromotionLoading] = useState(false);
  const [selectedVersionKey, setSelectedVersionKey] = useState("");
  const [versionDetail, setVersionDetail] = useState(null);
  const [busyVersionKey, setBusyVersionKey] = useState("");
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState("");

  function navigate(nextPage, options = {}) {
    const normalized = normalizePage(nextPage, options);
    if (normalized.assetTab) setAssetTab(normalized.assetTab);
    if (normalized.changesTab) setChangesTabState(normalized.changesTab);
    if (normalized.governanceTab) setGovernanceTabState(normalized.governanceTab);
    setPageState(normalized.page);
    updateUrl(normalized.page, {
      assetTab: normalized.assetTab || assetTab,
      changesTab: normalized.changesTab || changesTab,
      governanceTab: normalized.governanceTab || governanceTab,
    });
  }

  function setPage(nextPage) {
    navigate(nextPage);
  }

  function setChangesTab(nextTab) {
    setChangesTabState(nextTab);
    updateUrl("assets-changes", { changesTab: nextTab });
  }

  function setGovernanceTab(nextTab) {
    setGovernanceTabState(nextTab);
    updateUrl("assets-governance", { governanceTab: nextTab });
  }

  function setLibraryTab(nextTab) {
    setAssetTab(nextTab);
    updateUrl("assets-library", { assetTab: nextTab });
  }

  const refresh = useCallback(async () => {
    const settled = await Promise.allSettled([
      api.dashboard(),
      api.reviews(),
      api.promotions(),
      api.skills(),
      api.tools(),
      api.memories(),
      api.knowledgeBases(),
      api.changes(),
    ]);
    const [dashboardResult, reviewsResult, promosResult, skillsResult, toolsResult, memoriesResult, kbResult, changesResult] = settled;
    let reviewItems = [];
    let promoItems = [];
    let skillItems = [];
    if (dashboardResult.status === "fulfilled") setDashboard(dashboardResult.value.data);
    if (reviewsResult.status === "fulfilled") {
      reviewItems = reviewsResult.value.data || [];
      setReviews(reviewItems);
    }
    if (promosResult.status === "fulfilled") {
      promoItems = promosResult.value.data || [];
      setPromotions(promoItems);
      setSelectedPromoId((current) =>
        promoItems.some((promo) => promo.promo_id === current)
          ? current
          : promoItems[0]?.promo_id || "",
      );
    }
    if (skillsResult.status === "fulfilled") {
      skillItems = skillsResult.value.data || [];
      setSkills(skillItems);
    }
    if (toolsResult.status === "fulfilled") setTools(toolsResult.value.data || []);
    if (memoriesResult.status === "fulfilled") setMemories(memoriesResult.value.data || []);
    if (kbResult.status === "fulfilled") setKnowledgeBases(kbResult.value.data || []);
    if (changesResult.status === "fulfilled") setChanges(changesResult.value.data || []);
    return { reviews: reviewItems, promotions: promoItems, skills: skillItems };
  }, []);

  const loadVersions = useCallback(async (skillItems) => {
    const items = skillItems || skills;
    const results = await Promise.allSettled(items.map((skill) => api.skillVersions(skill.name)));
    const all = results.flatMap((result) => (result.status === "fulfilled" ? result.value.data || [] : []));
    setVersions(all);
    setSelectedVersionKey((current) => current || (all[0] ? versionKey(all[0]) : ""));
  }, [skills]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const route = routeFromLocation();
    updateUrl(route.page, route, true);
    const onPopState = () => {
      const next = routeFromLocation();
      setPageState(next.page);
      setAssetTab(next.assetTab || "skills");
      setChangesTabState(next.changesTab || "proposed");
      setGovernanceTabState(next.governanceTab || "reviews");
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refresh();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (skills.length) loadVersions(skills);
  }, [skills, loadVersions]);

  useEffect(() => {
    if (!selectedPromoId) {
      setEvolutionState(null);
      return;
    }
    api.evolutionState(selectedPromoId)
      .then((payload) => setEvolutionState(payload.data))
      .catch(() => setEvolutionState(null));
  }, [selectedPromoId, reviews, promotions]);

  useEffect(() => {
    const selected = versions.find((item) => versionKey(item) === selectedVersionKey);
    if (!selected) {
      setVersionDetail(null);
      return;
    }
    api.skillVersion(selected.skill, selected.version)
      .then((payload) => setVersionDetail(payload.data))
      .catch(() => setVersionDetail(null));
  }, [selectedVersionKey, versions]);

  const activeReview = useMemo(
    () => reviewDetail || reviews.find((review) => review.review_id === selectedReviewId),
    [reviewDetail, reviews, selectedReviewId],
  );
  const currentPromotion = useMemo(
    () => promotions.find((promo) => promo.promo_id === selectedPromoId) || null,
    [promotions, selectedPromoId],
  );

  function appendToolCall(name, status = "running") {
    const id = makeId();
    setMessages((items) => [
      ...items,
      { id, role: "tool", name, status, time: formatDate(new Date().toISOString()) },
    ]);
    return id;
  }

  function finishToolCall(id, status) {
    setMessages((items) =>
      items.map((item) => (item.id === id ? { ...item, status } : item)),
    );
  }

  function appendAgentResult(text, extra = {}) {
    setMessages((items) => [
      ...items,
      { id: makeId(), role: "agent", text, time: formatDate(new Date().toISOString()), ...extra },
    ]);
  }

  async function refreshAfterOperation(promoId = selectedPromoId) {
    const data = await refresh();
    await loadVersions(data.skills);
    if (promoId) {
      try {
        const state = await api.evolutionState(promoId);
        setEvolutionState(state.data);
      } catch {
        setEvolutionState(null);
      }
    }
  }

  async function openReview(reviewId) {
    setSelectedReviewId(reviewId);
    setReviewLoading(true);
    setReviewDetail(null);
    setReviewPatch(null);
    try {
      const [detail, patch] = await Promise.all([api.review(reviewId), api.reviewPatch(reviewId)]);
      setReviewDetail(detail.data);
      setReviewPatch(patch.data);
    } catch (error) {
      setToast(getErrorMessage(error));
    } finally {
      setReviewLoading(false);
    }
  }

  async function approveReview(reviewId) {
    setConfirmAction({
      kind: "approve_review",
      reviewId,
      title: "Approve review?",
      message: "This will generate a patch preview through the review API. It will not modify target files.",
    });
  }

  async function confirmApproveReview(reviewId) {
    setBusyReviewId(reviewId);
    const toolId = appendToolCall(`POST /api/reviews/${reviewId}/approve`);
    try {
      const payload = await api.approveReview(reviewId);
      setToast(payload.message || "Preview generated.");
      finishToolCall(toolId, "completed");
      appendAgentResult(payload.message || `Review ${reviewId} approved.`);
      setConfirmAction(null);
      await refreshAfterOperation();
      if (selectedReviewId === reviewId) await openReview(reviewId);
    } catch (error) {
      const message = getErrorMessage(error);
      finishToolCall(toolId, "failed");
      appendAgentResult(message);
      setToast(message);
    } finally {
      setBusyReviewId("");
    }
  }

  async function applyReview(reviewId) {
    let patch = null;
    try {
      const payload = await api.reviewPatch(reviewId);
      patch = payload.data;
    } catch {
      patch = null;
    }
    const review = reviewDetail?.review_id === reviewId
      ? reviewDetail
      : reviews.find((item) => item.review_id === reviewId);
    if (reviewNeedsPatch(review) && !patch?.has_changes) {
      setConfirmAction({
        kind: "empty_patch",
        reviewId,
        title: "Cannot apply",
        message: patch?.apply_blocked_reason || "Cannot apply: patch preview is empty.",
        patch: patch?.patch || "",
        confirmLabel: "Regenerate patch",
      });
      return;
    }
    setConfirmAction({
      kind: "apply_review",
      reviewId,
      title: "Apply change?",
      message: "This will modify the active file. Inspect the diff preview before continuing.",
      patch: patch?.patch || "",
    });
  }

  async function confirmApply() {
    if (!confirmAction) return;
    if (confirmAction.kind === "approve_review") {
      await confirmApproveReview(confirmAction.reviewId);
      return;
    }
    if (confirmAction.kind === "apply_review") {
      await confirmApplyReview(confirmAction.reviewId);
      return;
    }
    if (confirmAction.kind === "rollback_version") {
      await confirmRollbackVersion(confirmAction.version);
      return;
    }
    if (confirmAction.kind === "workspace_write") {
      await confirmWorkspaceWrite(confirmAction.body);
      return;
    }
    if (confirmAction.kind === "empty_patch") {
      await confirmApproveReview(confirmAction.reviewId);
      return;
    }
    if (confirmAction.kind === "chat_action") {
      await executeConfirmedChatAction(confirmAction.action, confirmAction.sourceMessage);
    }
  }

  async function rejectReview(reviewId) {
    setBusyReviewId(reviewId);
    const toolId = appendToolCall(`POST /api/reviews/${reviewId}/reject`);
    try {
      const payload = await api.rejectReview(reviewId);
      setToast(payload.message || "Review rejected.");
      finishToolCall(toolId, "completed");
      appendAgentResult(payload.message || `Review ${reviewId} rejected.`);
      await refreshAfterOperation();
      if (selectedReviewId === reviewId) await openReview(reviewId);
    } catch (error) {
      const message = getErrorMessage(error);
      finishToolCall(toolId, "failed");
      appendAgentResult(message);
      setToast(message);
    } finally {
      setBusyReviewId("");
    }
  }

  async function confirmApplyReview(reviewId) {
    setBusyReviewId(reviewId);
    const toolId = appendToolCall(`POST /api/reviews/${reviewId}/apply`);
    try {
      const payload = await api.applyReview(reviewId);
      setToast(payload.message || "Change applied.");
      finishToolCall(toolId, "completed");
      appendAgentResult(payload.message || `Review ${reviewId} applied.`);
      setConfirmAction(null);
      await refreshAfterOperation();
      if (selectedReviewId === reviewId) await openReview(reviewId);
    } catch (error) {
      if (error.payload?.error_code === "FILE_ALREADY_EXISTS") {
        finishToolCall(toolId, "failed");
        appendAgentResult("Existing file detected. View the diff or cancel; no file was overwritten.", {
          type: "error",
          data: {
            path: error.payload?.path || "",
            suggested_fix: "Existing file detected. View diff or cancel.",
          },
          actions: [
            { label: "View diff", method: "GET", path: `/api/reviews/${reviewId}/patch`, requires_confirmation: false },
            { label: "Cancel", method: "LOCAL", path: "cancel", requires_confirmation: false },
          ],
        });
        setToast("Existing file detected.");
        setConfirmAction(null);
        return;
      }
      const message = getErrorMessage(error);
      finishToolCall(toolId, "failed");
      appendAgentResult(message);
      setToast(message);
    } finally {
      setBusyReviewId("");
    }
  }

  async function confirmWorkspaceWrite(body) {
    const path = body?.path || "";
    const toolId = appendToolCall("POST /api/workspace/files/propose-write");
    try {
      const payload = await api.proposeWrite({ ...(body || {}), confirmed: true });
      finishToolCall(toolId, "completed");
      appendAgentResult(payload.message || `Wrote ${path}.`, {
        type: payload.data?.review ? "review_created" : "file_result",
        data: payload.data || {},
      });
      setToast(payload.message || "Workspace write completed.");
      setConfirmAction(null);
      await refreshAfterOperation();
      if (payload.data?.review?.review_id) {
        setPage("reviews");
        await openReview(payload.data.review.review_id);
      }
    } catch (error) {
      const message = getErrorMessage(error);
      finishToolCall(toolId, "failed");
      appendAgentResult(message, { type: "error" });
      setToast(message);
    }
  }

  async function executeConfirmedChatAction(action, sourceMessage) {
    const path = action?.path || "";
    const method = action?.method || "POST";
    const payloadBody = action?.payload || action?.body || {};
    const toolId = appendToolCall(`${method} ${path}`);
    try {
      let payload = null;
      if (method === "POST" && path === "/api/skills/propose") {
        payload = await api.proposeSkill(payloadBody);
        finishToolCall(toolId, "completed");
        const reviewId = payload.data?.review_id || payload.data?.review?.review_id;
        appendAgentResult(payload.message || `Created review ${reviewId}.`, {
          type: "review_created",
          risk: sourceMessage?.risk || action?.risk || "safe_write_preview",
          data: payload.data || {},
          actions: reviewId
            ? [
                { label: "View details", method: "GET", path: `/api/reviews/${reviewId}`, requires_confirmation: false },
                { label: "Approve", method: "POST", path: `/api/reviews/${reviewId}/approve`, requires_confirmation: true },
                { label: "Reject", method: "POST", path: `/api/reviews/${reviewId}/reject`, requires_confirmation: true },
              ]
            : [],
        });
        setConfirmAction(null);
        await refreshAfterOperation();
        setPage("reviews");
        if (reviewId) await openReview(reviewId);
        return;
      }
      if (method === "POST" && path === "/api/tools/create") {
        payload = await api.createTool(payloadBody);
        finishToolCall(toolId, "completed");
        appendAgentResult(payload.message || `Created ${payload.data?.tool_name || "tool"}.`, {
          type: "tool_result",
          risk: sourceMessage?.risk || action?.risk || "safe_write_preview",
          data: payload.data || {},
          trace: payload.data?.operation_trace || [],
          actions: [
            { label: "View in Assets > Tools", method: "GET", path: "/api/tools", requires_confirmation: false },
          ],
        });
        setConfirmAction(null);
        await refreshAfterOperation();
        navigate("assets-library", { assetTab: "tools" });
        return;
      }
      const toolReviewMatch = path.match(/^\/api\/tools\/([^/]+)\/update-review$/);
      if (method === "POST" && toolReviewMatch) {
        const toolName = decodeURIComponent(toolReviewMatch[1]);
        payload = await api.createToolUpdateReview(toolName, payloadBody);
        finishToolCall(toolId, "completed");
        const reviewId = payload.data?.review_id || payload.data?.review?.review_id;
        appendAgentResult(payload.message || `Created review ${reviewId}.`, {
          type: "review_created",
          risk: sourceMessage?.risk || action?.risk || "safe_write_preview",
          data: payload.data || {},
          actions: reviewId
            ? [
                { label: "View details", method: "GET", path: `/api/reviews/${reviewId}`, requires_confirmation: false },
                { label: "Approve", method: "POST", path: `/api/reviews/${reviewId}/approve`, requires_confirmation: true },
                { label: "Reject", method: "POST", path: `/api/reviews/${reviewId}/reject`, requires_confirmation: true },
              ]
            : [],
        });
        setConfirmAction(null);
        await refreshAfterOperation();
        setPage("reviews");
        if (reviewId) await openReview(reviewId);
        return;
      }
      if (method === "POST" && path === "/api/workspace/files/propose-write") {
        await confirmWorkspaceWrite(payloadBody);
        finishToolCall(toolId, "completed");
        return;
      }
      finishToolCall(toolId, "failed");
      appendAgentResult(`Action is not wired in the UI yet: ${method} ${path}`, { type: "error" });
      setConfirmAction(null);
    } catch (error) {
      if (error.payload?.error_code === "FILE_ALREADY_EXISTS") {
        finishToolCall(toolId, "failed");
        appendExistingFileResult(error, action, sourceMessage);
        setToast("Existing file detected.");
        setConfirmAction(null);
        return;
      }
      const message = getErrorMessage(error);
      finishToolCall(toolId, "failed");
      appendAgentResult(message, { type: "error" });
      setToast(message);
    }
  }

  async function sendChat(message) {
    setSending(true);
    setMessages((items) => [
      ...items,
      { id: makeId(), role: "user", type: "user_message", text: message, time: formatDate(new Date().toISOString()) },
    ]);
    try {
      const payload = await api.chatSend(message, {
        current_skill: currentPromotion?.target_skill || "",
        current_promo_id: selectedPromoId || "",
        current_review_id: selectedReviewId || activeReview?.review_id || "",
        page,
      });
      setMessages((items) => [
        ...items,
        {
          id: makeId(),
          role: "agent",
          text: payload.message || payload.data?.message || "Done.",
          type: payload.type || "answer",
          intent: payload.intent || "",
          risk: payload.risk || "",
          safety: payload.safety || {},
          asset_route: payload.asset_route || {},
          run_id: payload.run_id || "",
          used_skill: payload.used_skill || "",
          why: payload.why || "",
          memory_record_id: payload.memory_record_id || "",
          actions: payload.actions || [],
          trace: payload.trace || [],
          data: payload.data || {},
          time: formatDate(new Date().toISOString()),
        },
      ]);
      await refresh();
    } catch (error) {
      setMessages((items) => [
        ...items,
        {
          id: makeId(),
          role: "agent",
          text: getErrorMessage(error),
          time: formatDate(new Date().toISOString()),
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function viewPromotion(promoId) {
    setPromotionLoading(true);
    setSelectedPromotion({ promo_id: promoId });
    try {
      const payload = await api.promotion(promoId);
      setSelectedPromotion(payload.data);
    } catch (error) {
      setToast(getErrorMessage(error));
    } finally {
      setPromotionLoading(false);
    }
  }

  async function evolvePromotion(promoId) {
    if (!promoId) return;
    const promo = promotions.find((item) => item.promo_id === promoId);
    if (!promo) {
      const message = "Promotion candidate not found";
      setToast(message);
      appendAgentResult(message);
      return;
    }
    setBusyPromoId(promoId);
    const toolId = appendToolCall(`POST /api/promotions/${promoId}/evolve`);
    try {
      const payload = await api.evolvePromotion(promoId);
      setToast(payload.message || "Evolution flow updated.");
      finishToolCall(toolId, "completed");
      appendAgentResult(payload.message || `Evolution flow updated for ${promoId}.`);
      setSelectedPromoId(promoId);
        navigate("assets-library", { assetTab: "workflows" });
      await refreshAfterOperation(promoId);
    } catch (error) {
      const message = getErrorMessage(error);
      finishToolCall(toolId, "failed");
      appendAgentResult(message);
      setToast(message);
    } finally {
      setBusyPromoId("");
    }
  }

  async function regeneratePromotion(promoId) {
    if (!promoId) return;
    const promo = promotions.find((item) => item.promo_id === promoId);
    if (!promo) {
      const message = "Promotion candidate not found";
      setToast(message);
      appendAgentResult(message);
      return;
    }
    setBusyPromoId(promoId);
    const toolId = appendToolCall(`POST /api/promotions/${promoId}/regenerate`);
    try {
      const payload = await api.regeneratePromotion(promoId);
      const newPromoId = payload.data?.new_promo_id;
      setToast(payload.message || "Promotion regenerated.");
      finishToolCall(toolId, "completed");
      appendAgentResult(payload.message || `Promotion ${promoId} regenerated.`);
      if (newPromoId) {
        setSelectedPromoId(newPromoId);
        if (selectedPromotion?.promo_id === promoId) {
          setSelectedPromotion(payload.data?.new_promo || null);
        }
      }
      await refreshAfterOperation(newPromoId || promoId);
    } catch (error) {
      const message = getErrorMessage(error);
      finishToolCall(toolId, "failed");
      appendAgentResult(message);
      setToast(message);
    } finally {
      setBusyPromoId("");
    }
  }

  async function createRollbackReview(version) {
    setConfirmAction({
      kind: "rollback_version",
      version,
      title: "Create rollback review?",
      message: "This will ask the backend to create a rollback review. It will not directly modify SKILL.md. Continue?",
    });
  }

  async function confirmRollbackVersion(version) {
    const key = versionKey(version);
    setBusyVersionKey(key);
    const toolId = appendToolCall(`POST /api/skills/${version.skill}/rollback`);
    try {
      const payload = await api.rollbackSkill(version.skill, version.version);
      setToast(payload.message || "Rollback review created.");
      finishToolCall(toolId, "completed");
      appendAgentResult(payload.message || "Rollback review created.");
      setConfirmAction(null);
      await refreshAfterOperation();
      setPage("reviews");
      if (payload.data?.review_id) await openReview(payload.data.review_id);
    } catch (error) {
      const message = getErrorMessage(error);
      finishToolCall(toolId, "failed");
      appendAgentResult(message);
      setToast(message);
    } finally {
      setBusyVersionKey("");
    }
  }

  async function continueEvolution(promoId) {
    if (!promoId) return;
    const promo = promotions.find((item) => item.promo_id === promoId);
    if (!promo) {
      const message = "Promotion candidate not found";
      setToast(message);
      appendAgentResult(message);
      return;
    }
    if (promo?.requires_regeneration) {
      await regeneratePromotion(promoId);
      return;
    }
    let state = evolutionState;
    if (!state || state.promo_id !== promoId) {
      try {
        const payload = await api.evolutionState(promoId);
        state = payload.data;
        setEvolutionState(state);
      } catch {
        state = null;
      }
    }
    const action = state?.next_action || "create_regression_review";
    const reviewId = reviewIdForAction(state, action);
    if (action === "approve_regression_review" || action === "approve_skill_review") {
      if (reviewId) {
        await approveReview(reviewId);
      } else {
        const message = `No review id is available for ${action}.`;
        setToast(message);
        appendAgentResult(message);
      }
      return;
    }
    if (action === "apply_regression_review" || action === "apply_skill_review") {
      if (reviewId) {
        await applyReview(reviewId);
      } else {
        const message = `No review id is available for ${action}.`;
        setToast(message);
        appendAgentResult(message);
      }
      return;
    }
    if (action === "completed") {
      setPage("versions");
      return;
    }
    await evolvePromotion(promoId);
  }

  async function handleChatAction(action, sourceMessage) {
    const path = action?.path || "";
    const method = action?.method || "GET";
    if (method === "LOCAL") {
      if (path === "cancel") {
        appendAgentResult("Canceled. No workspace change was made.", { type: "answer" });
        return;
      }
      if (path === "configure_provider") {
        setPage("settings");
        appendAgentResult("Open Settings to configure the realtime provider. Creating a Tool Asset alone will not enable realtime access.", {
          type: "tool_result",
        });
        return;
      }
      if (path === "ask_without_realtime_data") {
        appendAgentResult("Without realtime data, I can give a general analysis framework, but I will not claim current prices, earnings, news, or sources.", {
          type: "answer",
        });
        return;
      }
      if (path === "details") {
        const data = sourceMessage?.data || {};
        const files = data.files || data.proposed_tool?.files || [];
        const preflight = data.preflight || {};
        const details = [
          data.path ? `Path: ${data.path}` : "",
          data.operation ? `Operation: ${data.operation}` : "",
          data.risk ? `Risk: ${data.risk}` : "",
          data.asset_type ? `Asset type: ${data.asset_type}` : "",
          data.target ? `Target: ${data.target}` : "",
          preflight.risk ? `Preflight risk: ${preflight.risk}` : "",
          preflight.existing_file_check ? `Existing file check: ${preflight.existing_file_check}` : "",
          files.length ? `Files:\n${files.map((file) => `- ${file.path}`).join("\n")}` : "",
          data.preflight?.files?.some((file) => file.diff)
            ? `Diff:\n${data.preflight.files.map((file) => file.diff).filter(Boolean).join("\n")}`
            : "",
          data.diffs ? `Diff:\n${Object.values(data.diffs).filter(Boolean).join("\n")}` : "",
          data.preview_content ? `Preview:\n${data.preview_content}` : "",
        ].filter(Boolean).join("\n");
        appendAgentResult(details || "No additional details are available.", { type: "tool_result" });
        return;
      }
    }
    if (method === "GET") {
      if (path === "/api/promotions") {
        navigate("assets-library", { assetTab: "workflows" });
        return;
      }
      if (path === "/api/skills") {
        navigate("assets-library", { assetTab: "skills" });
        return;
      }
      if (path === "/api/reviews") {
        setPage("reviews");
        return;
      }
      if (path === "/api/tools") {
        navigate("assets-library", { assetTab: "tools" });
        return;
      }
      if (path.startsWith("/api/tools/")) {
        navigate("assets-library", { assetTab: "tools" });
        return;
      }
      const reviewMatch = path.match(/^\/api\/reviews\/([^/]+)(?:\/patch)?$/);
      if (reviewMatch) {
        await openReview(decodeURIComponent(reviewMatch[1]));
        return;
      }
    }
    const evolveMatch = path.match(/^\/api\/promotions\/([^/]+)\/evolve$/);
    if (method === "POST" && evolveMatch) {
      await evolvePromotion(decodeURIComponent(evolveMatch[1]));
      return;
    }
    const promoteMatch = path.match(/^\/api\/memories\/([^/]+)\/promote$/);
    if (method === "POST" && promoteMatch) {
      const memoryId = decodeURIComponent(promoteMatch[1]);
      const toolId = appendToolCall(`POST /api/memories/${memoryId}/promote`);
      try {
        const payload = await api.promoteMemory(memoryId);
        finishToolCall(toolId, "completed");
        appendAgentResult(payload.message || `Promotion requested for ${memoryId}.`, {
          type: "tool_result",
          used_skill: "self_improvement",
        });
        await refreshAfterOperation();
        navigate("assets-library", { assetTab: "workflows" });
      } catch (error) {
        const message = getErrorMessage(error);
        finishToolCall(toolId, "failed");
        appendAgentResult(message, { type: "error" });
        setToast(message);
      }
      return;
    }
    if (method === "POST" && path === "/api/workspace/files/propose-write") {
      const body = action?.payload || action?.body || {};
      setConfirmAction({
        kind: "workspace_write",
        body,
        title: "Confirm workspace write?",
        message: [
          `Path: ${body.path || sourceMessage?.data?.path || "(unknown)"}`,
          `Operation: write`,
          `Risk: ${sourceMessage?.data?.risk || "safe_write_preview"}`,
          "Confirming will write the preview content or create a review for protected files.",
        ].join("\n"),
        patch: body.content || sourceMessage?.data?.preview_content || "",
      });
      return;
    }
    if (method === "POST" && path === "/api/skills/propose") {
      const payload = action?.payload || action?.body || {};
      const skillName = payload.skill_name || sourceMessage?.data?.proposed_skill?.skill_name || "new_skill";
      setConfirmAction({
        kind: "chat_action",
        action,
        sourceMessage,
        title: `Create ${skillName} skill review?`,
        message: [
          `Skill: ${skillName}`,
          "Operation: create skill review",
          `Risk: ${riskLabel(action?.risk || sourceMessage?.risk || "safe_write_preview")}`,
          "This will create a pending review. It will not write SKILL.md directly.",
        ].join("\n"),
        patch: JSON.stringify(payload, null, 2),
      });
      return;
    }
    if (method === "POST" && path === "/api/tools/create") {
      const payload = action?.payload || action?.body || {};
      const toolName = payload.tool_name || sourceMessage?.data?.tool_name || "new_tool";
      setConfirmAction({
        kind: "chat_action",
        action,
        sourceMessage,
        title: `Create ${toolName} tool?`,
        message: [
          `Tool: ${toolName}`,
          "Operation: create tool files",
          `Risk: ${riskLabel(action?.risk || sourceMessage?.risk || "safe_write_preview")}`,
          "Preflight must pass before files are written.",
        ].join("\n"),
        patch: JSON.stringify(payload, null, 2),
      });
      return;
    }
    const toolUpdateMatch = path.match(/^\/api\/tools\/([^/]+)\/update-review$/);
    if (method === "POST" && toolUpdateMatch) {
      const payload = action?.payload || action?.body || {};
      const toolName = decodeURIComponent(toolUpdateMatch[1]);
      setConfirmAction({
        kind: "chat_action",
        action,
        sourceMessage,
        title: `Create ${toolName} update review?`,
        message: [
          `Tool: ${toolName}`,
          "Operation: create tool update review",
          `Risk: ${riskLabel(action?.risk || sourceMessage?.risk || "safe_write_preview")}`,
          "This will create a pending review and will not overwrite tool files directly.",
        ].join("\n"),
        patch: JSON.stringify(payload, null, 2),
      });
      return;
    }
    const approveMatch = path.match(/^\/api\/reviews\/([^/]+)\/approve$/);
    if (method === "POST" && approveMatch) {
      await approveReview(decodeURIComponent(approveMatch[1]));
      return;
    }
    const rejectMatch = path.match(/^\/api\/reviews\/([^/]+)\/reject$/);
    if (method === "POST" && rejectMatch) {
      await rejectReview(decodeURIComponent(rejectMatch[1]));
      return;
    }
    const applyMatch = path.match(/^\/api\/reviews\/([^/]+)\/apply$/);
    if (method === "POST" && applyMatch) {
      const reviewId = decodeURIComponent(applyMatch[1]);
      const patchData = sourceMessage?.data?.patch;
      const patch = patchData?.patch;
      const review = sourceMessage?.data?.review || reviews.find((item) => item.review_id === reviewId);
      if (reviewNeedsPatch(review) && !patchData?.has_changes) {
        setConfirmAction({
          kind: "empty_patch",
          reviewId,
          title: "Cannot apply",
          message: patchData?.apply_blocked_reason || "Cannot apply: patch preview is empty.",
          patch: patch || "",
          confirmLabel: "Regenerate patch",
        });
      } else if (patch) {
        setConfirmAction({
          kind: "apply_review",
          reviewId,
          title: "Apply change?",
          message: "This will modify the active file. Inspect the diff preview before continuing.",
          patch,
        });
      } else {
        await applyReview(reviewId);
      }
      return;
    }
    appendAgentResult(`Action is not wired in the UI yet: ${method} ${path}`);
  }

  function appendExistingFileResult(error, action, sourceMessage) {
    const payload = error.payload || {};
    const data = payload.data || {};
    const toolName = data.tool_name || action?.payload?.tool_name || sourceMessage?.data?.tool_name || "";
    const reviewPath = data.review_endpoint || (toolName ? `/api/tools/${toolName}/update-review` : "");
    const diffs = data.diffs || {};
    appendAgentResult("Existing file detected. View the diff, create a review instead, or cancel.", {
      type: "error",
      data: {
        ...data,
        suggested_fix: "Existing file detected. View diff, create review instead, or cancel.",
      },
      actions: [
        { label: "View diff", method: "LOCAL", path: "details", requires_confirmation: false },
        reviewPath
          ? {
              label: "Create review instead",
              method: "POST",
              path: reviewPath,
              requires_confirmation: true,
              payload: action?.payload || action?.body || {},
              kind: "create_tool_update_review",
              risk: "high",
            }
          : null,
        { label: "Cancel", method: "LOCAL", path: "cancel", requires_confirmation: false },
      ].filter(Boolean),
      trace: [
        {
          type: "preflight",
          title: "Preflight",
          status: "failed",
          summary: "Existing file check failed.",
          existing_file_check: "failed",
        },
        ...Object.keys(diffs).map((filePath) => ({
          type: "file_trace",
          title: "Existing file detected",
          status: "failed",
          operation: "write",
          path: filePath,
          summary: "Target file already exists with different content.",
        })),
      ],
    });
  }

  const actionProps = {
    busyReviewId,
    onDetails: openReview,
    onApprove: approveReview,
    onApply: applyReview,
    onReject: rejectReview,
  };

  return (
    <>
      <AppShell
        page={page}
        onPageChange={setPage}
        skills={skills}
        reviews={reviews}
        evolutionState={evolutionState}
        currentPromotion={currentPromotion}
        onNextAction={continueEvolution}
        nextActionBusy={Boolean(busyPromoId || busyReviewId)}
      >
        {page === "workspace" ? (
          <WorkspacePage
            dashboard={dashboard}
            skills={skills}
            tools={tools}
            reviews={reviews}
            changes={changes}
            versions={versions}
            promotions={promotions}
            onNavigate={setPage}
          />
        ) : null}
        {page === "chat" ? (
          <ChatPage
            reviews={reviews}
            dashboard={dashboard}
            messages={messages}
            onSend={sendChat}
            sending={sending}
            actionProps={actionProps}
            onChatAction={handleChatAction}
          />
        ) : null}
        {page === "assets-changes" ? (
          <ChangesPage
            changes={changes}
            onOpenReview={openReview}
            onOpenVersions={() => setPage("versions")}
            activeTab={changesTab}
            onTabChange={setChangesTab}
          />
        ) : null}
        {page === "assets-library" ? (
          <AssetsPage
            skills={skills}
            tools={tools}
            reviews={reviews}
            changes={changes}
            promotions={promotions}
            memories={memories}
            knowledgeBases={knowledgeBases}
            versions={versions}
            onOpenReview={openReview}
            onOpenVersions={() => setPage("versions")}
            tab={assetTab}
            onTabChange={setLibraryTab}
          />
        ) : null}
        {page === "assets-governance" ? (
          <GovernancePage
            activeTab={governanceTab}
            onTabChange={setGovernanceTab}
            reviews={reviews}
            actionProps={actionProps}
            versions={versions}
            versionDetail={versionDetail}
            selectedVersionKey={selectedVersionKey}
            onSelectVersion={(version) => setSelectedVersionKey(versionKey(version))}
            onCreateRollback={createRollbackReview}
            busyVersionKey={busyVersionKey}
            changes={changes}
          />
        ) : null}
        {page === "settings" ? <SettingsPage dashboard={dashboard} /> : null}
      </AppShell>

      <ReviewModal
        open={Boolean(selectedReviewId)}
        review={activeReview}
        patch={reviewPatch}
        loading={reviewLoading}
        busy={Boolean(busyReviewId)}
        onClose={() => setSelectedReviewId("")}
        onApprove={() => selectedReviewId && approveReview(selectedReviewId)}
        onApply={() => selectedReviewId && applyReview(selectedReviewId)}
        onReject={() => selectedReviewId && rejectReview(selectedReviewId)}
      />
      <PromotionModal
        open={Boolean(selectedPromotion)}
        promotion={selectedPromotion}
        loading={promotionLoading}
        busy={Boolean(busyPromoId)}
        onClose={() => setSelectedPromotion(null)}
        onEvolve={evolvePromotion}
        onRegenerate={regeneratePromotion}
      />
      <ConfirmDialog
        open={Boolean(confirmAction)}
        title={confirmAction?.title || "Continue?"}
        message={confirmAction?.message || "Continue?"}
        patch={confirmAction?.patch || ""}
        busy={Boolean(busyReviewId || busyVersionKey)}
        confirmLabel={confirmAction?.confirmLabel || "Continue"}
        onCancel={() => setConfirmAction(null)}
        onConfirm={confirmApply}
      />
      {toast ? (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-line bg-white px-4 py-3 text-sm font-medium text-zinc-800 shadow-soft">
          <button className="mr-3 text-zinc-500" onClick={() => setToast("")}>Close</button>
          {toast}
        </div>
      ) : null}
    </>
  );
}

function reviewIdForAction(state, action) {
  const steps = state?.steps || [];
  const reviewName =
    action === "approve_regression_review" || action === "apply_regression_review"
      ? "regression_review"
      : "skill_promotion_review";
  return steps.find((step) => step.name === reviewName)?.review_id || "";
}

function reviewNeedsPatch(review) {
  const type = review?.type || "";
  const toolName = review?.tool_name || "";
  return ["skill.regression_case", "skill.promotion", "skill.creation", "file.write", "tool.update"].includes(type)
    || ["write_file", "edit_file"].includes(toolName);
}

function riskLabel(risk) {
  if (!risk) return "safe_write_preview";
  if (typeof risk === "string") return risk;
  return risk.level || "safe_write_preview";
}

function routeFromLocation() {
  if (typeof window === "undefined") return { page: "chat" };
  const path = window.location.pathname || "/chat";
  const params = new URLSearchParams(window.location.search);
  const tab = params.get("tab") || "";
  const routes = {
    "/chat": { page: "chat" },
    "/workspace": { page: "workspace" },
    "/assets/library": { page: "assets-library", assetTab: normalizeLibraryTab(tab) },
    "/assets/changes": { page: "assets-changes", changesTab: normalizeChangesTab(tab) },
    "/assets/governance": { page: "assets-governance", governanceTab: normalizeGovernanceTab(tab) },
    "/settings": { page: "settings" },
    "/assets/skills": { page: "assets-library", assetTab: "skills" },
    "/assets/tools": { page: "assets-library", assetTab: "tools" },
    "/assets/workflows": { page: "assets-library", assetTab: "workflows" },
    "/assets/memories": { page: "assets-library", assetTab: "memories" },
    "/assets/eval-cases": { page: "assets-library", assetTab: "eval-cases" },
    "/reviews": { page: "assets-governance", governanceTab: "reviews" },
    "/versions": { page: "assets-governance", governanceTab: "versions" },
    "/changes": { page: "assets-changes", changesTab: "proposed" },
    "/assets": { page: "assets-library", assetTab: "skills" },
    "/": { page: "chat" },
  };
  return routes[path] || { page: "chat" };
}

function normalizePage(page, options = {}) {
  if (page === "assets" || page === "assets-library") {
    return { page: "assets-library", assetTab: normalizeLibraryTab(options.assetTab) };
  }
  if (page === "changes" || page === "assets-changes") {
    return { page: "assets-changes", changesTab: normalizeChangesTab(options.changesTab) };
  }
  if (page === "reviews") return { page: "assets-governance", governanceTab: "reviews" };
  if (page === "versions") return { page: "assets-governance", governanceTab: "versions" };
  if (page === "promotions" || page === "evolution") {
    return { page: "assets-library", assetTab: "workflows" };
  }
  if (page === "assets-governance") {
    return { page: "assets-governance", governanceTab: normalizeGovernanceTab(options.governanceTab) };
  }
  if (["chat", "workspace", "settings"].includes(page)) return { page };
  return { page: "chat" };
}

function updateUrl(page, state = {}, replace = false) {
  if (typeof window === "undefined") return;
  const path = routeForPage(page, state);
  if (`${window.location.pathname}${window.location.search}` === path) return;
  const method = replace ? "replaceState" : "pushState";
  window.history[method]({}, "", path);
}

function routeForPage(page, state = {}) {
  if (page === "workspace") return "/workspace";
  if (page === "settings") return "/settings";
  if (page === "assets-library") return `/assets/library?tab=${normalizeLibraryTab(state.assetTab)}`;
  if (page === "assets-changes") return `/assets/changes?tab=${normalizeChangesTab(state.changesTab)}`;
  if (page === "assets-governance") return `/assets/governance?tab=${normalizeGovernanceTab(state.governanceTab)}`;
  return "/chat";
}

function normalizeLibraryTab(tab) {
  const normalized = tab === "eval" ? "eval-cases" : tab;
  return ["skills", "tools", "workflows", "memories", "eval-cases"].includes(normalized) ? normalized : "skills";
}

function normalizeChangesTab(tab) {
  return ["proposed", "review-required", "applied", "failed", "archived"].includes(tab) ? tab : "proposed";
}

function normalizeGovernanceTab(tab) {
  return ["reviews", "versions", "rollbacks", "safety-checks"].includes(tab) ? tab : "reviews";
}

function makeId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
