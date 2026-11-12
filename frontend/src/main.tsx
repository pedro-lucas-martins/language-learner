import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import "./index.css";
import { applyTheme, loadTheme } from "./theme.ts";

applyTheme(loadTheme()); // before the first paint, so there is no flash of the wrong theme

const root = document.getElementById("root");
if (!root) {
  throw new Error("Root element #root not found");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
