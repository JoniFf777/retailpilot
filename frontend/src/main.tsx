import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { router } from "./app/router";
import { AppProviders } from "./app/providers";
import "./styles/theme.css";

async function bootstrap() {
  if (import.meta.env.VITE_SHOPMIND_DEMO === "true") {
    const { installDemoTransport } = await import("./demo");
    installDemoTransport();
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>
    </StrictMode>,
  );
}

void bootstrap();
