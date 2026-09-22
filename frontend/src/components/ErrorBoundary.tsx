"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an unhandled React exception:", error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "var(--color-canvas)",
          color: "var(--color-ink)",
          fontFamily: "'Inter', system-ui, sans-serif",
          padding: "24px",
          textAlign: "center"
        }}>
          <div style={{
            background: "var(--color-canvas-raised)",
            border: "1px solid var(--color-hairline)",
            borderRadius: "12px",
            padding: "32px",
            maxWidth: "500px",
            width: "100%",
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)"
          }}>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 600, color: "#EF4444", marginBottom: "12px" }}>
              Something went wrong
            </h2>
            <p style={{ fontSize: "0.875rem", color: "var(--color-body)", marginBottom: "20px", lineHeight: 1.5 }}>
              Carole.ai encountered an unexpected rendering error. You can try refreshing the page to recover.
            </p>
            {this.state.error && (
              <pre style={{
                background: "var(--color-canvas)",
                border: "1px solid var(--color-hairline)",
                borderRadius: "6px",
                padding: "12px",
                fontSize: "0.75rem",
                color: "#F59E0B",
                textAlign: "left",
                overflowX: "auto",
                marginBottom: "20px",
                maxHeight: "150px"
              }}>
                {this.state.error.toString()}
              </pre>
            )}
            <button
              onClick={this.handleReset}
              style={{
                backgroundColor: "#10B981",
                color: "#FFFFFF",
                border: "none",
                borderRadius: "6px",
                padding: "10px 20px",
                fontSize: "0.875rem",
                fontWeight: 500,
                cursor: "pointer",
                transition: "background-color 150ms ease"
              }}
            >
              Reload Application
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
