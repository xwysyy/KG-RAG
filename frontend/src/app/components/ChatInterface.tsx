"use client";

import React, {
  useState,
  useRef,
  useCallback,
  useMemo,
  useEffect,
  FormEvent,
  Fragment,
} from "react";
import {
  Square,
  ArrowUp,
  CheckCircle,
  Clock,
  Circle,
  Bot,
} from "lucide-react";
import { ChatMessage } from "@/app/components/ChatMessage";
import { GhostMessage } from "@/app/components/GhostMessage";
import { SubTaskCard } from "@/app/components/SubTaskCard";
import { useAgentPhase } from "@/app/hooks/useAgentPhase";
import type {
  TodoItem,
  ToolCall,
  RunSnapshot,
} from "@/app/types/types";
import {
  extractStringFromMessageContent,
  stripThinkTags,
} from "@/app/utils/utils";
import { useChatContext } from "@/providers/ChatProvider";
import { cn } from "@/lib/utils";
import { useStickToBottom } from "use-stick-to-bottom";
import { useQueryState } from "nuqs";

const EMPTY_TOOL_CALLS: ToolCall[] = [];

const truncateText = (text: string, maxChars: number) => {
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars).trimEnd()}…`;
};

const SUGGESTION_QUESTIONS = [
  { text: "什么是动态规划？", icon: "💡" },
  { text: "解释 Dijkstra 算法的原理", icon: "🔍" },
  { text: "如何用线段树解决区间查询问题？", icon: "🌲" },
  { text: "比较 BFS 和 DFS 的适用场景", icon: "🔀" },
];

function WelcomePage({ onSend }: { onSend: (text: string) => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 pt-[20vh]">
      <div className="animate-fade-in-up text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[#49b1f5] to-[#62bfff] dark:from-[#2080c0] dark:to-[#3090d0] shadow-lg shadow-[#49b1f5]/25 dark:shadow-[#2080c0]/25">
          <Bot className="h-8 w-8 text-white" />
        </div>
        <h2 className="mb-2 text-2xl font-bold tracking-tight text-foreground">
          KG-RAG
        </h2>
        <p className="text-sm text-muted-foreground">
          算法知识问答系统 — 帮助你理解算法与数据结构
        </p>
      </div>

      <div className="mt-12" />

      <div className="grid w-full max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
        {SUGGESTION_QUESTIONS.map((q, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onSend(q.text)}
            className="animate-fade-in-up group rounded-xl border border-border/60 bg-card/80 px-4 py-3.5 text-left transition-all duration-200 hover:border-primary/40 hover:bg-primary/5 hover:shadow-md hover:shadow-primary/10"
            style={{ animationDelay: `${150 + i * 80}ms` }}
          >
            <div className="flex items-start gap-3">
              <span className="text-lg">{q.icon}</span>
              <span className="text-sm text-foreground/80 group-hover:text-foreground">
                {q.text}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export const ChatInterface = React.memo(() => {
  const [metaOpen, setMetaOpen] = useState<"tasks" | null>(null);
  const tasksContainerRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [input, setInput] = useState("");
  const { scrollRef, contentRef } = useStickToBottom();

  const {
    messages,
    todos,
    isLoading,
    isSessionLoading,
    sendMessage,
    stopStream,
    iteration,
    phase: serverPhase,
    liveToolCallsByTask,
    liveTaskStatusById,
    liveTaskResultById,
    livePlanningReasoning,
    liveAnswerReasoning,
    liveAnswerContent,
    liveReviewContent,
  } = useChatContext();

  const todosWithLiveStatus = useMemo(() => {
    const keys = Object.keys(liveTaskStatusById ?? {});
    if (keys.length === 0) return todos;
    return todos.map((t) => ({
      ...t,
      status: liveTaskStatusById[t.id] ?? t.status,
    }));
  }, [todos, liveTaskStatusById]);

  const { phase, phases } = useAgentPhase({
    phase: serverPhase,
  });

  // Snapshot management — persist to localStorage keyed by sessionId
  const [sessionId] = useQueryState("sessionId");
  const [snapshots, setSnapshots] = useState<Record<string, RunSnapshot>>({});
  const prevIsLoadingRef = useRef(isLoading);
  const prevSnapshotStorageKeyRef = useRef<string | null>(null);
  // Track message count at run start to avoid mis-associating snapshots on error/stop
  const messagesAtRunStartRef = useRef(messages.length);
  // Track run start time directly to avoid stale ref values from useAgentPhase
  const runStartTimeRef = useRef<number | null>(null);

  const snapshotStorageKey = useMemo(() => {
    if (!sessionId) return null;
    return `kg-rag:run-snapshots:${sessionId}`;
  }, [sessionId]);

  // Load snapshots from localStorage when session changes
  useEffect(() => {
    if (!snapshotStorageKey) return;
    const prevKey = prevSnapshotStorageKeyRef.current;
    const isSessionSwitch = prevKey !== null && prevKey !== snapshotStorageKey;
    prevSnapshotStorageKeyRef.current = snapshotStorageKey;
    try {
      const raw = localStorage.getItem(snapshotStorageKey);
      if (!raw) {
        if (isSessionSwitch) setSnapshots({});
        return;
      }
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        if (isSessionSwitch) {
          setSnapshots(parsed);
        } else {
          setSnapshots((prev) => ({
            ...(parsed as Record<string, RunSnapshot>),
            ...prev,
          }));
        }
        return;
      }
      if (isSessionSwitch) setSnapshots({});
    } catch {
      if (isSessionSwitch) setSnapshots({});
    }
  }, [snapshotStorageKey]);

  // Save snapshots to localStorage when they change.
  // IMPORTANT: only depend on `snapshots`, read the key from ref.
  const snapshotStorageKeyRef = useRef(snapshotStorageKey);
  snapshotStorageKeyRef.current = snapshotStorageKey;

  useEffect(() => {
    const key = snapshotStorageKeyRef.current;
    if (!key) return;
    if (Object.keys(snapshots).length === 0) return;
    try {
      localStorage.setItem(key, JSON.stringify(snapshots));
    } catch {
      // Ignore quota / privacy mode errors
    }
  }, [snapshots]);

  useEffect(() => {
    // Record message count when a new run starts
    if (!prevIsLoadingRef.current && isLoading) {
      messagesAtRunStartRef.current = messages.length;
      runStartTimeRef.current = Date.now();
    }
    // Detect transition from loading to not loading (run completed)
    if (prevIsLoadingRef.current && !isLoading && phase === "completed") {
      const lastAi = [...messages].reverse().find((m) => m.type === "ai");
      const hasNewAiMessage =
        lastAi?.id && messages.length > messagesAtRunStartRef.current;

      if (hasNewAiMessage) {
        const now = Date.now();
        const endTime = now;
        const startTime = runStartTimeRef.current ?? phases[0]?.startTime ?? now;

        const snapshotPhases =
          phases.length > 0
            ? phases.map((p, idx) => ({
                ...p,
                endTime:
                  p.endTime ??
                  (idx === phases.length - 1 ? endTime : p.endTime),
              }))
            : [];

        const rawAnswer = stripThinkTags(
          extractStringFromMessageContent(lastAi).trim()
        ).trim();

        const planningReasoning = livePlanningReasoning.trim();
        const reviewText = liveReviewContent.trim();
        const answerReasoning = liveAnswerReasoning.trim();

        const toolCallsByTask =
          liveToolCallsByTask && Object.keys(liveToolCallsByTask).length > 0
            ? Object.fromEntries(
                Object.entries(liveToolCallsByTask).map(([taskId, calls]) => [
                  taskId,
                  (calls ?? []).map((tc) => ({
                    ...tc,
                    thought:
                      typeof tc.thought === "string" && tc.thought.length > 0
                        ? truncateText(tc.thought, 8000)
                        : tc.thought,
                    result:
                      typeof tc.result === "string" && tc.result.length > 0
                        ? truncateText(tc.result, 12000)
                        : tc.result,
                  })),
                ])
              )
            : undefined;

        const taskResultsById =
          liveTaskResultById && Object.keys(liveTaskResultById).length > 0
            ? Object.fromEntries(
                Object.entries(liveTaskResultById).map(([taskId, result]) => [
                  taskId,
                  typeof result === "string"
                    ? truncateText(result, 12000)
                    : String(result ?? ""),
                ])
              )
            : undefined;

        const snapshot: RunSnapshot = {
          todos: [...todosWithLiveStatus],
          toolCalls: [],
          toolCallsByTask,
          taskResultsById,
          phases: snapshotPhases,
          totalDuration: endTime - startTime,
          reasoning: answerReasoning
            ? truncateText(answerReasoning, 12000)
            : undefined,
          planningReasoning: planningReasoning
            ? truncateText(planningReasoning, 12000)
            : undefined,
          reviewText: reviewText ? truncateText(reviewText, 12000) : undefined,
          finalAnswerText: rawAnswer ? truncateText(rawAnswer, 1600) : undefined,
        };

        setSnapshots((prev) => ({
          ...prev,
          [lastAi.id]: snapshot,
        }));
      }
    }
    prevIsLoadingRef.current = isLoading;
  }, [
    isLoading,
    phase,
    messages,
    todosWithLiveStatus,
    phases,
    liveToolCallsByTask,
    liveTaskResultById,
    livePlanningReasoning,
    liveAnswerReasoning,
    liveReviewContent,
  ]);

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      if (e) e.preventDefault();
      const messageText = input.trim();
      if (!messageText || isLoading) return;
      sendMessage(messageText);
      setInput("");
    },
    [input, isLoading, sendMessage]
  );

  const handleSuggestionSend = useCallback(
    (text: string) => {
      if (isLoading) return;
      sendMessage(text);
    },
    [isLoading, sendMessage]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (isLoading) return;
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit, isLoading]
  );

  // Build displayed messages
  const processedMessages = useMemo(() => {
    return messages.map((msg, index) => {
      const snapshot = msg.id ? snapshots[msg.id] : undefined;
      return {
        message: msg,
        toolCalls: EMPTY_TOOL_CALLS,
        sourceIndex: index,
        renderKey: msg.id ?? `msg-${index}-${msg.type}`,
        snapshot,
      };
    });
  }, [messages, snapshots]);

  const ghostStreamingContent = useMemo(() => {
    if (liveAnswerContent.trim()) return liveAnswerContent;
    return null;
  }, [liveAnswerContent]);

  const ghostStreamingReasoning = useMemo(() => {
    if (liveAnswerReasoning.trim()) return liveAnswerReasoning;
    return null;
  }, [liveAnswerReasoning]);

  const ghostPlanningReasoning = useMemo(() => {
    if (livePlanningReasoning.trim()) return livePlanningReasoning;
    return null;
  }, [livePlanningReasoning]);

  const ghostReviewContent = useMemo(() => {
    if (!isLoading) return null;
    const stripped = liveReviewContent.trim();
    return stripped || null;
  }, [isLoading, liveReviewContent]);

  const groupedTodos = useMemo(() => ({
    in_progress: todosWithLiveStatus.filter((t) => t.status === "in_progress"),
    pending: todosWithLiveStatus.filter((t) => t.status === "pending"),
    completed: todosWithLiveStatus.filter((t) => t.status === "completed"),
  }), [todosWithLiveStatus]);

  const hasTasks = todosWithLiveStatus.length > 0;
  const hasMessages = messages.length > 0;

  const getStatusIcon = (status: TodoItem["status"], className?: string) => {
    switch (status) {
      case "completed":
        return (
          <CheckCircle
            size={16}
            className={cn("text-success/80", className)}
          />
        );
      case "in_progress":
        return (
          <Clock
            size={16}
            className={cn("text-warning/80", className)}
          />
        );
      default:
        return (
          <Circle
            size={16}
            className={cn("text-muted-foreground/70", className)}
          />
        );
    }
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div
        className="flex-1 overflow-y-auto overflow-x-hidden overscroll-contain"
        ref={scrollRef}
      >
        <div
          className="mx-auto w-full max-w-[1024px] px-6 pb-6 pt-4"
          ref={contentRef}
        >
          {isSessionLoading ? (
            <div className="flex items-center justify-center p-8">
              <p className="text-muted-foreground">Loading...</p>
            </div>
          ) : !hasMessages && !isLoading ? (
            <WelcomePage onSend={handleSuggestionSend} />
          ) : (
            <>
              {processedMessages.map((data) => (
                <ChatMessage
                  key={data.renderKey}
                  message={data.message}
                  toolCalls={data.toolCalls}
                  isLoading={isLoading}
                  snapshot={data.snapshot}
                />
              ))}
              <GhostMessage
                phase={phase}
                todos={todosWithLiveStatus}
                iteration={iteration}
                planningReasoning={ghostPlanningReasoning}
                streamingReviewContent={ghostReviewContent}
                streamingReasoning={ghostStreamingReasoning}
                streamingContent={ghostStreamingContent}
                subTaskCards={
                  todosWithLiveStatus.length > 0 ? (
                    <div className="grid grid-cols-1 gap-4 pt-2 md:grid-cols-2">
                      {todosWithLiveStatus.map((todo) => (
                        <SubTaskCard
                          key={todo.id}
                          todo={todo}
                          toolCalls={liveToolCallsByTask[todo.id] ?? []}
                          result={liveTaskResultById[todo.id]}
                        />
                      ))}
                    </div>
                  ) : undefined
                }
              />
            </>
          )}
        </div>
      </div>

      <div className="flex-shrink-0 bg-gradient-to-t from-background via-background to-transparent pt-2">
        <div
          className={cn(
            "mx-auto mb-6 flex w-[calc(100%-32px)] max-w-[1024px] flex-shrink-0 flex-col overflow-hidden",
            "rounded-2xl border border-border/60 bg-card/80 shadow-lg shadow-[var(--color-shadow)] backdrop-blur-sm",
            "transition-all duration-200 focus-within:border-primary/30 focus-within:ring-2 focus-within:ring-primary/10"
          )}
        >
          {hasTasks && (
            <div className="flex max-h-72 flex-col overflow-y-auto border-b border-border/40 bg-sidebar/50 empty:hidden">
              {!metaOpen && (
                <>
                  {(() => {
                    const activeTask = todosWithLiveStatus.find(
                      (t) => t.status === "in_progress"
                    );

                    const totalTasks = todosWithLiveStatus.length;
                    const remainingTasks =
                      totalTasks - groupedTodos.pending.length;
                    const isCompleted = totalTasks === remainingTasks;

                    const tasksTrigger = (() => {
                      if (!hasTasks) return null;
                      return (
                        <button
                          type="button"
                          onClick={() =>
                            setMetaOpen((prev) =>
                              prev === "tasks" ? null : "tasks"
                            )
                          }
                          className="grid w-full cursor-pointer grid-cols-[auto_auto_1fr] items-center gap-3 px-[18px] py-3 text-left"
                          aria-expanded={metaOpen === "tasks"}
                        >
                          {(() => {
                            if (isCompleted) {
                              return [
                                <CheckCircle
                                  key="icon"
                                  size={16}
                                  className="text-success/80"
                                />,
                                <span
                                  key="label"
                                  className="ml-[1px] min-w-0 truncate text-sm"
                                >
                                  All tasks completed
                                </span>,
                              ];
                            }

                            if (activeTask != null) {
                              return [
                                <div key="icon">
                                  {getStatusIcon(activeTask.status)}
                                </div>,
                                <span
                                  key="label"
                                  className="ml-[1px] min-w-0 truncate text-sm"
                                >
                                  Task{" "}
                                  {totalTasks - groupedTodos.pending.length} of{" "}
                                  {totalTasks}
                                </span>,
                                <span
                                  key="content"
                                  className="min-w-0 gap-2 truncate text-sm text-muted-foreground"
                                >
                                  {activeTask.content}
                                </span>,
                              ];
                            }

                            return [
                              <Circle
                                key="icon"
                                size={16}
                                className="text-muted-foreground/70"
                              />,
                              <span
                                key="label"
                                className="ml-[1px] min-w-0 truncate text-sm"
                              >
                                Task {totalTasks - groupedTodos.pending.length}{" "}
                                of {totalTasks}
                              </span>,
                            ];
                          })()}
                        </button>
                      );
                    })();

                    return (
                      <div className="grid grid-cols-[1fr] items-center">
                        {tasksTrigger}
                      </div>
                    );
                  })()}
                </>
              )}

              {metaOpen && (
                <>
                  <div className="sticky top-0 flex items-stretch bg-sidebar/50 text-sm">
                    {hasTasks && (
                      <button
                        type="button"
                        className="py-3 pr-4 first:pl-[18px] aria-expanded:font-semibold"
                        onClick={() =>
                          setMetaOpen((prev) =>
                            prev === "tasks" ? null : "tasks"
                          )
                        }
                        aria-expanded={metaOpen === "tasks"}
                      >
                        Tasks
                      </button>
                    )}
                    <button
                      aria-label="Close"
                      className="flex-1"
                      onClick={() => setMetaOpen(null)}
                    />
                  </div>
                  <div
                    ref={tasksContainerRef}
                    className="px-[18px]"
                  >
                    {metaOpen === "tasks" &&
                      Object.entries(groupedTodos)
                        .filter(([_, todos]) => todos.length > 0)
                        .map(([status, todos]) => (
                          <div
                            key={status}
                            className="mb-4"
                          >
                            <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                              {
                                {
                                  pending: "Pending",
                                  in_progress: "In Progress",
                                  completed: "Completed",
                                }[status]
                              }
                            </h3>
                            <div className="grid grid-cols-[auto_1fr] gap-3 rounded-sm p-1 pl-0 text-sm">
                              {todos.map((todo, index) => (
                                <Fragment key={`${status}_${todo.id}_${index}`}>
                                  {getStatusIcon(todo.status, "mt-0.5")}
                                  <span className="break-words text-inherit">
                                    {todo.content}
                                  </span>
                                </Fragment>
                              ))}
                            </div>
                          </div>
                        ))}
                  </div>
                </>
              )}
            </div>
          )}
          <form
            onSubmit={handleSubmit}
            className="flex flex-col"
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isLoading ? "Running..." : "Ask about algorithms..."}
              className="font-inherit field-sizing-content flex-1 resize-none border-0 bg-transparent px-[18px] pb-3 pt-4 text-sm leading-7 text-foreground outline-none placeholder:text-muted-foreground/60"
              rows={1}
            />
            <div className="flex items-center justify-end gap-2 px-3 pb-3">
              {isLoading ? (
                <button
                  type="button"
                  onClick={stopStream}
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-destructive text-white transition-colors hover:bg-destructive/90"
                >
                  <Square size={14} />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={isLoading || !input.trim()}
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-r from-[#49b1f5] to-[#62bfff] dark:from-[#2080c0] dark:to-[#3090d0] text-white transition-all hover:from-[#1892ff] hover:to-[#49b1f5] hover:shadow-md disabled:opacity-40 disabled:hover:shadow-none"
                >
                  <ArrowUp size={16} />
                </button>
              )}
            </div>
          </form>
        </div>
      </div>
    </div>
  );
});

ChatInterface.displayName = "ChatInterface";
