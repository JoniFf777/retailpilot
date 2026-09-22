import { Link, NavLink, Outlet } from "react-router-dom";
import { cn } from "../components/cn";
import { useSystemReadiness } from "../features/status/useSystemReadiness";

type IconName = "chat" | "catalog" | "privacy" | "runs" | "status" | "orders" | "tasks";

const NAV_ITEMS: Array<{
  to: string;
  label: string;
  caption: string;
  icon: IconName;
  end?: boolean;
}> = [
  { to: "/", label: "决策工作台", caption: "Shopping desk", icon: "chat", end: true },
  { to: "/tasks", label: "任务工作台", caption: "Durable tasks", icon: "tasks" },
  { to: "/catalog", label: "浏览商品", caption: "Catalog browse", icon: "catalog" },
  { to: "/privacy", label: "隐私中心", caption: "Owner data", icon: "privacy" },
  { to: "/runs", label: "运行记录", caption: "Run inspector", icon: "runs" },
  { to: "/status", label: "服务状态", caption: "System health", icon: "status" },
];

const NAV_ITEMS_WITH_ORDERS = [
  ...NAV_ITEMS,
  { to: "/orders", label: "Orders", caption: "Order history", icon: "orders" as const },
];

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, string> = {
    chat: "M4 5.75A2.75 2.75 0 0 1 6.75 3h10.5A2.75 2.75 0 0 1 20 5.75v6.5A2.75 2.75 0 0 1 17.25 15H11l-4.75 4v-4h-.5A2.75 2.75 0 0 1 3 12.25v-6.5h1Zm4.5 3.5h5m-5 3h7",
    catalog:
      "M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5v-13Zm0 4h16M8 7.5h.01M11 7.5h.01",
    privacy:
      "M12 3.25 19 6v5.25c0 4.4-2.8 7.78-7 9.5-4.2-1.72-7-5.1-7-9.5V6l7-2.75Zm-2.75 8.5 1.8 1.8 3.9-4",
    runs: "M5 4.25h14A1.75 1.75 0 0 1 20.75 6v12A1.75 1.75 0 0 1 19 19.75H5A1.75 1.75 0 0 1 3.25 18V6A1.75 1.75 0 0 1 5 4.25Zm2.25 4h9.5M7.25 12h5.5m-5.5 3h7.5",
    status: "M12 3.5a8.5 8.5 0 1 0 8.5 8.5A8.5 8.5 0 0 0 12 3.5Zm0 4v5l3.25 2",
    orders:
      "M5 4.25h14A1.75 1.75 0 0 1 20.75 6v12A1.75 1.75 0 0 1 19 19.75H5A1.75 1.75 0 0 1 3.25 18V6A1.75 1.75 0 0 1 5 4.25Zm3.25 4h7.5M8.25 12h7.5m-7.5 3h5",
    tasks:
      "M6 4.5h12A1.5 1.5 0 0 1 19.5 6v12a1.5 1.5 0 0 1-1.5 1.5H6A1.5 1.5 0 0 1 4.5 18V6A1.5 1.5 0 0 1 6 4.5Zm2.5 4h7m-7 3.5h7m-7 3.5h4",
  };

  return (
    <svg aria-hidden="true" className="h-[1.15rem] w-[1.15rem]" fill="none" viewBox="0 0 24 24">
      <path
        d={paths[name]}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}

/**
 * Maps the shared readiness query (see `useSystemReadiness`) to what the shell's two
 * status lights show. Both call sites render from this one place so they can never
 * drift apart. "ready"/"blocked" are the only two values the backend returns
 * (`app/operations/readiness.py`); pending/error get a neutral "unknown" reading rather
 * than guessing.
 */
function systemStatusTone(readiness: ReturnType<typeof useSystemReadiness>): {
  label: string;
  dotClassName: string;
} {
  if (readiness.isPending) return { label: "检查中…", dotClassName: "bg-text-subtle" };
  if (!readiness.isError && readiness.data?.status === "ready") {
    return { label: "系统可用", dotClassName: "bg-success" };
  }
  if (!readiness.isError && readiness.data?.status === "blocked") {
    return { label: "存在阻塞", dotClassName: "bg-danger" };
  }
  return { label: "状态未知", dotClassName: "bg-warning" };
}

function StatusDot({ tone, className }: { tone: string; className?: string }) {
  return (
    <span
      className={cn("inline-block flex-none rounded-full ring-2 ring-surface", tone, className)}
    />
  );
}

