"use client";

export function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined") {
    const host = window.location.hostname || "localhost";
    const protocol = window.location.protocol || "http:";
    return `${protocol}//${host}:8000`;
  }
  return "http://localhost:8000";
}

// Simple in-flight deduplication map for GET requests
const _inflight = new Map<string, Promise<any>>();

async function apiFetch<T>(path: string, options?: RequestInit, retry = 1): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("carole_token") : null;
  const isFormData = options?.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...((options?.headers as Record<string, string>) || {}),
  };

  const key = `${options?.method || "GET"}:${path}`;
  const isGet = !options?.method || options.method === "GET";

  const execute = async (): Promise<T> => {
    let res: Response;
    const url = `${getApiBase()}${path}`;
    try {
      res = await fetch(url, { ...options, headers });
    } catch (err: any) {
      if (err instanceof TypeError || err?.name === "TypeError" || err?.message === "Failed to fetch") {
        const netErr: any = new Error(`Failed to connect to backend at ${url}. Ensure the FastAPI backend server is running.`);
        netErr.status = 0;
        netErr.endpoint = path;
        netErr.cause = err;
        throw netErr;
      }
      throw err;
    }
    if (!res.ok) {
      const text = await res.text().catch(() => "Unknown error");
      const err: any = new Error(`API ${res.status}: ${text}`);
      err.status = res.status;
      err.endpoint = path;
      err.body = text;
      throw err;
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.text() as any;
  };

  if (isGet) {
    if (_inflight.has(key)) return _inflight.get(key)!;
    const p = execute().catch(async (e) => {
      // Only retry on HTTP 5xx — a network-level TypeError (e.status ===
      // undefined) means the backend is unreachable, so retrying just delays
      // the inevitable and spams the server. Fail fast and let the caller
      // surface a retry affordance.
      if (retry > 0 && typeof e.status === "number" && e.status >= 500) {
        _inflight.delete(key);
        await new Promise(r => setTimeout(r, 500));
        return apiFetch<T>(path, options, retry - 1);
      }
      throw e;
    }).finally(() => _inflight.delete(key));
    _inflight.set(key, p);
    return p;
  }

  return execute();
}

