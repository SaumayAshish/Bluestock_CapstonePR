import type { Analytics, ApiKey, Client, Health, PortalMe, PortalUsage, Summary } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

type RequestOptions = RequestInit & {
  token?: string;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "object" && payload && "detail" in payload ? String(payload.detail) : String(payload);
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return payload as T;
}

export const api = {
  health: () => request<Health>("/health"),
  adminLogin: (email: string, password: string) =>
    request<{ token: string }>("/admin/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    }),
  adminSummary: (token: string) => request<Summary>("/admin/summary", { token }),
  adminAnalytics: (token: string) => request<Analytics>("/admin/analytics", { token }),
  adminClients: (token: string) => request<Client[]>("/admin/clients", { token }),
  approveClient: (token: string, id: number) => request<{ approved: boolean }>(`/admin/clients/${id}/approve`, { method: "POST", token }),
  suspendClient: (token: string, id: number) => request<{ suspended: boolean }>(`/admin/clients/${id}/suspend`, { method: "POST", token }),
  updateClient: (token: string, id: number, body: Partial<Pick<Client, "plan" | "status" | "is_active">>) =>
    request<{ updated: boolean }>(`/admin/clients/${id}`, { method: "PATCH", token, body: JSON.stringify(body) }),
  portalLogin: (email: string, password: string) =>
    request<{ token: string }>("/auth/client-login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    }),
  register: (body: { name: string; email: string; password: string; business_name?: string; plan: string; gst_number?: string; phone?: string }) =>
    request<{ token: string; status: string; client_id: number }>("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  portalMe: (token: string) => request<PortalMe>("/portal/me", { token }),
  portalKeys: (token: string) => request<ApiKey[]>("/portal/api-keys", { token }),
  createPortalKey: (token: string, name: string) =>
    request<{ api_key: string; api_secret: string }>("/portal/api-keys", { method: "POST", token, body: JSON.stringify({ name }) }),
  rotatePortalKey: (token: string, id: number) =>
    request<{ api_secret: string }>(`/portal/api-keys/${id}/rotate-secret`, { method: "POST", token }),
  revokePortalKey: (token: string, id: number) => request<{ revoked: boolean }>(`/portal/api-keys/${id}`, { method: "DELETE", token }),
  portalUsage: (token: string) => request<PortalUsage>("/portal/usage", { token })
};
