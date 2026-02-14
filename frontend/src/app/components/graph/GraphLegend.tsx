"use client";

import {
  ENTITY_TYPE_COLORS,
  RELATION_TYPE_COLORS,
} from "@/lib/graph-constants";

interface GraphLegendProps {
  entityCounts?: Record<string, number>;
}

export default function GraphLegend({ entityCounts }: GraphLegendProps) {
  return (
    <div className="absolute bottom-4 right-4 z-10 rounded-xl border border-border/50 bg-background/80 p-3 shadow-lg backdrop-blur-xl">
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Entity Types
      </div>
      <div className="space-y-1">
        {Object.entries(ENTITY_TYPE_COLORS)
          .filter(([k]) => k !== "Unknown")
          .map(([type, color]) => (
            <div key={type} className="flex items-center gap-2 text-xs">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span className="text-foreground">{type}</span>
              {entityCounts?.[type] != null && (
                <span className="ml-auto text-muted-foreground">
                  {entityCounts[type]}
                </span>
              )}
            </div>
          ))}
      </div>

      <div className="mb-2 mt-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Relations
      </div>
      <div className="space-y-1">
        {Object.entries(RELATION_TYPE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-2 text-xs">
            <span
              className="inline-block h-0.5 w-3"
              style={{ backgroundColor: color }}
            />
            <span className="text-foreground">{type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
