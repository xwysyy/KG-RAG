import type { Session, MessageResponse } from "@/app/types/types";
import { getApiUrl, authHeaders, handleResponse } from "@/lib/fetch-utils";

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
