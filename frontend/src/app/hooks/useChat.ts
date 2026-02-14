"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import type {
  TodoItem,
  ToolCall,
  Message,
  AgentPhase,
  MessageResponse,
} from "@/app/types/types";
import { api } from "@/lib/api";
import { parseSSEStream } from "@/lib/sse";
import { useQueryState } from "nuqs";

export type StateType = {
  messages: Message[];
  todos: TodoItem[];
  files: Record<string, string>;
  user_profile?: string;
  intermediate_results?: string[];
  final_answer?: string;
  iteration?: number;
};

const asRecord = (value: unknown): Record<string, unknown> | null => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
};

const asString = (value: unknown): string | undefined => {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
};

const pickFirstString = (...values: unknown[]): string | undefined => {
  for (const value of values) {
    const str = asString(value);
    if (str) return str;
  }
  return undefined;
};

/** Like asString but preserves leading/trailing whitespace (for streaming deltas). */
const asRawString = (value: unknown): string | undefined => {
  if (typeof value !== "string") return undefined;
  return value || undefined;
};

const pickFirstRawString = (...values: unknown[]): string | undefined => {
  for (const value of values) {
    const str = asRawString(value);
    if (str) return str;
  }
  return undefined;
};

const normalizeTaskStatus = (value: unknown): TodoItem["status"] | undefined => {
  const status = asString(value)?.toLowerCase();
  if (!status) return undefined;
  if (status === "in_progress" || status === "pending" || status === "completed") {
    return status;
  }
  return undefined;
};

const normalizeToolCallStatus = (value: unknown): ToolCall["status"] | undefined => {
  const status = asString(value)?.toLowerCase();
  if (!status) return undefined;
  if (status === "pending" || status === "completed" || status === "error" || status === "interrupted") {
    return status;
  }
  if (status === "success") return "completed";
  if (status === "failed") return "error";
  return undefined;
};

type NormalizedSubtaskEvent =
  | { type: "subtask_status"; subTaskId: string; status: TodoItem["status"] }
  | { type: "subtask_tool_call"; subTaskId: string; toolCall: Record<string, unknown> }
  | { type: "subtask_result"; subTaskId: string; result: string };

type ReasoningScope = "planning" | "answering";
type ContentScope = "answering" | "reviewing";

type NormalizedReasoningEvent =
  | { type: "reasoning_reset"; scope: ReasoningScope }
  | { type: "reasoning_delta"; scope: ReasoningScope; delta: string }
  | { type: "content_reset"; scope: ContentScope }
  | {
      type: "content_delta";
      scope: ContentScope;
      delta: string;
    };

type NormalizedCustomEvent = NormalizedSubtaskEvent | NormalizedReasoningEvent;

const normalizeReasoningScope = (value: unknown): ReasoningScope | undefined => {
  const scope = asString(value)?.toLowerCase();
  if (scope === "planning" || scope === "answering") {
    return scope;
  }
  return undefined;
};

const normalizeContentScope = (value: unknown): ContentScope | undefined => {
  const scope = asString(value)?.toLowerCase();
  if (scope === "answering" || scope === "reviewing") {
    return scope;
  }
  return undefined;
};

