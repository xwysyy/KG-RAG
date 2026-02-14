# KG-RAG — 架构文档

> KG-RAG：KG + RAG + Agentic 架构的算法领域知识问答系统，支持多轮有状态交互与用户画像。

## 1. 项目定位

- 核心场景：算法知识问答（涵盖算法教学与算法竞赛）
- 核心价值：KG 提供结构化关系推理（先修、改进、依赖），RAG 提供语义检索，Agent 编排多步推理
- 数据来源：OI-Wiki 算法文档（预处理后 ingest）

## 2. 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| Agent 编排 | LangGraph (StateGraph) | 有向图、循环、并行、状态管理 |
| Tool / LLM 接口 | langchain-core, langchain-openai | @tool 装饰器、ChatOpenAI (OpenAI-compatible) |
| 图数据库 | Neo4j (async driver) | KG 存储 + 用户画像 |
| 向量数据库 | NanoVectorDB | 文本块 embedding 检索 |
| Embedding | OpenAIEmbeddings (Qwen3-Embedding-8B) | 本地或远程 OpenAI-compatible 服务 |
| 联网搜索 | Firecrawl | web_search tool 后端 |
| LLM | OpenAI-compatible (默认 DeepSeek) | Plan/Sub-Agent/Cypher 生成/实体抽取 |
| 数据预处理 | scripts/preprocess.py | OI-Wiki MkDocs → 标准 Markdown（Phase1 正则 + Phase2 LLM） |

## 3. 项目结构

```
.
├── src/kg_rag/              # Python 后端（内部包名 kg_rag）
│   ├── api/                 # FastAPI API（Auth / Session / SSE / Graph）
│   ├── agent/               # LangGraph agent graph（Plan→Execute→Aggregate→Judge）
│   ├── ingest/              # 摄入：chunking / extract
│   ├── memory/              # 用户画像：读取 / 提案式写入
│   ├── storage/             # Neo4j + NanoVectorDB 适配
│   ├── tools/               # vector_search / graph_query / web_search
│   ├── asgi.py              # FastAPI ASGI app（uvicorn 入口）
│   ├── server.py            # LangGraph dev 入口（langgraph.json 引用，可选）
│   ├── main.py              # CLI（chat / ingest / ingest-dir / vector-retag / merge / serve）
│   ├── config.py            # 配置管理（.env → Settings dataclass）
│   ├── models.py            # Pydantic 数据模型
│   └── utils.py             # 公共工具函数（strip_code_fences 等）
├── frontend/                # Next.js 前端（App Router）
├── docker-compose.yml       # Neo4j（本地开发）
├── .env.example             # 环境变量模板
└── architecture.md          # 本文档
```

## 4. Agent 层

### 4.1 架构

Planner + 通用 Sub-Agent 池 + 迭代循环：

```
用户输入 + 用户画像
  → Plan Agent 规划，拆解为子任务（JSON array）
  → Sub-Agent 池并行执行（asyncio.gather）
  → Aggregator 聚合结果
  → Plan Agent 判断充分性
      ├─ 充分 → 生成最终回答 → 输出
      └─ 不充分 → 重新规划 → 下一轮（最多 max_iterations 轮）
```

### 4.2 角色

- Plan Agent：规划 + 质量判断双重角色，读取用户画像实现个性化
- Sub-Agent × N：通用 ReAct Agent，共享 tool 集，并行执行，上下文隔离
- Aggregator：收集 Sub-Agent 结果，合成中间结果

### 4.3 Tool 集

| Tool | 职责 | 适用场景 |
|------|------|---------|
| `vector_search` | 语义相似度检索文本块 | 概念性/描述性问题 |
| `graph_query` | NL → Cypher → Neo4j | 结构性/关系性问题（先修、改进、比较） |
| `web_search` | Firecrawl 联网搜索 | 本地知识不足时补充 |

## 5. 数据层

### 5.1 Neo4j 图模型

节点（双标签方案）：
- `:Entity` — 基础标签，所有知识实体共有
- `:Algorithm`, `:DataStructure`, `:Concept`, `:Problem`, `:Technique` — 类型标签，已知类型的实体同时拥有基础标签和类型标签（如 `:Entity:Algorithm`）
- 未知类型回退为仅 `:Entity`，原值写入 `type` 属性
- `:User` — 用户节点

已知类型集合定义在 `models.py` 的 `ENTITY_TYPE_LABELS` 常量中，storage / extract / tools 均从此处导入。

关系（allowlist 强制）：
- 知识图谱：`PREREQ`, `IMPROVES`, `APPLIES_TO`, `BELONGS_TO`, `VARIANT_OF`, `USES`, `RELATED_TO`
- 用户画像：`MASTERED`, `WEAK_AT`, `INTERESTED_IN`（带 `confidence`, `evidence`, `last_updated` 属性）

关系类型集合定义在 `models.py` 的 `KNOWLEDGE_REL_TYPES` 和 `PROFILE_REL_TYPES` 常量中，storage / main / proposal 均从此处导入。

约束：`Entity.entity_id` UNIQUE, 各类型标签 `entity_id` UNIQUE（`Algorithm`, `DataStructure` 等），`User.user_id` UNIQUE

### 5.2 向量存储

NanoVectorDB 存储文本块 embedding，用于语义检索。同步操作通过 `asyncio.to_thread` + `asyncio.Lock` 包裹。

### 5.3 数据摄入流水线

```
原始 Markdown → preprocess.py（正则 + LLM 清洗）
  → chunking（tiktoken 按 token 分块）
  → LLM 实体/关系抽取（JSON 解析加固 + 失败 retry）
  → 去重（alias cross-ref + LLM dedup 双层）
  → Neo4j（实体节点双标签 + 关系边）+ NanoVectorDB（文本块 embedding）
```

支持单文件 `ingest` 和批量 `ingest-dir`（共享 LLM/Semaphore，目录级并发）。

## 6. Memory 设计

| 层级 | 范围 | 存储 | 用途 |
|------|------|------|------|
| 短期记忆 | 会话级 | LangGraph 状态 | 当前对话上下文 |
| 长期记忆 | 用户级（跨会话） | Neo4j | 掌握情况、薄弱点、兴趣 |

写入安全机制（提案式写入）：
```
对话结束 → LLM 抽取用户信息 → 生成变更提案（含置信度 + 证据）
  → relation_type 校验（仅 MASTERED/WEAK_AT/INTERESTED_IN）
  → 置信度阈值过滤（≥0.7）
  → 写入 Neo4j
```

## 7. 安全措施

- Cypher 注入防护：注释剥离（`//` / `/* */`）+ 写操作关键词黑名单 + read-only prompt 约束
- Label/RelType allowlist：未知类型映射到安全默认值
- 日志脱敏：Cypher 仅 debug 级别，错误返回通用消息
- 查询限制：无 LIMIT 的查询自动追加 `LIMIT 50`
- 异常隔离：画像提取失败不影响资源释放
- 前端渲染视为不可信输入：Markdown 禁用 raw HTML；Mermaid 采用 `securityLevel: strict`
