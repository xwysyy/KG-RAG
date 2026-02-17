"use client";

import React, { useMemo, useState, useCallback } from "react";
import { Bot, Copy, Check } from "lucide-react";
import { SubAgentIndicator } from "@/app/components/SubAgentIndicator";
import { ToolCallBox } from "@/app/components/ToolCallBox";
import { MarkdownContent } from "@/app/components/MarkdownContent";
import { SubTaskCard } from "@/app/components/SubTaskCard";
import type {
  SubAgent,
  ToolCall,
  ActionRequest,
  ReviewConfig,
  RunSnapshot,
} from "@/app/types/types";
import { ThinkingAccordion } from "@/app/components/ThinkingAccordion";
import type { Message } from "@/app/types/types";
import {
  extractSubAgentContent,
  extractStringFromMessageContent,
  extractReasoningContent,
  stripThinkTags,
} from "@/app/utils/utils";
import { cn } from "@/lib/utils";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = React.useRef<ReturnType<typeof setTimeout>>(undefined);
  React.useEffect(() => () => clearTimeout(timerRef.current), []);
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard failures (e.g. permission denied).
    }
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        "flex-shrink-0 rounded-md p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground group-hover/msg:opacity-100"
      )}
      aria-label="Copy message"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  );
}

interface ChatMessageProps {
  message: Message;
  toolCalls: ToolCall[];
  isLoading?: boolean;
  actionRequestsMap?: Map<string, ActionRequest>;
  reviewConfigsMap?: Map<string, ReviewConfig>;
  onResumeInterrupt?: (value: any) => void;
  snapshot?: RunSnapshot;
  thinkingExecutionDetails?: React.ReactNode;
  thinkingPlanningReasoning?: string;
  thinkingReviewText?: string;
}

