"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { authApi } from "@/lib/auth-api";
import { setToken, setUser } from "@/lib/auth";

export default function AuthPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const resetForm = () => {
    setUsername("");
    setPassword("");
    setConfirmPassword("");
    setError("");
  };

  const handleLogin = async () => {
    if (!username.trim() || !password) {
      setError("请输入用户名和密码");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await authApi.login(username.trim(), password);
      setToken(res.access_token);
      setUser({ user_id: res.user_id, username: res.username });
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    const trimmed = username.trim();
    if (trimmed.length < 2) {
      setError("用户名至少 2 个字符");
      return;
    }
    if (password.length < 6) {
      setError("密码至少 6 个字符");
      return;
    }
    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await authApi.register(trimmed, password);
      setToken(res.access_token);
      setUser({ user_id: res.user_id, username: res.username });
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (tab === "login") handleLogin();
      else handleRegister();
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-primary/5 px-4">
      <div className="w-full max-w-sm">
        <div className="animate-fade-in-up mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[#49b1f5] to-[#62bfff] dark:from-[#2080c0] dark:to-[#3090d0] shadow-lg shadow-[#49b1f5]/25 dark:shadow-[#2080c0]/25">
            <Bot className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">KG-RAG</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            算法知识问答系统
          </p>
        </div>

        <Card className="animate-fade-in-up border-border/50 bg-card/80 shadow-xl shadow-[var(--color-shadow)] backdrop-blur-sm" style={{ animationDelay: "100ms" }}>
          <Tabs
            value={tab}
            onValueChange={(v) => {
              setTab(v as "login" | "register");
              resetForm();
            }}
          >
            <CardHeader className="pb-4">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="login">登录</TabsTrigger>
                <TabsTrigger value="register">注册</TabsTrigger>
              </TabsList>
            </CardHeader>

            <CardContent>
              <TabsContent value="login" className="mt-0 space-y-4">
                <CardDescription>输入用户名和密码登录</CardDescription>
                <div className="space-y-2">
                  <Label htmlFor="login-username">用户名</Label>
                  <Input
                    id="login-username"
                    placeholder="请输入用户名"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    onKeyDown={handleKeyDown}
                    autoFocus
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="login-password">密码</Label>
                  <Input
                    id="login-password"
                    type="password"
                    placeholder="请输入密码"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={handleKeyDown}
                  />
                </div>
                {error && (
                  <p className="text-sm text-destructive">{error}</p>
                )}
                <Button
                  className="w-full bg-gradient-to-r from-[#49b1f5] to-[#62bfff] dark:from-[#2080c0] dark:to-[#3090d0] text-white shadow-sm hover:from-[#1892ff] hover:to-[#49b1f5]"
                  onClick={handleLogin}
                  disabled={loading}
                >
                  {loading ? "登录中..." : "登录"}
                </Button>
              </TabsContent>

              <TabsContent value="register" className="mt-0 space-y-4">
                <CardDescription>创建新账号</CardDescription>
                <div className="space-y-2">
                  <Label htmlFor="reg-username">用户名</Label>
                  <Input
                    id="reg-username"
                    placeholder="2-32 个字符"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    onKeyDown={handleKeyDown}
                    autoFocus
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="reg-password">密码</Label>
                  <Input
                    id="reg-password"
                    type="password"
                    placeholder="至少 6 个字符"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={handleKeyDown}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="reg-confirm">确认密码</Label>
                  <Input
                    id="reg-confirm"
                    type="password"
                    placeholder="再次输入密码"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    onKeyDown={handleKeyDown}
                  />
                </div>
                {error && (
                  <p className="text-sm text-destructive">{error}</p>
                )}
                <Button
                  className="w-full bg-gradient-to-r from-[#49b1f5] to-[#62bfff] dark:from-[#2080c0] dark:to-[#3090d0] text-white shadow-sm hover:from-[#1892ff] hover:to-[#49b1f5]"
                  onClick={handleRegister}
                  disabled={loading}
                >
                  {loading ? "注册中..." : "注册"}
                </Button>
              </TabsContent>
            </CardContent>
          </Tabs>
        </Card>
      </div>
    </div>
  );
}
