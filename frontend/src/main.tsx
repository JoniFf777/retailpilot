import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { router } from "./app/router";
import { AppProviders } from "./app/providers";
import "./styles/cart.css";
import "./styles/checkout.css";
import "./styles/orders.css";
import "./styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><AppProviders><RouterProvider router={router} /></AppProviders></StrictMode>,
);
