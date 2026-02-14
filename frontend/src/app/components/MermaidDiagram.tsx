"use client";

import React, { useEffect, useId, useMemo, useState } from "react";
import { cn } from "@/lib/utils";

interface MermaidDiagramProps {
  code: string;
  className?: string;
}

const getPrefersDark = () => {
  if (typeof window === "undefined") return false;
  if (typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
};

/**
 * Escape `[` and `]` inside Mermaid node labels to prevent the parser from
 * treating inner brackets as syntax.
 *
 * Mermaid flowcharts use brackets for node shapes (e.g. `A[Label]`). If the
 * label itself contains bracket characters (like `dp[1]`), Mermaid will parse
 * them as nested syntax and fail. We replace inner brackets with HTML entities:
 * `&#91;` for `[` and `&#93;` for `]`.
 */
function escapeBracketsInLabels(src: string): string {
  const BRACKET_OPEN = "&#91;";
  const BRACKET_CLOSE = "&#93;";

  const firstMeaningfulLine =
    src
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line.length > 0 && !line.startsWith("%%")) ?? "";

  const isFlowchartLike = /^(flowchart|graph)\b/i.test(firstMeaningfulLine);

  // For non-flowchart diagrams, keep the transformation conservative and only
  // escape inside explicit quoted labels: `["..."]`.
  if (!isFlowchartLike) {
    return src.replace(
      /(\[")((?:[^"\\]|\\.)*)("\])/g,
      (_, open, content, close) =>
        open +
        String(content)
          .replace(/\[/g, BRACKET_OPEN)
          .replace(/\]/g, BRACKET_CLOSE) +
        close
    );
  }

  let out = "";

  // We only treat square brackets as label delimiters when NOT inside quotes.
  let inSingleQuote = false;
  let inDoubleQuote = false;

  // Square label state: `[ ... ]` or `[[ ... ]]` (subroutine shape).
  let inSquareLabel = false;
  let squareOpenLen: 1 | 2 = 1;
  let nestedSquareDepth = 0;

  for (let i = 0; i < src.length; i += 1) {
    const ch = src[i] ?? "";
    const prev = i > 0 ? (src[i - 1] ?? "") : "";

    if (!inSquareLabel) {
      if (!inSingleQuote && ch === '"' && prev !== "\\") {
        inDoubleQuote = !inDoubleQuote;
        out += ch;
        continue;
      }
      if (!inDoubleQuote && ch === "'" && prev !== "\\") {
        inSingleQuote = !inSingleQuote;
        out += ch;
        continue;
      }

      if (!inSingleQuote && !inDoubleQuote && ch === "[") {
        if (src[i + 1] === "[") {
          inSquareLabel = true;
          squareOpenLen = 2;
          nestedSquareDepth = 0;
          out += "[[";
          i += 1; // consume second `[`
          continue;
        }

        inSquareLabel = true;
        squareOpenLen = 1;
        nestedSquareDepth = 0;
        out += "[";
        continue;
      }

      out += ch;
      continue;
    }

    // Inside square label content: escape any nested `[`/`]`.
    if (ch === "[") {
      nestedSquareDepth += 1;
      out += BRACKET_OPEN;
      continue;
    }

    if (ch === "]") {
      if (nestedSquareDepth > 0) {
        nestedSquareDepth -= 1;
        out += BRACKET_CLOSE;
        continue;
      }

      if (squareOpenLen === 2) {
        // Close `[[...]]` only on a `]]` sequence. A single `]` inside a label
        // is treated as literal text and escaped.
        if (src[i + 1] === "]") {
          out += "]]";
          i += 1; // consume the second `]`
          inSquareLabel = false;
          continue;
        }
        out += BRACKET_CLOSE;
        continue;
      }

      // Close `[...]`.
      out += "]";
      inSquareLabel = false;
      continue;
    }

    out += ch;
  }

  // If we ended mid-label, return original (it's invalid Mermaid anyway and we
  // don't want to produce a misleading transformation).
  if (inSquareLabel) return src;

  return out;
}

export const MermaidDiagram = React.memo<MermaidDiagramProps>(
  ({ code, className }) => {
    const reactId = useId();
    const baseId = useMemo(() => {
      const safe = reactId.replace(/[^a-z0-9_-]/gi, "");
      return `mermaid-${safe || "diagram"}`;
    }, [reactId]);

    const [svg, setSvg] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
      let cancelled = false;
      setSvg(null);
      setError(null);

      const prefersDark = getPrefersDark();

      (async () => {
        // Lazy-load Mermaid only when needed (keeps initial chat rendering fast).
        const mod = await import("mermaid");
        const mermaid: any = (mod as any).default ?? mod;

        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: prefersDark ? "dark" : "default",
          flowchart: {
            htmlLabels: true,
          },
        });

        // Ensure uniqueness across multiple diagrams and re-renders.
        const uniqueId = `${baseId}-${Date.now().toString(36)}`;

        const result = await mermaid.render(uniqueId, escapeBracketsInLabels(code));
        const nextSvg = typeof result === "string" ? result : result?.svg;

        if (!nextSvg) {
          throw new Error("Mermaid returned empty SVG output.");
        }

        if (!cancelled) {
          setSvg(nextSvg);
        }
      })().catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        if (!cancelled) setError(msg);
      });

      return () => {
        cancelled = true;
      };
    }, [baseId, code]);

    if (error) {
      return (
        <div
          className={cn(
            "my-4 rounded-md border border-border bg-muted/30 p-3 text-xs leading-relaxed",
            className
          )}
        >
          <p className="mb-2 font-semibold text-destructive">
            Mermaid render failed
          </p>
          <pre className="m-0 whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-foreground">
            {code}
          </pre>
          <p className="mt-2 text-muted-foreground">{error}</p>
        </div>
      );
    }

    if (!svg) {
      return (
        <div
          className={cn(
            "my-4 rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground",
            className
          )}
        >
          Rendering diagram…
        </div>
      );
    }

    return (
      <div
        className={cn(
          "my-4 overflow-x-auto rounded-md border border-border bg-background p-2 [&_svg]:h-auto [&_svg]:max-w-full",
          className
        )}
      >
        <div
          className="not-prose"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    );
  }
);

MermaidDiagram.displayName = "MermaidDiagram";
