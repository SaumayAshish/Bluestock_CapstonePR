import { Activity, BarChart3, Database, KeyRound, LayoutDashboard, LogOut, ShieldCheck, UserRound } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { AdminDashboard } from "./pages/AdminDashboard";
import { Portal } from "./pages/Portal";
import { api } from "./api/client";
import { useAuthStore } from "./store/auth";
import { useState } from "react";

type View = "admin" | "portal";

export function App() {
  const [view, setView] = useState<View>("admin");
  const { adminToken, portalToken, logout } = useAuthStore();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const activeToken = view === "admin" ? adminToken : portalToken;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Database size={22} />
          <span>BlueStock</span>
        </div>
        <button className={view === "admin" ? "nav active" : "nav"} onClick={() => setView("admin")}>
          <LayoutDashboard size={18} /> Admin Dashboard
        </button>
        <button className={view === "portal" ? "nav active" : "nav"} onClick={() => setView("portal")}>
          <UserRound size={18} /> B2B Portal
        </button>
        <div className="sidebar-status">
          <span className="caption">Integration Status</span>
          <span className="health-line">
            <Activity size={16} /> API {health.data?.status || "checking"}
          </span>
          <span className="health-line">
            <ShieldCheck size={16} /> Redis {health.data?.redis || "unknown"}
          </span>
          <span className="health-line">
            <BarChart3 size={16} /> Recharts complete
          </span>
          <span className="health-line">
            <KeyRound size={16} /> API keys complete
          </span>
        </div>
        {activeToken && (
          <button className="nav" onClick={() => logout(view)}>
            <LogOut size={18} /> Logout
          </button>
        )}
      </aside>
      <main className="content">{view === "admin" ? <AdminDashboard /> : <Portal />}</main>
    </div>
  );
}
