import { getApiUrl, authHeaders, handleResponse } from "@/lib/fetch-utils";

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  description: string;
  aliases: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  description: string;
  weight: number;
}

export interface GraphOverview {
  nodes: GraphNode[];
  edges: GraphEdge[];
  is_truncated: boolean;
}

export interface GraphStats {
  total_entities: number;
  total_relations: number;
  entities_by_type: Record<string, number>;
  relations_by_type: Record<string, number>;
}

export const graphApi = {
  getStats: () =>
    fetch(`${getApiUrl()}/api/v1/graph/stats`, {
      headers: authHeaders(),
    }).then((res) => handleResponse<GraphStats>(res)),

  getOverview: (params?: { entity_type?: string; limit?: number }) => {
    const sp = new URLSearchParams();
    if (params?.entity_type) sp.set("entity_type", params.entity_type);
    if (params?.limit) sp.set("limit", String(params.limit));
    const qs = sp.toString();
    return fetch(`${getApiUrl()}/api/v1/graph/overview${qs ? `?${qs}` : ""}`, {
      headers: authHeaders(),
    }).then((res) => handleResponse<GraphOverview>(res));
  },

  searchEntities: (params: { q: string; entity_type?: string; limit?: number }) => {
    const sp = new URLSearchParams({ q: params.q });
    if (params.entity_type) sp.set("entity_type", params.entity_type);
    if (params.limit) sp.set("limit", String(params.limit));
    return fetch(`${getApiUrl()}/api/v1/graph/entities/search?${sp}`, {
      headers: authHeaders(),
    }).then((res) => handleResponse<GraphNode[]>(res));
  },

  getNeighbors: (entityId: string, params?: { depth?: number; limit?: number }) => {
    const sp = new URLSearchParams();
    if (params?.depth) sp.set("depth", String(params.depth));
    if (params?.limit) sp.set("limit", String(params.limit));
    const qs = sp.toString();
    return fetch(
      `${getApiUrl()}/api/v1/graph/entities/${entityId}/neighbors${qs ? `?${qs}` : ""}`,
      { headers: authHeaders() }
    ).then((res) => handleResponse<GraphOverview>(res));
  },
};
