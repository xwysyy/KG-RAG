"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Brain, ChevronDown, ChevronRight, Copy, Check } from "lucide-react";
import { MarkdownContent } from "@/app/components/MarkdownContent";
import { cn } from "@/lib/utils";

interface ReasoningBlockProps {
  content: string;
  isStreaming?: boolean;
  defaultOpen?: boolean;
  durationSeconds?: number;
  title?: string;
  compact?: boolean;
}

export const ReasoningBlock = React.memo<ReasoningBlockProps>(
  ({
    content,
    isStreaming = false,
    defaultOpen,
    durationSeconds,
    title,
    compact = false,
  }) => {
    const [isOpen, setIsOpen] = useState(
      defaultOpen ?? (isStreaming ? true : false)
    );
    const [copied, setCopied] = useState(false);
    const [elapsed, setElapsed] = useState<number | null>(null);
    const startTimeRef = useRef<number>(Date.now());

    // Track streaming duration
    useEffect(() => {
      if (!isStreaming) {
        setElapsed(
          typeof durationSeconds === "number" && Number.isFinite(durationSeconds)
            ? durationSeconds
            : null
        );
        return;
      }

      startTimeRef.current = Date.now();
      const timer = setInterval(() => {
        setElapsed((Date.now() - startTimeRef.current) / 1000);
      }, 250);
      return () => clearInterval(timer);
    }, [isStreaming, durationSeconds]);

    // Auto-collapse when streaming ends
    useEffect(() => {
      if (!isStreaming && defaultOpen === undefined) {
        setIsOpen(false);
      }
    }, [isStreaming, defaultOpen]);

    const handleCopy = useCallback(async () => {
      try {
        await navigator.clipboard.writeText(content);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        // silently fail — don't show copied state
      }
    }, [content]);

    const headerLabel =
      title ??
      (isStreaming
        ? "Thinking..."
        : elapsed !== null
          ? `Thought for ${elapsed.toFixed(1)}s`
          : "Thought process");

    return (
      <div
        className={cn(
          compact ? "my-1 rounded-md" : "my-3 rounded-lg",
          "glass-card transition-all duration-300",
          isStreaming && "border-primary/40 shadow-[0_0_10px_hsl(var(--primary)/0.1)]"
        )}
      >
        {/* Header */}
        <div
          onClick={() => setIsOpen((v) => !v)}
          className={cn(
            "flex w-full cursor-pointer items-center gap-2 text-left select-none transition-colors hover:bg-muted/50",
            compact ? "px-2 py-1.5 text-xs" : "px-3 py-2 text-sm",
            "text-muted-foreground"
          )}
        >
          <Brain
            size={compact ? 12 : 14}
            className={cn(
              isStreaming && "animate-pulse-slow text-primary"
            )}
          />
          {isOpen ? (
            <ChevronDown size={compact ? 12 : 14} />
          ) : (
            <ChevronRight size={compact ? 12 : 14} />
          )}
          <span className={cn("font-medium", compact && "text-xs")}>
            {headerLabel}
            {isStreaming && (
              <span
                className={cn(
                  "ml-1 inline-block animate-cursor-blink bg-primary",
                  compact ? "h-3 w-0.5" : "h-3.5 w-1"
                )}
              />
            )}
          </span>

          {/* Copy button (only when collapsed or completed) */}
          {!isStreaming && !compact && (
            <button
              type="button"
              className="ml-auto text-muted-foreground hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation();
                handleCopy();
              }}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          )}
        </div>

        {/* Content */}
        {isOpen && (
          <div
            className={cn(
              "border-t",
              compact
                ? "max-h-32 overflow-y-auto px-2 py-1.5 text-xs leading-relaxed"
                : "px-3 py-2 text-sm leading-relaxed",
              "border-border text-foreground"
            )}
          >
            {isStreaming ? (
              <pre
                className={cn(
                  "m-0 whitespace-pre-wrap break-words font-mono",
                  compact ? "text-[11px] leading-5" : "text-xs leading-relaxed"
                )}
              >
                {content}
              </pre>
            ) : (
              <MarkdownContent content={content} />
            )}
          </div>
        )}
      </div>
    );
  }
);

ReasoningBlock.displayName = "ReasoningBlock";
