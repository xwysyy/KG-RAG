import type { Message } from "@/app/types/types";
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const DISPLAY_CONTENT_TYPES = new Set([
  "text",
  "text_delta",
  "output_text",
  "output_text_delta",
  "input_text",
  "input_text_delta",
  "markdown",
  "output_markdown",
  "response.output_text",
]);

const REASONING_CONTENT_TYPES = new Set([
  "reasoning",
  "reasoning_delta",
  "reasoning_content",
  "reasoning_text",
  "reasoning_summary",
  "thinking",
  "thinking_delta",
  "analysis",
]);

const NON_DISPLAY_CONTENT_TYPES = new Set([
  "tool_use",
  "tool_call",
  "function_call",
  "image",
  "image_url",
  "input_image",
  "audio",
  "file",
]);

const REACT_TRANSCRIPT_LINE_RE =
  /^\s*(Thought|Action|Action\s*Input|Observation|Final\s*Answer)\s*:/im;

const collectTextStrings = (value: unknown, depth = 0): string[] => {
  if (value == null || depth > 4) return [];
  if (typeof value === "string") return value.trim() ? [value] : [];
  if (typeof value === "number" || typeof value === "boolean") {
    return [String(value)];
  }

  if (Array.isArray(value)) {
    return value.flatMap((item) => collectTextStrings(item, depth + 1));
  }

  if (typeof value !== "object") return [];

  const obj = value as Record<string, unknown>;
  const keysInPriorityOrder = [
    "text",
    "content",
    "value",
    "delta",
    "output_text",
    "input_text",
    "markdown",
    "reasoning_content",
    "reasoning",
    "thinking",
    "analysis",
    "summary",
    "parts",
  ];

  const collected: string[] = [];
  for (const key of keysInPriorityOrder) {
    if (!(key in obj)) continue;
    collected.push(...collectTextStrings(obj[key], depth + 1));
  }
  return collected;
};

const collectTextFromCandidates = (values: unknown[]): string | null => {
  const parts = values.flatMap((value) => collectTextStrings(value));
  if (parts.length === 0) return null;
  const text = parts.join("").trim();
  return text || null;
};

const normalizeContentType = (value: unknown): string | null => {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase();
  return normalized || null;
};

export function extractStringFromMessageContent(message: Message): string {
  if (typeof message.content === "string") {
    return message.content;
  }

  if (!Array.isArray(message.content)) {
    return "";
  }

  const textParts: string[] = [];
  for (const part of message.content) {
    if (typeof part === "string") {
      textParts.push(part);
      continue;
    }
    if (!part || typeof part !== "object") {
      continue;
    }

    const partObj = part as Record<string, unknown>;
    const type = normalizeContentType(partObj.type);

    if (type && REASONING_CONTENT_TYPES.has(type)) continue;
    if (type && NON_DISPLAY_CONTENT_TYPES.has(type)) continue;
    if (type && !DISPLAY_CONTENT_TYPES.has(type)) {
      continue;
    }

    const extracted = collectTextFromCandidates([
      partObj.text,
      partObj.content,
      partObj.value,
      partObj.output_text,
      partObj.input_text,
      partObj.markdown,
      partObj.delta,
    ]);
    if (extracted) {
      textParts.push(extracted);
    }
  }

  return textParts.join("").trim();
}

export function extractSubAgentContent(data: unknown): string {
  if (typeof data === "string") {
    return data;
  }

  if (data && typeof data === "object") {
    const dataObj = data as Record<string, unknown>;

    // Try to extract description first
    if (dataObj.description && typeof dataObj.description === "string") {
      return dataObj.description;
    }

    // Then try prompt
    if (dataObj.prompt && typeof dataObj.prompt === "string") {
      return dataObj.prompt;
    }

    // For output objects, try result
    if (dataObj.result && typeof dataObj.result === "string") {
      return dataObj.result;
    }

    // Fallback to JSON stringification
    return JSON.stringify(data, null, 2);
  }

  // Fallback for any other type
  return JSON.stringify(data, null, 2);
}

export function isPreparingToCallTaskTool(messages: Message[]): boolean {
  const lastMessage = messages[messages.length - 1];
  return (
    (lastMessage.type === "ai" &&
      lastMessage.tool_calls?.some(
        (call: { name?: string }) => call.name === "task"
      )) ||
    false
  );
}

