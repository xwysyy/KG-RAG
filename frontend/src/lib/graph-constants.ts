/** Entity type → display color mapping (vibrant, high-saturation) */
export const ENTITY_TYPE_COLORS: Record<string, string> = {
  Algorithm: "#6366f1",     // indigo — core algorithms stand out
  DataStructure: "#06b6d4", // cyan — structural, cool tone
  Concept: "#f59e0b",       // amber — warm, knowledge-like
  Problem: "#f43f5e",       // rose — attention-grabbing
  Technique: "#a855f7",     // violet — creative/method
  Unknown: "#94a3b8",       // slate
};

/** Relation type → display color (with alpha for layering) */
export const RELATION_TYPE_COLORS: Record<string, string> = {
  PREREQ: "#f43f5e",
  IMPROVES: "#10b981",
  APPLIES_TO: "#6366f1",
  BELONGS_TO: "#a855f7",
  VARIANT_OF: "#f59e0b",
  USES: "#06b6d4",
  RELATED_TO: "#94a3b8",
};

export const ENTITY_TYPES = [
  "Algorithm",
  "DataStructure",
  "Concept",
  "Problem",
  "Technique",
] as const;

export type EntityType = (typeof ENTITY_TYPES)[number];

/** Node sizing based on degree — wider range for visual hierarchy */
export const NODE_MIN_SIZE = 3;
export const NODE_MAX_SIZE = 28;
export const NODE_SIZE_SCALE = 2.5;

/** Selected node border color */
export const SELECTED_BORDER_COLOR = "#F57F17";

/** Dimmed color for non-highlighted nodes/edges */
export const DIM_COLOR = "#e2e8f0";
export const DIM_COLOR_DARK = "#1e293b";
