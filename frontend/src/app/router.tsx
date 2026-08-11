import { createBrowserRouter } from "react-router-dom";
import { ChatPage } from "../features/chat/ChatPage";
import { PrivacyPage } from "../features/privacy/PrivacyPage";
import { RunsPage } from "../features/runs/RunsPage";
import { StatusPage } from "../features/status/StatusPage";
import { CheckoutPage } from "../features/checkout/CheckoutPage";
import { OrderDetailPage } from "../features/orders/OrderDetailPage";
import { OrdersPage } from "../features/orders/OrdersPage";
import { App } from "./App";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <ChatPage /> },
      { path: "privacy", element: <PrivacyPage /> },
      { path: "runs", element: <RunsPage /> },
      { path: "status", element: <StatusPage /> },
      { path: "checkout", element: <CheckoutPage /> },
      { path: "orders", element: <OrdersPage /> },
      { path: "orders/:orderId", element: <OrderDetailPage /> },
    ],
  },
]);
