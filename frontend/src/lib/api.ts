import type { Session, MessageResponse } from "@/app/types/types";
import { getToken, clearAuth } from "@/lib/auth";

function getApiUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8765";
  return raw.replace(/\/+$/, "");
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    clearAuth();
    if (typeof window !== "undefined") {
      window.location.href = "/auth";
    }
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

export const api = {
  createSession: (title?: string) =>
    fetch(`${getApiUrl()}/api/v1/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ title: title || "" }),
    }).then((res) => handleResponse<Session>(res)),

  listSessions: (limit = 20, offset = 0) =>
    fetch(
      `${getApiUrl()}/api/v1/sessions?limit=${limit}&offset=${offset}`,
      { headers: authHeaders() }
    ).then((res) => handleResponse<Session[]>(res)),

  getSessionMessages: (sessionId: string) =>
    fetch(`${getApiUrl()}/api/v1/sessions/${sessionId}/messages`, {
      headers: authHeaders(),
    }).then((res) =>
      handleResponse<{
        session: Session;
        messages: MessageResponse[];
      }>(res)
    ),

  chatStream: (
    sessionId: string,
    content: string,
    signal?: AbortSignal
  ) =>
    fetch(`${getApiUrl()}/api/v1/sessions/${sessionId}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ content }),
      signal,
    }),

  deleteSession: (sessionId: string) =>
    fetch(`${getApiUrl()}/api/v1/sessions/${sessionId}`, {
      method: "DELETE",
      headers: authHeaders(),
    }).then((res) => handleResponse<{ ok: boolean }>(res)),
};
