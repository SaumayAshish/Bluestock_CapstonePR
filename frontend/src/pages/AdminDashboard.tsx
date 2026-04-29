import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, RefreshCw, ShieldAlert, SlidersHorizontal } from "lucide-react";
import { FormEvent, useState } from "react";
import { EndpointBar, PlansPie, RequestsArea, ResponseTimeLine, StateBar } from "../components/Charts";
import { StatusPill } from "../components/StatusPill";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

export function AdminDashboard() {
  const { adminToken, setToken } = useAuthStore();
  const [error, setError] = useState("");
  const summary = useQuery({ queryKey: ["admin-summary"], queryFn: () => api.adminSummary(adminToken), enabled: !!adminToken });
  const analytics = useQuery({ queryKey: ["admin-analytics"], queryFn: () => api.adminAnalytics(adminToken), enabled: !!adminToken });
  const clients = useQuery({ queryKey: ["admin-clients"], queryFn: () => api.adminClients(adminToken), enabled: !!adminToken });
  const queryClient = useQueryClient();

  const action = useMutation({
    mutationFn: ({ id, type }: { id: number; type: "approve" | "suspend" }) =>
      type === "approve"
        ? api.approveClient(adminToken, id).then(() => ({ ok: true }))
        : api.suspendClient(adminToken, id).then(() => ({ ok: true })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-clients"] })
  });

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await api.adminLogin(String(form.get("email")), String(form.get("password")));
      setToken("admin", result.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Admin login failed");
    }
  }

  if (!adminToken) {
    return (
      <section className="auth-panel">
        <div>
          <p className="eyebrow">Complete implementation</p>
          <h1>Admin Dashboard</h1>
          <p className="lede">Operational console for client approvals, plan controls, usage analytics, and platform health.</p>
        </div>
        <form className="login-card" onSubmit={login}>
          <label>Email<input name="email" defaultValue="admin@bluestock.local" /></label>
          <label>Password<input name="password" type="password" /></label>
          {error && <p className="form-error">{error}</p>}
          <button type="submit">Sign in</button>
        </form>
      </section>
    );
  }

  return (
    <div className="stack">
      <header className="page-header">
        <div>
          <p className="eyebrow">Complete implementation</p>
          <h1>Admin Dashboard</h1>
        </div>
        <button onClick={() => void Promise.all([summary.refetch(), analytics.refetch(), clients.refetch()])}>
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      <section className="metric-grid">
        {Object.entries(summary.data?.summary || {}).map(([key, value]) => (
          <div className="metric" key={key}>
            <span>{key.replaceAll("_", " ")}</span>
            <strong>{Number(value).toLocaleString()}</strong>
          </div>
        ))}
      </section>

      <section className="chart-grid">
        <article className="panel wide"><h2>Requests Over Time</h2><RequestsArea data={analytics.data?.requests_30d || []} /></article>
        <article className="panel"><h2>Users By Plan</h2><PlansPie data={analytics.data?.plans || []} /></article>
        <article className="panel wide"><h2>Top States By Village Count</h2><StateBar data={analytics.data?.top_states || []} /></article>
        <article className="panel"><h2>Endpoint Usage</h2><EndpointBar data={analytics.data?.endpoints || []} /></article>
        <article className="panel wide"><h2>Response-Time Trends</h2><ResponseTimeLine data={analytics.data?.response_times || []} /></article>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><h2>Client Management</h2><p>Approval, suspension, and plan visibility are wired to FastAPI endpoints.</p></div>
          <SlidersHorizontal size={18} />
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Client</th><th>Plan</th><th>Status</th><th>Keys</th><th>Requests</th><th>Latency</th><th>Actions</th></tr></thead>
            <tbody>
              {(clients.data || []).map((client) => (
                <tr key={client.id}>
                  <td><strong>{client.name}</strong><span>{client.email}</span></td>
                  <td>{client.plan}</td>
                  <td><StatusPill value={client.status} /></td>
                  <td>{client.api_keys}</td>
                  <td>{Number(client.total_requests).toLocaleString()}</td>
                  <td>{client.avg_latency_ms} ms</td>
                  <td className="actions">
                    <button className="icon-button" title="Approve client" onClick={() => action.mutate({ id: client.id, type: "approve" })}><CheckCircle size={16} /></button>
                    <button className="icon-button danger" title="Suspend client" onClick={() => action.mutate({ id: client.id, type: "suspend" })}><ShieldAlert size={16} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
