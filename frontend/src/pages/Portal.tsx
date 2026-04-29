import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, RefreshCw, RotateCw, Trash2 } from "lucide-react";
import { FormEvent, useState } from "react";
import { EndpointBar, RequestsArea } from "../components/Charts";
import { StatusPill } from "../components/StatusPill";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

export function Portal() {
  const { portalToken, setToken } = useAuthStore();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [credential, setCredential] = useState<{ api_key?: string; api_secret?: string } | null>(null);
  const me = useQuery({ queryKey: ["portal-me"], queryFn: () => api.portalMe(portalToken), enabled: !!portalToken });
  const keys = useQuery({ queryKey: ["portal-keys"], queryFn: () => api.portalKeys(portalToken), enabled: !!portalToken });
  const usage = useQuery({ queryKey: ["portal-usage"], queryFn: () => api.portalUsage(portalToken), enabled: !!portalToken });
  const queryClient = useQueryClient();

  const createKey = useMutation({
    mutationFn: (name: string) => api.createPortalKey(portalToken, name),
    onSuccess: (data) => {
      setCredential(data);
      void queryClient.invalidateQueries({ queryKey: ["portal-keys"] });
    }
  });
  const rotateKey = useMutation({
    mutationFn: (id: number) => api.rotatePortalKey(portalToken, id),
    onSuccess: (data) => setCredential({ api_secret: data.api_secret })
  });
  const revokeKey = useMutation({
    mutationFn: (id: number) => api.revokePortalKey(portalToken, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portal-keys"] })
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const email = String(form.get("email"));
      const password = String(form.get("password"));
      const result =
        mode === "login"
          ? await api.portalLogin(email, password)
          : await api.register({
              name: String(form.get("name")),
              business_name: String(form.get("business")),
              email,
              password,
              plan: String(form.get("plan")),
              gst_number: String(form.get("gst")),
              phone: String(form.get("phone"))
            });
      setToken("portal", result.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portal request failed");
    }
  }

  if (!portalToken) {
    return (
      <section className="auth-panel">
        <div>
          <p className="eyebrow">Complete implementation</p>
          <h1>B2B User Portal</h1>
          <p className="lede">Business registration, login, API key lifecycle, and client-level usage analytics.</p>
        </div>
        <form className="login-card" onSubmit={submit}>
          <div className="segmented">
            <button type="button" className={mode === "login" ? "selected" : ""} onClick={() => setMode("login")}>Login</button>
            <button type="button" className={mode === "register" ? "selected" : ""} onClick={() => setMode("register")}>Register</button>
          </div>
          {mode === "register" && (
            <>
              <label>Name<input name="name" /></label>
              <label>Business<input name="business" /></label>
              <label>Plan<select name="plan" defaultValue="free"><option>free</option><option>premium</option><option>pro</option><option>unlimited</option></select></label>
              <label>GST Number<input name="gst" /></label>
              <label>Phone<input name="phone" /></label>
            </>
          )}
          <label>Email<input name="email" /></label>
          <label>Password<input name="password" type="password" /></label>
          {error && <p className="form-error">{error}</p>}
          <button type="submit">{mode === "login" ? "Sign in" : "Create account"}</button>
        </form>
      </section>
    );
  }

  return (
    <div className="stack">
      <header className="page-header">
        <div>
          <p className="eyebrow">Complete implementation</p>
          <h1>B2B User Portal</h1>
        </div>
        <button onClick={() => void Promise.all([me.refetch(), keys.refetch(), usage.refetch()])}><RefreshCw size={16} /> Refresh</button>
      </header>

      <section className="metric-grid">
        <div className="metric"><span>Account</span><strong>{me.data?.client.name || "-"}</strong></div>
        <div className="metric"><span>Status</span><strong><StatusPill value={me.data?.client.status || "unknown"} /></strong></div>
        <div className="metric"><span>Daily Limit</span><strong>{Number(me.data?.plan_limits.daily || 0).toLocaleString()}</strong></div>
        <div className="metric"><span>24h Requests</span><strong>{Number(me.data?.usage.requests_24h || 0).toLocaleString()}</strong></div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><h2>API Key Management</h2><p>Create, rotate, and revoke credentials against the existing portal API.</p></div>
          <button onClick={() => createKey.mutate("Dashboard key")}><KeyRound size={16} /> Create key</button>
        </div>
        {credential && (
          <div className="secret-box">
            {credential.api_key && <code>X-API-Key: {credential.api_key}</code>}
            {credential.api_secret && <code>X-API-Secret: {credential.api_secret}</code>}
            <button className="icon-button" title="Copy credentials" onClick={() => navigator.clipboard.writeText(Object.values(credential).filter(Boolean).join("\n"))}><Copy size={16} /></button>
          </div>
        )}
        {createKey.error && <p className="form-error">{createKey.error.message}</p>}
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Prefix</th><th>Status</th><th>Created</th><th>Last Used</th><th>Actions</th></tr></thead>
            <tbody>
              {(keys.data || []).map((key) => (
                <tr key={key.id}>
                  <td>{key.name}</td>
                  <td><code>{key.key_prefix}****</code></td>
                  <td><StatusPill value={key.is_active} /></td>
                  <td>{new Date(key.created_at).toLocaleDateString()}</td>
                  <td>{key.last_used_at ? new Date(key.last_used_at).toLocaleString() : "-"}</td>
                  <td className="actions">
                    <button className="icon-button" title="Rotate secret" onClick={() => rotateKey.mutate(key.id)}><RotateCw size={16} /></button>
                    <button className="icon-button danger" title="Revoke key" onClick={() => revokeKey.mutate(key.id)}><Trash2 size={16} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="chart-grid">
        <article className="panel wide"><h2>Daily Usage</h2><RequestsArea data={(usage.data?.daily || []).slice().reverse()} /></article>
        <article className="panel"><h2>Endpoint Mix</h2><EndpointBar data={usage.data?.endpoints || []} /></article>
      </section>
    </div>
  );
}
