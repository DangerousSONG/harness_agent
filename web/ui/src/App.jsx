import { useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "./components/AppShell";
import ConfirmDialog from "./components/ConfirmDialog";
import PromotionModal from "./components/PromotionModal";
import ReviewModal from "./components/ReviewModal";
import { api, getErrorMessage } from "./lib/api";
import { formatDate } from "./lib/format";
import AssetsPage from "./pages/AssetsPage";
import ChatPage from "./pages/ChatPage";
import EvolutionPage from "./pages/EvolutionPage";
import PromotionsPage from "./pages/PromotionsPage";
import ReviewsPage from "./pages/ReviewsPage";
import VersionsPage, { versionKey } from "./pages/VersionsPage";

const initialMessages = [
  {
    id: "hello",
    role: "agent",
    text: "SafeHarness Console is ready. I will surface approval cards here when the backend creates a review.",
    time: formatDate(new Date().toISOString()),
  },
];

export default function App() {
  const [page, setPage] = useState("chat");
  const [dashboard, setDashboard] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [promotions, setPromotions] = useState([]);
  const [skills, setSkills] = useState([]);
  const [tools, setTools] = useState([]);
  const [memories, setMemories] = useState([]);
  const [knowledgeBases, setKnowledgeBases] = useState([]);
  const [versions, setVersions] = useState([]);
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

  const refresh = useCallback(async () => {
    const settled = await Promise.allSettled([
      api.dashboard(),
      api.reviews(),
      api.promotions(),
      api.skills(),
      api.tools(),
      api.memories(),
      api.knowledgeBases(),
    ]);
    const [dashboardResult, reviewsResult, promosResult, skillsResult, toolsResult, memoriesResult, kbResult] = settled;
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

  function appendAgentResult(text) {
    setMessages((items) => [
      ...items,
      { id: makeId(), role: "agent", text, time: formatDate(new Date().toISOString()) },
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
    setBusyReviewId(reviewId);
    const toolId = appendToolCall(`POST /api/reviews/${reviewId}/approve`);
    try {
      const payload = await api.approveReview(reviewId);
      setToast(payload.message || "Preview generated.");
      finishToolCall(toolId, "completed");
      appendAgentResult(payload.message || `Review ${reviewId} approved.`);
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
    setConfirmAction({
      kind: "apply_review",
      reviewId,
      title: "Apply change?",
      message: "This will modify the active file. Continue?",
    });
  }

  async function confirmApply() {
    if (!confirmAction) return;
    if (confirmAction.kind === "apply_review") {
      await confirmApplyReview(confirmAction.reviewId);
      return;
    }
    if (confirmAction.kind === "rollback_version") {
      await confirmRollbackVersion(confirmAction.version);
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
      const message = getErrorMessage(error);
      finishToolCall(toolId, "failed");
      appendAgentResult(message);
      setToast(message);
    } finally {
      setBusyReviewId("");
    }
  }

  async function sendChat(message) {
    setSending(true);
    setMessages((items) => [
      ...items,
      { id: makeId(), role: "user", text: message, time: formatDate(new Date().toISOString()) },
    ]);
    try {
      const payload = await api.chatSend(message);
      setMessages((items) => [
        ...items,
        {
          id: makeId(),
          role: "agent",
          text: payload.message || payload.data?.message || "Done.",
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
      setPage("evolution");
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
        {page === "chat" ? (
          <ChatPage
            reviews={reviews}
            dashboard={dashboard}
            messages={messages}
            onSend={sendChat}
            sending={sending}
            actionProps={actionProps}
          />
        ) : null}
        {page === "reviews" ? <ReviewsPage reviews={reviews} actionProps={actionProps} /> : null}
        {page === "assets" ? (
          <AssetsPage
            skills={skills}
            tools={tools}
            memories={memories}
            knowledgeBases={knowledgeBases}
            versions={versions}
          />
        ) : null}
        {page === "promotions" ? (
          <PromotionsPage
            promotions={promotions}
            busyPromoId={busyPromoId}
            onView={viewPromotion}
            onEvolve={evolvePromotion}
            onRegenerate={regeneratePromotion}
          />
        ) : null}
        {page === "evolution" ? (
          <EvolutionPage
            promotions={promotions}
            selectedPromoId={selectedPromoId}
            onSelectPromo={setSelectedPromoId}
            evolutionState={evolutionState}
            currentPromotion={currentPromotion}
            busyPromoId={busyPromoId}
            onContinue={continueEvolution}
          />
        ) : null}
        {page === "versions" ? (
          <VersionsPage
            versions={versions}
            versionDetail={versionDetail}
            selectedVersionKey={selectedVersionKey}
            onSelectVersion={(version) => setSelectedVersionKey(versionKey(version))}
            onCreateRollback={createRollbackReview}
            busyVersionKey={busyVersionKey}
          />
        ) : null}
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
        busy={Boolean(busyReviewId || busyVersionKey)}
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

function makeId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
