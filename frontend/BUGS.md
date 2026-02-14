# 前端 Bug 清单与修复记录

本文记录该项目前端（`frontend/`，Next.js App Router）目前发现的问题、根因分析与修复要点，便于后续回归与继续迭代。

## 已修复（本次改动覆盖）

### 1) 推理模型的「折叠思维链 / 思考内容」渲染不出来

**现象**
- 推理模型输出了思考内容（`reasoning_content` / `<think>...</think>`），但 UI 中没有可折叠的思考块，或思考块偶发不显示。

**根因**
- 前端对消息内容的解析过于「窄」：只识别 `content` 数组里 `type === "text"` 的块，导致某些 provider 的文本块（如 `output_text` / `markdown`）被忽略。
- 推理内容提取只覆盖了 `additional_kwargs.reasoning_content` + `<think>`，对 `content` block 形式（`type: reasoning/thinking/analysis`）支持不足。

**修复**
- 扩展 `extractStringFromMessageContent()`，兼容更多「可显示文本」块类型（例如 `output_text` / `input_text` / `markdown`）。
- 扩展 `extractReasoningContent()`：
  - 支持从 `additional_kwargs.reasoning_content/reasoning/thinking/...` 提取
  - 支持从 `content` blocks（`reasoning/thinking/analysis`）提取
  - 支持 `<think>/<analysis>/<reasoning>` 标签兜底
- `stripThinkTags()` 同步扩展到 `<think>/<analysis>/<reasoning>`。


### 2) 子代理（Sub-agent）内容不在框里 / 归属错乱

**现象**
- 子任务执行阶段（子代理工具调用）内容要么很难定位，要么显示不在卡片/框里，或者出现在错误的子任务卡片中。

**根因**
- 后端 `_run_react_loop()` 生成的结构化 tool call 卡片没有携带「属于哪个 sub-task」的 ID，导致前端只能“平均分配” tool call → 任务卡片，天然会错位。
- 前端 ToolCallBox 原本只显示「tool 名称 + args + result」，但子代理 ReAct 的“Thought（AIMessage.content）”被隐藏掉了（因为 AI tool-call message 被统一 `hidden`），用户感知为“内容不在框里/丢了”。

**修复**
- 后端：在结构化 tool call 的 `args` 中补充 `sub_task_id`，让前端可准确归属。
- 前端：优先按 `args.sub_task_id` 分配 tool call 到对应 `SubTaskCard`；没有 ID 时再兜底平均分配。
- 前端：ToolCallBox 展开时增加 `Thought` 区块，把 tool-call 伴随的思考文本放回到“框”里展示，并补齐卡片边框样式。


### 3) 页面卡顿严重（性能问题）

**现象**
- 流式输出时页面明显掉帧/卡顿，甚至“卡爆”。

**主要原因（组合拳）**
- 流式阶段对 Markdown 进行高频解析/渲染，且语法高亮对长代码块非常重（Prism / highlight.js 都会放大这个开销）。
- 渲染链路中存在「无意义的 props 变化」导致列表消息组件频繁重渲染（例如把变化频繁的 streaming/live state 作为 props 逐层传递）。
- 工具调用信息从消息列表中提取时存在不必要的 O(n²) 查找。

**修复（优先级从高到低）**
- `MarkdownContent` 从 `react-markdown`/Prism 系列方案切换到 `md-editor-rt` Preview（highlight.js + Mermaid + KaTeX），避免长代码块高亮导致的爆炸开销与自定义 renderer 引发的 hydration 问题。
- 流式 answering 阶段：隐藏消息列表中的“正在生成的最终回答消息”，改由 `GhostMessage` 用纯文本（`whitespace-pre-wrap`）显示，结束后再用最终消息一次性渲染 Markdown。
- `processedMessages`：
  - tool result 回填改为 O(n) 映射，不再遍历所有 message entries
  - tool-call ID fallback 改为稳定的 deterministic id（避免 `Math.random()` 引发的重挂载/重渲染）
  - 空 toolCalls 使用共享常量数组，减少不必要的 props 变动
- 降低计时器刷新频率（100ms → 250ms）。


### 4) 写完答案后「思考过程 / 过程流」直接消失

**现象**
- agent 跑完后，过程流（Planning/Executing/Reviewing/Answering）显示消失，无法回看。
- 某些推理模型只输出 `reasoning_content`（思考）而几乎不输出正文时，UI 也很难定位“最终回答消息”，导致过程流与思考块无法稳定出现/点击。

**根因**
- 过程快照（`RunSnapshot`）保存在 `useRef(Map)` 并在 `useEffect` 里写入：写入发生在 render 之后，且 ref 更新不会触发重新渲染 → UI 不会出现折叠回放组件。
- 之前对“最终回答消息”的识别过度依赖 `content` 非空；当正文为空、只有 reasoning 时，无法绑定到正确 message id。

