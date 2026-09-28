import { createBrowserRouter, createHashRouter } from "react-router-dom";
import { ChatPage } from "../features/chat/ChatPage";
import { PrivacyPage } from "../features/privacy/PrivacyPage";
import { RunsPage } from "../features/runs/RunsPage";
import { StatusPage } from "../features/status/StatusPage";
import { CheckoutPage } from "../features/checkout/CheckoutPage";
import { OrderDetailPage } from "../features/orders/OrderDetailPage";
import { OrdersPage } from "../features/orders/OrdersPage";
import { App } from "./App";
import {
  CatalogCategoryPage,
  CatalogHomePage,
  CatalogProductDetailPage,
} from "../features/catalog/CatalogPages";
import { AdminAiPage } from "../features/admin-ai/AdminAiPage";
import { TasksPage } from "../features/tasks/TasksPage";
import { TaskDetailPage } from "../features/tasks/TaskDetailPage";

/**
 * `createBrowserRouter` deep-links 404 on a static host with no server-side rewrite rule
 * (GitHub Pages, a plain S3 bucket, ...) — the server sees a request for e.g. `/tasks/123`
 * and has no `index.html` to fall back to. `createHashRouter` sidesteps this entirely:
 * every route lives after a `#` (`/#/tasks/123`), which the server never sees, so it
 * always serves `index.html` for the one real path (`/`). Demo builds (the ones actually
 * meant for static hosting) use it; a real backend deployment is expected to have proper
 * server-side routing and keeps the cleaner `createBrowserRouter` URLs.
 */
const buildRouter =
  import.meta.env.VITE_SHOPMIND_DEMO === "true" ? createHashRouter : createBrowserRouter;

export const router = buildRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <ChatPage /> },
      { path: "tasks", element: <TasksPage /> },
      { path: "tasks/:taskId", element: <TaskDetailPage /> },
      { path: "catalog", element: <CatalogHomePage /> },
      { path: "catalog/:category", element: <CatalogCategoryPage /> },
      { path: "catalog/:category/:product", element: <CatalogProductDetailPage /> },
      { path: "privacy", element: <PrivacyPage /> },
      { path: "runs", element: <RunsPage /> },
      { path: "status", element: <StatusPage /> },
      { path: "checkout", element: <CheckoutPage /> },
      { path: "orders", element: <OrdersPage /> },
      { path: "orders/:orderId", element: <OrderDetailPage /> },
      { path: "admin/ai", element: <AdminAiPage /> },
    ],
  },
]);
