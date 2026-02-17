"use client";

import {
  useEffect,
  useRef,
  useState,
  useMemo,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";
import * as THREE from "three";
import SpriteText from "three-spritetext";
import { useTheme } from "next-themes";
import type { GraphOverview } from "@/lib/graph-api";
import {
  ENTITY_TYPE_COLORS,
  RELATION_TYPE_COLORS,
  NODE_MIN_SIZE,
  NODE_SIZE_SCALE,
  NODE_MAX_SIZE,
} from "@/lib/graph-constants";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface NodeObject {
  id: string;
  label: string;
  entityType: string;
  val: number;
  color: string;
  x?: number;
  y?: number;
  z?: number;
}

interface LinkObject {
  source: string | NodeObject;
  target: string | NodeObject;
  relType: string;
  color: string;
  width: number;
}

interface GraphData {
  nodes: NodeObject[];
  links: LinkObject[];
}

export interface GraphViewerHandle {
  focusNode: (nodeId: string) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetView: () => void;
  toggleAutoRotate: () => boolean;
}

interface GraphViewerProps {
  data: GraphOverview;
  onClickNode?: (nodeId: string) => void;
  onClickStage?: () => void;
  focusNodeId?: string | null;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function buildGraphData(data: GraphOverview): GraphData {
  const degreeMap = new Map<string, number>();
  for (const edge of data.edges) {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1);
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1);
  }

  const nodes: NodeObject[] = data.nodes.map((n) => {
    const degree = degreeMap.get(n.id) || 0;
    const size = Math.min(
      NODE_MAX_SIZE,
      NODE_MIN_SIZE + NODE_SIZE_SCALE * Math.sqrt(degree)
    );
    return {
      id: n.id,
      label: n.label,
      entityType: n.type,
      val: size,
      color: ENTITY_TYPE_COLORS[n.type] || ENTITY_TYPE_COLORS.Unknown,
    };
  });

  const nodeIds = new Set(data.nodes.map((n) => n.id));
  const links: LinkObject[] = data.edges
    .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map((e) => ({
      source: e.source,
      target: e.target,
      relType: e.type,
      color: RELATION_TYPE_COLORS[e.type] || RELATION_TYPE_COLORS.RELATED_TO,
      width: Math.max(0.3, Math.min(1.5, e.weight * 0.6)),
    }));

  return { nodes, links };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const GraphViewer = forwardRef<GraphViewerHandle, GraphViewerProps>(
  function GraphViewer({ data, onClickNode, onClickStage, focusNodeId }, ref) {
    const { resolvedTheme } = useTheme();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const fgRef = useRef<any>(undefined);
    const containerRef = useRef<HTMLDivElement>(null);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
    const [hoveredNode, setHoveredNode] = useState<NodeObject | null>(null);
    const [selectedNode, setSelectedNode] = useState<string | null>(null);
    const [autoRotate, setAutoRotate] = useState(true);

    const graphData = useMemo(() => buildGraphData(data), [data]);

    // Neighbor set for highlighting
    const highlightSet = useMemo(() => {
      const activeId = hoveredNode?.id || selectedNode;
      if (!activeId) return null;
      const set = new Set<string>();
      set.add(activeId);
      for (const link of graphData.links) {
        const srcId =
          typeof link.source === "string" ? link.source : link.source.id;
        const tgtId =
          typeof link.target === "string" ? link.target : link.target.id;
        if (srcId === activeId) set.add(tgtId);
        if (tgtId === activeId) set.add(srcId);
      }
      return set;
    }, [hoveredNode, selectedNode, graphData.links]);

    // Link highlight set
    const highlightLinks = useMemo(() => {
      const activeId = hoveredNode?.id || selectedNode;
      if (!activeId) return null;
      const set = new Set<string>();
      for (const link of graphData.links) {
        const srcId =
          typeof link.source === "string" ? link.source : link.source.id;
        const tgtId =
          typeof link.target === "string" ? link.target : link.target.id;
        if (srcId === activeId || tgtId === activeId) {
          set.add(`${srcId}->${tgtId}`);
        }
      }
      return set;
    }, [hoveredNode, selectedNode, graphData.links]);

    // Resize observer
    useEffect(() => {
      const el = containerRef.current;
      if (!el) return;
      const ro = new ResizeObserver((entries) => {
        const { width, height } = entries[0].contentRect;
        setDimensions({ width, height });
      });
      ro.observe(el);
      return () => ro.disconnect();
    }, []);

    // Auto-rotate
    useEffect(() => {
      const ctrl = fgRef.current?.controls();
      if (ctrl && "autoRotate" in ctrl) {
        (ctrl as { autoRotate: boolean; autoRotateSpeed: number }).autoRotate =
          autoRotate;
        (ctrl as { autoRotate: boolean; autoRotateSpeed: number }).autoRotateSpeed =
          0.5;
      }
    }, [autoRotate]);

    // Initial camera distance after mount
    useEffect(() => {
      const timer = setTimeout(() => {
        fgRef.current?.zoomToFit(800, 60);
      }, 2000);
      return () => clearTimeout(timer);
    }, [data]);

    // Focus on node
    useEffect(() => {
      if (!focusNodeId || !fgRef.current) return;
      const node = graphData.nodes.find((n) => n.id === focusNodeId);
      if (!node || node.x == null) return;
      const distance = 120;
      const distRatio = 1 + distance / Math.max(Math.hypot(node.x!, node.y!, node.z!), 1);
      fgRef.current.cameraPosition(
        {
          x: node.x! * distRatio,
          y: node.y! * distRatio,
          z: node.z! * distRatio,
        },
        { x: node.x!, y: node.y!, z: node.z! },
        1000
      );
    }, [focusNodeId, graphData.nodes]);

    // Imperative handle for parent
    useImperativeHandle(ref, () => ({
      focusNode(nodeId: string) {
        const node = graphData.nodes.find((n) => n.id === nodeId);
        if (!node || node.x == null || !fgRef.current) return;
        const distance = 120;
        const distRatio =
          1 + distance / Math.max(Math.hypot(node.x!, node.y!, node.z!), 1);
        fgRef.current.cameraPosition(
          {
            x: node.x! * distRatio,
            y: node.y! * distRatio,
            z: node.z! * distRatio,
          },
          { x: node.x!, y: node.y!, z: node.z! },
          1000
        );
      },
      zoomIn() {
        const fg = fgRef.current;
        if (!fg) return;
        const { x, y, z } = fg.cameraPosition();
        fg.cameraPosition(
          { x: x * 0.7, y: y * 0.7, z: z * 0.7 },
          undefined,
          400
        );
      },
      zoomOut() {
        const fg = fgRef.current;
        if (!fg) return;
        const { x, y, z } = fg.cameraPosition();
        fg.cameraPosition(
          { x: x * 1.4, y: y * 1.4, z: z * 1.4 },
          undefined,
          400
        );
      },
      resetView() {
        fgRef.current?.zoomToFit(600, 60);
      },
      toggleAutoRotate() {
        setAutoRotate((prev) => !prev);
        return !autoRotate;
      },
    }));

    // Node click
    const handleNodeClick = useCallback(
      (node: NodeObject) => {
        setSelectedNode((prev) => (prev === node.id ? null : node.id));
        onClickNode?.(node.id);
      },
      [onClickNode]
    );

    // Background click
    const handleBgClick = useCallback(() => {
      setSelectedNode(null);
      onClickStage?.();
    }, [onClickStage]);

    // Node hover
    const handleNodeHover = useCallback((node: NodeObject | null) => {
      setHoveredNode(node);
      if (containerRef.current) {
        containerRef.current.style.cursor = node ? "pointer" : "default";
      }
    }, []);

    const bgColor = resolvedTheme === "dark" ? "#080b12" : "#f0f4f8";
    const dimOpacity = resolvedTheme === "dark" ? 0.08 : 0.15;

    // Node color with highlight
    const nodeColor = useCallback(
      (node: NodeObject) => {
        if (!highlightSet) return node.color;
        return highlightSet.has(node.id)
          ? node.color
          : resolvedTheme === "dark"
            ? "rgba(30,41,59,0.3)"
            : "rgba(200,210,220,0.4)";
      },
      [highlightSet, resolvedTheme]
    );

    // Link color with highlight
    const linkColor = useCallback(
      (link: LinkObject) => {
        if (!highlightLinks) {
          // Default: semi-transparent
          const base = link.color;
          return base + "60";
        }
        const srcId =
          typeof link.source === "string" ? link.source : link.source.id;
        const tgtId =
          typeof link.target === "string" ? link.target : link.target.id;
        const key = `${srcId}->${tgtId}`;
        if (highlightLinks.has(key)) return link.color;
        return `rgba(100,100,100,${dimOpacity})`;
      },
      [highlightLinks, dimOpacity]
    );

    // Link width with highlight
    const linkWidth = useCallback(
      (link: LinkObject) => {
        if (!highlightLinks) return link.width;
        const srcId =
          typeof link.source === "string" ? link.source : link.source.id;
        const tgtId =
          typeof link.target === "string" ? link.target : link.target.id;
        const key = `${srcId}->${tgtId}`;
        return highlightLinks.has(key) ? link.width * 2.5 : 0.1;
      },
      [highlightLinks]
    );

    // Particle count — only on highlighted links
    const linkParticles = useCallback(
      (link: LinkObject) => {
        if (!highlightLinks) return 0;
        const srcId =
          typeof link.source === "string" ? link.source : link.source.id;
        const tgtId =
          typeof link.target === "string" ? link.target : link.target.id;
        const key = `${srcId}->${tgtId}`;
        return highlightLinks.has(key) ? 2 : 0;
      },
      [highlightLinks]
    );

    // Custom node object with glow + text label
    const nodeThreeObject = useCallback(
      (node: NodeObject) => {
        const isActive = highlightSet?.has(node.id);
        const isDimmed = highlightSet && !isActive;
        const baseSize = Math.cbrt(node.val) * 1.2;

        const group = new THREE.Group();

        // Core sphere
        const geometry = new THREE.SphereGeometry(baseSize, 24, 24);
        const material = new THREE.MeshPhongMaterial({
          color: isDimmed
            ? resolvedTheme === "dark"
              ? 0x1e293b
              : 0xc8d2dc
            : new THREE.Color(node.color).getHex(),
          transparent: !!isDimmed,
          opacity: isDimmed ? 0.3 : 1,
          shininess: 80,
        });
        const sphere = new THREE.Mesh(geometry, material);
        group.add(sphere);

        // Glow ring for active/hovered node
        if (isActive && !isDimmed) {
          const glowGeometry = new THREE.SphereGeometry(
            baseSize * 1.6,
            24,
            24
          );
          const glowMaterial = new THREE.MeshBasicMaterial({
            color: new THREE.Color(node.color).getHex(),
            transparent: true,
            opacity: 0.15,
          });
          const glow = new THREE.Mesh(glowGeometry, glowMaterial);
          group.add(glow);
        }

        // Text label below sphere
        const label = new SpriteText(node.label);
        label.textHeight = Math.max(2, baseSize * 0.8);
        label.color = isDimmed
          ? "transparent"
          : resolvedTheme === "dark"
            ? "#cbd5e1"
            : "#334155";
        label.backgroundColor = false as unknown as string;
        label.fontFace = "Inter, system-ui, sans-serif";
        label.fontWeight = "500";
        label.position.y = -(baseSize + label.textHeight + 1.5);
        group.add(label);

        return group;
      },
      [highlightSet, resolvedTheme]
    );

    // Node label
    const nodeLabel = useCallback(
      (node: NodeObject) =>
        `<div style="
          background: ${resolvedTheme === "dark" ? "rgba(15,17,23,0.9)" : "rgba(255,255,255,0.95)"};
          color: ${resolvedTheme === "dark" ? "#e2e8f0" : "#1e293b"};
          padding: 6px 10px;
          border-radius: 8px;
          font-size: 12px;
          font-family: 'Inter', system-ui, sans-serif;
          border: 1px solid ${resolvedTheme === "dark" ? "rgba(100,116,139,0.3)" : "rgba(148,163,184,0.3)"};
          box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        ">
          <span style="
            display: inline-block;
            width: 8px; height: 8px;
            border-radius: 50%;
            background: ${node.color};
            margin-right: 6px;
            vertical-align: middle;
          "></span>
          <strong>${node.label}</strong>
          <span style="
            margin-left: 8px;
            color: ${resolvedTheme === "dark" ? "#94a3b8" : "#64748b"};
            font-size: 10px;
          ">${node.entityType}</span>
        </div>`,
      [resolvedTheme]
    );

    return (
      <div ref={containerRef} className="h-full w-full">
        <ForceGraph3D
          ref={fgRef}
          width={dimensions.width}
          height={dimensions.height}
          graphData={graphData}
          backgroundColor={bgColor}
          // Nodes
          nodeThreeObject={nodeThreeObject}
          nodeThreeObjectExtend={false}
          nodeLabel={nodeLabel}
          nodeColor={nodeColor}
          onNodeClick={handleNodeClick}
          onNodeHover={handleNodeHover}
          // Links
          linkColor={linkColor}
          linkWidth={linkWidth}
          linkOpacity={0.6}
          linkDirectionalParticles={linkParticles}
          linkDirectionalParticleWidth={1.5}
          linkDirectionalParticleSpeed={0.004}
          linkDirectionalParticleColor={(link: LinkObject) => link.color}
          linkCurvature={0.15}
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={0.95}
          linkDirectionalArrowColor={(link: LinkObject) => link.color}
          // Interaction
          onBackgroundClick={handleBgClick}
          enableNodeDrag={true}
          enableNavigationControls={true}
          // Force engine
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
          warmupTicks={80}
          cooldownTicks={200}
        />
      </div>
    );
  }
);

export default GraphViewer;
