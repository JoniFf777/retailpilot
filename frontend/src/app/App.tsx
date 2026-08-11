import { Link, NavLink, Outlet } from "react-router-dom";

type IconName = "chat" | "privacy" | "runs" | "status" | "orders";

const NAV_ITEMS: Array<{ to: string; label: string; caption: string; icon: IconName; end?: boolean }> = [
  { to: "/", label: "决策工作台", caption: "Shopping desk", icon: "chat", end: true },
  { to: "/privacy", label: "隐私中心", caption: "Owner data", icon: "privacy" },
  { to: "/runs", label: "运行记录", caption: "Run inspector", icon: "runs" },
  { to: "/status", label: "服务状态", caption: "System health", icon: "status" },
];

const NAV_ITEMS_WITH_ORDERS = [...NAV_ITEMS, { to: "/orders", label: "Orders", caption: "Order history", icon: "orders" as const }];

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, string> = {
    chat: "M4 5.75A2.75 2.75 0 0 1 6.75 3h10.5A2.75 2.75 0 0 1 20 5.75v6.5A2.75 2.75 0 0 1 17.25 15H11l-4.75 4v-4h-.5A2.75 2.75 0 0 1 3 12.25v-6.5h1Zm4.5 3.5h5m-5 3h7",
    privacy: "M12 3.25 19 6v5.25c0 4.4-2.8 7.78-7 9.5-4.2-1.72-7-5.1-7-9.5V6l7-2.75Zm-2.75 8.5 1.8 1.8 3.9-4",
    runs: "M5 4.25h14A1.75 1.75 0 0 1 20.75 6v12A1.75 1.75 0 0 1 19 19.75H5A1.75 1.75 0 0 1 3.25 18V6A1.75 1.75 0 0 1 5 4.25Zm2.25 4h9.5M7.25 12h5.5m-5.5 3h7.5",
    status: "M12 3.5a8.5 8.5 0 1 0 8.5 8.5A8.5 8.5 0 0 0 12 3.5Zm0 4v5l3.25 2",
    orders: "M5 4.25h14A1.75 1.75 0 0 1 20.75 6v12A1.75 1.75 0 0 1 19 19.75H5A1.75 1.75 0 0 1 3.25 18V6A1.75 1.75 0 0 1 5 4.25Zm3.25 4h7.5M8.25 12h7.5m-7.5 3h5",
  };

  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 24 24">
      <path d={paths[name]} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

export function App() {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="sidebar-content">
          <Link className="brand" to="/">
            <span aria-hidden="true" className="brand-mark"><span /></span>
            <span className="brand-copy"><strong>ShopMind</strong><small>Decision workspace</small></span>
          </Link>

          <div className="sidebar-section-label">工作台</div>
          <nav aria-label="主导航" className="sidebar-nav">
            {NAV_ITEMS_WITH_ORDERS.map((item) => (
              <NavLink
                className={({ isActive }) => `nav-item ${isActive ? "nav-item-active" : ""}`}
                end={item.end}
                key={item.to}
                to={item.to}
              >
                <span className="nav-icon-wrap"><Icon name={item.icon} /></span>
                <span className="nav-copy"><strong>{item.label}</strong><small>{item.caption}</small></span>
                <span aria-hidden="true" className="nav-active-indicator" />
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="sidebar-footer">
          <div className="system-indicator"><span className="system-pulse" /><span><strong>系统可用</strong><small>开发环境 · V6</small></span></div>
          <span className="version-tag">0.1</span>
        </div>
      </aside>

      <div className="app-main">
        <div className="mobile-context-bar"><span>ShopMind / Decision workspace</span><span className="topbar-status"><span className="system-pulse" />在线</span></div>
        <main className="page-frame"><Outlet /></main>
      </div>
    </div>
  );
}
