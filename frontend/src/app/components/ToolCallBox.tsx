"use client";

import React, { useState, useMemo, useCallback } from "react";
import {
  ChevronDown,
  ChevronUp,
  Terminal,
  AlertCircle,
  Loader2,
  CircleCheckBigIcon,
  StopCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ToolCall, ActionRequest, ReviewConfig } from "@/app/types/types";
import { cn } from "@/lib/utils";
import { ToolApprovalInterrupt } from "@/app/components/ToolApprovalInterrupt";
import { MarkdownContent } from "@/app/components/MarkdownContent";

interface ToolCallBoxProps {
  toolCall: ToolCall;
  actionRequest?: ActionRequest;
  reviewConfig?: ReviewConfig;
  onResume?: (value: any) => void;
  isLoading?: boolean;
  compact?: boolean;
}

export const ToolCallBox = React.memo<ToolCallBoxProps>(
  ({
    toolCall,
    actionRequest,
    reviewConfig,
    onResume,
    isLoading,
    compact,
  }) => {
    const [isExpanded, setIsExpanded] = useState(
      () => !!actionRequest
    );
    const [expandedArgs, setExpandedArgs] = useState<Record<string, boolean>>(
      {}
    );

    const { name, args, result, status } = useMemo(() => {
      return {
        name: toolCall.name || "Unknown Tool",
        args: toolCall.args || {},
        result: toolCall.result,
        status: toolCall.status || "completed",
      };
    }, [toolCall]);

    const statusIcon = useMemo(() => {
      switch (status) {
        case "completed":
          return <CircleCheckBigIcon />;
        case "error":
          return (
            <AlertCircle
              size={14}
              className="text-destructive"
            />
          );
        case "pending":
          return (
            <Loader2
              size={14}
              className="animate-spin"
            />
          );
        case "interrupted":
          return (
            <StopCircle
              size={14}
              className="text-orange-500"
            />
          );
        default:
          return (
            <Terminal
              size={14}
              className="text-muted-foreground"
            />
          );
      }
    }, [status]);

    const toggleExpanded = useCallback(() => {
      setIsExpanded((prev) => !prev);
    }, []);

    const toggleArgExpanded = useCallback((argKey: string) => {
      setExpandedArgs((prev) => ({
        ...prev,
        [argKey]: !prev[argKey],
      }));
    }, []);

    const hasThought =
      typeof toolCall.thought === "string" && toolCall.thought.trim() !== "";
    const hasContent = hasThought || result || Object.keys(args).length > 0;

    const borderColor = cn(
      "border-l-2",
      status === "pending" && "border-l-[hsl(var(--status-warning))]",
      status === "completed" && "border-l-[hsl(var(--status-completed))]",
      status === "error" && "border-l-[hsl(var(--status-error))]",
      status === "interrupted" && "border-l-[hsl(var(--status-warning))]"
    );

    return (
      <div
        className={cn(
          "w-full overflow-hidden rounded-lg border border-border bg-background shadow-sm outline-none transition-all duration-200 hover:shadow-md",
          isExpanded && hasContent && "bg-accent",
          borderColor
        )}
      >
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleExpanded}
          className={cn(
            "flex w-full items-center justify-between gap-2 border-none text-left shadow-none outline-none focus-visible:ring-0 focus-visible:ring-offset-0 disabled:cursor-default",
            compact ? "px-2 py-1" : "px-2 py-2"
          )}
          disabled={!hasContent}
        >
          <div className="flex w-full items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {statusIcon}
              <span
                className={cn(
                  "font-medium text-foreground",
                  compact
                    ? "font-mono text-xs"
                    : "font-mono text-xs tracking-[-0.3px]"
                )}
              >
                {name}
              </span>
            </div>
            {hasContent &&
              (isExpanded ? (
                <ChevronUp
                  size={14}
                  className="shrink-0 text-muted-foreground"
                />
              ) : (
                <ChevronDown
                  size={14}
                  className="shrink-0 text-muted-foreground"
                />
              ))}
          </div>
        </Button>

        {isExpanded && hasContent && (
          <div className="px-4 pb-4">
            {actionRequest && onResume ? (
              // Show tool approval UI when there's an action request but no GenUI
              <div className="mt-4">
                <ToolApprovalInterrupt
                  actionRequest={actionRequest}
                  reviewConfig={reviewConfig}
                  onResume={onResume}
                  isLoading={isLoading}
                />
              </div>
            ) : (
              <>
                {hasThought && (
                  <div className="mt-4">
                    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Thought
                    </h4>
                    <div className="rounded-sm border border-border bg-background p-2">
                      <MarkdownContent
                        content={toolCall.thought as string}
                        className="text-xs [&_p]:mb-2"
                      />
                    </div>
                  </div>
                )}
                {Object.keys(args).length > 0 && (
                  <div className="mt-4">
                    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Arguments
                    </h4>
                    <div className="space-y-2">
                      {Object.entries(args).map(([key, value]) => (
                        <div
                          key={key}
                          className="rounded-sm border border-border"
                        >
                          <button
                            onClick={() => toggleArgExpanded(key)}
                            className="flex w-full items-center justify-between bg-muted/30 p-2 text-left text-xs font-medium transition-colors hover:bg-muted/50"
                          >
                            <span className="font-mono">{key}</span>
                            {expandedArgs[key] ? (
                              <ChevronUp
                                size={12}
                                className="text-muted-foreground"
                              />
                            ) : (
                              <ChevronDown
                                size={12}
                                className="text-muted-foreground"
                              />
                            )}
                          </button>
                          {expandedArgs[key] && (
                            <div className="border-t border-border bg-muted/20 p-2">
                              <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs leading-6 text-foreground">
                                {typeof value === "string"
                                  ? value
                                  : JSON.stringify(value, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {result && (
                  <div className="mt-4">
                    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Result
                    </h4>
                    <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-all rounded-sm border border-border/50 bg-card/80 p-2 font-mono text-xs leading-7 text-foreground backdrop-blur-sm">
                      {typeof result === "string"
                        ? result
                        : JSON.stringify(result, null, 2)}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    );
  }
);

ToolCallBox.displayName = "ToolCallBox";
