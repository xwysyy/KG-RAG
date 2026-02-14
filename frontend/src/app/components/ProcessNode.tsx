"use client";

import React from "react";
import { Loader2, CheckCircle2, ChevronUp, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

type NodeStatus = "idle" | "active" | "completed";

interface ProcessNodeProps {
  icon: React.ElementType;
  title: string;
  status: NodeStatus;
  subtitle?: string;
  children?: React.ReactNode;
  isExpanded: boolean;
  onToggle: () => void;
}

export const ProcessNode = React.memo<ProcessNodeProps>(
  ({ icon: Icon, title, status, subtitle, children, isExpanded, onToggle }) => {
    const isActive = status === "active";
    const isCompleted = status === "completed";

    return (
      <div
        className={cn(
          "relative z-10 overflow-hidden rounded-xl border transition-all duration-500",
          isActive
            ? "border-[hsl(var(--status-active))] bg-[hsl(var(--status-active)/0.05)] shadow-[0_0_15px_hsl(var(--status-active)/0.15)]"
            : "border-border bg-background"
        )}
      >
        <div
          className="flex cursor-pointer items-center justify-between p-3 transition-colors hover:bg-accent"
          onClick={onToggle}
        >
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full transition-colors duration-300",
                isActive && "animate-pulse-slow bg-[hsl(var(--status-active))] text-white",
                isCompleted && "bg-[hsl(var(--status-completed))] text-white",
                !isActive && !isCompleted && "bg-muted text-muted-foreground"
              )}
            >
              {isActive ? (
                <Loader2 size={16} className="animate-spin" />
              ) : isCompleted ? (
                <CheckCircle2 size={16} />
              ) : (
                <Icon size={16} />
              )}
            </div>
            <div>
              <h3
                className={cn(
                  "text-sm font-semibold",
                  isActive && "text-foreground",
                  isCompleted && "text-foreground",
                  !isActive && !isCompleted && "text-muted-foreground"
                )}
              >
                {title}
              </h3>
              {isActive && (
                <p className="text-xs text-primary">
                  {subtitle || "Processing..."}
                </p>
              )}
            </div>
          </div>
          {children && (
            <div className="text-muted-foreground">
              {isExpanded ? (
                <ChevronUp size={18} />
              ) : (
                <ChevronDown size={18} />
              )}
            </div>
          )}
        </div>

        {isExpanded && children && (
          <div className="border-t border-border bg-accent/50 p-4">
            {children}
          </div>
        )}
      </div>
    );
  }
);

ProcessNode.displayName = "ProcessNode";
