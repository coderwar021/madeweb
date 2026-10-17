import { explainApiError } from "../i18n";

const csrf = new Map<string, string>();

export type AppUser = { id: string; name: string; role: string };

async function send(appId: string, path: string, options: { method?: string; body?: unknown; draft?: boolean } = {}) {
  const method = options.method || "GET";
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrf.get(appId) || "";
  const join = path.includes("?") ? "&" : "?";
  const url = `/api/v1/runtime/${appId}${path}${options.draft ? `${join}draft=1` : ""}`;
  const response = await fetch(url, {
    method,
    credentials: "include",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(explainApiError(typeof data.detail === "string" ? data.detail : undefined));
  if (data.csrfToken) csrf.set(appId, data.csrfToken);
  return data;
}

export async function bootApp(appId: string, draft: boolean): Promise<AppUser | null> {
  try {
    const data = await send(appId, "/auth/me", { draft });
    return data.user;
  } catch {
    const data = await send(appId, "/auth/csrf", { draft });
    csrf.set(appId, data.csrfToken);
    return null;
  }
}

export const appApi = send;

export async function uploadFile(appId: string, file: File, draft: boolean) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`/api/v1/runtime/${appId}/upload${draft ? "?draft=1" : ""}`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrf.get(appId) || "" },
    body,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(explainApiError(typeof data.detail === "string" ? data.detail : undefined, "upload"));
  return data as { id: string; url: string };
}
