"use client";

import React, { useState } from "react";
import {
  Loader2,
  CheckCircle2,
  Circle,
  BrainCircuit,
  MessageSquareText,
} from "lucide-react";
import type { TodoItem, ToolCall } from "@/app/types/types";
import { ToolCallBox } from "@/app/components/ToolCallBox";
import { MarkdownContent } from "@/app/components/MarkdownContent";
import { cn } from "@/lib/utils";

interface SubTaskCardProps {
  todo: TodoItem;
  toolCalls: ToolCall[];
  result?: string;
}

export const SubTaskCard = React.memo<SubTaskCardProps>(
  ({ todo, toolCalls, result }) => {
    const [view, setView] = useState<"tools" | "result">("tools");

    const isPending = todo.status === "pending";
    const isActive = todo.status === "in_progress";
    const isCompleted = todo.status === "completed";

    const hasTools = toolCalls.length > 0;
    const hasResult = !!result;

    return (
      <div
        className={cn(
          "glass-card flex h-64 flex-col overflow-hidden rounded-xl transition-all duration-300",
          isActive &&
            "border-[hsl(var(--status-active))] shadow-[0_0_12px_hsl(var(--status-active)/0.1)]",
          isCompleted &&
            "border-[hsl(var(--status-completed))]",
          isPending && "border-border"
        )}
      >
        {/* Header */}
        <div
          className={cn(
            "flex items-start gap-2 border-b p-3",
            isCompleted
              ? "border-[hsl(var(--status-completed)/0.2)] bg-[hsl(var(--status-completed)/0.05)]"
              : "border-border bg-accent/50"
          )}
        >
          <div className="mt-0.5">
            {isActive && (
              <Loader2
                size={14}
                className="animate-spin text-[hsl(var(--status-active))]"
              />
            )}
            {isCompleted && (
              <CheckCircle2 size={14} className="text-[hsl(var(--status-completed))]" />
            )}
            {isPending && (
              <Circle size={14} className="animate-pulse text-muted-foreground/50" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-foreground">
              {todo.content}
            </p>
          </div>
        </div>

        {/* Tabs */}
        {!isPending && (
          <div className="flex border-b border-border text-[10px] font-medium uppercase tracking-wider">
            <button
              onClick={() => setView("tools")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 py-2 transition-colors",
                view === "tools"
                  ? "border-b-2 border-[hsl(var(--status-active))] bg-accent text-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <BrainCircuit size={12} />
              Tools ({toolCalls.length})
            </button>
            <button
              onClick={() => setView("result")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 py-2 transition-colors",
                view === "result"
                  ? "border-b-2 border-[hsl(var(--status-completed))] bg-background text-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <MessageSquareText size={12} />
              Result
            </button>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto bg-background p-2">
          {isPending ? (
            <div className="flex h-full flex-col items-center justify-center text-muted-foreground/50">
              <Circle size={24} className="mb-1 opacity-50" />
              <span className="text-xs italic">Waiting...</span>
            </div>
          ) : view === "tools" ? (
            <div className="space-y-1">
              {hasTools ? (
                toolCalls.map((tc) => (
                  <ToolCallBox
                    key={tc.id}
                    toolCall={tc}
                    compact
                  />
                ))
              ) : (
                <p className="py-4 text-center text-xs italic text-muted-foreground">
                  No tool calls
                </p>
              )}
            </div>
          ) : (
            <div className="p-2">
              {hasResult ? (
                <div className="text-xs leading-relaxed">
                  <MarkdownContent content={result} />
                </div>
              ) : (
                <p className="py-4 text-center text-xs italic text-muted-foreground">
                  {isActive ? "In progress..." : "No result"}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }
);

SubTaskCard.displayName = "SubTaskCard";
