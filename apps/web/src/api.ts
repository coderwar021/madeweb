import { explainApiError } from "./i18n";

export type PlatformUser = {
  id: string;
  email: string;
  name: string;
  admin: boolean;
  role: "user" | "admin" | "root";
  status: "active" | "disabled";
  group: string;
  quota: number;
  usedQuota: number;
};

let platformCsrf = "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function read(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = explainApiError(typeof data.detail === "string" ? data.detail : undefined);
    throw new ApiError(response.status, detail);
  }
  if (data.csrfToken) platformCsrf = data.csrfToken;
  return data;
}

export async function bootSession(): Promise<PlatformUser | null> {
  const me = await fetch("/api/v1/auth/me", { credentials: "include" });
  if (me.ok) {
    const data = await me.json();
    platformCsrf = data.csrfToken;
    return data.user;
  }
  const csrf = await fetch("/api/v1/auth/csrf", { credentials: "include" });
  const data = await csrf.json();
  platformCsrf = data.csrfToken;
  return null;
}

export async function refreshAnonCsrf() {
  const csrf = await fetch("/api/v1/auth/csrf", { credentials: "include" });
  const data = await csrf.json();
  if (typeof data.csrfToken === "string") platformCsrf = data.csrfToken;
}

export async function api(path: string, options: { method?: string; body?: unknown } = {}) {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = platformCsrf;
  const response = await fetch(path, {
    method: options.method || "GET",
    credentials: "include",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  return read(response);
}

export function rememberPrompt(prompt: string) {
  sessionStorage.setItem("awp_pending_prompt", prompt);
}

export function takePrompt() {
  const value = sessionStorage.getItem("awp_pending_prompt") || "";
  sessionStorage.removeItem("awp_pending_prompt");
  return value;
}
