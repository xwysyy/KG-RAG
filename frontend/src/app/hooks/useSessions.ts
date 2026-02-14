import useSWR from "swr";
import { api } from "@/lib/api";
import type { Session } from "@/app/types/types";

export interface SessionItem {
  id: string;
  updatedAt: Date;
  title: string;
  description: string;
}

export function useSessions(props?: { limit?: number }) {
  const pageSize = props?.limit || 20;

  const result = useSWR(
    { kind: "sessions" as const, pageSize },
    async ({ pageSize: limit }) => {
      const sessions = await api.listSessions(limit);
      return sessions.map(
        (s: Session): SessionItem => ({
          id: s.session_id,
          updatedAt: new Date(s.updated_at),
          title: s.title || `Session ${s.session_id.slice(0, 8)}`,
          description: s.last_message || "",
        })
      );
    },
    {
      revalidateOnFocus: true,
    }
  );

  return result;
}
