"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { getUser, clearAuth, isAuthenticated } from "@/lib/auth";
import { graphApi } from "@/lib/graph-api";
import type { GraphNode, GraphOverview } from "@/lib/graph-api";
import type { GraphViewerHandle } from "@/app/components/graph/GraphViewer";
import { Button } from "@/components/ui/button";
import { MessagesSquare, LogOut, Sun, Moon, Bot, Network, Loader2 } from "lucide-react";
import { useGraphStats } from "@/app/hooks/useGraphData";
import GraphToolbar from "@/app/components/graph/GraphToolbar";
import GraphSearch from "@/app/components/graph/GraphSearch";
import GraphNodePanel from "@/app/components/graph/GraphNodePanel";

const GraphViewer = dynamic(
  () => import("@/app/components/graph/GraphViewer"),
  { ssr: false }
);
import GraphLegend from "@/app/components/graph/GraphLegend";
import GraphStatsBar from "@/app/components/graph/GraphStatsBar";

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="h-8 w-8" />;
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
      aria-label="Toggle theme"
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

export default function GraphPage() {
  const router = useRouter();
  const [username, setUsername] = useState<string | null>(null);

  const [graphData, setGraphData] = useState<GraphOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string | undefined>(undefined);
  const [autoRotate, setAutoRotate] = useState(true);

  const { data: stats } = useGraphStats();
  const graphViewerRef = useRef<GraphViewerHandle>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auth check
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/auth");
      return;
    }
    const user = getUser();
    setUsername(user?.username ?? "User");
  }, [router]);

  // Load graph data
  useEffect(() => {
    if (!username) return;
    setLoading(true);
    setError(null);
    graphApi
      .getOverview({ entity_type: filterType, limit: 50 })
      .then((data) => {
        setGraphData(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [username, filterType]);

  const handleLogout = useCallback(() => {
    clearAuth();
    router.push("/auth");
  }, [router]);

  const handleClickNode = useCallback(
    (nodeId: string) => {
      const node = graphData?.nodes.find((n) => n.id === nodeId);
      if (node) {
        setSelectedNode(node);
        setFocusNodeId(nodeId);
      }
    },
    [graphData]
  );

  const handleNavigateNode = useCallback(
    (nodeId: string) => {
      const existing = graphData?.nodes.find((n) => n.id === nodeId);
      if (existing) {
        setSelectedNode(existing);
        setFocusNodeId(nodeId);
        graphViewerRef.current?.focusNode(nodeId);
        return;
      }
      graphApi.getNeighbors(nodeId, { depth: 1, limit: 50 }).then((data) => {
        const targetNode = data.nodes.find((n) => n.id === nodeId);
        if (targetNode) {
          setSelectedNode(targetNode);
          if (graphData) {
            const existingNodeIds = new Set(graphData.nodes.map((n) => n.id));
            const existingEdgeIds = new Set(graphData.edges.map((e) => e.id));
            const newNodes = data.nodes.filter((n) => !existingNodeIds.has(n.id));
            const newEdges = data.edges.filter((e) => !existingEdgeIds.has(e.id));
            setGraphData({
              nodes: [...graphData.nodes, ...newNodes],
              edges: [...graphData.edges, ...newEdges],
              is_truncated: graphData.is_truncated,
            });
          }
          setFocusNodeId(nodeId);
        }
      });
    },
    [graphData]
  );

  const handleSearchSelect = useCallback(
    (nodeId: string) => {
      handleNavigateNode(nodeId);
    },
    [handleNavigateNode]
  );

  const handleZoomIn = useCallback(() => {
    graphViewerRef.current?.zoomIn();
  }, []);

  const handleZoomOut = useCallback(() => {
    graphViewerRef.current?.zoomOut();
  }, []);

  const handleReset = useCallback(() => {
    graphViewerRef.current?.resetView();
  }, []);

  const handleToggleAutoRotate = useCallback(() => {
    const newVal = graphViewerRef.current?.toggleAutoRotate();
    if (newVal !== undefined) setAutoRotate(newVal);
  }, []);

  const handleFullScreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      el.requestFullscreen();
    }
  }, []);

  if (!username) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-border/50 bg-background/80 px-5 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[#49b1f5] to-[#62bfff] dark:from-[#2080c0] dark:to-[#3090d0]">
            <Bot className="h-4.5 w-4.5 text-white" />
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">
            KG-RAG
          </h1>

          <div className="ml-2 flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push("/")}
              className="rounded-lg text-muted-foreground hover:text-foreground"
            >
              <MessagesSquare className="mr-1.5 h-4 w-4" />
              Chat
            </Button>
            <Button
              variant="secondary"
              size="sm"
              className="rounded-lg"
            >
              <Network className="mr-1.5 h-4 w-4" />
              Graph
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <GraphStatsBar
            stats={stats}
            isTruncated={graphData?.is_truncated}
          />
          <ThemeToggle />
          <span className="text-sm text-muted-foreground">{username}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLogout}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            <LogOut className="mr-1.5 h-4 w-4" />
            退出
          </Button>
        </div>
      </header>

      {/* Graph canvas */}
      <div ref={containerRef} className="relative flex-1 overflow-hidden">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">
                Loading knowledge graph...
              </p>
            </div>
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <p className="text-sm text-destructive">{error}</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => {
                  setError(null);
                  setLoading(true);
                  graphApi
                    .getOverview({ entity_type: filterType, limit: 50 })
                    .then((data) => {
                      setGraphData(data);
                      setLoading(false);
                    })
                    .catch((err) => {
                      setError(err.message);
                      setLoading(false);
                    });
                }}
              >
                Retry
              </Button>
            </div>
          </div>
        ) : graphData && graphData.nodes.length > 0 ? (
          <>
            <GraphViewer
              ref={graphViewerRef}
              data={graphData}
              onClickNode={handleClickNode}
              onClickStage={() => setSelectedNode(null)}
              focusNodeId={focusNodeId}
            />

            <GraphSearch
              onSelectNode={handleSearchSelect}
              onFilterType={setFilterType}
              activeFilter={filterType}
            />

            {selectedNode && (
              <GraphNodePanel
                node={selectedNode}
                onClose={() => setSelectedNode(null)}
                onNavigate={handleNavigateNode}
              />
            )}

            <GraphToolbar
              autoRotate={autoRotate}
              onZoomIn={handleZoomIn}
              onZoomOut={handleZoomOut}
              onReset={handleReset}
              onToggleAutoRotate={handleToggleAutoRotate}
              onFullScreen={handleFullScreen}
            />

            <GraphLegend entityCounts={stats?.entities_by_type} />
          </>
        ) : (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-muted-foreground">
              No entities found in the knowledge graph.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
