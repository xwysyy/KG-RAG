import { getToken, clearAuth } from "@/lib/auth";

export function getApiUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8765";
  return raw.replace(/\/+$/, "");
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function handleResponse<T>(res: Response): Promise<T> {
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
