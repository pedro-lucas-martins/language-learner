import { useCallback, useState } from "react";

import { ChatScreen } from "./components/ChatScreen.tsx";
import { LoginScreen } from "./components/LoginScreen.tsx";
import { detectLang, t } from "./i18n.ts";
import { clearToken, loadToken, saveToken } from "./storage.ts";

const browserLang = detectLang(navigator.languages ?? [navigator.language]);

export default function App() {
  const [token, setToken] = useState<string | null>(() => loadToken());
  const [loginError, setLoginError] = useState<string | null>(null);

  const login = useCallback((value: string) => {
    // Saved right away; cleared again if the server rejects it.
    saveToken(value);
    setLoginError(null);
    setToken(value);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setToken(null);
  }, []);

  const onAuthFailed = useCallback((reason: "unauthorized" | "origin") => {
    clearToken();
    setToken(null);
    setLoginError(t(browserLang, reason === "origin" ? "loginOrigin" : "loginInvalid"));
  }, []);

  if (!token) {
    return <LoginScreen lang={browserLang} error={loginError} onSubmit={login} />;
  }
  return (
    <ChatScreen
      key={token}
      token={token}
      fallbackLang={browserLang}
      onAuthFailed={onAuthFailed}
      onLogout={logout}
    />
  );
}
