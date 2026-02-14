"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import { useQueryState } from "nuqs";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { getUser, clearAuth, isAuthenticated } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { MessagesSquare, LogOut, Sun, Moon, Bot, Network } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { SessionList } from "@/app/components/SessionList";
import { ChatProvider } from "@/providers/ChatProvider";
import { ChatInterface } from "@/app/components/ChatInterface";

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return <div className="h-8 w-8" />;
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="h-8 w-8 rounded-full text-muted-foreground hover:text-foreground"
      aria-label="Toggle theme"
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </Button>
  );
}

function HomePageInner({ username }: { username: string }) {
  const router = useRouter();
  const [sessionId, setSessionId] = useQueryState("sessionId");
  const [sidebar, setSidebar] = useQueryState("sidebar");
  const showSidebar = sidebar !== "0";

  const [mutateSessions, setMutateSessions] = useState<(() => void) | null>(null);

  const handleLogout = useCallback(() => {
    clearAuth();
    router.push("/auth");
  }, [router]);

  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-border/50 bg-background/80 px-5 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[#49b1f5] to-[#62bfff] dark:from-[#2080c0] dark:to-[#3090d0]">
            <Bot className="h-4.5 w-4.5 text-white" />
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">KG-RAG</h1>
          {!showSidebar && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSidebar(null)}
              className="ml-1 rounded-lg text-muted-foreground hover:text-foreground"
            >
              <MessagesSquare className="mr-1.5 h-4 w-4" />
              History
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/graph")}
            className="rounded-lg text-muted-foreground hover:text-foreground"
          >
            <Network className="mr-1.5 h-4 w-4" />
            Graph
          </Button>
        </div>
        <div className="flex items-center gap-1.5">
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

      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup
          direction="horizontal"
          autoSaveId="standalone-chat"
        >
          {showSidebar && (
            <>
              <ResizablePanel
                id="session-history"
                order={1}
                defaultSize={20}
                minSize={16}
                className="relative min-w-[280px]"
              >
                <SessionList
                  onSessionSelect={async (id) => {
                    await setSessionId(id);
                  }}
                  onNewChat={() => setSessionId(null)}
                  onMutateReady={(fn) => setMutateSessions(() => fn)}
                  onClose={() => setSidebar("0")}
                />
              </ResizablePanel>
              <ResizableHandle className="w-0 bg-transparent after:w-1" />
            </>
          )}

          <ResizablePanel
            id="chat"
            className="relative flex flex-col"
            order={2}
          >
            <ChatProvider
              onHistoryRevalidate={() => mutateSessions?.()}
            >
              <ChatInterface />
            </ChatProvider>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  );
}

function HomePageContent() {
  const router = useRouter();
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/auth");
      return;
    }
    const user = getUser();
    setUsername(user?.username ?? "User");
  }, [router]);

  if (!username) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return <HomePageInner username={username} />;
}

export default function HomePage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      }
    >
      <HomePageContent />
    </Suspense>
  );
}
