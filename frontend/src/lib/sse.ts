import type { SSEEvent } from "@/app/types/types";

export async function* parseSSEStream(
  response: Response
): AsyncGenerator<SSEEvent> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Normalize \r\n to \n for cross-platform SSE compatibility
      buffer = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

      // Split on double newline (SSE event boundary)
      const parts = buffer.split("\n\n");
      // Keep the last incomplete part in the buffer
      buffer = parts.pop() || "";

      for (const part of parts) {
        if (!part.trim()) continue;

        let eventType = "message";
        const dataLines: string[] = [];

        for (const line of part.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataLines.push(line.slice(6));
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5));
          }
        }

        // Per SSE spec, multiple data lines are joined with \n
        const dataStr = dataLines.join("\n");

        if (!dataStr) continue;

        try {
          const data = JSON.parse(dataStr);
          yield { event: eventType, data } as SSEEvent;
        } catch {
          // Skip malformed JSON
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
