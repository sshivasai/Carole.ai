"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Lightweight fetch wrapper for the Carole.ai REST API.
 */
async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

// ---- Projects ----
export const api = {
  seedDemo: () => apiFetch<any>("/api/seed", { method: "POST" }),
  
  // ---- Users / Tenants ----
  listUsers: () => apiFetch<any[]>("/api/users"),
  createUser: (email: string, firstName?: string, lastName?: string) =>
    apiFetch<any>("/api/users", { method: "POST", body: JSON.stringify({ email, first_name: firstName, last_name: lastName }) }),
  deleteUser: (userId: string) => apiFetch<any>(`/api/users/${userId}`, { method: "DELETE" }),

  // ---- Projects ----
  listProjects: () => apiFetch<any[]>("/api/projects"),
  getProject: (projectId: string) => apiFetch<any>(`/api/projects/single/${projectId}`),
  createProject: (name: string, ownerId?: string) =>
    apiFetch<any>("/api/projects", { method: "POST", body: JSON.stringify({ name, owner_id: ownerId }) }),
  deleteProject: (projectId: string) => apiFetch<any>(`/api/projects/${projectId}`, { method: "DELETE" }),

  // ---- Learnings / Knowledge ----
  listLearnings: (projectId: string) => apiFetch<any[]>(`/api/learnings/${projectId}`),
  createLearning: (data: { project_id: string, task_summary: string, lesson_rule: string, team_id?: string }) =>
    apiFetch<any>("/api/learnings", { method: "POST", body: JSON.stringify(data) }),

  // ---- Teams ----
  listTeams: (projectId: string) => apiFetch<any[]>(`/api/teams/${projectId}`),
  getTeam: (teamId: string) => apiFetch<any>(`/api/teams/single/${teamId}`),
  createTeam: (name: string, projectId: string) =>
    apiFetch<any>("/api/teams", { method: "POST", body: JSON.stringify({ name, project_id: projectId }) }),
  deleteTeam: (teamId: string) => apiFetch<any>(`/api/teams/${teamId}`, { method: "DELETE" }),

  // ---- Agents ----
  listAgents: (teamId: string) => apiFetch<any[]>(`/api/agents/${teamId}`),
  createAgent: (data: any) => apiFetch<any>("/api/agents", { method: "POST", body: JSON.stringify(data) }),
  updateAgent: (agentId: string, data: any) =>
    apiFetch<any>(`/api/agents/${agentId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteAgent: (agentId: string) => apiFetch<any>(`/api/agents/${agentId}`, { method: "DELETE" }),

  // ---- Messages ----
  listMessages: (teamId: string, limit = 50) => apiFetch<any[]>(`/api/messages/${teamId}?limit=${limit}`),
  searchMessages: (teamId: string, query: string, limit = 10) =>
    apiFetch<any[]>(`/api/messages/search/${teamId}?q=${encodeURIComponent(query)}&limit=${limit}`),

  // ---- Tasks ----
  listTasks: (teamId: string, status?: string) =>
    apiFetch<any[]>(`/api/tasks/${teamId}${status ? `?status=${status}` : ""}`),
  createTask: (data: any) => apiFetch<any>("/api/tasks", { method: "POST", body: JSON.stringify(data) }),
  updateTask: (taskId: string, data: any) =>
    apiFetch<any>(`/api/tasks/${taskId}`, { method: "PUT", body: JSON.stringify(data) }),

  // ---- Tools ----
  listTools: () => apiFetch<any[]>("/api/tools"),

  // ---- Approvals ----
  approveToolExecution: (txId: string, approved: boolean) =>
    apiFetch<any>(`/api/tools/approve/${txId}`, { method: "POST", body: JSON.stringify({ approved }) }),

  // ---- Agent Questions ----
  answerAgentQuestion: (questionId: string, answer: string) =>
    apiFetch<any>(`/api/agent/answer/${questionId}`, { method: "POST", body: JSON.stringify({ answer }) }),

  // ---- Role Templates ----
  listRoleTemplates: () => apiFetch<any[]>("/api/role-templates"),
  getRoleTemplate: (role: string) => apiFetch<any>(`/api/role-templates/${role}`),

  // ---- Auth ----
  signup: (email: string, password: string, firstName?: string, lastName?: string) =>
    apiFetch<any>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, first_name: firstName, last_name: lastName }),
    }),
  login: (email: string, password: string) =>
    apiFetch<any>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  getMe: (token: string) =>
    apiFetch<any>("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    }),

  // ---- Knowledge File Upload & Usage ----
  uploadKnowledgeFile: async (projectId: string, teamId: string | null, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const path = `/api/knowledge/upload?project_id=${projectId}${teamId ? `&team_id=${teamId}` : ""}`;
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Upload failed ${res.status}: ${text}`);
    }
    return res.json();
  },
  getProjectUsage: (projectId: string) => apiFetch<any>(`/api/usage/${projectId}`),

  // ---- Health ----
  healthCheck: () => apiFetch<any>("/health"),
};