export const ChatMessage = React.memo<ChatMessageProps>(
  ({
    message,
    toolCalls,
    isLoading,
    actionRequestsMap,
    reviewConfigsMap,
    onResumeInterrupt,
    snapshot,
    thinkingExecutionDetails,
    thinkingPlanningReasoning,
    thinkingReviewText,
  }) => {
    const isUser = message.type === "human";
    const messageContent = extractStringFromMessageContent(message);

    // Extract reasoning content from message or snapshot
    const reasoningContent = useMemo(() => {
      if (!isUser) {
        const fromMsg = extractReasoningContent(message);
        if (fromMsg) return fromMsg;
        if (snapshot?.reasoning) return snapshot.reasoning;
      }
      return null;
    }, [message, snapshot, isUser]);

    // Strip <think> tags from display content
    const displayContent = useMemo(() => {
      if (!messageContent) return "";
      return isUser ? messageContent : stripThinkTags(messageContent);
    }, [messageContent, isUser]);

    const replayFinalAnswerText = useMemo(() => {
      if (isUser) return undefined;
      const fromSnapshot = snapshot?.finalAnswerText;
      if (fromSnapshot && fromSnapshot.trim()) return fromSnapshot;
      const trimmed = displayContent.trim();
      if (!trimmed) return undefined;
      if (trimmed.length <= 1600) return trimmed;
      return `${trimmed.slice(0, 1600).trimEnd()}…`;
    }, [displayContent, isUser, snapshot?.finalAnswerText]);

    const replayExecutionDetails = useMemo(() => {
      if (!snapshot) return undefined;

      const todosForReplay = snapshot.todos ?? [];
      if (todosForReplay.length === 0) return undefined;

      const hasAnyDetails =
        (snapshot.toolCallsByTask &&
          Object.keys(snapshot.toolCallsByTask).length > 0) ||
        (snapshot.taskResultsById &&
          Object.keys(snapshot.taskResultsById).length > 0);

      if (!hasAnyDetails) {
        return (
          <p className="pl-2 text-sm text-muted-foreground">
            No saved sub-task execution details for this run.
          </p>
        );
      }

      return (
        <div className="grid grid-cols-1 gap-4 pt-2 md:grid-cols-2">
          {todosForReplay.map((todo) => (
            <SubTaskCard
              key={todo.id}
              todo={todo}
              toolCalls={snapshot.toolCallsByTask?.[todo.id] ?? []}
              result={snapshot.taskResultsById?.[todo.id]}
            />
          ))}
        </div>
      );
    }, [snapshot]);

    const hasContent = displayContent && displayContent.trim() !== "";
    const hasToolCalls = toolCalls.length > 0;
    const subAgents = useMemo(() => {
      return toolCalls
        .filter((toolCall: ToolCall) => {
          return (
            toolCall.name === "task" &&
            toolCall.args["subagent_type"] &&
            toolCall.args["subagent_type"] !== "" &&
            toolCall.args["subagent_type"] !== null
          );
        })
        .map((toolCall: ToolCall) => {
          const subagentType = (toolCall.args as Record<string, unknown>)[
            "subagent_type"
          ] as string;
          return {
            id: toolCall.id,
            name: toolCall.name,
            subAgentName: subagentType,
            input: toolCall.args,
            output: toolCall.result ? { result: toolCall.result } : undefined,
            status: toolCall.status,
          } as SubAgent;
        });
    }, [toolCalls]);

    const [expandedSubAgents, setExpandedSubAgents] = useState<
      Record<string, boolean>
    >({});
    const isSubAgentExpanded = useCallback(
      (id: string) => expandedSubAgents[id] ?? true,
      [expandedSubAgents]
    );
    const toggleSubAgent = useCallback((id: string) => {
      setExpandedSubAgents((prev) => ({
        ...prev,
        [id]: prev[id] === undefined ? false : !prev[id],
      }));
    }, []);

    return (
      <div
        className={cn(
          "flex w-full max-w-full overflow-x-hidden",
          isUser ? "flex-row-reverse" : "gap-3"
        )}
      >
        {/* AI avatar */}
        {!isUser && (
          <div className="mt-4 flex-shrink-0">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-[#49b1f5] to-[#62bfff] dark:from-[#5bb8e8] dark:to-[#6ec5f0]">
              <Bot className="h-3.5 w-3.5 text-white" />
            </div>
          </div>
        )}
        <div
          className={cn(
            "min-w-0 max-w-full",
            isUser ? "max-w-[70%]" : "w-full"
          )}
        >
          {/* ThinkingAccordion for final AI answers */}
          {!isUser && snapshot && (
            <div className="mt-4">
              <ThinkingAccordion
                snapshot={snapshot}
                executionDetails={
                  thinkingExecutionDetails ?? replayExecutionDetails
                }
                planningReasoning={
                  thinkingPlanningReasoning ?? snapshot.planningReasoning
                }
                reasoningText={reasoningContent ?? undefined}
                reviewText={thinkingReviewText ?? snapshot.reviewText}
                finalAnswerText={replayFinalAnswerText}
              />
            </div>
          )}
          {hasContent && (
            <div
              className={cn(
                "group/msg relative mt-4 flex items-start gap-1",
                isUser && "flex-row-reverse"
              )}
            >
              <div
                className={cn(
                  "overflow-hidden break-words text-base font-normal leading-[150%]",
                  isUser
                    ? "rounded-2xl rounded-br-sm bg-gradient-to-r from-[#49b1f5] to-[#62bfff] dark:from-[#5bb8e8] dark:to-[#6ec5f0] px-4 py-2.5 text-white dark:text-gray-100 shadow-sm"
                    : "border-l-2 border-primary/20 pl-3 text-foreground"
                )}
              >
                {isUser ? (
                  <p className="m-0 whitespace-pre-wrap break-words text-base leading-relaxed">
                    {displayContent}
                  </p>
                ) : hasContent ? (
                  <MarkdownContent content={displayContent} />
                ) : null}
              </div>
              <CopyButton text={displayContent} />
            </div>
          )}
          {hasToolCalls && (
            <div className="mt-4 flex w-full flex-col">
              {toolCalls.map((toolCall: ToolCall) => {
                if (toolCall.name === "task") return null;
                const actionRequest = actionRequestsMap?.get(toolCall.name);
                const reviewConfig = reviewConfigsMap?.get(toolCall.name);
                return (
                  <ToolCallBox
                    key={toolCall.id}
                    toolCall={toolCall}
                    actionRequest={actionRequest}
                    reviewConfig={reviewConfig}
                    onResume={onResumeInterrupt}
                    isLoading={isLoading}
                  />
                );
              })}
            </div>
          )}
          {!isUser && subAgents.length > 0 && (
            <div className="flex w-fit max-w-full flex-col gap-4">
              {subAgents.map((subAgent) => (
                <div
                  key={subAgent.id}
                  className="flex w-full flex-col gap-2"
                >
                  <div className="flex items-end gap-2">
                    <div className="w-[calc(100%-100px)]">
                      <SubAgentIndicator
                        subAgent={subAgent}
                        onClick={() => toggleSubAgent(subAgent.id)}
                        isExpanded={isSubAgentExpanded(subAgent.id)}
                      />
                    </div>
                  </div>
                  {isSubAgentExpanded(subAgent.id) && (
                    <div className="w-full max-w-full">
                      <div className="rounded-md border border-border bg-muted/30 p-4">
                        <h4 className="text-primary/70 mb-2 text-xs font-semibold uppercase tracking-wider">
                          Input
                        </h4>
                        <div className="mb-4">
                          <MarkdownContent
                            content={extractSubAgentContent(subAgent.input)}
                          />
                        </div>
                        {subAgent.output && (
                          <>
                            <h4 className="text-primary/70 mb-2 text-xs font-semibold uppercase tracking-wider">
                              Output
                            </h4>
                            <MarkdownContent
                              content={extractSubAgentContent(subAgent.output)}
                            />
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }
);

ChatMessage.displayName = "ChatMessage";
