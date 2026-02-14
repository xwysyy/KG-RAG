"use client";

import { Circle, ArrowRight } from "lucide-react";
import type { GraphStats } from "@/lib/graph-api";

interface GraphStatsBarProps {
  stats: GraphStats | undefined;
  isTruncated?: boolean;
}

export default function GraphStatsBar({
  stats,
  isTruncated,
}: GraphStatsBarProps) {
  if (!stats) return null;

  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground">
      <span className="flex items-center gap-1">
        <Circle className="h-3 w-3" />
        {stats.total_entities.toLocaleString()} entities
      </span>
      <span className="flex items-center gap-1">
        <ArrowRight className="h-3 w-3" />
        {stats.total_relations.toLocaleString()} relations
      </span>
      {isTruncated && (
        <span className="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-amber-600 dark:text-amber-400">
          truncated
        </span>
      )}
    </div>
  );
}
