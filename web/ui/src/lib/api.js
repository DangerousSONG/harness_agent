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
  changes: () => request("/api/changes"),
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
  fastTrackPromotion: (id) =>
    request(`/api/promotions/${encodeURIComponent(id)}/fast-track`, { method: "POST" }),
  regeneratePromotion: (id) =>
    request(`/api/promotions/${encodeURIComponent(id)}/regenerate`, { method: "POST" }),
  evolutionState: (id) => request(`/api/evolution/${encodeURIComponent(id)}/state`),
  runs: (params = {}) => {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.outcome) query.set("outcome", params.outcome);
    if (params.intent) query.set("intent", params.intent);
    if (params.should_emit !== undefined && params.should_emit !== null) {
      query.set("should_emit", params.should_emit ? "true" : "false");
    }
    const qs = query.toString();
    return request(`/api/runs${qs ? `?${qs}` : ""}`);
  },
  run: (runId) => request(`/api/runs/${encodeURIComponent(runId)}`),
  evolutionScoutScan: () => request("/api/evolution/scout/scan", { method: "POST" }),
  evolutionScoutSignals: () => request("/api/evolution/scout/signals"),
  evolutionScoutOpportunities: () => request("/api/evolution/scout/opportunities"),
  evolutionScoutOpportunity: (id) =>
    request(`/api/evolution/scout/opportunities/${encodeURIComponent(id)}`),
  evolutionScoutBatches: () => request("/api/evolution/scout/batches"),
  evolutionScoutBatchCreate: (opportunityIds) =>
    request("/api/evolution/scout/batches", {
      method: "POST",
      body: JSON.stringify({ opportunity_ids: opportunityIds || [] }),
    }),
  evolutionOptimizerPropose: (body) =>
    request("/api/evolution/optimizer/propose", {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  evolutionOptimizerEdits: () => request("/api/evolution/optimizer/edits"),
  evolutionOptimizerEdit: (id) =>
    request(`/api/evolution/optimizer/edits/${encodeURIComponent(id)}`),
  evolutionOptimizerValidate: (id) =>
    request(`/api/evolution/optimizer/edits/${encodeURIComponent(id)}/validate`, {
      method: "POST",
    }),
  evolutionOptimizerRejected: () => request("/api/evolution/optimizer/rejected"),
  assets: () => request("/api/assets"),
  skills: () => request("/api/skills"),
  skill: (name) => request(`/api/skills/${encodeURIComponent(name)}`),
  skillActive: (name) => request(`/api/skills/${encodeURIComponent(name)}/active`),
  skillEvalCases: (name) => request(`/api/skills/${encodeURIComponent(name)}/eval-cases`),
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
  tool: (name) => request(`/api/tools/${encodeURIComponent(name)}`),
  runTool: (name, inputs) =>
    request(`/api/tools/${encodeURIComponent(name)}/run`, {
      method: "POST",
      body: JSON.stringify({ inputs: inputs || {} }),
    }),
  runToolPayload: (name, body) =>
    request(`/api/tools/${encodeURIComponent(name)}/run`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  proposeToolCreate: (body) =>
    request("/api/tools/propose-create", {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  createTool: (body) =>
    request("/api/tools/create", {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  createToolUpdateReview: (name, body) =>
    request(`/api/tools/${encodeURIComponent(name)}/update-review`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
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
  knowledgeBase: (id) => request(`/api/knowledge-bases/${encodeURIComponent(id)}`),
  knowledgeBaseTree: (id) => request(`/api/knowledge-bases/${encodeURIComponent(id)}/tree`),
  knowledgeBaseFile: (id, path) =>
    request(`/api/knowledge-bases/${encodeURIComponent(id)}/file?path=${encodeURIComponent(path)}`),
  knowledgeBaseCreate: (body) =>
    request("/api/knowledge-bases", { method: "POST", body: JSON.stringify(body || {}) }),
  knowledgeBaseDelete: (id) =>
    request(`/api/knowledge-bases/${encodeURIComponent(id)}`, { method: "DELETE" }),
  knowledgeBaseImportGithub: (id, body) =>
    request(`/api/knowledge-bases/${encodeURIComponent(id)}/import-github`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  knowledgeBaseUpload: (id, formData) =>
    fetch(`${API_BASE}/api/knowledge-bases/${encodeURIComponent(id)}/upload`, {
      method: "POST",
      body: formData,
    }).then(async (response) => {
      const payload = await response.json().catch(() => ({ ok: false, message: "Bad response" }));
      if (!response.ok || payload.ok === false) {
        const error = new Error(payload.message || `Upload failed: ${response.status}`);
        error.status = response.status;
        error.payload = payload;
        throw error;
      }
      return payload;
    }),
  chatSend: (message, context = {}) =>
    request("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, context }),
    }),
  chatEvents: () => request("/api/chat/events"),
  providerSettings: () => request("/api/settings/providers"),
  saveProviderSettings: (body) =>
    request("/api/settings/providers", {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  testSearchProvider: (query) =>
    request("/api/settings/providers/test-search", {
      method: "POST",
      body: JSON.stringify({ query: query || "OpenAI", max_results: 3 }),
    }),
};

export function getErrorMessage(error) {
  if (!(error instanceof Error)) return "Something went wrong.";
  if (error.payload?.error_code === "FILE_ALREADY_EXISTS") {
    return "Existing file detected.";
  }
  if (error.payload?.error_code === "EMPTY_PATCH_PREVIEW") {
    return "Cannot apply: patch preview is empty.";
  }
  const prefix = error.status ? `HTTP ${error.status}` : "Request failed";
  return `${prefix}: ${error.message}`;
}
