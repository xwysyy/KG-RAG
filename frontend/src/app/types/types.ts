export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  /** Optional tool-call "thought" content emitted alongside the call. */
  thought?: string;
  result?: string;
  status: "pending" | "completed" | "error" | "interrupted";
}

export interface SubAgent {
  id: string;
  name: string;
  subAgentName: string;
  input: Record<string, unknown>;
  output?: Record<string, unknown>;
  status: "pending" | "active" | "completed" | "error";
}

export interface FileItem {
  path: string;
  content: string;
}

export interface TodoItem {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed";
  updatedAt?: Date;
}

export interface Thread {
  id: string;
  title: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface InterruptData {
  value: any;
  ns?: string[];
  scope?: string;
}

export interface ActionRequest {
  name: string;
  args: Record<string, unknown>;
  description?: string;
}

export interface ReviewConfig {
  actionName: string;
  allowedDecisions?: string[];
}

export interface ToolApprovalInterruptData {
  action_requests: ActionRequest[];
  review_configs?: ReviewConfig[];
}

export type AgentPhase = 'idle' | 'planning' | 'executing' | 'reviewing' | 'answering' | 'completed';

export interface PhaseTimestamp {
  phase: AgentPhase;
  startTime: number;
  endTime?: number;
}

export interface RunSnapshot {
  todos: TodoItem[];
  toolCalls: ToolCall[];
  phases: PhaseTimestamp[];
  totalDuration: number;
  reasoning?: string;
  /** Planning-phase reasoning text (streamed). */
  planningReasoning?: string;
  /** Reviewing-phase judge/verdict text (streamed). */
  reviewText?: string;
  /** Truncated final answer preview for replay UI. */
  finalAnswerText?: string;
  /** Tool calls grouped by sub-task id for replay. */
  toolCallsByTask?: Record<string, ToolCall[]>;
  /** Final sub-task results by sub-task id for replay. */
  taskResultsById?: Record<string, string>;
}

// --- SSE / REST API types ---

export type ContentPart = {
  type?: string;
  text?: string;
  content?: string;
  value?: string;
  [key: string]: unknown;
};

export interface Message {
  id: string;
  type: "human" | "ai" | "tool";
  content: string | ContentPart[];
  tool_calls?: ToolCallObj[];
  additional_kwargs?: Record<string, unknown>;
  response_metadata?: Record<string, unknown>;
  name?: string;
  tool_call_id?: string;
}

export interface ToolCallObj {
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
  function?: { name?: string; arguments?: unknown };
  type?: string;
  input?: unknown;
}

export interface Session {
  session_id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message?: string | null;
}

export interface MessageResponse {
  message_id: number;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
}

export type CustomEvent = Record<string, unknown>;

export type SSEEvent =
  | { event: "metadata"; data: { session_id: string; user_message: MessageResponse } }
  | { event: "state"; data: { phase: AgentPhase; todos: TodoItem[]; final_answer: string; iteration: number } }
  | { event: "custom"; data: CustomEvent }
  | { event: "done"; data: { assistant_message: MessageResponse; final_answer: string } }
  | { event: "error"; data: { detail: string } };
