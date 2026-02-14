"use client";

import { useState, useCallback } from "react";
import { Search, X, Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useGraphSearch } from "@/app/hooks/useGraphData";
import {
  ENTITY_TYPES,
  ENTITY_TYPE_COLORS,
} from "@/lib/graph-constants";
import type { GraphNode } from "@/lib/graph-api";

interface GraphSearchProps {
  onSelectNode: (nodeId: string) => void;
  onFilterType: (type: string | undefined) => void;
  activeFilter?: string;
}

export default function GraphSearch({
  onSelectNode,
  onFilterType,
  activeFilter,
}: GraphSearchProps) {
  const [query, setQuery] = useState("");
  const [showFilter, setShowFilter] = useState(false);
  const { data: results, isLoading } = useGraphSearch(query, activeFilter);

  const handleSelect = useCallback(
    (node: GraphNode) => {
      onSelectNode(node.id);
      setQuery("");
    },
    [onSelectNode]
  );

  return (
    <div className="absolute left-4 top-4 z-10 flex flex-col gap-2">
      {/* Search bar */}
      <div className="flex items-center gap-1.5">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search entities..."
            className="h-9 w-64 rounded-lg border border-border/50 bg-background/80 pl-8 pr-8 text-sm shadow-lg backdrop-blur-xl focus:outline-none focus:ring-1 focus:ring-ring"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <Button
          variant={showFilter ? "secondary" : "ghost"}
          size="icon"
          className="h-9 w-9 rounded-lg border border-border/50 bg-background/80 shadow-lg backdrop-blur-xl"
          onClick={() => setShowFilter(!showFilter)}
        >
          <Filter className="h-4 w-4" />
        </Button>
      </div>

      {/* Type filter chips */}
      {showFilter && (
        <div className="flex flex-wrap gap-1 rounded-lg border border-border/50 bg-background/80 p-2 shadow-lg backdrop-blur-xl">
          <button
            onClick={() => onFilterType(undefined)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              !activeFilter
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
            }`}
          >
            All
          </button>
          {ENTITY_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => onFilterType(activeFilter === t ? undefined : t)}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                activeFilter === t
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted"
              }`}
            >
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: ENTITY_TYPE_COLORS[t] }}
              />
              {t}
            </button>
          ))}
        </div>
      )}

      {/* Search results dropdown */}
      {query && (
        <div className="max-h-72 overflow-y-auto rounded-lg border border-border/50 bg-background/80 shadow-lg backdrop-blur-xl">
          {isLoading ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              Searching...
            </div>
          ) : results && results.length > 0 ? (
            results.map((node) => (
              <button
                key={node.id}
                onClick={() => handleSelect(node)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted/50"
              >
                <span
                  className="inline-block h-2.5 w-2.5 flex-shrink-0 rounded-full"
                  style={{
                    backgroundColor:
                      ENTITY_TYPE_COLORS[node.type] ||
                      ENTITY_TYPE_COLORS.Unknown,
                  }}
                />
                <span className="truncate font-medium">{node.label}</span>
                <span className="ml-auto flex-shrink-0 text-xs text-muted-foreground">
                  {node.type}
                </span>
              </button>
            ))
          ) : (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              No results
            </div>
          )}
        </div>
      )}
    </div>
  );
}
