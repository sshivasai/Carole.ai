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
  listProjects: () => apiFetch<any[]>("/api/projects"),
  createProject: (name: string) => apiFetch<any>("/api/projects", { method: "POST", body: JSON.stringify({ name }) }),

  // ---- Teams ----
  listTeams: (projectId: string) => apiFetch<any[]>(`/api/teams/${projectId}`),
  createTeam: (name: string, projectId: string) =>
    apiFetch<any>("/api/teams", { method: "POST", body: JSON.stringify({ name, project_id: projectId }) }),

  // ---- Agents ----
  listAgents: (teamId: string) => apiFetch<any[]>(`/api/agents/${teamId}`),
  createAgent: (data: any) => apiFetch<any>("/api/agents", { method: "POST", body: JSON.stringify(data) }),
  updateAgent: (agentId: string, data: any) =>
    apiFetch<any>(`/api/agents/${agentId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteAgent: (agentId: string) => apiFetch<any>(`/api/agents/${agentId}`, { method: "DELETE" }),

  // ---- Messages ----
  listMessages: (teamId: string, limit = 50) => apiFetch<any[]>(`/api/messages/${teamId}?limit=${limit}`),

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

  // ---- Health ----
  healthCheck: () => apiFetch<any>("/health"),
};
