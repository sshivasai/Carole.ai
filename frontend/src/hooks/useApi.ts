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
  getWsTicket: () => apiFetch<{ ticket: string }>("/api/auth/ws-ticket", { method: "POST" }),

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

  // ── Notifications ──
  markNotificationsRead: (notificationId?: string) =>
    apiFetch<any>("/api/notifications/read", { method: "POST", body: JSON.stringify({ notification_id: notificationId ?? null }) }),
  deleteNotification: (notificationId: string) => apiFetch<any>(`/api/notifications/${notificationId}`, { method: "DELETE" }),
  clearAllNotifications: () => apiFetch<any>("/api/notifications", { method: "DELETE" }),

  // ── Scheduled Tasks (Cron) ──
  listScheduledTasks: (teamId: string) => apiFetch<any[]>(`/api/cron/${teamId}`),
  createScheduledTask: (teamId: string, task: { name: string; agent_id: string; cron_expression: string; prompt: string }) =>
    apiFetch<any>(`/api/cron/${teamId}`, { method: "POST", body: JSON.stringify(task) }),
  updateScheduledTask: (taskId: string, task: { name?: string; cron_expression?: string; prompt?: string; is_active?: boolean }) =>
    apiFetch<any>(`/api/cron/${taskId}`, { method: "PUT", body: JSON.stringify(task) }),
  deleteScheduledTask: (taskId: string) => apiFetch<any>(`/api/cron/${taskId}`, { method: "DELETE" }),

  // ── Models & Catalog ──
  listModels: () => apiFetch<Record<string, any>>("/api/models"),
  getModelCatalog: () => apiFetch<Record<string, any>>("/api/models/catalog"),
  saveModelCatalog: (data: any) =>
    apiFetch<any>("/api/models/catalog", { method: "POST", body: JSON.stringify(data) }),
  resetModelCatalog: () =>
    apiFetch<Record<string, any>>("/api/models/catalog/reset", { method: "POST" }),

  // ── Prompt Blocks ──
  getPromptBlocks: () => apiFetch<import("../lib/types").PromptBlock[]>("/api/settings/prompt-blocks"),
  savePromptBlocks: (updates: Array<{ key: string; enabled: boolean; content: string }>) =>
    apiFetch<import("../lib/types").PromptBlock[]>("/api/settings/prompt-blocks", { method: "PUT", body: JSON.stringify(updates) }),
  resetPromptBlock: (key: string) =>
    apiFetch<import("../lib/types").PromptBlock>(`/api/settings/prompt-blocks/${key}/reset`, { method: "POST" }),

  // ── Prompts ──
  getPrompts: () => apiFetch<Record<string, string>>("/api/prompts"),
  savePrompts: (data: Record<string, string>) =>
    apiFetch<any>("/api/prompts", { method: "POST", body: JSON.stringify(data) }),
  resetPrompts: () =>
    apiFetch<Record<string, string>>("/api/prompts/reset", { method: "POST" }),

  // ── Global Settings ──
  getSettings: () => apiFetch<Record<string, any>>("/api/settings"),
  saveSettings: (data: Record<string, any>) =>
    apiFetch<Record<string, any>>("/api/settings", { method: "POST", body: JSON.stringify(data) }),

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
  listMessages: (teamId: string, opts?: { limit?: number; before?: string }) => {
    const params = new URLSearchParams({ limit: String(opts?.limit ?? 100) });
    if (opts?.before) params.set("before", opts.before);
    return apiFetch<any[]>(`/api/messages/${teamId}?${params}`);
  },
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

  // ── Implementation Plans ──
  getTaskPlan: (taskId: string) => apiFetch<any>(`/api/tasks/${taskId}/plan`),
  approvePlan: (taskId: string) =>
    apiFetch<any>(`/api/tasks/${taskId}/plan/approve`, { method: "POST" }),
  rejectPlan: (taskId: string, feedback?: string) =>
    apiFetch<any>(`/api/tasks/${taskId}/plan/reject`, {
      method: "POST",
      body: JSON.stringify({ feedback }),
    }),
  addPlanInlineComment: (taskId: string, lineIndex: number, text: string) =>
    apiFetch<any>(`/api/tasks/${taskId}/plan/comment`, {
      method: "POST",
      body: JSON.stringify({ line_index: lineIndex, text }),
    }),
  editPlan: (taskId: string, planMarkdown: string) =>
    apiFetch<any>(`/api/tasks/${taskId}/plan`, {
      method: "PATCH",
      body: JSON.stringify({ plan_markdown: planMarkdown }),
    }),
  updateTodos: (taskId: string, data: { todos?: any[]; toggle_id?: string }) =>
    apiFetch<any>(`/api/tasks/${taskId}/todos`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // ── Memory / Learning ──
  listLearnings: (projectId: string, teamId?: string) => {
    const qs = new URLSearchParams({ project_id: projectId });
    if (teamId) qs.set("team_id", teamId);
    return apiFetch<any[]>(`/api/learnings?${qs}`);
  },
  createLearning: (data: { project_id: string; task_summary: string; lesson_rule: string; team_id?: string }) =>
    apiFetch<any>("/api/learnings", { method: "POST", body: JSON.stringify(data) }),
  updateLearning: (learningId: string, data: { task_summary?: string; lesson_rule?: string; project_id?: string | null }) =>
    apiFetch<any>(`/api/learnings/${learningId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteLearning: (learningId: string) =>
    apiFetch<any>(`/api/learnings/${learningId}`, { method: "DELETE" }),

  listEntityMemories: (projectId?: string, teamId?: string) => {
    const qs = new URLSearchParams();
    if (projectId) qs.set("project_id", projectId);
    if (teamId) qs.set("team_id", teamId);
    return apiFetch<any[]>(`/api/memories/entities?${qs}`);
  },
  createEntityMemory: (data: { project_id?: string; team_id?: string; key: string; value: string }) =>
    apiFetch<any>("/api/memories/entities", { method: "POST", body: JSON.stringify(data) }),
  deleteEntityMemory: (memoryId: string) =>
    apiFetch<any>(`/api/memories/entities/${memoryId}`, { method: "DELETE" }),

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
  listPendingApprovals: (teamId: string) => apiFetch<any[]>(`/api/tools/approvals/pending/${teamId}`),
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
  getMcpTemplates: () => apiFetch<any[]>("/api/mcp/templates"),
  resolveMcpLogo: (data: { server_name: string; command?: string; args?: string }) =>
    apiFetch<{ slug: string; logo_url: string; cached: boolean }>("/api/mcp/resolve-logo", {
      method: "POST",
      body: JSON.stringify(data),
    }),

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
  copyFile: (source: string, destination: string, projectId?: string) =>
    apiFetch<any>("/api/files/copy", { method: "POST", body: JSON.stringify({ source, destination, project_id: projectId }) }),
  duplicateFile: (path: string, projectId?: string) =>
    apiFetch<any>("/api/files/duplicate", { method: "POST", body: JSON.stringify({ path, project_id: projectId }) }),
  batchCopyFiles: (sources: string[], destinationDir: string = ".", projectId?: string) =>
    apiFetch<any>("/api/files/batch/copy", { method: "POST", body: JSON.stringify({ sources, destination_dir: destinationDir, project_id: projectId }) }),
  batchMoveFiles: (sources: string[], destinationDir: string = ".", projectId?: string) =>
    apiFetch<any>("/api/files/batch/move", { method: "POST", body: JSON.stringify({ sources, destination_dir: destinationDir, project_id: projectId }) }),
  batchDeleteFiles: (paths: string[], projectId?: string) =>
    apiFetch<any>("/api/files/batch/delete", { method: "POST", body: JSON.stringify({ paths, project_id: projectId }) }),
  deleteFile: (path: string, projectId?: string) =>
    apiFetch<any>(`/api/files/delete?path=${encodeURIComponent(path)}${projectId ? `&project_id=${projectId}` : ""}`, { method: "DELETE" }),
  getDownloadZipUrl: (paths?: string[], projectId?: string) => {
    const params = new URLSearchParams();
    if (paths && paths.length > 0) params.append("paths", paths.join(","));
    if (projectId) params.append("project_id", projectId);
    return `${getApiBase()}/api/files/download_zip${params.toString() ? `?${params.toString()}` : ""}`;
  },
  downloadZip: async (paths?: string[], projectId?: string, filename?: string) => {
    const params = new URLSearchParams();
    if (paths && paths.length > 0) params.append("paths", paths.join(","));
    if (projectId) params.append("project_id", projectId);
    const token = typeof window !== "undefined" ? localStorage.getItem("carole_token") : null;
    const url = `${getApiBase()}/api/files/download_zip${params.toString() ? `?${params.toString()}` : ""}`;
    const res = await fetch(url, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!res.ok) {
      const err = await res.text().catch(() => "Download failed");
      throw new Error(`Download failed: ${err}`);
    }
    const blob = await res.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = filename || `workspace_${projectId || "export"}.zip`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(downloadUrl);
    document.body.removeChild(a);
  },
  getFileLogs: (teamId: string) => apiFetch<any[]>(`/api/files/logs/${teamId}`),
  deleteFileLog: (logId: string) => apiFetch<any>(`/api/files/logs/${logId}`, { method: "DELETE" }),

  // File Version History (Wave 2.3)
  getFileHistory: (path: string, projectId?: string) =>
    apiFetch<any[]>(`/api/files/history?path=${encodeURIComponent(path)}${projectId ? `&project_id=${projectId}` : ""}`),
  getBackupContent: (backupId: string) =>
    apiFetch<{ content: string; backup_id: string }>(`/api/files/history/content/${backupId}`),
  restoreFileBackup: (backupId: string, projectId?: string) =>
    apiFetch<any>(`/api/files/history/restore/${backupId}${projectId ? `?project_id=${projectId}` : ""}`, { method: "POST" }),

  // Agent clone (Wave 2.2)
  cloneAgent: (agentId: string) => apiFetch<any>(`/api/agents/${agentId}/clone`, { method: "POST" }),

  // Bulk export (Wave 2.5)
  exportConversation: (teamId: string, format: "json" | "markdown" = "markdown") =>
    `/api/teams/${teamId}/export?format=${format}`,



  // ── Terminal ──
  executeTerminal: (command: string, projectId?: string, timeout: number = 60.0) =>
    apiFetch<any>("/api/terminal/execute", { method: "POST", body: JSON.stringify({ command, project_id: projectId, timeout }) }),



  // ── Git ──
  getGitStatus: (projectSlug: string) =>
    apiFetch<{ status: string; changes: { file: string; status: string; staged: boolean; unstaged: boolean }[]; message?: string }>(`/api/git/status?slug=${projectSlug}`),
  commitChanges: (message: string, projectSlug: string) =>
    apiFetch<any>(`/api/git/commit?slug=${projectSlug}`, { method: "POST", body: JSON.stringify({ message }) }),
  initGit: (projectSlug: string) =>
    apiFetch<any>(`/api/git/init?slug=${projectSlug}`, { method: "POST" }),
  getGitFileContent: (filepath: string, projectSlug: string) =>
    apiFetch<{ status: string; content: string; message?: string }>(`/api/git/show?slug=${projectSlug}&file=${encodeURIComponent(filepath)}`),
  stageFile: (filepath: string, projectSlug: string) =>
    apiFetch<any>(`/api/git/stage`, { method: "POST", body: JSON.stringify({ file: filepath, slug: projectSlug }) }),
  unstageFile: (filepath: string, projectSlug: string) =>
    apiFetch<any>(`/api/git/unstage`, { method: "POST", body: JSON.stringify({ file: filepath, slug: projectSlug }) }),
  discardChanges: (filepath: string, projectSlug: string) =>
    apiFetch<any>(`/api/git/discard`, { method: "POST", body: JSON.stringify({ file: filepath, slug: projectSlug }) }),
  ignoreFile: (filepath: string, projectSlug: string) =>
    apiFetch<any>(`/api/git/ignore`, { method: "POST", body: JSON.stringify({ file: filepath, slug: projectSlug }) }),
  getGitLog: (projectSlug: string, limit = 50) =>
    apiFetch<{ status: string; commits: { hash: string; author: string; date: string; message: string }[]; message?: string }>(`/api/git/log?slug=${projectSlug}&limit=${limit}`),

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

  // ── Browser Automation Direct Interaction & Takeover ──
  browserAct: (data: { agent_id?: string; kind: string; x?: number; y?: number; text?: string; key?: string; ref?: number; selector?: string; url?: string }) =>
    apiFetch<{ status: string; url?: string; title?: string; screenshot?: string; message?: string }>("/api/browser/act", { method: "POST", body: JSON.stringify(data) }),
  getBrowserScreenshot: (agentId = "global") =>
    apiFetch<{ status: string; url?: string; title?: string; screenshot?: string; message?: string }>(`/api/browser/screenshot?agent_id=${encodeURIComponent(agentId)}`),
  resolveBrowserHIL: (questionId: string, answer = "Solved by user") =>
    apiFetch<{ status: string; message: string }>("/api/browser/resolve-hil", { method: "POST", body: JSON.stringify({ question_id: questionId, answer }) }),

  // ── Memory / Compaction ──
  compactTeam: (teamId: string) =>
    apiFetch<{ event_id: string; messages_compacted: number; triggered_by: string; summary_preview: string; created_at: string }>(
      `/api/teams/${teamId}/compact`,
      { method: "POST" }
    ),
  listCompactions: (teamId: string) =>
    apiFetch<{ id: string; triggered_by: string; message_count_before?: number; summary_preview?: string; created_at?: string }[]>(
      `/api/teams/${teamId}/compactions`
    ),

  // ── Observability & OpenLLMetry ──
  getObservabilityStats: () => apiFetch<any>("/api/observability/stats"),
  getObservabilityTraces: (agent?: string) =>
    apiFetch<any>(`/api/observability/traces${agent ? `?agent=${encodeURIComponent(agent)}` : ""}`),
  emitSampleTrace: () => apiFetch<any>("/api/observability/emit-sample", { method: "POST" }),
  clearObservability: () => apiFetch<any>("/api/observability/clear", { method: "POST" }),
};
