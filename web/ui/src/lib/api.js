const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = {
      ok: false,
      data: null,
      message: "The server returned an unreadable response.",
      errors: [],
    };
  }
  if (!response.ok || payload?.ok === false) {
    const message = payload?.message || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

export const api = {
  dashboard: () => request("/api/dashboard"),
  reviews: () => request("/api/reviews"),
  review: (id) => request(`/api/reviews/${encodeURIComponent(id)}`),
  reviewPatch: (id) => request(`/api/reviews/${encodeURIComponent(id)}/patch`),
  approveReview: (id) =>
    request(`/api/reviews/${encodeURIComponent(id)}/approve`, { method: "POST" }),
  applyReview: (id) =>
    request(`/api/reviews/${encodeURIComponent(id)}/apply`, { method: "POST" }),
  rejectReview: (id) =>
    request(`/api/reviews/${encodeURIComponent(id)}/reject`, { method: "POST" }),
  promotions: () => request("/api/promotions"),
  promotion: (id) => request(`/api/promotions/${encodeURIComponent(id)}`),
  evolvePromotion: (id) =>
    request(`/api/promotions/${encodeURIComponent(id)}/evolve`, { method: "POST" }),
  evolutionState: (id) => request(`/api/evolution/${encodeURIComponent(id)}/state`),
  assets: () => request("/api/assets"),
  skills: () => request("/api/skills"),
  skill: (name) => request(`/api/skills/${encodeURIComponent(name)}`),
  skillVersions: (name) => request(`/api/skills/${encodeURIComponent(name)}/versions`),
  skillVersion: (name, version) =>
    request(
      `/api/skills/${encodeURIComponent(name)}/versions/${encodeURIComponent(version)}`,
    ),
  rollbackSkill: (name, version) =>
    request(`/api/skills/${encodeURIComponent(name)}/rollback`, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),
  tools: () => request("/api/tools"),
  memories: () => request("/api/memories"),
  knowledgeBases: () => request("/api/knowledge-bases"),
  chatSend: (message) =>
    request("/api/chat/send", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  chatEvents: () => request("/api/chat/events"),
};

export function getErrorMessage(error) {
  return error instanceof Error ? error.message : "Something went wrong.";
}
