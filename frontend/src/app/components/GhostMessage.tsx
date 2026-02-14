"use client";

import React from "react";
import { Loader2 } from "lucide-react";
import type { AgentPhase, TodoItem } from "@/app/types/types";
import { ProcessFlow } from "@/app/components/ProcessFlow";
import { ReasoningBlock } from "@/app/components/ReasoningBlock";

interface GhostMessageProps {
  phase: AgentPhase;
  todos: TodoItem[];
  iteration?: number;
  subTaskCards?: React.ReactNode;
  planningReasoning?: string | null;
  streamingReviewContent?: string | null;
  streamingReasoning?: string | null;
  streamingContent?: string | null;
}

export const GhostMessage = React.memo<GhostMessageProps>(
  ({
    phase,
    todos,
    iteration,
    subTaskCards,
    planningReasoning,
    streamingReviewContent,
    streamingReasoning,
    streamingContent,
  }) => {
    if (phase === "idle" || phase === "completed") {
      return null;
    }

    return (
      <div className="flex w-full max-w-full gap-3">
        {/* AI avatar */}
        <div className="mt-4 flex-shrink-0">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-[#49b1f5] to-[#62bfff] dark:from-[#2080c0] dark:to-[#3090d0]">
            <Loader2
              size={14}
              className="animate-spin text-white"
            />
          </div>
        </div>
        <div className="w-full min-w-0">
          <div className="mt-4">
            <span className="mb-3 inline-block text-sm font-medium text-muted-foreground">
              Thinking...
            </span>

            {/* ProcessFlow */}
            <div className="rounded-xl border border-border/50 bg-card/80 p-4 shadow-sm backdrop-blur-sm">
              <ProcessFlow
                phase={phase}
                todos={todos}
                iteration={iteration}
                planningReasoning={planningReasoning ?? undefined}
                reviewContent={
                  phase === "reviewing" && streamingReviewContent ? (
                    <pre className="max-h-56 overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-border/50 bg-muted/30 p-3 text-xs leading-relaxed text-foreground">
                      {streamingReviewContent}
                      <span className="ml-0.5 inline-block h-3.5 w-1 animate-cursor-blink bg-primary align-middle" />
                    </pre>
                  ) : undefined
                }
                finalAnswerContent={
                  phase === "answering" &&
                  (streamingReasoning || streamingContent) ? (
                    <div className="space-y-2 pl-2">
                      {streamingReasoning && (
                        <ReasoningBlock
                          content={streamingReasoning}
                          title="Thought Chain"
                          isStreaming
                          defaultOpen={false}
                          compact
                        />
                      )}
                      {streamingContent && (
                        <ReasoningBlock
                          content={streamingContent}
                          title="Generating Answer"
                          isStreaming
                          defaultOpen={false}
                          compact
                        />
                      )}
                    </div>
                  ) : undefined
                }
              >
                {subTaskCards}
              </ProcessFlow>
            </div>
          </div>
        </div>
      </div>
    );
  }
);

GhostMessage.displayName = "GhostMessage";