// Helper for Next.js internal API routes (without API_BASE)
async function nextApiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("carole_token") : null;
  const headers: Record<string, string> = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    "Content-Type": "application/json",
    ...((options?.headers as Record<string, string>) || {}),
  };

  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  // ── Auth ──
  signup: (email: string, password: string, firstName?: string, lastName?: string) =>
    apiFetch<{ user: any; token: string }>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, first_name: firstName, last_name: lastName }),
    }),
  login: (email: string, password: string) =>
    apiFetch<{ user: any; token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  getMe: () => apiFetch<any>("/api/auth/me"),

  // ── Users ──
  listUsers: () => apiFetch<any[]>("/api/users"),
  createUser: (email: string, firstName?: string, lastName?: string) =>
    apiFetch<any>("/api/users", { method: "POST", body: JSON.stringify({ email, first_name: firstName, last_name: lastName }) }),
  deleteUser: (userId: string) => apiFetch<any>(`/api/users/${userId}`, { method: "DELETE" }),

  // ── Projects ──
  listProjects: () => apiFetch<any[]>("/api/projects"),
  getProject: (projectId: string) => apiFetch<any>(`/api/projects/single/${projectId}`),
  createProject: (name: string, ownerId?: string) =>
    apiFetch<any>("/api/projects", { method: "POST", body: JSON.stringify({ name, owner_id: ownerId }) }),
  deleteProject: (projectId: string, deleteContent?: boolean) => apiFetch<any>(`/api/projects/${projectId}${deleteContent ? '?delete_content=true' : ''}`, { method: "DELETE" }),

  // ── Teams ──
  listTeams: (projectId: string) => apiFetch<any[]>(`/api/teams/${projectId}`),
  getTeam: (teamId: string) => apiFetch<any>(`/api/teams/single/${teamId}`),
  createTeam: (name: string, projectId: string) =>
    apiFetch<any>("/api/teams", { method: "POST", body: JSON.stringify({ name, project_id: projectId }) }),
  deleteTeam: (teamId: string, deleteContent?: boolean) => apiFetch<any>(`/api/teams/${teamId}${deleteContent ? '?delete_content=true' : ''}`, { method: "DELETE" }),

  // ── Models & Catalog ──
  listModels: () => apiFetch<Record<string, any>>("/api/models"),
  getModelCatalog: () => apiFetch<Record<string, any>>("/api/models/catalog"),
  saveModelCatalog: (data: any) =>
    apiFetch<any>("/api/models/catalog", { method: "POST", body: JSON.stringify(data) }),
  resetModelCatalog: () =>
    apiFetch<Record<string, any>>("/api/models/catalog/reset", { method: "POST" }),

  // ── Prompts ──
  getPrompts: () => apiFetch<Record<string, string>>("/api/prompts"),
  savePrompts: (data: Record<string, string>) =>
    apiFetch<any>("/api/prompts", { method: "POST", body: JSON.stringify(data) }),
  resetPrompts: () =>
    apiFetch<Record<string, string>>("/api/prompts/reset", { method: "POST" }),

  // ── Agents ──
  listAgents: (teamId: string) => apiFetch<any[]>(`/api/agents/${teamId}`),
  createAgent: (data: any) => apiFetch<any>("/api/agents", { method: "POST", body: JSON.stringify(data) }),
  updateAgent: (agentId: string, data: any) =>
    apiFetch<any>(`/api/agents/${agentId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteAgent: (agentId: string) => apiFetch<any>(`/api/agents/${agentId}`, { method: "DELETE" }),
  stopAgent: (agentId: string) => apiFetch<any>(`/api/agents/${agentId}/stop`, { method: "POST" }),

  // 💬 Messages 💬
  uploadFile: (teamId: string | null, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const qs = teamId ? `?team_id=${teamId}` : "";
    return apiFetch<any>(`/api/upload${qs}`, { method: "POST", body: formData });
  },
  listMessages: (teamId: string, limit = 50) => apiFetch<any[]>(`/api/messages/${teamId}?limit=${limit}`),
  searchMessages: (teamId: string, query: string, limit = 10) =>
    apiFetch<any[]>(`/api/messages/search/${teamId}?q=${encodeURIComponent(query)}&limit=${limit}`),
  editMessage: (messageId: string, text: string) =>
    apiFetch<any>(`/api/messages/${messageId}`, { method: "PUT", body: JSON.stringify({ text }) }),
  deleteMessage: (messageId: string) =>
    apiFetch<any>(`/api/messages/${messageId}`, { method: "DELETE" }),
  clearTeamChat: (teamId: string) =>
    apiFetch<any>(`/api/teams/${teamId}/messages`, { method: "DELETE" }),
  rollbackFromMessage: (messageId: string) =>
    apiFetch<any>(`/api/messages/${messageId}/rollback`, { method: "DELETE" }),

  // ── Tasks ──
  listTasks: (teamId: string, status?: string) =>
    apiFetch<any[]>(`/api/tasks/${teamId}${status ? `?status=${status}` : ""}`),
  createTask: (data: any) => apiFetch<any>("/api/tasks", { method: "POST", body: JSON.stringify(data) }),
  updateTask: (taskId: string, data: any) =>
    apiFetch<any>(`/api/tasks/${taskId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteTask: (taskId: string) => apiFetch<any>(`/api/tasks/${taskId}`, { method: "DELETE" }),
  getTaskComments: (taskId: string) => apiFetch<any[]>(`/api/tasks/${taskId}/comments`),
  addTaskComment: (taskId: string, authorId: string, authorName: string, text: string) =>
    apiFetch<any>(`/api/tasks/${taskId}/comments`, {
      method: "POST",
      body: JSON.stringify({ author_id: authorId, author_name: authorName, text }),
    }),

  // ── Learnings ──
  listLearnings: (projectId: string) => apiFetch<any[]>(`/api/learnings/${projectId}`),
  createLearning: (data: { project_id: string; task_summary: string; lesson_rule: string; team_id?: string }) =>
    apiFetch<any>("/api/learnings", { method: "POST", body: JSON.stringify(data) }),
  updateLearning: (learningId: string, data: { task_summary?: string; lesson_rule?: string }) =>
    apiFetch<any>(`/api/learnings/${learningId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteLearning: (learningId: string) => apiFetch<any>(`/api/learnings/${learningId}`, { method: "DELETE" }),

  // ── Scratchpads ──
  listScratchpads: (teamId: string) =>
    apiFetch<import("../lib/types").ScratchpadItem[]>(`/api/scratchpad/${teamId}`),
  readScratchpad: (teamId: string, target: "team" | "personal", agentName: string) =>
    apiFetch<import("../lib/types").ScratchpadItem>(
      `/api/scratchpad/${teamId}/${target}${target === "personal" ? `?agent_name=${encodeURIComponent(agentName)}` : ""}`,
    ),
  writeScratchpad: (teamId: string, body: { content: string; target?: "team" | "personal"; mode?: "append" | "overwrite"; agent_name: string; agent_id?: string; author?: string }) =>
    apiFetch<any>(`/api/scratchpad/${teamId}`, { method: "POST", body: JSON.stringify(body) }),
  updateScratchpad: (teamId: string, body: { content: string; target?: "team" | "personal"; agent_name: string; agent_id?: string; author?: string }) =>
    apiFetch<any>(`/api/scratchpad/${teamId}`, { method: "PUT", body: JSON.stringify(body) }),
  clearScratchpad: (teamId: string, target: "team" | "personal", agentName: string) =>
    apiFetch<any>(`/api/scratchpad/${teamId}?target=${target}${target === "personal" ? `&agent_name=${encodeURIComponent(agentName)}` : ""}`, { method: "DELETE" }),

  // ── Tools & Plugins ──
  listTools: () => apiFetch<any[]>("/api/tools"),
  approveToolExecution: (txId: string, approved: boolean) =>
    apiFetch<any>(`/api/tools/approve/${txId}`, { method: "POST", body: JSON.stringify({ approved }) }),
  registerTool: (data: { name: string; description: string; parameters: any; endpoint_url: string }) =>
    apiFetch<any>("/api/tools/register", { method: "POST", body: JSON.stringify(data) }),
  listPlugins: () => apiFetch<any[]>("/api/plugins"),
  savePlugin: (filename: string, code: string) =>
    apiFetch<any>(`/api/plugins/${filename}`, { method: "POST", body: JSON.stringify({ code }) }),
  deletePlugin: (filename: string) =>
    apiFetch<any>(`/api/plugins/${filename}`, { method: "DELETE" }),
  generatePlugin: (prompt: string) =>
    apiFetch<any>("/api/plugins/action/generate", { method: "POST", body: JSON.stringify({ prompt }) }),

  // ── Skills ──
  listSkills: (teamId: string) => apiFetch<any[]>(`/api/skills/${teamId}`),
  createSkill: (data: { team_id: string; name: string; description?: string; system_prompt_addendum?: string; tools?: string[]; mcp_servers?: string[] }) =>
    apiFetch<any>("/api/skills", { method: "POST", body: JSON.stringify(data) }),
  updateSkill: (skillId: string, data: { name?: string; description?: string; system_prompt_addendum?: string; tools?: string[]; mcp_servers?: string[]; is_active?: boolean }) =>
    apiFetch<any>(`/api/skills/${skillId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteSkill: (skillId: string) =>
    apiFetch<any>(`/api/skills/${skillId}`, { method: "DELETE" }),

  // ── Agent Questions ──
  answerAgentQuestion: (questionId: string, answer: string) =>
    apiFetch<any>(`/api/agent/answer/${questionId}`, { method: "POST", body: JSON.stringify({ answer }) }),

  // ── Role Templates ──
  listRoleTemplates: () => apiFetch<any[]>("/api/role-templates"),
  getRoleTemplate: (role: string) => apiFetch<any>(`/api/role-templates/${role}`),

  // ── MCP ──
  listGlobalMcpServers: () => apiFetch<any[]>("/api/mcp/global"),
  toggleGlobalMcpServer: (serverName: string) =>
    apiFetch<any>(`/api/mcp/global/${serverName}/toggle`, { method: "POST" }),
  listMcpServers: (teamId: string) => apiFetch<any[]>(`/api/mcp/${teamId}`),
  createMcpServer: (data: { team_id: string; server_name: string; command: string; args: string; agent_id?: string; env_vars?: Record<string, string> }) =>
    apiFetch<any>("/api/mcp", { method: "POST", body: JSON.stringify(data) }),
  deleteMcpServer: (serverId: string) =>
    apiFetch<any>(`/api/mcp/${serverId}`, { method: "DELETE" }),
  getMcpStatus: () => apiFetch<Record<string, any>>("/api/mcp/status"),

  // ── Knowledge ──
  uploadKnowledgeFile: async (projectId: string, teamId: string | null, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const path = `/api/knowledge/upload?project_id=${projectId}${teamId ? `&team_id=${teamId}` : ""}`;
    const token = typeof window !== "undefined" ? localStorage.getItem("carole_token") : null;
    const res = await fetch(`${getApiBase()}${path}`, {
      method: "POST",
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Upload failed ${res.status}`);
    return res.json();
  },

  // ── Audio Transcription ──
  transcribeAudio: async (teamId: string, audioBlob: Blob) => {
    const formData = new FormData();
    formData.append("file", audioBlob, "recording.webm");
    const token = typeof window !== "undefined" ? localStorage.getItem("carole_token") : null;
    const res = await fetch(`${getApiBase()}/api/audio/transcribe/${teamId}`, {
      method: "POST",
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Transcription failed ${res.status}`);
    return res.json();
  },

  // ── Usage & Health ──
  getProjectUsage: (projectId: string) => apiFetch<any>(`/api/usage/${projectId}`),
  wsStatus: (teamId: string) => apiFetch<any>(`/api/ws/status/${teamId}`),
  healthCheck: () => apiFetch<any>("/health"),
  seedDemo: () => apiFetch<any>("/api/seed", { method: "POST" }),

  // ── Files ──
  listFiles: (path: string = ".", projectId?: string) =>
    apiFetch<any[]>(`/api/files/list?path=${encodeURIComponent(path)}${projectId ? `&project_id=${projectId}` : ""}`),
  listFileTree: (projectId?: string, teamId?: string) => {
    const params = new URLSearchParams();
    if (projectId) params.append("project_id", projectId);
    if (teamId) params.append("team_id", teamId);
    const query = params.toString();
    return apiFetch<{ files: string[]; truncated?: boolean }>(`/api/files/tree${query ? `?${query}` : ""}`);
  },
  readFile: (path: string, projectId?: string) =>
    apiFetch<{ content: string }>(`/api/files/read?path=${encodeURIComponent(path)}${projectId ? `&project_id=${projectId}` : ""}`),
  writeFile: (path: string, content: string, projectId?: string) =>
    apiFetch<any>("/api/files/write", { method: "POST", body: JSON.stringify({ path, content, project_id: projectId }) }),
  createFolder: (path: string, projectId?: string) =>
    apiFetch<any>("/api/files/create_folder", { method: "POST", body: JSON.stringify({ path, project_id: projectId }) }),
  renameFile: (source: string, destination: string, projectId?: string) =>
    apiFetch<any>("/api/files/rename", { method: "POST", body: JSON.stringify({ source, destination, project_id: projectId }) }),
  deleteFile: (path: string, projectId?: string) =>
    apiFetch<any>(`/api/files/delete?path=${encodeURIComponent(path)}${projectId ? `&project_id=${projectId}` : ""}`, { method: "DELETE" }),
  getFileLogs: (teamId: string) => apiFetch<any[]>(`/api/files/logs/${teamId}`),
  deleteFileLog: (logId: string) => apiFetch<any>(`/api/files/logs/${logId}`, { method: "DELETE" }),

  // ── Terminal ──
  executeTerminal: (command: string, projectId?: string, timeout: number = 60.0) =>
    apiFetch<any>("/api/terminal/execute", { method: "POST", body: JSON.stringify({ command, project_id: projectId, timeout }) }),



  // ── Git ──
  getGitStatus: (projectSlug: string) =>
    nextApiFetch<{ status: string; changes: { file: string; status: string }[]; message?: string }>(`/api/git/status?slug=${projectSlug}`),
  commitChanges: (message: string, projectSlug: string) =>
    nextApiFetch<any>(`/api/git/commit?slug=${projectSlug}`, { method: "POST", body: JSON.stringify({ message }) }),
  initGit: (projectSlug: string) =>
    nextApiFetch<any>(`/api/git/init?slug=${projectSlug}`, { method: "POST" }),
  getGitFileContent: (filepath: string, projectSlug: string) =>
    nextApiFetch<{ status: string; content: string; message?: string }>(`/api/git/show?slug=${projectSlug}&file=${encodeURIComponent(filepath)}`),

  // ── Search ──
  searchFiles: (query: string, projectId?: string) =>
    apiFetch<{ status: string; results: { file: string; line: string; content: string }[]; message?: string }>(`/api/search/grep?q=${encodeURIComponent(query)}${projectId ? `&project_id=${projectId}` : ""}`),

  // ── Cost Management ──
  getCostStats: (projectId: string) =>
    apiFetch<any>(`/api/cost/stats?project_id=${encodeURIComponent(projectId)}`),
  updateBudget: (data: { project_id: string; budget_limit_usd: number | null }) =>
    apiFetch<any>("/api/cost/budget", { method: "POST", body: JSON.stringify(data) }),

  // ── App Settings ──
  getAppConfig: () => apiFetch<any>("/api/settings"),
  updateAppConfig: (config: { api_keys?: Record<string, string>; providers?: Record<string, string>; default_models?: Record<string, string>; agent_settings?: Record<string, unknown>; browser_automation?: any }) =>
    apiFetch<any>("/api/settings", { method: "POST", body: JSON.stringify(config) }),

  // ── Google OAuth ──
  getGoogleStatus: () => apiFetch<any>("/api/auth/google/status"),
  disconnectGoogle: () => apiFetch<any>("/api/auth/google/disconnect", { method: "POST" }),
  getGoogleAuthUrl: () => `${getApiBase()}/api/auth/google/authorize`,
};
