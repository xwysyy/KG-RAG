"use client";

import React, { useMemo } from "react";
import dynamic from "next/dynamic";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import { config } from "md-editor-rt";
import hljs from "highlight.js";
import mermaid from "mermaid";
import katex from "katex";
import { g as mdEditorGlobalConfig } from "md-editor-rt/lib/es/chunks/config.mjs";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

const MdPreview = dynamic(
  () => import("md-editor-rt").then((mod) => mod.MdPreview),
  {
    ssr: false,
    loading: () => (
      <div className="text-sm text-muted-foreground">Rendering…</div>
    ),
  }
);

function normalizeMermaidFlowchartLabels(src: string): string {
  const firstMeaningfulLine =
    src
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find((line) => line.length > 0 && !line.startsWith("%%")) ?? "";

  const isFlowchartLike = /^(flowchart|graph)\b/i.test(firstMeaningfulLine);

  if (!isFlowchartLike) return src;

  let out = "";
  let inSingleQuote = false;
  let inDoubleQuote = false;
  let inSquareLabel = false;
  let squareOpenLen: 1 | 2 = 1;
  let nestedSquareDepth = 0;
  let squareLabel = "";
  let sawNestedSquare = false;

  const flushSquareLabel = () => {
    if (squareOpenLen === 2) {
      out += `[[${squareLabel}]]`;
      return;
    }

    const trimmed = squareLabel.trim();
    const alreadyQuoted =
      trimmed.length >= 2 &&
      ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
        (trimmed.startsWith("'") && trimmed.endsWith("'")));

    // If the label is already quoted, or there are no nested brackets, keep it.
    if (!sawNestedSquare || alreadyQuoted) {
      out += `[${squareLabel}]`;
      return;
    }

    // Mermaid-friendly: wrap label in quotes instead of injecting `&#91;`/`&#93;`.
    out += `["${squareLabel.replaceAll('"', '\\"')}"]`;
  };

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
        const next = src[i + 1] ?? "";

        if (src[i + 1] === "[") {
          inSquareLabel = true;
          squareOpenLen = 2;
          nestedSquareDepth = 0;
          squareLabel = "";
          sawNestedSquare = false;
          i += 1;
          continue;
        }

        // Leave other bracket-based shapes alone: `[(...)]`, `[/.../]`, `[\\...\\]`.
        if (next === "(" || next === "/" || next === "\\") {
          out += ch;
          continue;
        }

        inSquareLabel = true;
        squareOpenLen = 1;
        nestedSquareDepth = 0;
        squareLabel = "";
        sawNestedSquare = false;
        continue;
      }

      out += ch;
      continue;
    }

    if (ch === "[") {
      nestedSquareDepth += 1;
      sawNestedSquare = true;
      squareLabel += ch;
      continue;
    }

    if (ch === "]") {
      if (nestedSquareDepth > 0) {
        nestedSquareDepth -= 1;
        squareLabel += ch;
        continue;
      }

      if (squareOpenLen === 2) {
        if (src[i + 1] === "]") {
          flushSquareLabel();
          i += 1;
          inSquareLabel = false;
          continue;
        }
        squareLabel += ch;
        continue;
      }

      flushSquareLabel();
      inSquareLabel = false;
      continue;
    }

    squareLabel += ch;
  }

  if (inSquareLabel) return src;
  return out;
}

const normalizeMathLineBreaks = (src: string): string =>
  src.replace(/(^|[^\\])\\\s*\n/g, "$1\\\\\n");

const decodeMermaidBracketEntities = (src: string): string =>
  src
    .replace(/&(?:amp;)?#(?:91|x5[bB]);/g, "[")
    .replace(/&(?:amp;)?#(?:93|x5[dD]);/g, "]");

const sanitizeMermaidSvg = async (svg: string): Promise<string> =>
  decodeMermaidBracketEntities(svg);

let didConfigure = false;
const ensureMdEditorConfigured = () => {
  if (didConfigure) return;
  didConfigure = true;

  // Prefer local instances (avoid runtime CDN fetches from unpkg).
  mdEditorGlobalConfig.editorExtensions.highlight.instance = hljs;
  mdEditorGlobalConfig.editorExtensions.mermaid.instance = mermaid;
  mdEditorGlobalConfig.editorExtensions.katex.instance = katex;

  config({
    markdownItConfig(md) {
      // Treat assistant/user content as untrusted: disable raw HTML in Markdown.
      md.set({ html: false });

      // Normalize Mermaid + KaTeX sources before rendering.
      md.core.ruler.after("inline", "kg-rag-normalize", (state) => {
        const stack = [...state.tokens];
        while (stack.length > 0) {
          const token = stack.pop();
          if (!token) continue;

          if (token.type === "fence" && token.info?.trim() === "mermaid") {
            token.content = normalizeMermaidFlowchartLabels(token.content);
          }

          if (token.type === "math_block" || token.type === "math_inline") {
            token.content = normalizeMathLineBreaks(token.content);
          }

          if (Array.isArray(token.children)) {
            stack.push(...token.children);
          }
        }

        return true;
      });
    },
    mermaidConfig(mermaidConfig) {
      const prevFlowchart = (mermaidConfig as any).flowchart ?? {};
      return {
        ...mermaidConfig,
        securityLevel: "strict",
        flowchart: {
          ...prevFlowchart,
          htmlLabels: true,
        },
      };
    },
  });
};

export const MarkdownContent = React.memo<MarkdownContentProps>(
  ({ content, className }) => {
    ensureMdEditorConfigured();

    const { resolvedTheme } = useTheme();
    const theme = resolvedTheme === "dark" ? "dark" : "light";
    const value = useMemo(() => content ?? "", [content]);

    return (
      <div
        className={cn(
          // Keep layout constraints consistent with chat bubbles/cards.
          "min-w-0 max-w-full overflow-hidden break-words text-sm leading-relaxed",
          className
        )}
      >
        <MdPreview
          value={value}
          theme={theme}
          previewTheme="github"
          codeTheme="github"
          sanitizeMermaid={sanitizeMermaidSvg}
        />
      </div>
    );
  }
);

MarkdownContent.displayName = "MarkdownContent";