**修复**
- 将 snapshots 从 `ref` 改为 `useState` 保存（以 `message.id` 为 key），写入快照时触发 re-render，使 `ThinkingAccordion` 能在最终消息上稳定显示。
- “最终回答消息”的识别改为：只要不是 `[Plan]` / `[Aggregated Results]`、不是 tool-call 消息，并且 `content` 或 `reasoning` 任一存在即可。

### 5) 刷新页面后「思考过程 / reasoning」消失

**现象**
- 同一会话跑完后能看到折叠过程流 / reasoning；但刷新页面（F5）后，这些内容消失。

**根因**
- 过程快照与流式 reasoning 的“兜底副本”之前只存在于前端内存（组件 state/ref），刷新后自然丢失。
- 部分 provider 最终 `AIMessage` 可能不会完整保留 `reasoning_content`（流式阶段有，但最终消息没有），仅依赖“最终消息”会导致回放丢失。
- 部分环境下消息 `message.id` 可能在刷新/重连后不稳定（或历史消息缺少 id），导致“快照按 message.id 绑定”的 UI 元素无法重新挂载回对应消息。

**修复**
- 为 `RunSnapshot` 增加 localStorage 持久化（按 `sessionId` 分 bucket）：
  - key: `kg-rag:run-snapshots:${sessionId}`
  - sessionId 变化时加载；snapshots 更新时写回 localStorage（忽略 quota/private mode 异常）。
- SSE 流式阶段把 reasoning/review/tool-call 等增量信息聚合到 live state；run 完成后在**最后一条 assistant 消息**上生成 `RunSnapshot` 并绑定到该消息的 `message.id`（因此刷新后能稳定命中并回放）。
- 历史消息通过 `GET /api/v1/sessions/{session_id}/messages` 加载，前端会复用同一个 `message.id` 格式（`msg-<message_id>`），保证 snapshot key 可复现。

### 6) 子 agent 过程输出先出现在页面最上方，结束后才进入 SubTaskCard

**现象**
- 子 agent 在执行过程中会把 ReAct 过程（`Thought/Action/Action Input/Final Answer`）当作普通 AI 消息刷在主消息列表顶部。
- SubTaskCard 里的工具调用列表要等到子任务全部完成后才出现（甚至归属错位）。

**根因**
- 早期 SSE 只推送粗粒度 `state/done`，缺少可被 UI 直接消费的「结构化子任务事件」（tool call/status/result），导致：
  - 执行期要么看不到细节，要么只能把文本片段当普通消息塞进主消息列表（“顶上刷屏”）。
  - tool call 归属缺少 `sub_task_id` 时，只能兜底平均分配（见上面的 #2）。

**修复**
- 后端：在 SSE `custom` 事件中推送结构化事件（并携带 `sub_task_id`）：
  - `subtask_status`（in_progress/completed）
  - `subtask_tool_call`（pending/completed/error + result）
  - `subtask_result`（子任务最终答案，供 Result tab 实时渲染）
- 前端：`useChat` 使用 `parseSSEStream()` 解析 SSE，并把 `custom` 事件聚合到：
  - `liveToolCallsByTask: Record<sub_task_id, ToolCall[]>`
  - `liveTaskStatusById: Record<sub_task_id, status>`
  - `liveTaskResultById: Record<sub_task_id, result>`
  从而实现“从一开始就在各自 SubTaskCard 内实时渲染”。
- 前端：仅在 `done` 事件追加最终 assistant 消息，避免执行期 transcript “顶上刷屏”。

### 7) 过程流回放（ThinkingAccordion）内容不完整 / 展开控制异常

**现象**
- 「Sub-task Execution」节点在最终消息的回放里无法展开（没有内容/没有展开箭头）。
- 四个节点（Planning/Executing/Reviewing/Answering）展开/收起无法独立控制：点一个全都一起开/一起关。
- 「Quality Review」「Final Answer」节点只有占位文案（`Review complete.` / `Answer delivered.`），没有实际聚合内容与最终回答摘要。
- 刷新后如果快照丢失，回放头部偶发显示 `0.0s`（误导性耗时）。

**根因**
- `ThinkingAccordion` 在最终消息回放里只渲染了 `ProcessFlow` 的结构节点，但没有把 SubTaskCard grid（执行细节）传进去。
- `ProcessFlow` 只维护了一个全局 `isExpanded`，导致所有节点共享同一展开状态。
- `ProcessFlow` 的「Quality Review」「Final Answer」节点没有接收任何真实内容，只能显示静态占位文本。
- 轻量兜底快照为了保证按钮不消失，曾使用 `Date.now()` 生成假的 start/end，导致 `LiveTimer` 显示 `0.0s`。

**修复**
- `ThinkingAccordion` 新增 `executionDetails/reviewText/finalAnswerText` 输入：
  - `Sub-task Execution` 节点可回放 SubTaskCard（工具调用+结果）；
  - `Quality Review` 节点优先显示后端持久化的 `[Quality Review]`（Judge verdict）；旧线程无该信息时显示提示文案；
  - `Final Answer` 节点显示最终回答的截断预览。
- `ProcessFlow` 改为按节点维护独立的展开状态（planning/executing/reviewing/answering 各自 toggle）。
- 兜底快照不再生成伪造的 phase timestamp（`phases: []`），避免误导性的 `0.0s` 计时器显示。

