const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, options = {}) {
  const method = options.method || "GET";
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
    const error = new Error(message);
    error.status = response.status;
    error.statusText = response.statusText;
    error.payload = payload;
    error.path = path;
    error.method = method;
    throw error;
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
  regeneratePromotion: (id) =>
    request(`/api/promotions/${encodeURIComponent(id)}/regenerate`, { method: "POST" }),
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
  promoteMemory: (id) =>
    request(`/api/memories/${encodeURIComponent(id)}/promote`, { method: "POST" }),
  proposeWrite: (body) =>
    request("/api/workspace/files/propose-write", {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  proposeSkill: (body) =>
    request("/api/skills/propose", {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  runCommand: (command) =>
    request("/api/workspace/commands/run", {
      method: "POST",
      body: JSON.stringify({ command }),
    }),
  knowledgeBases: () => request("/api/knowledge-bases"),
  chatSend: (message, context = {}) =>
    request("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, context }),
    }),
  chatEvents: () => request("/api/chat/events"),
};

export function getErrorMessage(error) {
  if (!(error instanceof Error)) return "Something went wrong.";
  const prefix = error.status ? `HTTP ${error.status}` : "Request failed";
  return `${prefix}: ${error.message}`;
}
