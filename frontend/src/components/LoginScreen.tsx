import { useEffect, useState, type FormEvent } from "react";

import { API_URL } from "../config.ts";

import { t } from "../i18n.ts";
import type { Lang } from "../protocol.ts";

interface Props {
  lang: Lang;
  error: string | null;
  onSubmit: (token: string) => void;
}

export function LoginScreen({ lang, error, onSubmit }: Props) {
  const [token, setToken] = useState("");

  // Wake the (free, sleeping) server while the learner types the token.
  useEffect(() => {
    fetch(`${API_URL}/health`).catch(() => undefined);
  }, []);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const value = token.trim();
    if (value) onSubmit(value);
  }

  return (
    <main className="flex h-[100dvh] items-center justify-center p-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">{t(lang, "appTitle")}</h1>
          <p className="muted text-sm">Português ⇄ Polski</p>
        </div>
        <label className="block space-y-1">
          <span className="text-sm font-medium">{t(lang, "loginTokenLabel")}</span>
          <input
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="field"
          />
          <span className="muted block text-xs">
            {t(lang, "loginTokenHelp")}
          </span>
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={!token.trim()}
          className="btn-primary w-full"
        >
          {t(lang, "loginButton")}
        </button>
      </form>
    </main>
  );
}
