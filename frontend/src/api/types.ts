export type Health = {
  status: string;
  database: string;
  redis: string;
  villages: number;
};

export type Summary = {
  summary: Record<string, number | string>;
  plans: Array<{ plan: string; clients: number }>;
};

export type Analytics = {
  top_states: Array<{ state: string; villages: number }>;
  requests_30d: Array<{ day: string; requests: number }>;
  plans: Array<{ plan: string; users: number }>;
  endpoints: Array<{ endpoint: string; requests: number }>;
  hourly: Array<{ hour: number; requests: number }>;
  response_times: Array<{ day: string; avg_ms: number; max_ms: number }>;
};

export type Client = {
  id: number;
  name: string;
  email: string;
  business_name?: string;
  plan: string;
  status: string;
  is_active: boolean;
  created_at: string;
  api_keys: number;
  total_requests: number;
  avg_latency_ms: number;
};

export type PortalMe = {
  client: Client;
  plan_limits: { daily: number; burst: number };
  usage: { requests_24h: number; avg_latency_ms: number };
};

export type ApiKey = {
  id: number;
  name: string;
  key_prefix: string;
  is_active: boolean;
  created_at: string;
  last_used_at?: string | null;
  expires_at?: string | null;
};

export type PortalUsage = {
  daily: Array<{ day: string; requests: number; avg_latency_ms: number }>;
  endpoints: Array<{ endpoint: string; requests: number; avg_latency_ms: number }>;
};
