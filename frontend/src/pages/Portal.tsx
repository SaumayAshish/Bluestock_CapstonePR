import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, KeyRound, LogOut, RefreshCw, RotateCw, Trash2 } from "lucide-react";
import { FormEvent, useState } from "react";
import { EndpointBar, RequestsArea } from "../components/Charts";
import { StatusPill } from "../components/StatusPill";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

function formValue(form: FormData, name: string) {
  return String(form.get(name) || "").trim();
}

function optionalFormValue(form: FormData, name: string) {
  const value = formValue(form, name);
  return value || undefined;
}

export function Portal() {
  const { portalToken, setToken, logout } = useAuthStore();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [credential, setCredential] = useState<{ api_key?: string; api_secret?: string } | null>(null);
  const me = useQuery({ queryKey: ["portal-me"], queryFn: () => api.portalMe(portalToken), enabled: !!portalToken });
  const keys = useQuery({ queryKey: ["portal-keys"], queryFn: () => api.portalKeys(portalToken), enabled: !!portalToken });
  const usage = useQuery({ queryKey: ["portal-usage"], queryFn: () => api.portalUsage(portalToken), enabled: !!portalToken });
  const queryClient = useQueryClient();

  const createKey = useMutation({
    mutationFn: (name: string) => api.createPortalKey(portalToken, name),
    onSuccess: (data) => {
      setCredential(data);
      setNotice("API key created. Copy the secret now; it will not be shown again.");
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["portal-me"] }),
        queryClient.invalidateQueries({ queryKey: ["portal-keys"] }),
        queryClient.invalidateQueries({ queryKey: ["portal-usage"] })
      ]);
    }
  });
  const rotateKey = useMutation({
    mutationFn: (id: number) => api.rotatePortalKey(portalToken, id),
    onSuccess: (data) => {
      setCredential({ api_secret: data.api_secret });
      setNotice("Secret rotated successfully. Existing clients must switch to the new secret.");
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["portal-me"] }),
        queryClient.invalidateQueries({ queryKey: ["portal-usage"] })
      ]);
    }
  });
  const revokeKey = useMutation({
    mutationFn: (id: number) => api.revokePortalKey(portalToken, id),
    onSuccess: () => {
      setCredential(null);
      setNotice("API key revoked. It is disabled immediately.");
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["portal-me"] }),
        queryClient.invalidateQueries({ queryKey: ["portal-keys"] }),
        queryClient.invalidateQueries({ queryKey: ["portal-usage"] })
      ]);
    }
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    const form = new FormData(event.currentTarget);
    try {
      const email = formValue(form, "email");
      const password = formValue(form, "password");
      const result =
        mode === "login"
          ? await api.portalLogin(email, password)
          : await api.register({
              name: formValue(form, "name"),
              business_name: optionalFormValue(form, "business"),
              email,
              password,
              plan: formValue(form, "plan"),
              gst_number: optionalFormValue(form, "gst"),
              phone: optionalFormValue(form, "phone")
            });
      setToken("portal", result.token);
      if (mode === "register") {
        setNotice("Registration received. Demo accounts are approved by the admin before key creation.");
      }
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
          <div className="demo-note">
            <strong>Demo login</strong>
            <span>demo@bluestock.local</span>
            <span>Demo12345</span>
          </div>
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
          {notice && <p className="form-success"><CheckCircle2 size={16} /> {notice}</p>}
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
          <p className="lede">Approved demo buyer account with live API key controls and usage analytics.</p>
        </div>
        <div className="header-actions">
          <button onClick={() => void Promise.all([me.refetch(), keys.refetch(), usage.refetch()])}><RefreshCw size={16} /> Refresh</button>
          <button className="secondary" onClick={() => logout("portal")}><LogOut size={16} /> Sign out</button>
        </div>
      </header>

      {me.data?.client.status === "pending_approval" && (
        <section className="approval-banner">
          <strong>Approval pending</strong>
          <span>Your registration is saved. An administrator must approve the account before API keys can be created.</span>
        </section>
      )}

      <section className="metric-grid">
        <div className="metric"><span>Account</span><strong>{me.data?.client.name || "-"}</strong></div>
        <div className="metric"><span>Status</span><strong><StatusPill value={me.data?.client.status || "unknown"} /></strong></div>
        <div className="metric"><span>Daily Limit</span><strong>{Number(me.data?.plan_limits.daily || 0).toLocaleString()}</strong></div>
        <div className="metric"><span>24h Requests</span><strong>{Number(me.data?.usage.requests_24h || 0).toLocaleString()}</strong></div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><h2>API Key Management</h2><p>Create, rotate, and revoke credentials against the existing portal API.</p></div>
          <button disabled={createKey.isPending || me.data?.client.status !== "active"} onClick={() => createKey.mutate("Dashboard demo key")}>
            <KeyRound size={16} /> {createKey.isPending ? "Creating..." : "Create key"}
          </button>
        </div>
        {notice && <p className="form-success"><CheckCircle2 size={16} /> {notice}</p>}
        {credential && (
          <div className="secret-box">
            {credential.api_key && <code>X-API-Key: {credential.api_key}</code>}
            {credential.api_secret && <code>X-API-Secret: {credential.api_secret}</code>}
            <button className="icon-button" title="Copy credentials" onClick={() => navigator.clipboard.writeText(Object.values(credential).filter(Boolean).join("\n"))}><Copy size={16} /></button>
          </div>
        )}
        {createKey.error && <p className="form-error">Key creation is available after account approval. Use the seeded demo login for the live workflow.</p>}
        {rotateKey.error && <p className="form-error">Unable to rotate this key. Refresh the portal and try again.</p>}
        {revokeKey.error && <p className="form-error">Unable to revoke this key. Refresh the portal and try again.</p>}
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
