"use client";

import { useEffect, useMemo, useRef, useCallback } from "react";
import { format } from "date-fns";
import { X, Plus, MessageSquare, Trash2, History } from "lucide-react";
import { useQueryState } from "nuqs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { SessionItem } from "@/app/hooks/useSessions";
import { useSessions } from "@/app/hooks/useSessions";

const GROUP_LABELS = {
  today: "Today",
  yesterday: "Yesterday",
  week: "This Week",
  older: "Older",
} as const;

function formatTime(date: Date, now = new Date()): string {
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) return format(date, "HH:mm");
  if (days === 1) return "Yesterday";
  if (days < 7) return format(date, "EEEE");
  return format(date, "MM/dd");
}

function LoadingState() {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full rounded-lg" />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="py-10 text-center text-sm text-muted-foreground">
      <p>No chat history yet.</p>
    </div>
  );
}

interface SessionListProps {
  onSessionSelect: (id: string) => void;
  onNewChat: () => void;
  onMutateReady?: (mutate: () => void) => void;
  onClose?: () => void;
}

export function SessionList({
  onSessionSelect,
  onNewChat,
  onMutateReady,
  onClose,
}: SessionListProps) {
  const [currentSessionId] = useQueryState("sessionId");
  const sessions = useSessions({ limit: 50 });

  const items = useMemo(() => sessions.data ?? [], [sessions.data]);
  const isEmpty = items.length === 0 && !sessions.isLoading;

  const grouped = useMemo(() => {
    const now = new Date();
    const groups: Record<keyof typeof GROUP_LABELS, SessionItem[]> = {
      today: [],
      yesterday: [],
      week: [],
      older: [],
    };

    items.forEach((session) => {
      const diff = now.getTime() - session.updatedAt.getTime();
      const days = Math.floor(diff / (1000 * 60 * 60 * 24));

      if (days === 0) groups.today.push(session);
      else if (days === 1) groups.yesterday.push(session);
      else if (days < 7) groups.week.push(session);
      else groups.older.push(session);
    });

    return groups;
  }, [items]);

  // Expose revalidation to parent
  const onMutateReadyRef = useRef(onMutateReady);
  const mutateRef = useRef(sessions.mutate);

  useEffect(() => {
    onMutateReadyRef.current = onMutateReady;
  }, [onMutateReady]);

  useEffect(() => {
    mutateRef.current = sessions.mutate;
  }, [sessions.mutate]);

  const mutateFn = useCallback(() => {
    mutateRef.current();
  }, []);

  useEffect(() => {
    onMutateReadyRef.current?.(mutateFn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = useCallback(
    async (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        await api.deleteSession(id);
        sessions.mutate();
      } catch {
        // ignore
      }
    },
    [sessions]
  );

  return (
    <div className="absolute inset-0 flex h-full flex-col border-r border-border/50 bg-sidebar">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-border/40 p-4">
        <div className="flex items-center gap-2 font-semibold text-foreground">
          <History size={18} />
          <span>History</span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <X size={20} />
          </button>
        )}
      </div>

      {/* New Chat Button */}
      <div className="shrink-0 p-4">
        <button
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 px-4 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90"
        >
          <Plus size={16} />
          New Chat
        </button>
      </div>

      {/* Session List */}
      <ScrollArea className="h-0 flex-1">
        {sessions.error && (
          <div className="p-8 text-center">
            <p className="text-sm text-destructive">Failed to load sessions</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {sessions.error.message}
            </p>
          </div>
        )}

        {!sessions.error && !sessions.data && sessions.isLoading && (
          <LoadingState />
        )}

        {!sessions.error && !sessions.isLoading && isEmpty && <EmptyState />}

        {!sessions.error && !isEmpty && (
          <div className="space-y-1 px-3 pb-4">
            {(
              Object.keys(GROUP_LABELS) as Array<keyof typeof GROUP_LABELS>
            ).map((group) => {
              const groupSessions = grouped[group];
              if (groupSessions.length === 0) return null;

              return (
                <div key={group}>
                  <h4 className="px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                    {GROUP_LABELS[group]}
                  </h4>
                  {groupSessions.map((session) => {
                    const isActive = currentSessionId === session.id;
                    return (
                      <div
                        key={session.id}
                        onClick={() => onSessionSelect(session.id)}
                        className={cn(
                          "group relative flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-all",
                          isActive
                            ? "border-border bg-card text-foreground shadow-sm"
                            : "border-transparent text-muted-foreground hover:bg-accent"
                        )}
                      >
                        <MessageSquare
                          size={16}
                          className={cn(
                            "shrink-0",
                            isActive ? "text-primary" : "text-muted-foreground/40"
                          )}
                        />
                        <div className="min-w-0 flex-1">
                          <h4 className="truncate pr-6 text-sm font-medium text-foreground">
                            {session.title}
                          </h4>
                          <span className="text-[10px] text-muted-foreground/60">
                            {formatTime(session.updatedAt)}
                          </span>
                        </div>

                        {/* Hover-reveal delete button */}
                        <button
                          onClick={(e) => handleDelete(session.id, e)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground/40 opacity-0 transition-all hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
