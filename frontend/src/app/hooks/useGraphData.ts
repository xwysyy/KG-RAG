import useSWR from "swr";
import { graphApi } from "@/lib/graph-api";
import type { GraphOverview, GraphStats, GraphNode } from "@/lib/graph-api";

export function useGraphStats() {
  return useSWR<GraphStats>("graph-stats", () => graphApi.getStats(), {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });
}

export function useGraphOverview(params?: { entity_type?: string; limit?: number }) {
  const key = params
    ? `graph-overview-${params.entity_type ?? "all"}-${params.limit ?? 500}`
    : "graph-overview-all-500";

  return useSWR<GraphOverview>(key, () => graphApi.getOverview(params), {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
  });
}

export function useGraphNeighbors(
  entityId: string | null,
  params?: { depth?: number; limit?: number }
) {
  const key = entityId
    ? `graph-neighbors-${entityId}-${params?.depth ?? 1}-${params?.limit ?? 50}`
    : null;

  return useSWR<GraphOverview>(
    key,
    () => (entityId ? graphApi.getNeighbors(entityId, params) : null!),
    { revalidateOnFocus: false, dedupingInterval: 30000 }
  );
}

export function useGraphSearch(q: string, entityType?: string) {
  const key = q.length >= 1 ? `graph-search-${q}-${entityType ?? "all"}` : null;

  return useSWR<GraphNode[]>(
    key,
    () => graphApi.searchEntities({ q, entity_type: entityType, limit: 20 }),
    { revalidateOnFocus: false, dedupingInterval: 5000 }
  );
}
