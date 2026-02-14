"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { AgentPhase, TodoItem, RunSnapshot } from "@/app/types/types";
import { ProcessFlow } from "@/app/components/ProcessFlow";
import { ReasoningBlock } from "@/app/components/ReasoningBlock";
import { cn } from "@/lib/utils";

interface ThinkingAccordionProps {
  snapshot?: RunSnapshot;
  isThinking?: boolean;
  phase?: AgentPhase;
  todos?: TodoItem[];
  iteration?: number;
  executionDetails?: React.ReactNode;
  planningReasoning?: string;
  reasoningText?: string;
  reviewText?: string;
  finalAnswerText?: string;
}

export const ThinkingAccordion = React.memo<ThinkingAccordionProps>(
  ({
    snapshot,
    isThinking,
    phase,
    todos,
    iteration,
    executionDetails,
    planningReasoning,
    reasoningText,
    reviewText,
    finalAnswerText,
  }) => {
    const [isOpen, setIsOpen] = useState(false);

    const hasData =
      isThinking ||
      (snapshot &&
        (snapshot.phases.length > 0 ||
          snapshot.todos.length > 0 ||
          !!snapshot.reasoning)) ||
      (todos && todos.length > 0);

    if (!hasData) return null;

    const displayDuration = snapshot
      ? snapshot.totalDuration > 0
        ? (snapshot.totalDuration / 1000).toFixed(1)
        : null
      : null;

    const label = isThinking
      ? "Thinking..."
      : displayDuration
        ? `Thought for ${displayDuration} seconds`
        : "Reasoning Process";

    // Use snapshot data if available, otherwise use live data
    const displayPhase = snapshot ? "completed" : (phase ?? "completed");
    const displayTodos = snapshot?.todos ?? todos ?? [];
    const displayIteration = iteration;

    return (
      <div className="mb-3">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={cn(
            "glass-card flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground transition-all hover:shadow-md hover:text-foreground md:w-auto"
          )}
        >
          <span>{label}</span>
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        {isOpen && (
          <div className="transition-expand mt-3 rounded-xl border border-border/50 bg-card/80 p-4 shadow-sm backdrop-blur-sm">
            <ProcessFlow
              phase={displayPhase as AgentPhase}
              todos={displayTodos}
              iteration={displayIteration}
              defaultExpanded
              planningReasoning={planningReasoning}
              reviewContent={
                reviewText ? (
                  <pre className="glass-card max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-md p-3 text-xs leading-relaxed text-foreground">
                    {reviewText}
                  </pre>
                ) : (
                  <p className="pl-2 text-sm text-muted-foreground">
                    No saved review content for this run.
                  </p>
                )
              }
              finalAnswerContent={
                reasoningText || finalAnswerText ? (
                  <div className="space-y-2 pl-2">
                    {reasoningText && (
                      <ReasoningBlock
                        content={reasoningText}
                        title="Thought Chain"
                        defaultOpen={false}
                        compact
                      />
                    )}
                    {finalAnswerText ? (
                      <pre className="glass-card max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-md p-3 text-xs leading-relaxed text-foreground">
                        {finalAnswerText}
                      </pre>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No saved final answer preview for this run.
                      </p>
                    )}
                  </div>
                ) : undefined
              }
            >
              {executionDetails}
            </ProcessFlow>
          </div>
        )}
      </div>
    );
  }
);

ThinkingAccordion.displayName = "ThinkingAccordion";
