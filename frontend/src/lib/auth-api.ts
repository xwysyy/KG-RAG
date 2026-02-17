import { getApiUrl } from "@/lib/fetch-utils";

interface AuthResponse {
  user_id: string;
  username: string;
  access_token: string;
  token_type: string;
}

async function handleAuthResponse(res: Response): Promise<AuthResponse> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const authApi = {
  register: (username: string, password: string) =>
    fetch(`${getApiUrl()}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }).then(handleAuthResponse),

  login: (username: string, password: string) =>
    fetch(`${getApiUrl()}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }).then(handleAuthResponse),
};
