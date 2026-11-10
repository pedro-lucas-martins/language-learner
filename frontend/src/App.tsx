import { useEffect, useState } from "react";

import { API_URL } from "./config.ts";

type BackendStatus = { state: "checking" } | { state: "ok"; env: string } | { state: "down" };

/**
 * Slice 0 placeholder screen: confirms the frontend can reach the backend.
 * Replaced by the real chat UI in slice 1.
 */
export default function App() {
  const [status, setStatus] = useState<BackendStatus>({ state: "checking" });

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as { status: string; env: string };
        setStatus({ state: "ok", env: body.env });
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setStatus({ state: "down" });
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="flex h-[100dvh] flex-col items-center justify-center gap-4 p-4 text-center">
      <h1 className="text-2xl font-semibold">Language Learner</h1>
      <p className="text-slate-500 dark:text-slate-400">pt-BR ⇄ pl-PL</p>
      <p className="rounded-full border border-slate-300 px-4 py-2 text-sm dark:border-slate-700">
        {status.state === "checking" && "Verificando backend…"}
        {status.state === "ok" && `Backend OK (${status.env})`}
        {status.state === "down" && `Backend inacessível em ${API_URL}`}
      </p>
    </main>
  );
}
