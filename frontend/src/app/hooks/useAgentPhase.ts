"use client";

import { useRef, useEffect } from "react";
import type { AgentPhase, PhaseTimestamp } from "@/app/types/types";

interface UseAgentPhaseOptions {
  phase: AgentPhase;
}

export function useAgentPhase({ phase }: UseAgentPhaseOptions) {
  const phasesRef = useRef<PhaseTimestamp[]>([]);
  const processStartTimeRef = useRef<number | null>(null);
  const processEndTimeRef = useRef<number | null>(null);
  const prevPhaseRef = useRef<AgentPhase>("idle");

  useEffect(() => {
    const prev = prevPhaseRef.current;
    prevPhaseRef.current = phase;

    if (phase === "idle") {
      return;
    }

    const now = Date.now();

    if (phase === "planning") {
      // Detect new run: reset if coming from idle/completed or if phases
      // already contain a completed planning phase (re-run scenario).
      const needsReset =
        prev === "idle" ||
        prev === "completed" ||
        phasesRef.current.length === 0 ||
        phasesRef.current.some((p) => p.phase === "planning" && p.endTime);

      if (needsReset) {
        phasesRef.current = [{ phase: "planning", startTime: now }];
        processStartTimeRef.current = now;
        processEndTimeRef.current = null;
        return;
      }
    }

    if (phase === "completed") {
      processEndTimeRef.current = now;
      const last = phasesRef.current[phasesRef.current.length - 1];
      if (last && !last.endTime) {
        last.endTime = now;
      }
      return;
    }

    // Transition to a different active phase
    const phases = phasesRef.current;
    const last = phases[phases.length - 1];
    if (last && last.phase !== phase) {
      if (!last.endTime) {
        last.endTime = now;
      }
      phases.push({ phase, startTime: now });
    }
  }, [phase]);

  return {
    phase,
    phases: phasesRef.current,
    processStartTime: processStartTimeRef.current,
    processEndTime: processEndTimeRef.current,
  };
}
