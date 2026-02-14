"use client";

import { X, Link, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useGraphNeighbors } from "@/app/hooks/useGraphData";
import {
  ENTITY_TYPE_COLORS,
  RELATION_TYPE_COLORS,
} from "@/lib/graph-constants";
import type { GraphNode } from "@/lib/graph-api";

interface GraphNodePanelProps {
  node: GraphNode;
  onClose: () => void;
  onNavigate: (nodeId: string) => void;
}

export default function GraphNodePanel({
  node,
  onClose,
  onNavigate,
}: GraphNodePanelProps) {
  const { data: neighbors } = useGraphNeighbors(node.id, { depth: 1, limit: 30 });

  const neighborNodes = neighbors?.nodes.filter((n) => n.id !== node.id) ?? [];
  const edges = neighbors?.edges ?? [];

  return (
    <div className="absolute right-4 top-4 z-10 w-80 rounded-xl border border-border/50 bg-background/80 shadow-xl backdrop-blur-xl">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-border/50 p-4">
        <div className="flex-1 pr-2">
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-3 w-3 rounded-full"
              style={{
                backgroundColor:
                  ENTITY_TYPE_COLORS[node.type] || ENTITY_TYPE_COLORS.Unknown,
              }}
            />
            <h3 className="text-sm font-semibold leading-tight">
              {node.label}
            </h3>
          </div>
          <span className="mt-1 inline-block rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {node.type}
          </span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onClose}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Body */}
      <div className="max-h-[calc(100vh-200px)] overflow-y-auto p-4">
        {/* Description */}
        {node.description && (
          <div className="mb-4">
            <p className="text-xs leading-relaxed text-muted-foreground">
              {node.description}
            </p>
          </div>
        )}

        {/* Aliases */}
        {node.aliases.length > 0 && (
          <div className="mb-4">
            <div className="mb-1.5 flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <Tag className="h-3 w-3" />
              Aliases
            </div>
            <div className="flex flex-wrap gap-1">
              {node.aliases.map((a) => (
                <span
                  key={a}
                  className="rounded-md bg-muted px-2 py-0.5 text-xs"
                >
                  {a}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Connections */}
        {neighborNodes.length > 0 && (
          <div>
            <div className="mb-1.5 flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <Link className="h-3 w-3" />
              Connections ({neighborNodes.length})
            </div>
            <div className="space-y-1">
              {neighborNodes.map((n) => {
                const edge = edges.find(
                  (e) =>
                    (e.source === node.id && e.target === n.id) ||
                    (e.target === node.id && e.source === n.id)
                );
                return (
                  <button
                    key={n.id}
                    onClick={() => onNavigate(n.id)}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted/50"
                  >
                    <span
                      className="inline-block h-2 w-2 flex-shrink-0 rounded-full"
                      style={{
                        backgroundColor:
                          ENTITY_TYPE_COLORS[n.type] ||
                          ENTITY_TYPE_COLORS.Unknown,
                      }}
                    />
                    <span className="flex-1 truncate">{n.label}</span>
                    {edge && (
                      <span
                        className="flex-shrink-0 rounded px-1.5 py-0.5 text-[10px]"
                        style={{
                          backgroundColor: `${RELATION_TYPE_COLORS[edge.type] || "#6b7280"}20`,
                          color:
                            RELATION_TYPE_COLORS[edge.type] || "#6b7280",
                        }}
                      >
                        {edge.type}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
