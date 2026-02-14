"use client";

import React, { useState } from "react";
import { ListTodo, Zap, Search, MessageSquare, Repeat } from "lucide-react";
import type { AgentPhase, TodoItem } from "@/app/types/types";
import { ProcessNode } from "@/app/components/ProcessNode";
import { ReasoningBlock } from "@/app/components/ReasoningBlock";
import { cn } from "@/lib/utils";

interface ProcessFlowProps {
  phase: AgentPhase;
  todos: TodoItem[];
  iteration?: number;
  defaultExpanded?: boolean | Partial<Record<ExpandablePhase, boolean>>;
  children?: React.ReactNode;
  planningReasoning?: string;
  reviewContent?: React.ReactNode;
  finalAnswerContent?: React.ReactNode;
}

type NodeStatus = "idle" | "active" | "completed";
type ExpandablePhase = Exclude<AgentPhase, "idle" | "completed">;
type ExpandedState = Record<ExpandablePhase, boolean>;

const PHASE_ORDER: AgentPhase[] = [
  "planning",
  "executing",
  "reviewing",
  "answering",
];

function getNodeStatus(
  nodePhase: AgentPhase,
  currentPhase: AgentPhase
): NodeStatus {
  const currentIdx = PHASE_ORDER.indexOf(currentPhase);
  const nodeIdx = PHASE_ORDER.indexOf(nodePhase);

  if (currentPhase === "completed") return "completed";
  if (currentPhase === "idle") return "idle";
  if (nodeIdx < currentIdx) return "completed";
  if (nodeIdx === currentIdx) return "active";
  return "idle";
}

export const ProcessFlow = React.memo<ProcessFlowProps>(
  ({
    phase,
    todos,
    iteration,
    defaultExpanded = true,
    children,
    planningReasoning,
    reviewContent,
    finalAnswerContent,
  }) => {
    const [expanded, setExpanded] = useState<ExpandedState>(() => {
      const base: ExpandedState = {
        planning: true,
        executing: true,
        reviewing: true,
        answering: true,
      };

      if (typeof defaultExpanded === "boolean") {
        return {
          planning: defaultExpanded,
          executing: defaultExpanded,
          reviewing: defaultExpanded,
          answering: defaultExpanded,
        };
      }

      return { ...base, ...(defaultExpanded ?? {}) };
    });

    const planStatus = getNodeStatus("planning", phase);
    const execStatus = getNodeStatus("executing", phase);
    const reviewStatus = getNodeStatus("reviewing", phase);
    const answerStatus = getNodeStatus("answering", phase);

    const hasTodos = todos.length > 0;
    const completedCount = todos.filter(
      (t) => t.status === "completed"
    ).length;

    const anyExpanded =
      expanded.planning ||
      expanded.executing ||
      expanded.reviewing ||
      expanded.answering;

    return (
      <div className="relative w-full space-y-4 pt-1">
        {/* Header with iteration badge */}
        {typeof iteration === "number" && iteration > 1 && (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary">
              <Repeat size={10} />
              Round {iteration}
            </div>
          </div>
        )}

        <div className="relative space-y-2">
          {/* Connector line */}
          <div
            className={cn(
              "absolute bottom-2 left-4 top-2 w-0.5 bg-gradient-to-b from-primary/30 to-border transition-opacity duration-300",
              anyExpanded ? "opacity-100" : "opacity-0"
            )}
          />

          {/* Node 1: Planning Strategy */}
          <ProcessNode
            icon={ListTodo}
            title="Planning Strategy"
            status={planStatus}
            subtitle="Decomposing question into sub-tasks..."
            isExpanded={expanded.planning}
            onToggle={() =>
              setExpanded((prev) => ({ ...prev, planning: !prev.planning }))
            }
          >
            {planningReasoning && (
              <ReasoningBlock
                content={planningReasoning}
                title="Thought Chain"
                defaultOpen={false}
                compact
              />
            )}
            {hasTodos && (
              <div className="space-y-1.5 pl-2">
                {todos.map((todo) => (
                  <div
                    key={todo.id}
                    className="flex items-start gap-2 rounded-md px-1 py-0.5 text-sm transition-colors hover:bg-accent/50"
                  >
                    <span
                      className={cn(
                        "mt-1 h-1.5 w-1.5 shrink-0 rounded-full",
                        todo.status === "completed" && "bg-[hsl(var(--status-completed))]",
                        todo.status === "in_progress" && "bg-[hsl(var(--status-active))]",
                        todo.status === "pending" && "bg-[hsl(var(--status-pending))]"
                      )}
                    />
                    <span
                      className={cn(
                        "text-sm",
                        todo.status === "completed"
                          ? "text-muted-foreground line-through"
                          : "text-foreground"
                      )}
                    >
                      {todo.content}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </ProcessNode>

          {/* Node 2: Sub-task Execution */}
          <ProcessNode
            icon={Zap}
            title="Sub-task Execution"
            status={execStatus}
            subtitle={
              hasTodos
                ? `Running tasks (${completedCount}/${todos.length})...`
                : "Executing sub-tasks..."
            }
            isExpanded={expanded.executing}
            onToggle={() =>
              setExpanded((prev) => ({ ...prev, executing: !prev.executing }))
            }
          >
            {/* SubTaskCard grid will be rendered here in Phase 3 */}
            {children}
          </ProcessNode>

          {/* Node 3: Quality Review */}
          <ProcessNode
            icon={Search}
            title="Quality Review"
            status={reviewStatus}
            subtitle="Aggregating and judging results..."
            isExpanded={expanded.reviewing}
            onToggle={() =>
              setExpanded((prev) => ({ ...prev, reviewing: !prev.reviewing }))
            }
          >
            {reviewStatus !== "idle" && (
              <>
                {reviewContent ? (
                  reviewContent
                ) : (
                  <p className="pl-2 text-sm text-muted-foreground">
                    {reviewStatus === "active"
                      ? "Evaluating result completeness..."
                      : "Review complete."}
                  </p>
                )}
              </>
            )}
          </ProcessNode>

          {/* Node 4: Final Answer */}
          <ProcessNode
            icon={MessageSquare}
            title="Final Answer"
            status={answerStatus}
            subtitle="Generating response..."
            isExpanded={expanded.answering}
            onToggle={() =>
              setExpanded((prev) => ({ ...prev, answering: !prev.answering }))
            }
          >
            {answerStatus !== "idle" && (
              <>
                {finalAnswerContent ? (
                  finalAnswerContent
                ) : (
                  <p className="pl-2 text-sm text-muted-foreground">
                    {answerStatus === "active"
                      ? "Composing final answer..."
                      : "Answer delivered."}
                  </p>
                )}
              </>
            )}
          </ProcessNode>
        </div>
      </div>
    );
  }
);

ProcessFlow.displayName = "ProcessFlow";
