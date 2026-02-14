"use client";

import React, { useState, useEffect } from "react";
import { Clock } from "lucide-react";
import { cn } from "@/lib/utils";

interface LiveTimerProps {
  startTime: number | null;
  endTime?: number | null;
  isRunning: boolean;
  className?: string;
  compact?: boolean;
}

export const LiveTimer = React.memo<LiveTimerProps>(
  ({ startTime, endTime, isRunning, className, compact }) => {
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
      let interval: ReturnType<typeof setInterval>;

      if (isRunning && startTime) {
        setElapsed(Date.now() - startTime);
        interval = setInterval(() => {
          setElapsed(Date.now() - startTime);
        }, 250);
      } else if (!isRunning && startTime && endTime) {
        setElapsed(endTime - startTime);
      } else {
        setElapsed(0);
      }

      return () => clearInterval(interval);
    }, [isRunning, startTime, endTime]);

    if (!startTime) return null;

    const seconds = (elapsed / 1000).toFixed(1);

    if (compact) {
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground",
            className
          )}
        >
          {seconds}s
        </span>
      );
    }

    return (
      <div
        className={cn(
          "flex items-center gap-1.5 rounded-lg bg-muted px-2 py-1 font-mono text-xs text-muted-foreground",
          className
        )}
      >
        <Clock size={12} className="text-primary" />
        <span>{seconds}s</span>
      </div>
    );
  }
);

LiveTimer.displayName = "LiveTimer";
