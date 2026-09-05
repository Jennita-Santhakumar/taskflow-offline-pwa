const API_BASE_URL: string = (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:8060";
export const WS_BASE_URL: string = (import.meta as any).env?.VITE_WS_BASE_URL || "ws://localhost:8060";

let accessToken: string | null = null;
let refreshToken: string | null = null;

export function setTokens(access: string | null, refresh: string | null) {
  accessToken = access;
  refreshToken = refresh;
  if (access) localStorage.setItem("access_token", access);
  else localStorage.removeItem("access_token");
  if (refresh) localStorage.setItem("refresh_token", refresh);
  else localStorage.removeItem("refresh_token");
}

export function loadTokens() {
  accessToken = localStorage.getItem("access_token");
  refreshToken = localStorage.getItem("refresh_token");
  return { accessToken, refreshToken };
}

export function getAccessToken() {
  return accessToken;
}

async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const resp = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (resp.status === 401 && retry && refreshToken) {
    const refreshed = await tryRefresh();
    if (refreshed) return request<T>(path, options, false);
  }

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${body}`);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

async function tryRefresh(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!resp.ok) return false;
    const body = await resp.json();
    setTokens(body.access_token, body.refresh_token);
    return true;
  } catch {
    return false;
  }
}

export const api = {
  register: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: string; email: string }>("/auth/me"),
  syncPush: (deviceId: string, items: unknown[]) =>
    request<{ results: any[]; sync_version: number }>("/sync/push", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId, items }),
    }),
  syncPull: (deviceId: string, since: number) =>
    request<{ tasks: any[]; sync_version: number; has_more: boolean }>(
      `/sync/pull?device_id=${encodeURIComponent(deviceId)}&since=${since}`
    ),
  nextTasks: () => request<{ items: any[]; model_version: string; cached: boolean }>("/recommendations/next-tasks"),
};

export { API_BASE_URL };