export function App() {
  const readiness = useSystemReadiness();
  const status = systemStatusTone(readiness);

  return (
    <div className="grid min-h-screen lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="sticky top-0 z-10 flex flex-col justify-between self-start border-0 border-b border-solid border-border bg-surface/90 px-4 py-3 lg:min-h-screen lg:border-r lg:border-b-0 lg:px-4 lg:py-6">
        <div className="grid gap-4 lg:gap-7">
          <Link className="inline-flex items-center gap-3 rounded-md px-1 py-1 lg:px-2" to="/">
            <span
              aria-hidden="true"
              className="relative inline-flex h-10 w-10 flex-none -rotate-6 items-center justify-center rounded-xl bg-brand shadow-[0_8px_18px_rgb(8_127_104_/_20%)]"
            >
              <span className="absolute h-5 w-5 rounded-full border-[1.5px] border-solid border-white/80" />
              <span className="absolute h-2.5 w-2.5 rounded-full border-[1.5px] border-solid border-white/80" />
              <span className="h-1 w-1 rounded-full bg-white" />
            </span>
            <span className="hidden flex-col gap-0.5 lg:flex">
              <strong className="text-[1.05rem] tracking-tight text-text-primary">
                RetailPilot
              </strong>
              <small className="text-[0.68rem] tracking-wide text-text-subtle">
                Decision workspace
              </small>
            </span>
          </Link>

          <div className="hidden px-2 text-[0.68rem] font-extrabold tracking-[0.14em] text-text-subtle uppercase lg:block">
            工作台
          </div>
          <nav
            aria-label="主导航"
            className="flex [scrollbar-width:none] gap-1.5 overflow-x-auto pb-1 [-ms-overflow-style:none] lg:grid lg:overflow-visible lg:pb-0 [&::-webkit-scrollbar]:hidden"
          >
            {NAV_ITEMS_WITH_ORDERS.map((item) => (
              <NavLink
                className={({ isActive }) =>
                  cn(
                    "flex min-h-11 flex-none items-center gap-3 rounded-md border border-solid border-transparent px-2.5 py-1.5 text-text-muted transition-colors duration-200 ease-standard hover:bg-surface-soft hover:text-brand-strong lg:min-h-[3.35rem] lg:flex-auto lg:px-3",
                    isActive &&
                      "border-[#c9e9dd] bg-brand-soft text-brand-strong hover:bg-brand-soft",
                  )
                }
                end={item.end}
                key={item.to}
                to={item.to}
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={cn(
                        "inline-flex h-8 w-8 flex-none items-center justify-center rounded-lg border border-solid border-brand/10 bg-white/70",
                        isActive && "border-transparent bg-brand text-white",
                      )}
                    >
                      <Icon name={item.icon} />
                    </span>
                    <span className="hidden min-w-0 flex-col gap-0.5 lg:grid">
                      <strong className="text-[0.86rem] font-bold">{item.label}</strong>
                      <small
                        className={cn(
                          "hidden text-[0.65rem] text-text-subtle xl:block",
                          isActive && "text-brand",
                        )}
                      >
                        {item.caption}
                      </small>
                    </span>
                    <span
                      aria-hidden="true"
                      className={cn(
                        "ml-auto hidden h-1.5 w-1.5 flex-none rounded-full bg-brand lg:block",
                        isActive ? "opacity-100" : "opacity-0",
                      )}
                    />
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="hidden items-center justify-between border-0 border-t border-solid border-border pt-5 lg:flex">
          <div className="flex items-center gap-2">
            <StatusDot className="h-3 w-3" tone={status.dotClassName} />
            <span className="grid gap-0.5">
              <strong className="text-[0.73rem] text-text-primary">{status.label}</strong>
              <small className="text-[0.65rem] text-text-subtle">开发环境 · V6</small>
            </span>
          </div>
          <span className="rounded-full bg-surface-soft px-2 py-1 text-[0.65rem] text-text-muted">
            0.1
          </span>
        </div>
      </aside>

      <div className="min-w-0">
        <div className="flex items-center justify-between px-5 pt-4 text-[0.7rem] tracking-wide text-text-subtle sm:px-8 lg:hidden">
          <span>RetailPilot / Decision workspace</span>
          <span className="inline-flex items-center gap-1.5">
            <StatusDot className="h-2 w-2" tone={status.dotClassName} />
            {status.label}
          </span>
        </div>
        <main className="mx-auto max-w-[1300px] px-5 pt-8 pb-20 sm:px-8 sm:pt-10 lg:pt-16">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
