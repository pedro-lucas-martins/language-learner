import { useState, type FormEvent } from "react";

import { t } from "../i18n.ts";
import type { Lang } from "../protocol.ts";

interface Props {
  lang: Lang;
  error: string | null;
  onSubmit: (token: string) => void;
}

export function LoginScreen({ lang, error, onSubmit }: Props) {
  const [token, setToken] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const value = token.trim();
    if (value) onSubmit(value);
  }

  return (
    <main className="flex h-[100dvh] items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-4 rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900"
      >
        <div>
          <h1 className="text-xl font-semibold">{t(lang, "appTitle")}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">pt-BR ⇄ pl-PL</p>
        </div>
        <label className="block space-y-1">
          <span className="text-sm font-medium">{t(lang, "loginTokenLabel")}</span>
          <input
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 outline-none focus:border-sky-500 dark:border-slate-700"
          />
          <span className="block text-xs text-slate-500 dark:text-slate-400">
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
          className="min-h-12 w-full rounded-lg bg-sky-600 px-4 font-medium text-white disabled:opacity-50"
        >
          {t(lang, "loginButton")}
        </button>
      </form>
    </main>
  );
}