### 8) Mermaid 流程图/图表不渲染（只显示纯文本或 code block）

**现象**
- AI 输出 Mermaid（例如 `flowchart TD ...`）时，页面不会渲染为图，只能看到纯文本/代码块。

**根因**
- Mermaid 必须以 fenced code block 的形式出现，且 Mermaid 语法本身对 flowchart 的 label 语法较敏感：
  - 例如节点 label **嵌套 `[]`**（`B[定义状态 dp[...]]`）会触发解析错误（`Expecting ... got 'SQS'`）。

**修复**
- `MarkdownContent` 改为 `md-editor-rt` Preview，并配置 Mermaid 实例（`securityLevel: strict`）。
- 渲染前对 `flowchart/graph` 的 label 做规范化：检测到嵌套 `[]` 时自动改写为 Mermaid 友好的 `["..."]` 形式。
- Mermaid 输出的 SVG 中如出现 `&#91;`/`&#93;` 这类 bracket entities，会在前端解码，避免渲染为 `&...;` 乱码。

**使用提示**
- Mermaid 必须放在 Markdown 的 code fence 中才会被当作一段“代码块”识别：
  - ✅ ` ```mermaid` + Mermaid 内容 + ` ````
  - ❌ 直接把 `flowchart TD ...` 当普通段落输出（这不是 Markdown 代码块）
- Mermaid 节点 label 如果包含 `[`/`]`（例如 `dp[i][j]`），优先用引号包住 label：`B["定义状态 dp[i][j]"]`（或改用括号 `dp(i,j)`）。


## 其他发现（建议后续跟进）

### A) Tailwind 主题 token 冲突/缺失风险
- `tailwind.config.mjs` 曾扩展 `backgroundColor/textColor/borderColor` 指向一组未定义的 CSS 变量（例如 `--text-tertiary`），会导致诸如 `text-primary/bg-primary` 这类 shadcn token 语义被覆盖后“失效或异常”。
- 已通过移除这些扩展并统一到 shadcn 的 `colors` token 来降低风险。

### B) ESLint Fast Refresh warnings
- `frontend/src/components/ui/button.tsx` 与 `frontend/src/providers/*` 有 `react-refresh/only-export-components` 警告（不影响运行，但影响 HMR 体验）。
- 如需消除，建议拆分常量/Context 到单独文件。

### C) SubTaskCard 与 tool call 的进一步可用性
- 当前 ToolCallBox（compact）默认折叠，信息密度低；可考虑：
  - 对有 `error/interrupted` 状态的 tool call 默认展开
  - 或在 header 上显示 args/result 的简短摘要

### D) `yarn format:check` 会把 `.next/` 产物也纳入检查
- 当前 `frontend/package.json` 中 `format:check` 是 `prettier --check .`。
- 由于没有 `.prettierignore`，一旦本地运行过 `yarn dev` / `yarn build` 生成 `.next/`，`format:check` 会在大量生成文件上报 “Code style issues found…”，导致该命令基本不可用。
- 本次已添加 `frontend/.prettierignore`（至少忽略 `.next/`、`node_modules/`、`out/` 等）。
- 后续如需进一步降噪，可将脚本改为只检查 `src/`（如 `prettier --check "src/**/*.{ts,tsx,js,jsx,css,md,json}"`）。

### E) `yarn build` 在无外网/受限网络环境会因为 Google Fonts 拉取失败而报错
- Next.js 的 `next/font/google` 会在构建时请求 Google Fonts（例如 `Inter`）。
- 在 CI / 内网环境无法访问 `fonts.googleapis.com` 时会直接导致 build 失败。
- 建议：
  - 改用 `next/font/local` 并把字体文件加入仓库（或内部制品库）。
  - 或在 CI 中提供可访问外网的构建环境/代理（取决于部署策略）。


## 自测建议（回归 Checklist）

1. `cd frontend && yarn dev`，打开页面。
2. 用推理模型跑一轮完整流程：
   - answering 阶段看到 “Thinking...” + reasoning（可折叠）+ 最终回答纯文本流式输出
   - 完成后：最终回答消息下能看到可折叠的过程流（ThinkingAccordion）和 reasoning block（可折叠）
   - 刷新页面后：仍能看到该轮的 ThinkingAccordion 与 reasoning（来自 localStorage snapshot）
   - 打开 ThinkingAccordion 后：
     - Sub-task Execution 节点能看到 SubTaskCard 网格（且可独立展开/收起）
     - Quality Review / Final Answer 节点有实际文本内容（非占位）
3. 子任务执行阶段：
   - SubTaskCard 中每个任务卡片的 Tools 列表归属正确（不再平均错位）
   - ToolCallBox 展开能看到 Thought/Arguments/Result
   - 执行过程中不再在页面顶部刷出 ReAct transcript；工具调用在对应卡片内实时更新（pending→completed）
   - 子任务完成后，其 Result tab 立刻可见（不再等全部子任务结束）
