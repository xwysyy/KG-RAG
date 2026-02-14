"use client";

import { ZoomIn, ZoomOut, RotateCcw, Orbit, Maximize2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface GraphToolbarProps {
  autoRotate: boolean;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
  onToggleAutoRotate: () => void;
  onFullScreen?: () => void;
}

export default function GraphToolbar({
  autoRotate,
  onZoomIn,
  onZoomOut,
  onReset,
  onToggleAutoRotate,
  onFullScreen,
}: GraphToolbarProps) {
  return (
    <div className="absolute bottom-4 left-4 z-10 flex flex-col gap-1 rounded-xl border border-border/50 bg-background/80 p-1.5 shadow-lg backdrop-blur-xl">
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={onZoomIn}
        title="Zoom in"
      >
        <ZoomIn className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={onZoomOut}
        title="Zoom out"
      >
        <ZoomOut className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={onReset}
        title="Reset view"
      >
        <RotateCcw className="h-4 w-4" />
      </Button>
      <div className="my-0.5 h-px bg-border/50" />
      <Button
        variant={autoRotate ? "secondary" : "ghost"}
        size="icon"
        className="h-8 w-8"
        onClick={onToggleAutoRotate}
        title={autoRotate ? "Stop rotation" : "Auto rotate"}
      >
        <Orbit className="h-4 w-4" />
      </Button>
      {onFullScreen && (
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onFullScreen}
          title="Fullscreen"
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
