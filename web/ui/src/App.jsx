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
  const [confirmReviewId, setConfirmReviewId] = useState("");
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
    if (dashboardResult.status === "fulfilled") setDashboard(dashboardResult.value.data);
    if (reviewsResult.status === "fulfilled") setReviews(reviewsResult.value.data || []);
    if (promosResult.status === "fulfilled") {
      const items = promosResult.value.data || [];
      setPromotions(items);
      setSelectedPromoId((current) => current || items[0]?.promo_id || "");
    }
    if (skillsResult.status === "fulfilled") setSkills(skillsResult.value.data || []);
    if (toolsResult.status === "fulfilled") setTools(toolsResult.value.data || []);
    if (memoriesResult.status === "fulfilled") setMemories(memoriesResult.value.data || []);
    if (kbResult.status === "fulfilled") setKnowledgeBases(kbResult.value.data || []);
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
    try {
      const payload = await api.approveReview(reviewId);
      setToast(payload.message || "Preview generated.");
      await refresh();
      if (selectedReviewId === reviewId) await openReview(reviewId);
    } catch (error) {
      setToast(getErrorMessage(error));
    } finally {
      setBusyReviewId("");
    }
  }

  async function applyReview(reviewId) {
    setConfirmReviewId(reviewId);
  }

  async function confirmApply() {
    const reviewId = confirmReviewId;
    setBusyReviewId(reviewId);
    try {
      const payload = await api.applyReview(reviewId);
      setToast(payload.message || "Change applied.");
      setConfirmReviewId("");
      await refresh();
      await loadVersions();
      if (selectedReviewId === reviewId) await openReview(reviewId);
    } catch (error) {
      setToast(getErrorMessage(error));
    } finally {
      setBusyReviewId("");
    }
  }

  async function rejectReview(reviewId) {
    setBusyReviewId(reviewId);
    try {
      const payload = await api.rejectReview(reviewId);
      setToast(payload.message || "Review rejected.");
      await refresh();
      if (selectedReviewId === reviewId) await openReview(reviewId);
    } catch (error) {
      setToast(getErrorMessage(error));
    } finally {
      setBusyReviewId("");
    }
  }

  async function sendChat(message) {
    setSending(true);
    setMessages((items) => [
      ...items,
      { id: crypto.randomUUID(), role: "user", text: message, time: formatDate(new Date().toISOString()) },
    ]);
    try {
      const payload = await api.chatSend(message);
      setMessages((items) => [
        ...items,
        {
          id: crypto.randomUUID(),
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
          id: crypto.randomUUID(),
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
    setBusyPromoId(promoId);
    try {
      const payload = await api.evolvePromotion(promoId);
      setToast(payload.message || "Evolution flow updated.");
      setSelectedPromoId(promoId);
      setPage("evolution");
      await refresh();
    } catch (error) {
      setToast(getErrorMessage(error));
    } finally {
      setBusyPromoId("");
    }
  }

  async function createRollbackReview(version) {
    const key = versionKey(version);
    setBusyVersionKey(key);
    try {
      const payload = await api.rollbackSkill(version.skill, version.version);
      setToast(payload.message || "Rollback review created.");
      await refresh();
      setPage("reviews");
      if (payload.data?.review_id) await openReview(payload.data.review_id);
    } catch (error) {
      setToast(getErrorMessage(error));
    } finally {
      setBusyVersionKey("");
    }
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
          />
        ) : null}
        {page === "evolution" ? (
          <EvolutionPage
            promotions={promotions}
            selectedPromoId={selectedPromoId}
            onSelectPromo={setSelectedPromoId}
            evolutionState={evolutionState}
            busyPromoId={busyPromoId}
            onEvolve={evolvePromotion}
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
      />
      <ConfirmDialog
        open={Boolean(confirmReviewId)}
        title="Apply change?"
        message="This will modify the active file. Continue?"
        busy={Boolean(busyReviewId)}
        onCancel={() => setConfirmReviewId("")}
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