const normalizeSubtaskEvent = (rawEvent: unknown): NormalizedCustomEvent | null => {
  const stack: unknown[] = [rawEvent];
  const visited = new Set<unknown>();

  while (stack.length > 0) {
    const current = stack.pop();
    if (current == null || visited.has(current)) continue;
    visited.add(current);

    const rec = asRecord(current);
    if (!rec) {
      if (Array.isArray(current)) {
        for (const item of current) stack.push(item);
      }
      continue;
    }

    const data = asRecord(rec.data) ?? asRecord(rec.payload) ?? null;
    const type = pickFirstString(rec.type, rec.event, data?.type, data?.event)?.toLowerCase();

    const subTaskId = pickFirstString(
      rec.sub_task_id,
      rec.subTaskId,
      rec.task_id,
      rec.todo_id,
      data?.sub_task_id,
      data?.subTaskId,
      data?.task_id,
      data?.todo_id,
      rec.id,
      data?.id
    );

    if (type === "subtask_status" && subTaskId) {
      const status = normalizeTaskStatus(rec.status ?? data?.status ?? rec.state ?? data?.state);
      if (!status) return null;
      return { type, subTaskId, status };
    }

    if (type === "subtask_tool_call" && subTaskId) {
      const toolCall =
        asRecord(rec.tool_call) ??
        asRecord(rec.toolCall) ??
        asRecord(data?.tool_call) ??
        asRecord(data?.toolCall) ??
        asRecord(rec.call) ??
        asRecord(data?.call);
      if (!toolCall) return null;
      return { type, subTaskId, toolCall };
    }

    if (type === "subtask_result" && subTaskId) {
      const result = pickFirstRawString(rec.result, data?.result, rec.output, data?.output, rec.text, data?.text);
      if (!result) return null;
      return { type, subTaskId, result };
    }

    if (type === "reasoning_reset") {
      const scope = normalizeReasoningScope(rec.scope ?? data?.scope);
      if (!scope) return null;
      return { type, scope };
    }

    if (type === "reasoning_delta") {
      const scope = normalizeReasoningScope(rec.scope ?? data?.scope);
      const delta = pickFirstRawString(rec.delta, data?.delta, rec.content, data?.content, rec.text, data?.text);
      if (!scope || !delta) return null;
      return { type, scope, delta };
    }

    if (type === "content_reset") {
      const scope = normalizeContentScope(rec.scope ?? data?.scope);
      if (!scope) return null;
      return { type, scope };
    }

    if (type === "content_delta") {
      const scope = normalizeContentScope(rec.scope ?? data?.scope);
      const delta = pickFirstRawString(rec.delta, data?.delta, rec.content, data?.content, rec.text, data?.text);
      if (!scope || !delta) return null;
      return { type, scope, delta };
    }

    if (rec.data !== undefined) stack.push(rec.data);
    if (rec.payload !== undefined) stack.push(rec.payload);
    if (rec.detail !== undefined) stack.push(rec.detail);
    if (rec.custom !== undefined) stack.push(rec.custom);
    if (rec.value !== undefined) stack.push(rec.value);
    if (rec.event !== undefined && typeof rec.event !== "string") stack.push(rec.event);
  }

  return null;
};

