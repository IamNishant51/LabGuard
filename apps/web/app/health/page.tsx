"use client";

import { useEffect, useState } from "react";

type Health = { status: string; server_time: string; version: string };
type State =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; message: string };

const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function HealthPage() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiBase}/api/v1/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<Health>;
      })
      .then((health) => {
        if (!cancelled) setState({ kind: "ok", health });
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Unknown error",
          });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <h1>API health</h1>
      {state.kind === "loading" && <p>Checking API…</p>}
      {state.kind === "ok" && (
        <div className="status-box">
          <p>Status: {state.health.status}</p>
          <p>Server time: {state.health.server_time}</p>
          <p>Version: {state.health.version}</p>
        </div>
      )}
      {state.kind === "error" && (
        <div className="status-box">
          <p>API is not reachable.</p>
          <p className="muted">
            Expected when the backend is stopped. Start it with
            `uvicorn labguard_api.main:app` in `services/api`, then reload this
            page. ({state.message})
          </p>
        </div>
      )}
    </>
  );
}
