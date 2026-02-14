# Project Notes
禁止使用git回滚，但应该看看相似问题以前是怎么修复的

## 项目命名与入口

- 项目名称：`KG-RAG`
- 默认分支：`project-frontend`
- Python 内部包名：`kg_rag`
- CLI 入口：`kg-rag`（见 `pyproject.toml` 的 `[project.scripts]`）
  - 启动后端（FastAPI）：`kg-rag serve`

## Markdown / Mermaid / LaTeX 输出规范

前端使用 `md-editor-rt` 的 Preview 渲染（见 `frontend/src/app/components/MarkdownContent.tsx`），对模型输出有一些约定（否则容易“看起来像乱码/不渲染”）：

- Mermaid 必须用 fenced code block：` ```mermaid` + 内容 + ` ````
- Mermaid 的节点 label **不要嵌套 `[]`**（例如 `B[定义状态 dp[...]]` 会导致解析失败）；推荐写法：
  - ✅ `B["定义状态 dp[i][j]"]`（用引号包住 label）
  - ✅ `B[定义状态 dp(i,j)]`（用括号替代方括号）
- 数学公式建议用块级写法（`$$` 独占一行），换行必须用 `\\`（不要写成行末单个 `\`）：
  - ✅
    ```
    $$
    dp[i][j] = \begin{cases}
    dp[i-1][j], & \text{if } j < w_i \\
    \max(\cdots), & \text{if } j \geq w_i
    \end{cases}
    $$
    ```
- 代码块尽量标注语言（例如 ` ```python` / ` ```ts`），便于高亮。

## Frontend 包管理

前端项目（`frontend/`）使用 **yarn**，不要使用 npm。
- 安装依赖：`yarn`
- 添加包：`yarn add <pkg>`
- 移除包：`yarn remove <pkg>`
- 构建：`yarn build`
- 开发：`yarn dev`

## Frontend-Backend Architecture

前端已从 LangGraph SDK 迁移到 FastAPI + SSE 架构：
- **后端 SSE 端点**：`POST /api/v1/sessions/{id}/chat/stream`，返回 `text/event-stream`
- **SSE 事件流**：`metadata` → `state`（多次） → `custom`（多次） → `done`
- **前端 Hook**：`useChat` 使用 fetch + `parseSSEStream()` 消费 SSE，不依赖任何 `@langchain/*` 包
- **阶段检测**：由服务端 `_compute_phase()` 计算，通过 SSE `state` 事件推送给前端
- **Session 管理**：前端通过 REST API 管理 session（创建/列表/历史），首次发送消息时自动创建
- **流取消**：前端使用 `AbortController.abort()` 中断 SSE 流

### 关键文件
- `src/kg_rag/api/service.py` — `ask_stream()` 异步生成器，`_compute_phase()`、`_serialize_todos()` 辅助函数
- `src/kg_rag/api/app.py` — SSE 端点 `chat_turn_stream`
- `frontend/src/lib/api.ts` — fetch API 客户端
- `frontend/src/lib/sse.ts` — SSE 流解析器
- `frontend/src/app/hooks/useChat.ts` — 核心聊天 hook（本地 state + SSE）
- `frontend/src/app/hooks/useSessions.ts` — SWR session 列表（替代 useThreads）

### 已移除的依赖
- 前端：`@langchain/langgraph-sdk`、`@langchain/core`、`@langchain/langgraph`
- 后端：`langgraph-cli[inmem]`（不再需要 LangGraph Server）
- 已删除文件：`ClientProvider.tsx`、`useThreads.ts`、`ThreadList.tsx`

## NanoVectorDB

重置向量存储时，直接删除 `data/nano_vector.json` 文件，不要写入 `{}`。
NanoVectorDB 加载时要求文件包含 `matrix` 字段，空 JSON 会触发 `KeyError: 'matrix'`。
文件不存在时 NanoVectorDB 会自动创建合法的空数据库。

## Neo4j Entity 属性

实体类型存储在 `type` 属性中，不是 `entity_type`。
`upsert_node` 采用双标签方案：已知类型（见 models.py ENTITY_TYPE_LABELS）
同时拥有 `:Entity` 基础标签和类型标签（如 `:Entity:Algorithm`），
未知类型回退为仅 `:Entity`，原值写入 `type` 属性。
查询优先用类型标签（`MATCH (e:Algorithm)`），也可用属性（`WHERE e.type = "Algorithm"`）。
已有数据若只有 `:Entity` 标签，重新 ingest 即可补全，无需迁移脚本。

## Neo4j User 节点

User 节点主键是 `user_id`（非 `entity_id`）。
约束：`FOR (u:User) REQUIRE u.user_id IS UNIQUE`。
`upsert_node` 对 User 使用 `MERGE (n:User {user_id: $eid})`。
`profile.py` 读取使用 `MATCH (u:User {user_id: $uid})`。
两者通过 `user_id` 统一，不要用 `entity_id` 查 User 节点。

## Cypher 安全

`graph_query.py` 的注入防护流程：先剥离 `//` 和 `/* */` 注释，再做写关键词黑名单 + apoc 检测。
无 LIMIT 的查询自动追加 `LIMIT 50`。LIMIT 检测也在剥离注释后进行。

## 凭证管理

`docker-compose.yml` 通过 `env_file: .env` + `${NEO4J_PASSWORD}` 读取密码，不要硬编码。
`.env.example` 中 API key 使用 `your-xxx-api-key` 占位符，不要写真实值。

## LangSmith / Tracing 常见坑

- 报错 `{"detail":"Invalid token"}`（401 Unauthorized）时，优先怀疑**环境变量未加载**而不是 key 真失效：
  - Python 脚本里如果直接 `from langsmith import Client`，但没有先加载 `.env`，`LANGSMITH_API_KEY` 可能为空。
  - 本仓库推荐：在任何使用 LangSmith 的脚本最前面先 `from kg_rag.config import settings`（该模块会在导入时 `load_dotenv` 项目根目录的 `.env`）。
  - 或者运行前显式导出：`export LANGSMITH_API_KEY=...`，并确认 `echo $LANGSMITH_API_KEY` 非空。
- `client.list_runs(limit=...)` 的 `limit` **最大只能是 100**，否则会报 `Limit exceeds maximum allowed value of 100`。需要更大范围时做分页/多次调用。
- 前端侧如果使用 `NEXT_PUBLIC_LANGSMITH_API_KEY` 作为默认值，注意它会暴露到浏览器；更安全的方式是用户在 UI 中手动填写自己的 key。


## Known Issues (Backlog)

Codex 审查中发现但暂未修复的问题，按优先级排列。

### 可扩展性
- `preprocess.py:235` / `extract.py:420` — `asyncio.gather` 一次性创建所有 task，Semaphore 限制并发但不限 task 对象总数。当前数据规模（~500 文件）无问题，万级时可改用分批 gather 或 `asyncio.TaskGroup`
- `nano_vector.py` — `upsert()` / `delete()` 每次调 `save()` 写全量 JSON。ingest 瓶颈在 LLM 调用，save 开销可忽略。如需优化可只在 `finalize()` 中调用

### 代码卫生
- `main.py:22` — `logging.basicConfig()` 在模块级执行，作为库导入时会污染宿主日志配置。低优先级，可移到 `if __name__ == "__main__"` 内
- `third_party/` 目录无引用（清理问题，不影响功能）

### 数据质量（孤立实体 ~502/6135，约 8%）
- 噪声 Concept（275 个）— 提取了泛化词（`Optimal Strategy`、`Basic Operation`）、平台/比赛名（`Luogu`、`Cook-Off`）等非独立知识点，应批量清理
- 孤立 Problem（182 个）— 题目节点被提取但缺少 APPLIES_TO 关系，可尝试对这批节点补建关系
- 杂项 Algorithm/Technique（40 个）— 混入实现细节（`Insert`、`IO Synchronization`）和非 OI 内容（`Finite Element Method`），需清理
- 根因：extraction prompt 的 quality rules 对噪声过滤不够严格，后续 ingest 应调优 prompt 减少增量噪声