export function useChat({
  onHistoryRevalidate,
}: {
  onHistoryRevalidate?: () => void;
}) {
  const [sessionId, setSessionId] = useQueryState("sessionId");

  // Core state
  const [messages, setMessages] = useState<Message[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [finalAnswer, setFinalAnswer] = useState<string | undefined>(undefined);
  const [iteration, setIteration] = useState<number | undefined>(undefined);
  const [phase, setPhase] = useState<AgentPhase>("idle");
  const [isLoading, setIsLoading] = useState(false);
  const [isSessionLoading, setIsSessionLoading] = useState(false);

  // Live streaming state
  const [liveToolCallsByTask, setLiveToolCallsByTask] = useState<
    Record<string, ToolCall[]>
  >({});
  const [liveTaskStatusById, setLiveTaskStatusById] = useState<
    Record<string, TodoItem["status"]>
  >({});
  const [liveTaskResultById, setLiveTaskResultById] = useState<
    Record<string, string>
  >({});
  const [livePlanningReasoning, setLivePlanningReasoning] = useState("");
  const [liveAnswerReasoning, setLiveAnswerReasoning] = useState("");
  const [liveAnswerContent, setLiveAnswerContent] = useState("");
  const [liveReviewContent, setLiveReviewContent] = useState("");

  const abortRef = useRef<AbortController | null>(null);
  // Guard: when true, the sessionId-change effect skips message loading
  const streamingRef = useRef(false);

  // Reset live state
  const resetLiveState = useCallback(() => {
    setLiveToolCallsByTask({});
    setLiveTaskStatusById({});
    setLiveTaskResultById({});
    setLivePlanningReasoning("");
    setLiveAnswerReasoning("");
    setLiveAnswerContent("");
    setLiveReviewContent("");
  }, []);

  // Load session messages when sessionId changes (only when NOT streaming)
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      setTodos([]);
      setFinalAnswer(undefined);
      setIteration(undefined);
      setPhase("idle");
      resetLiveState();
      return;
    }

    // Skip loading if we're in the middle of sending a message
    // (sendMessage sets sessionId then immediately starts streaming)
    if (streamingRef.current) return;

    // Abort any in-flight stream when switching sessions
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
      setIsLoading(false);
    }

    let cancelled = false;
    setIsSessionLoading(true);

    api
      .getSessionMessages(sessionId)
      .then((data) => {
        if (cancelled) return;
        // Convert MessageResponse[] to Message[]
        const msgs: Message[] = data.messages.map((m) => ({
          id: `msg-${m.message_id}`,
          type: m.role === "user" ? "human" : "ai",
          content: m.content,
        }));
        setMessages(msgs);
        setPhase("idle");
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("Failed to load session messages:", err);
      })
      .finally(() => {
        if (!cancelled) setIsSessionLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId, resetLiveState]);

  // Handle custom event from SSE
  const handleCustomEvent = useCallback((eventData: unknown) => {
    const evt = normalizeSubtaskEvent(eventData);
    if (!evt) return;

    if (evt.type === "subtask_status") {
      setLiveTaskStatusById((prev) => ({ ...prev, [evt.subTaskId]: evt.status }));
      return;
    }

    if (evt.type === "subtask_tool_call") {
      const toolCall = evt.toolCall;
      const id = String(toolCall.id ?? "");
      if (!id) return;

      setLiveToolCallsByTask((prev) => {
        const existing = prev[evt.subTaskId] ?? [];
        const next = existing.slice();
        const idx = next.findIndex((tc) => tc.id === id);

        const updated: ToolCall = {
          id,
          name: String(toolCall.name ?? (idx >= 0 ? next[idx].name : "unknown")),
          args:
            (toolCall.args && typeof toolCall.args === "object"
              ? toolCall.args
              : idx >= 0
                ? next[idx].args
                : {}) as Record<string, unknown>,
          thought:
            typeof toolCall.thought === "string"
              ? toolCall.thought
              : idx >= 0
                ? next[idx].thought
                : undefined,
          status:
            normalizeToolCallStatus(toolCall.status) ??
            (idx >= 0 ? next[idx].status : "pending"),
          result:
            typeof toolCall.result === "string"
              ? toolCall.result
              : idx >= 0
                ? next[idx].result
                : undefined,
        };

        if (idx >= 0) {
          next[idx] = updated;
        } else {
          next.push(updated);
        }

        return { ...prev, [evt.subTaskId]: next };
      });
      return;
    }

    if (evt.type === "subtask_result") {
      setLiveTaskResultById((prev) => ({ ...prev, [evt.subTaskId]: evt.result }));
      return;
    }

    if (evt.type === "reasoning_reset") {
      if (evt.scope === "planning") {
        setLivePlanningReasoning("");
        return;
      }
      setLiveAnswerReasoning("");
      return;
    }

    if (evt.type === "reasoning_delta") {
      if (evt.scope === "planning") {
        setLivePlanningReasoning((prev) => `${prev}${evt.delta}`);
        return;
      }
      setLiveAnswerReasoning((prev) => `${prev}${evt.delta}`);
      return;
    }

    if (evt.type === "content_reset") {
      if (evt.scope === "reviewing") {
        setLiveReviewContent("");
        return;
      }
      setLiveAnswerContent("");
      return;
    }

    if (evt.type === "content_delta") {
      if (evt.scope === "reviewing") {
        setLiveReviewContent((prev) => `${prev}${evt.delta}`);
        return;
      }
      setLiveAnswerContent((prev) => `${prev}${evt.delta}`);
    }
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      // Mark streaming so the sessionId-change effect won't overwrite state
      streamingRef.current = true;

      // If no session, create one first
      let currentSessionId = sessionId;
      if (!currentSessionId) {
        try {
          const session = await api.createSession(content.slice(0, 50));
          currentSessionId = session.session_id;
          await setSessionId(currentSessionId);
        } catch (err) {
          console.error("Failed to create session:", err);
          streamingRef.current = false;
          return;
        }
      }

      // Add optimistic user message
      const userMsg: Message = {
        id: uuidv4(),
        type: "human",
        content,
      };
      setMessages((prev) => [...prev, userMsg]);

      // Reset state for new run
      setTodos([]);
      setFinalAnswer("");
      setIteration(0);
      setPhase("planning");
      setIsLoading(true);
      resetLiveState();

      // Start SSE stream
      const abortController = new AbortController();
      abortRef.current = abortController;

      try {
        const response = await api.chatStream(
          currentSessionId,
          content,
          abortController.signal
        );

        if (!response.ok) {
          const body = await response.text().catch(() => "");
          throw new Error(`SSE request failed: ${response.status} ${body}`);
        }

        for await (const event of parseSSEStream(response)) {
          if (abortController.signal.aborted) break;

          switch (event.event) {
            case "metadata":
              // User message already added optimistically
              break;

            case "state": {
              const stateData = event.data as {
                phase: AgentPhase;
                todos: TodoItem[];
                final_answer: string;
                iteration: number;
              };
              setPhase(stateData.phase);
              setTodos(stateData.todos);
              setFinalAnswer(stateData.final_answer);
              setIteration(stateData.iteration);

              // Update live task statuses from state todos
              const nextStatus: Record<string, TodoItem["status"]> = {};
              for (const todo of stateData.todos) {
                if (todo.id && todo.status) {
                  nextStatus[todo.id] = todo.status;
                }
              }
              if (Object.keys(nextStatus).length > 0) {
                setLiveTaskStatusById((prev) => ({ ...prev, ...nextStatus }));
              }
              break;
            }

            case "custom":
              handleCustomEvent(event.data);
              break;

            case "done": {
              const doneData = event.data as {
                assistant_message: MessageResponse;
                final_answer: string;
              };
              // Add assistant message
              const aiMsg: Message = {
                id: `msg-${doneData.assistant_message.message_id}`,
                type: "ai",
                content: doneData.final_answer,
              };
              setMessages((prev) => [...prev, aiMsg]);
              setFinalAnswer(doneData.final_answer);
              setPhase("completed");
              break;
            }

            case "error": {
              const errorData = event.data as { detail: string };
              console.error("SSE error:", errorData.detail);
              setPhase("completed");
              break;
            }
          }
        }
      } catch (err) {
        if (abortController.signal.aborted) {
          // Intentional abort, not an error
        } else {
          console.error("Stream error:", err);
          setPhase("completed");
        }
      } finally {
        setIsLoading(false);
        streamingRef.current = false;
        abortRef.current = null;
        onHistoryRevalidate?.();
      }
    },
    [sessionId, setSessionId, resetLiveState, handleCustomEvent, onHistoryRevalidate]
  );

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
    setPhase((prev) => (prev === "idle" ? "idle" : "completed"));
  }, []);

  return {
    messages,
    todos,
    finalAnswer,
    iteration,
    phase,
    isLoading,
    isSessionLoading,
    liveToolCallsByTask,
    liveTaskStatusById,
    liveTaskResultById,
    livePlanningReasoning,
    liveAnswerReasoning,
    liveAnswerContent,
    liveReviewContent,
    sendMessage,
    stopStream,
  };
}
