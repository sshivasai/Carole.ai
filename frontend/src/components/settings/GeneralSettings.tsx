"use client";
import React, { useState, useEffect, useCallback } from "react";
import { User, ShieldCheck, Activity, CheckCircle, AlertTriangle, RefreshCw, Loader2, Calendar, Mail, Video, ExternalLink, ListChecks } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/hooks/useApi";
import SettingTooltip from "./SettingTooltip";

interface Props {
  teamId: string | null;
  onToast: (msg: string, type: "success" | "error" | "info") => void;
}

interface HealthData {
  status: string;
  tools_registered?: number;
  version?: string;
}

export default function GeneralSettings({ teamId, onToast }: Props) {
  const { user } = useAuth();

  // ── Google Account State ──────────────────────────────────────────────────
  const [googleStatus, setGoogleStatus] = useState<any>(null);
  const [googleLoading, setGoogleLoading] = useState(true);
  const [disconnectingGoogle, setDisconnectingGoogle] = useState(false);

  const fetchGoogleStatus = useCallback(async () => {
    setGoogleLoading(true);
    try {
      const res = await api.getGoogleStatus();
      setGoogleStatus(res);
    } catch {
      setGoogleStatus(null);
    } finally {
      setGoogleLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGoogleStatus();
    if (typeof window !== "undefined" && window.location.search.includes("google_connected")) {
      fetchGoogleStatus();
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [fetchGoogleStatus]);

  const handleConnectGoogle = async () => {
    try {
      const { url } = await api.getGoogleAuthUrl();
      window.location.href = url;
    } catch {
      onToast("Could not start Google authorization", "error");
    }
  };

  const handleDisconnectGoogle = async () => {
    setDisconnectingGoogle(true);
    try {
      await api.disconnectGoogle();
      setGoogleStatus({ connected: false });
      onToast("Google account disconnected", "info");
    } catch {
      onToast("Failed to disconnect Google account", "error");
    } finally {
      setDisconnectingGoogle(false);
    }
  };

  // ── Health State ──────────────────────────────────────────────────────────
  const [health, setHealth] = useState<HealthData | null>(null);
  const [wsStatus, setWsStatus] = useState<any>(null);
  const [healthLoading, setHealthLoading] = useState(true);

  const refreshHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const [h, ws] = await Promise.all([
        api.healthCheck(),
        teamId ? api.wsStatus(teamId) : Promise.resolve(null),
      ]);
      setHealth(h);
      setWsStatus(ws);
    } catch {
      setHealth(null);
      setWsStatus(null);
    } finally {
      setHealthLoading(false);
    }
  }, [teamId]);

  useEffect(() => {
    refreshHealth();
  }, [refreshHealth]);

  const isHealthOk = health?.status === "ok" || health?.status === "healthy";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2xl)" }}>
      {/* ── User Profile Card ── */}
      {user && (
        <div className="card" style={{ padding: "var(--sp-xl)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)", marginBottom: "var(--sp-lg)" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--radius-sm)",
                background: "var(--color-primary-glow)",
                border: "1px solid var(--color-primary-soft)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-primary)",
              }}
            >
              <User size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center" }}>
                <h3 className="display-sm" style={{ margin: 0 }}>User Profile</h3>
                <SettingTooltip
                  title="Active Profile"
                  why="Identifies your author identity across team chats, git commits, and memory logs."
                  how="Used as the user identity when agents generate pull requests or log memories."
                />
              </div>
              <p className="caption text-mute" style={{ margin: 0 }}>Your active workspace account details</p>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))", gap: "var(--sp-md)" }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ fontSize: 11 }}>First Name</label>
              <input className="input" value={user.first_name || ""} readOnly style={{ background: "var(--color-canvas-raised)" }} />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label" style={{ fontSize: 11 }}>Last Name</label>
              <input className="input" value={user.last_name || ""} readOnly style={{ background: "var(--color-canvas-raised)" }} />
            </div>
            <div className="form-group" style={{ marginBottom: 0, gridColumn: "1 / -1" }}>
              <label className="form-label" style={{ fontSize: 11 }}>Email Address</label>
              <input className="input" value={user.email} readOnly style={{ background: "var(--color-canvas-raised)" }} />
            </div>
          </div>
        </div>
      )}

      {/* ── Google Integration Card ── */}
      <div className="card" style={{ padding: "var(--sp-xl)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--sp-md)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--radius-sm)",
                background: "rgba(234, 67, 53, 0.1)",
                border: "1px solid rgba(234, 67, 53, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <svg width="18" height="18" viewBox="0 0 48 48">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
                <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
              </svg>
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "var(--sp-sm)" }}>
                <h3 className="display-sm" style={{ margin: 0 }}>Google Workspace Integration</h3>
                <SettingTooltip
                  title="Google OAuth"
                  why="Grants agents scoped access to Gmail, Calendar, Meet scheduling, and Google Tasks."
                  how="Your OAuth tokens stay on this computer in the operating-system credential vault. External changes always require human approval."
                />
                {googleStatus?.connected ? (
                  <span className="badge badge-green" style={{ fontSize: 9 }}>Connected</span>
                ) : (
                  <span className="badge badge-gray" style={{ fontSize: 9 }}>Disconnected</span>
                )}
              </div>
              <p className="caption text-mute" style={{ margin: 0 }}>
                Connect your own Google account. Read actions are scoped; sends, edits, trash, and deletes require your approval.
              </p>
            </div>
          </div>
        </div>

        {googleLoading ? (
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "var(--sp-sm)", padding: "var(--sp-md)" }}>
            <Loader2 size={15} className="animate-spin" style={{ color: "var(--color-primary)" }} />
            <span className="caption">Checking Google connection status…</span>
          </div>
        ) : googleStatus?.connected ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "var(--sp-md) var(--sp-lg)",
                background: "rgba(16, 185, 129, 0.06)",
                border: "1px solid rgba(16, 185, 129, 0.2)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "var(--sp-sm)" }}>
                <CheckCircle size={15} color="var(--color-success)" />
                <div>
                  <div className="body-sm-strong" style={{ color: "var(--color-success)" }}>
                    Connected Account
                  </div>
                  {googleStatus.email && (
                    <div className="caption" style={{ fontFamily: "var(--font-mono)" }}>
                      {googleStatus.email}
                    </div>
                  )}
                </div>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={handleDisconnectGoogle}
                disabled={disconnectingGoogle}
                style={{ color: "var(--color-danger)" }}
              >
                {disconnectingGoogle && <Loader2 size={12} className="animate-spin" />}
                Disconnect
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(180px, 100%), 1fr))", gap: "var(--sp-sm)" }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--sp-sm)",
                  padding: "var(--sp-sm) var(--sp-md)",
                  background: "var(--color-canvas-soft)",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--color-hairline)",
                  fontSize: 11,
                }}
              >
                <Calendar size={13} color="#4285F4" />
                <span>Google Calendar Sync</span>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--sp-sm)",
                  padding: "var(--sp-sm) var(--sp-md)",
                  background: "var(--color-canvas-soft)",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--color-hairline)",
                  fontSize: 11,
                }}
              >
                <Video size={13} color="#34A853" />
                <span>Google Meet Scheduling</span>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--sp-sm)",
                  padding: "var(--sp-sm) var(--sp-md)",
                  background: "var(--color-canvas-soft)",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--color-hairline)",
                  fontSize: 11,
                }}
              >
                <Mail size={13} color="#EA4335" />
                <span>Gmail Read &amp; Manage</span>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--sp-sm)",
                  padding: "var(--sp-sm) var(--sp-md)",
                  background: "var(--color-canvas-soft)",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--color-hairline)",
                  fontSize: 11,
                }}
              >
                <ListChecks size={13} color="#4285F4" />
                <span>Google Tasks</span>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-md)" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--sp-sm)",
                padding: "var(--sp-md)",
                background: "var(--color-canvas-raised)",
                border: "1px solid var(--color-hairline)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <AlertTriangle size={14} color="var(--color-mute)" />
              <div className="caption">
                {googleStatus?.reason === "secure_token_store_unavailable"
                  ? "A secure OS credential vault is unavailable. Configure Windows Credential Manager, macOS Keychain, or Linux Secret Service before connecting."
                  : "No Google account connected. Connect to unlock Gmail, Meet, Calendar, and Tasks agent tools."}
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                id="connect-google"
                className="btn btn-primary btn-sm"
                onClick={handleConnectGoogle}
                style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "var(--sp-sm)" }}
              >
                <ExternalLink size={13} />
                Connect Google Account
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── System Health Card ── */}
      <div className="card" style={{ padding: "var(--sp-xl)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--sp-lg)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-md)" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: "var(--radius-sm)",
                background: "rgba(16, 185, 129, 0.1)",
                border: "1px solid rgba(16, 185, 129, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-success)",
              }}
            >
              <Activity size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center" }}>
                <h3 className="display-sm" style={{ margin: 0 }}>System Health &amp; Diagnostics</h3>
                <SettingTooltip
                  title="System Telemetry"
                  why="Verifies connectivity between the Next.js frontend, Python FastAPI backend, and real-time WebSocket bus."
                  how="Pings /api/health and checks active registered tools and active WebSocket subscribers in real time."
                />
              </div>
              <p className="caption text-mute" style={{ margin: 0 }}>Live backend telemetry, WebSocket channels, and registered tools</p>
            </div>
          </div>
          <button
            className="btn btn-icon btn-ghost btn-sm"
            onClick={refreshHealth}
            disabled={healthLoading}
            title="Refresh System Health"
          >
            <RefreshCw size={13} className={healthLoading ? "animate-spin" : ""} />
          </button>
        </div>

        {healthLoading ? (
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "var(--sp-sm)", padding: "var(--sp-md)" }}>
            <Loader2 size={15} className="animate-spin" style={{ color: "var(--color-primary)" }} />
            <span className="caption">Fetching diagnostic telemetry…</span>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(200px, 100%), 1fr))", gap: "var(--sp-md)" }}>
            <div
              style={{
                background: "var(--color-canvas-raised)",
                border: "1px solid var(--color-hairline)",
                borderRadius: "var(--radius-sm)",
                padding: "var(--sp-md)",
              }}
            >
              <div className="caption text-mute" style={{ marginBottom: 4 }}>FastAPI Core Service</div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {isHealthOk ? <CheckCircle size={14} color="var(--color-success)" /> : <AlertTriangle size={14} color="var(--color-danger)" />}
                <span className="body-sm-strong" style={{ textTransform: "uppercase" }}>{health?.status || "Offline"}</span>
              </div>
            </div>

            <div
              style={{
                background: "var(--color-canvas-raised)",
                border: "1px solid var(--color-hairline)",
                borderRadius: "var(--radius-sm)",
                padding: "var(--sp-md)",
              }}
            >
              <div className="caption text-mute" style={{ marginBottom: 4 }}>Registered Agent Tools</div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <ShieldCheck size={14} color="var(--color-primary)" />
                <span className="body-sm-strong">{health?.tools_registered ?? "—"} active tools</span>
              </div>
            </div>

            <div
              style={{
                background: "var(--color-canvas-raised)",
                border: "1px solid var(--color-hairline)",
                borderRadius: "var(--radius-sm)",
                padding: "var(--sp-md)",
              }}
            >
              <div className="caption text-mute" style={{ marginBottom: 4 }}>WebSocket Real-Time Feed</div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: teamId ? "var(--color-success)" : "var(--color-mute)" }} />
                <span className="body-sm-strong">{wsStatus?.connections ?? (teamId ? "Connected" : "Idle")}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