export function formatMessageForLLM(message: Message): string {
  let role: string;
  if (message.type === "human") {
    role = "Human";
  } else if (message.type === "ai") {
    role = "Assistant";
  } else if (message.type === "tool") {
    role = `Tool Result`;
  } else {
    role = message.type || "Unknown";
  }

  const timestamp = message.id ? ` (${message.id.slice(0, 8)})` : "";

  let contentText = "";

  // Extract content text
  if (typeof message.content === "string") {
    contentText = message.content;
  } else if (Array.isArray(message.content)) {
    const textParts: string[] = [];

    message.content.forEach((part: any) => {
      if (typeof part === "string") {
        textParts.push(part);
      } else if (part && typeof part === "object" && part.type === "text") {
        textParts.push(part.text || "");
      }
      // Ignore other types like tool_use in content - we handle tool calls separately
    });

    contentText = textParts.join("\n\n").trim();
  }

  // For tool messages, include additional tool metadata
  if (message.type === "tool") {
    const toolName = (message as any).name || "unknown_tool";
    const toolCallId = (message as any).tool_call_id || "";
    role = `Tool Result [${toolName}]`;
    if (toolCallId) {
      role += ` (call_id: ${toolCallId.slice(0, 8)})`;
    }
  }

  // Handle tool calls from .tool_calls property (for AI messages)
  const toolCallsText: string[] = [];
  if (
    message.type === "ai" &&
    message.tool_calls &&
    Array.isArray(message.tool_calls) &&
    message.tool_calls.length > 0
  ) {
    message.tool_calls.forEach((call: any) => {
      const toolName = call.name || "unknown_tool";
      const toolArgs = call.args ? JSON.stringify(call.args, null, 2) : "{}";
      toolCallsText.push(`[Tool Call: ${toolName}]\nArguments: ${toolArgs}`);
    });
  }

  // Combine content and tool calls
  const parts: string[] = [];
  if (contentText) {
    parts.push(contentText);
  }
  if (toolCallsText.length > 0) {
    parts.push(...toolCallsText);
  }

  if (parts.length === 0) {
    return `${role}${timestamp}: [Empty message]`;
  }

  if (parts.length === 1) {
    return `${role}${timestamp}: ${parts[0]}`;
  }

  return `${role}${timestamp}:\n${parts.join("\n\n")}`;
}

export function formatConversationForLLM(messages: Message[]): string {
  const formattedMessages = messages.map(formatMessageForLLM);
  return formattedMessages.join("\n\n---\n\n");
}

export function isReactTranscriptLike(content: string | null | undefined): boolean {
  if (typeof content !== "string" || !content.trim()) return false;
  return REACT_TRANSCRIPT_LINE_RE.test(content);
}

/** Extract reasoning/thinking content from a message */
export function extractReasoningContent(message: Message): string | null {
  const additional = message.additional_kwargs as Record<string, unknown> | undefined;
  if (additional) {
    const fromAdditional = collectTextFromCandidates([
      additional.reasoning_content,
      additional.reasoning,
      additional.reasoning_text,
      additional.reasoningContent,
      additional.thinking,
      additional.thoughts,
      additional.analysis,
      additional.summary,
    ]);
    if (fromAdditional) {
      return fromAdditional;
    }
  }

  const responseMeta =
    message.response_metadata as Record<string, unknown> | undefined;
  if (responseMeta) {
    const fromResponseMeta = collectTextFromCandidates([
      responseMeta.reasoning_content,
      responseMeta.reasoning,
      responseMeta.reasoning_text,
      responseMeta.reasoningContent,
      responseMeta.thinking,
      responseMeta.analysis,
      responseMeta.summary,
      responseMeta.output,
    ]);
    if (fromResponseMeta) {
      return fromResponseMeta;
    }
  }

  // Some providers put reasoning in content blocks (separate from display text).
  if (Array.isArray(message.content)) {
    const reasoningParts: string[] = [];
    for (const part of message.content) {
      if (!part || typeof part !== "object") continue;
      const partObj = part as Record<string, unknown>;
      const type = normalizeContentType(partObj.type);
      const typeSuggestsReasoning =
        type !== null && REASONING_CONTENT_TYPES.has(type);
      const payloadSuggestsReasoning =
        partObj.reasoning_content != null ||
        partObj.reasoning != null ||
        partObj.reasoning_text != null ||
        partObj.thinking != null ||
        partObj.analysis != null ||
        partObj.summary != null;

      if (!typeSuggestsReasoning && !payloadSuggestsReasoning) continue;

      const extracted = collectTextFromCandidates([
        partObj.reasoning_content,
        partObj.reasoning,
        partObj.reasoning_text,
        partObj.thinking,
        partObj.analysis,
        partObj.summary,
        partObj.text,
        partObj.content,
        partObj.value,
      ]);
      if (extracted) {
        reasoningParts.push(extracted);
      }
    }
    if (reasoningParts.length > 0) {
      return reasoningParts.join("\n\n").trim();
    }
  }

  // Fallback: extract from inline tags.
  const content =
    typeof message.content === "string"
      ? message.content
      : extractStringFromMessageContent(message);
  if (!content) return null;

  const tagMatches = Array.from(
    content.matchAll(/<(think|thinking|analysis|reasoning)>([\s\S]*?)<\/\1>/gi)
  )
    .map((match) => match[2]?.trim())
    .filter((value): value is string => Boolean(value));
  if (tagMatches.length > 0) {
    return tagMatches.join("\n\n");
  }
  return null;
}

/** Strip <think> tags to avoid duplicating reasoning in main content */
export function stripThinkTags(content: string): string {
  return content
    .replace(/<(think|thinking|analysis|reasoning)>[\s\S]*?<\/\1>/gi, "")
    .trim();
}
