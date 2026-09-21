# RydeResolve-Agent 技术方案全景对比报告

> **项目**: RydeResolve-Agent — 多Agent自动争议调解系统  
> **场景**: 腾讯云 AI CAN DO IT Hackathon Singapore 2026 (Ryde 赛道)  
> **生成日期**: 2026年9月21日  
> **项目当前技术栈**: Hunyuan LLM + LangChain + ChromaDB + FastAPI + React + Docker

---

## 目录

1. [多Agent编排框架](#1-多agent编排框架)
2. [LLM API / 推理层](#2-llm-api--推理层)
3. [LLM 网关与路由](#3-llm-网关与路由)
4. [向量数据库与 RAG 引擎](#4-向量数据库与-rag-引擎)
5. [RAG 框架](#5-rag-框架)
6. [前端 UI 与 Dashboard](#6-前端-ui-与-dashboard)
7. [LLM 可观测性](#7-llm-可观测性)
8. [部署平台](#8-部署平台)
9. [实时通信层](#9-实时通信层)
10. [最终推荐方案](#10-最终推荐方案)

---

## 1. 多Agent编排框架

### 1.1 全景对比表

| 框架 | GitHub Stars | 维护方 | 语言 | 架构模式 | 状态 | 适合本项目 |
|------|-------------|--------|------|----------|------|-----------|
| **LangGraph** | 42K | LangChain Inc. | Python/JS | 图编排 (Pregel) | 活跃 | ✅ 强烈推荐 |
| **AutoGen** | 61K | Microsoft | Python/.NET | 对话式编排 | ⚠️ 维护模式 | ❌ 不推荐新项目 |
| **CrewAI** | 59K | CrewAI Inc. | Python | 角色协作 + 事件流 | 活跃 | ✅ 推荐 |
| **MetaGPT** | 71K | FoundationAgents | Python | SOP协作 (软件公司模拟) | 活跃 | ⚠️ 偏重 |
| **Microsoft Agent Framework** | 新 | Microsoft | Python/.NET | 企业级编排 (AutoGen继任者) | 活跃 | ⚠️ 过于企业级 |

### 1.2 详细对比

#### LangGraph ⭐ 推荐
| 优点 | 缺点 |
|------|------|
| • 持久化执行 (Durable Execution) — Agent崩溃可恢复 | • 低层API，上手门槛较高 |
| • Human-in-the-loop — 可在任意节点插入人工审核 | • 需配合LangSmith才能发挥最大调试能力 |
| • 短期+长期记忆，适合争议调解的多轮对话 | • 社区生态不如CrewAI成熟 |
| • 图结构编排，完美映射我们的6-Agent架构 | |
| • 与LangChain生态无缝集成 | |

#### CrewAI ⭐ 推荐
| 优点 | 缺点 |
|------|------|
| • 角色制设计 — 天然映射Passenger/Driver/Judge | • 对复杂图编排支持不如LangGraph |
| • Crews(自治) + Flows(控制流) 双模式 | • 性能开销略大 |
| • 10万+认证开发者，社区最活跃 | • 深度定制需深入框架源码 |
| • 内置Memory、Tools、MCP支持 | |
| • human-in-the-loop原生支持 | |

#### AutoGen ❌ 不推荐新项目
| 优点 | 缺点 |
|------|------|
| • GitHub star最高，社区大 | • **已进入维护模式**，不再更新 |
| • 多Agent对话模式丰富 | • 建议迁移到Microsoft Agent Framework |
| • AutoGen Studio提供可视化 | • 架构复杂，Python+.NET双语言 |

### 1.3 本项目适用性分析

我们的架构有 **并行调查 → 对抗辩论 → 仲裁裁决** 的非线形流程：

```
Report → Collector → Classifier → Parallel(Passenger, Driver, Policy) → Arbitration → Execution
```

- **LangGraph 最匹配** — 图结构天然表达并行分支和汇聚
- **CrewAI 次选** — 角色制直接映射Agent身份，但并行控制不如LangGraph精细
- **当前项目用 "LangChain + custom async pipeline"** → 如果团队要升级，LangGraph是自然过渡路径

---

## 2. LLM API / 推理层

### 2.1 全景对比表

| 提供商 | 代表模型 | 价格(输入/输出 per 1M tokens) | 最大上下文 | Function Calling | 中文能力 | 适合本项目 |
|--------|---------|------|------|------|---------|-----------|
| **Tencent Hunyuan** | Hunyuan-Pro/Standard/Lite | 免费 ~ ¥0.03/1K | 32K | ✅ | ⭐ 最佳 | ✅ 已选用 |
| **OpenAI** | GPT-4o / o1 | $0.15-$15 / $0.60-$60 | 128K-200K | ✅ 最成熟 | 好 | ✅ Fallback |
| **Anthropic** | Claude 3.5 Sonnet | $3-$15 / $15-$75 | 200K | ✅ | 好 | ⚠️ 备选 |
| **Google Gemini** | Gemini 2.0 Flash | $0.10-$1.25 / $0.40-$5 | 1M-2M | ✅ | 好 | ⚠️ 备选 |
| **Together AI** | Llama 3.x 200+模型 | $0.18-$5 / $0.20-$5 | 128K | ✅ 部分模型 | 一般 | ⚠️ 开源模型 |
| **Groq** | Llama 3.x | $0.05-$0.59 / $0.08-$0.79 | 8K-128K | ✅ | 一般 | ⚠️ 极速推理 |
| **Fireworks AI** | 100+开源模型 | $0.20-$0.90 | 128K | ✅ + 语法约束 | 一般 | ⚠️ 结构化输出 |
| **Replicate** | 数千模型 | 按秒计费 | 不定 | ⚠️ 有限 | 不定 | ❌ 不适合 |

### 2.2 推荐策略

```
首选: Tencent Hunyuan (Pro for仲裁, Standard for收集/分类, Lite for执行通知)
  ↓ Fallback
次选: OpenAI GPT-4o (结构化输出, function calling最成熟)
  ↓
极速推理场景: Groq (Llama 3.1 — 用于实时辩论轮次)
```

**理由**:
1. 比赛要求使用腾讯云技术 → Hunyuan是首选
2. Hunyuan中文能力最强 → 适合新加坡多语言场景(EN/CN/MS/Tamil)
3. OpenAI作为fallback → API格式兼容，切换成本低
4. Groq的500+ tokens/sec → 如果需要实时辩论展示，速度无敌

---

## 3. LLM 网关与路由

### 3.1 对比表

| 方案 | 类型 | 数据主权 | 部署方式 | 成本控制 | 路由/兜底 | 适合本项目 |
|------|------|---------|----------|---------|----------|-----------|
| **LiteLLM** | 开源自托管 | ✅ 完全自有(VPC) | Docker/K8s/Helm | ⭐ 硬预算上限+团队分账 | ⭐ 自动路由+语义缓存 | ✅ 推荐(生产) |
| **OpenRouter** | 云SaaS | ❌ 数据离开基础设施 | 云托管 | 中等(统一计费) | 基础路由+兜底 | ✅ 推荐(快速原型) |
| **直接API调用** | 无网关 | 各提供商 | N/A | ❌ 难以集中控制 | ❌ 手动编码 | ⚠️ 当前方案 |

### 3.2 详细分析

#### LiteLLM ⭐ 生产环境推荐
- **140+提供商, 1800+模型** 统一OpenAI兼容API
- **Rust网关**: p99延迟仅0.66ms
- **硬预算上限**: 每Key/团队/组织，超额自动熔断
- **自动路由**: 简单prompt→便宜模型, 复杂prompt→强模型
- **语义缓存**: 相同问题不重复付费
- **安全**: PII脱敏, prompt注入检测, 密钥泄露保护
- **MIT开源**, 可自托管在腾讯云VPC

#### OpenRouter ⭐ 快速原型推荐
- 500+模型, 80+提供商, 单一API
- 自动故障转移: 提供商宕机自动切换
- 400T+月tokens处理量, 10M+用户
- 无需自建基础设施
- 适合Hackathon快速验证

### 3.3 本项目建议

| 阶段 | 推荐方案 | 理由 |
|------|---------|------|
| Hackathon开发期 | **直接Hunyuan API** | 比赛要求，最简 |
| Hackathon展示期 | **OpenRouter** (Hunyuan + GPT-4o fallback) | 展示多模型能力 |
| 生产部署 | **LiteLLM自托管** | 成本控制+数据主权+自动路由 |

---

## 4. 向量数据库与 RAG 引擎

### 4.1 全景对比表

| 向量数据库 | 类型 | 混合搜索 | 可扩展性 | 易用性 | 中文优化 | 适合本项目 |
|-----------|------|---------|---------|--------|---------|-----------|
| **腾讯云 VectorDB** | 全托管云 | ✅ 稠密+稀疏+标量 | ⭐ 分布式存算分离 | ⭐ 控制台+API | ⭐ 深度优化 | ✅ 已选用/推荐 |
| **Pinecone** | 全托管Serverless | ✅ 原生 | ⭐ Serverless弹性 | ⭐ 极高 | 一般 | ⚠️ 备选 |
| **Weaviate** | 开源+云 | ⭐ 最强(BM25+稠密) | 高 | 高 | 一般 | ⚠️ 备选 |
| **Qdrant** | 开源+云(Rust) | ✅ | 高 | 中高 | 一般 | ⚠️ 备选 |
| **Milvus/Zilliz** | 开源+云 | ✅ | ⭐ 百亿级 | 中(自建难) | 一般 | ⚠️ 过重 |
| **ChromaDB** | 开源轻量 | ❌ 弱 | ❌ 低 | ⭐ 极高 | 一般 | ✅ 当前选用 |
| **pgvector** | PG扩展 | ✅ SQL+全文 | 中 | 高(熟悉SQL) | 一般 | ⚠️ 备选 |

### 4.2 本项目关键需求

我们的Policy Agent需要从Ryde ToS、Code of Conduct、退款政策中做RAG检索：

1. **数据量小** — 策略文档数十页，不是百亿级
2. **中文+英文混合** — 新加坡多语言政策文档
3. **混合搜索重要** — 需要关键词精确匹配(条款编号)+语义模糊搜索
4. **比赛要求用腾讯云** → VectorDB天然契合

### 4.3 建议升级路径

```
当前: ChromaDB (本地轻量)
  ↓ 升级理由: 混合搜索弱, 中文优化不足
推荐: 腾讯云 VectorDB
  - 原生中文embedding优化
  - 稠密+稀疏混合检索 (精确条款号 + 语义匹配)
  - 与Hunyuan生态无缝集成
  - 比赛加分项(使用腾讯云技术)
  ↓ 如果不用腾讯云
备选: Qdrant Cloud (免费层, Rust高性能, 混合搜索)
```

---

## 5. RAG 框架

### 5.1 对比表

| 框架 | 核心定位 | 文档解析 | 索引结构 | 混合检索 | 适合本项目 |
|------|---------|---------|---------|---------|-----------|
| **LangChain** | LLM编排(通用) | 基础 | 向量为主 | 需集成 | ✅ 已选用(通用性强) |
| **LlamaIndex** | 数据摄取+复杂解析 | ⭐ 最佳(表格/图表/手写) | ⭐ 层级/树/关键词/向量 | ✅ | ✅ 推荐(政策文档复杂) |
| **Haystack** | 搜索+QA管线 | 好(标准PDF) | 强(BM25+向量) | ⭐ 最强 | ⚠️ 偏搜索 |

### 5.2 本项目分析

我们的RAG需求:
- Ryde ToS / Code of Conduct → 主要是文本, 不太复杂
- 退款政策 → 可能有表格
- 判例库(Stretch Goal) → 需要语义检索

**建议**: 保持LangChain(已选) + 可选集成LlamaIndex的LlamaParse用于复杂文档解析

---

## 6. 前端 UI 与 Dashboard

### 6.1 全景对比表

| 方案 | 类型 | Dashboard能力 | AI流式支持 | 定制自由度 | 学习曲线 | 适合本项目 |
|------|------|-------------|----------|----------|---------|-----------|
| **shadcn/ui** | 复制粘贴组件集 | ⭐ 生产级Dashboard块 | ✅ AI streaming演示 | ⭐ 完全拥有源码 | 低 | ✅ 强烈推荐 |
| **Vercel AI SDK** | TS工具包 | N/A (配合UI库) | ⭐ 统一流式原语 | ⭐ Provider无关 | 低 | ✅ 强烈推荐 |
| **Tremor** | npm组件库 | ⭐ 专为Dashboard设计 | ❌ 需自建 | 中(Tailwind) | 低 | ⚠️ 仅Dashboard |
| **MUI** | npm组件库 | 需MUI X Pro(付费) | ❌ 需自建 | 中(Emotion) | 中 | ⚠️ 笨重 |
| **Ant Design** | npm组件库 | 数据表格强 | ❌ 需自建 | 中(Less) | 中 | ⚠️ 企业风 |
| **Chakra UI** | npm组件库 | 一般 | ❌ 需自建 | 中(Styled) | 低 | ⚠️ 通用 |
| **LobeChat/LobeHub** | AI聊天应用 | ❌ 聊天界面 | ✅ 内置 | 低(成品应用) | 低 | ❌ 太重 |
| **Chatbot UI** | AI聊天应用 | ❌ 聊天界面 | ✅ 内置 | 低 | 低 | ❌ 太重 |

### 6.2 推荐组合

```
Next.js (框架)
  + shadcn/ui (组件层 — 完全拥有源码, 生产级Dashboard块)
  + Vercel AI SDK (AI流式层 — 统一多Provider, 生成式UI)
  + Tailwind CSS (样式层)
```

**理由**:
1. **shadcn/ui** — 不是npm依赖, 代码直接在项目中, 可随意改 → 适合Hackathon快速定制
2. **Vercel AI SDK** — 统一流式原语, Agent输出可直接渲染到UI, 支持生成式UI(RSC)
3. 两者天然搭配, shadcn/ui官网就有AI streaming演示
4. Tremor可以作为补充(如果需要更丰富的图表)

### 6.3 与当前项目对比

当前: `React + TypeScript + Vite + Tailwind CSS`
推荐: `Next.js + shadcn/ui + Vercel AI SDK + Tailwind CSS`

| 差异 | 当前 | 推荐 | 理由 |
|------|------|------|------|
| 构建工具 | Vite | Next.js | SSR + API Routes + 部署更简 |
| 组件 | 无统一库 | shadcn/ui | 生产级Dashboard块 |
| AI流式 | 需手动SSE | AI SDK | 统一Provider流式原语 |

> 如果不想换框架, 也可以 `Vite + shadcn/ui + AI SDK` (AI SDK支持Vite)

---

## 7. LLM 可观测性

### 7.1 全景对比表

| 工具 | 类型 | 开源 | 层级追踪 | Agent框架集成 | 成本/延迟分析 | 适合本项目 |
|------|------|------|---------|-------------|-------------|-----------|
| **Langfuse** | 端到端平台 | ✅ MIT | ⭐ 层级Trace | ⭐ CrewAI/AutoGen等 | ⭐ 细粒度 | ✅ 强烈推荐 |
| **Phoenix (Arize)** | 可观测+评估 | ✅ ELPL | ⭐ 强 | 好 | 好 | ✅ 推荐 |
| **Helicone** | 代理+日志 | ✅ | 中(代理层) | 一般 | 好(成本追踪) | ⚠️ 偏简单 |
| **OpenLLMetry** | OTel标准 | ✅ Apache | 中(导出到其他工具) | 一般 | 依赖后端 | ⚠️ 仅标准 |
| **Weights & Biases** | ML实验 | ❌ SaaS | 中 | 一般 | 中 | ❌ 偏ML实验 |

### 7.2 Langfuse 深度分析 ⭐

**为什么最适合多Agent系统**:
1. **层级追踪** — 捕获每个LLM调用、工具调用、检索步骤, 以层级结构展示
   - 对我们的6-Agent架构至关重要: 可看到 Collector→Classifier→Passenger→Arbitration 全链路
2. **框架原生集成** — 直接支持 CrewAI, AutoGen, OpenAI Agents SDK, Microsoft Agent Framework
3. **成本+延迟细分** — 每个Agent步骤的token花费和延迟可单独追踪
4. **闭环评估** — 生产trace → 数据集 → 离线实验 → 新prompt → 一键回滚
5. **MIT开源** — 可自托管, 处理90B+月事件, Fortune 50中21家在用

### 7.3 建议

```
开发期: Langfuse自托管 (Docker, 免费)
  - 追踪每个Agent的LLM调用
  - 可视化6-Agent通信链路
  - 成本追踪(Hunyuan + fallback模型)
展示期: Langfuse Dashboard截图 → 展示系统可观测性
```

---

## 8. 部署平台

### 8.1 全景对比表

| 平台 | 易用性 | 可扩展性 | 成本 | 持久进程 | 适合本项目 |
|------|--------|---------|------|---------|-----------|
| **腾讯云 (CVM/TKE)** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ | ✅ 比赛首选 |
| **Fly.io** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ Machines | ✅ 推荐(非腾讯) |
| **Railway** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | ✅ MVP快速 |
| **Render** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ Workers | ⚠️ 备选 |
| **Vercel** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ❌ Serverless | ⚠️ 仅前端 |
| **Docker + VPS** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ | ⚠️ 备选 |
| **K8s (TKE/EKS)** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ | ❌ 过重 |
| **AWS** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | ❌ 过重 |

### 8.2 推荐架构

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Vercel / 腾讯云  │     │  腾讯云 CVM /     │     │  Upstash /       │
│   (Dashboard     │◄───►│  Fly.io          │◄───►│  腾讯云Redis     │
│   前端)           │     │  (Agent Workers) │     │  (Pub/Sub +     │
│                  │     │                  │     │   State Store)   │
│ Next.js +        │     │ Python FastAPI   │     │                 │
│ shadcn/ui        │     │ + LangChain/     │     │ 实时事件流       │
│ + AI SDK         │     │   CrewAI         │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │
        │                        ▼
        │               ┌──────────────────┐
        │               │  腾讯云 VectorDB   │
        │               │  / Qdrant Cloud  │
        │               │  (Agent 记忆)     │
        └──────────────►└──────────────────┘
```

### 8.3 比赛场景推荐

| 优先级 | 推荐方案 | 月成本 | 部署时间 |
|--------|---------|--------|---------|
| **比赛要求用腾讯云** | 腾讯云 CVM + TKE | ¥100-500 | ~2小时 |
| **最快部署** | Railway (全栈) | ~$5-20 | ~10分钟 |
| **最佳平衡** | Fly.io(Agents) + Vercel(UI) + Upstash(Redis) | ~$15-30 | ~30分钟 |
| **最便宜** | Docker + Hetzner VPS | ~$5-15 | ~1-2小时 |

---

## 9. 实时通信层

### 9.1 对比表

| 技术 | 延迟 | 复杂度 | 适合场景 | 本项目适用 |
|------|------|--------|---------|-----------|
| **SSE (Server-Sent Events)** | ~10ms | 低 | Agent状态更新 | ✅ 前端展示Agent辩论 |
| **WebSocket (Socket.io)** | ~10ms | 中 | 双向通信 | ✅ 用户提交争议 |
| **Redis Pub/Sub** | ~1ms | 中 | Agent间协调 | ✅ 后端Agent通信 |
| **NATS** | ~1ms | 中 | 高吞吐消息 | ⚠️ 过重 |

### 9.2 推荐组合

```
用户交互层: WebSocket (争议提交, 实时状态查询)
Agent状态推送: SSE (单向流, 前端展示辩论过程)
Agent间通信: Redis Pub/Sub (后端内部)
```

```python
# FastAPI + SSE 实时推送Agent辩论
@app.get("/stream/debate/{dispute_id}")
async def stream_debate(dispute_id: str):
    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"debate:{dispute_id}")
        async for message in pubsub.listen():
            yield f"data: {message['data']}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## 10. 最终推荐方案

### 10.1 三套方案

#### 方案A: 腾讯云全栈 (比赛最优) ⭐⭐⭐

| 层 | 技术 | 理由 |
|----|------|------|
| LLM | **Tencent Hunyuan** (Pro/Standard/Lite) | 比赛要求, 中文最强 |
| Agent框架 | **LangGraph** (升级自当前LangChain) | 图编排完美匹配6-Agent架构 |
| LLM路由 | **LiteLLM自托管** (Hunyuan + GPT-4o fallback) | 成本控制+自动故障转移 |
| 向量数据库 | **腾讯云 VectorDB** (升级自ChromaDB) | 混合搜索+中文优化+比赛加分 |
| RAG框架 | **LangChain** (保留) + LlamaIndex(复杂文档) | 已有基础 |
| 前端 | **Next.js + shadcn/ui + Vercel AI SDK** | 生产级Dashboard+AI流式 |
| 可观测性 | **Langfuse自托管** | 层级追踪6-Agent链路 |
| 部署 | **腾讯云 CVM + Docker Compose** | 比赛要求+成本可控 |
| 实时通信 | **SSE + Redis Pub/Sub** | 辩论过程实时展示 |

#### 方案B: 开源全栈 (非腾讯云备选) ⭐⭐

| 层 | 技术 |
|----|------|
| LLM | OpenAI GPT-4o + Groq (Llama 3.1 极速) |
| Agent框架 | LangGraph |
| LLM路由 | OpenRouter (快速) 或 LiteLLM自托管 (生产) |
| 向量数据库 | Qdrant Cloud (免费层, Rust高性能) |
| 前端 | Next.js + shadcn/ui + Vercel AI SDK |
| 可观测性 | Langfuse自托管 |
| 部署 | Fly.io (Agents) + Vercel (UI) + Upstash (Redis) |

#### 方案C: 最简快速原型 (Hackathon冲刺) ⭐

| 层 | 技术 |
|----|------|
| LLM | Hunyuan直接API |
| Agent框架 | 保持当前 LangChain + custom async |
| 向量数据库 | 保持 ChromaDB (够用) |
| 前端 | 保持 React + Vite, 加 shadcn/ui + AI SDK |
| 部署 | Docker Compose (已有) |

### 10.2 推荐升级路径

```
当前状态                          推荐升级                      优先级
─────────────────────────────────────────────────────────────────────
LangChain + custom async    →   LangGraph                    高 (架构匹配)
ChromaDB                    →   腾讯云 VectorDB               高 (混合搜索+比赛加分)
React + Vite                →   + shadcn/ui + AI SDK          中 (UI升级)
直接Hunyuan API              →   + LiteLLM (fallback)         中 (可靠性)
无可观测性                   →   + Langfuse                    低 (但展示加分)
Docker Compose              →   腾讯云 CVM 部署               低 (已有基础)
```

### 10.3 成本估算

| 组件 | 方案A(腾讯云) | 方案B(开源) | 方案C(最简) |
|------|-------------|------------|------------|
| LLM | Hunyuan (免费-¥0.03/1K) | GPT-4o (~$50/mo) | Hunyuan (免费) |
| 向量DB | VectorDB (~¥50-200/mo) | Qdrant Free | ChromaDB (免费) |
| 部署 | CVM (~¥100-500/mo) | Fly.io (~$10-30) | Docker (免费) |
| 可观测性 | Langfuse自托管 (免费) | Langfuse自托管 (免费) | 无 |
| **月总计** | **¥150-700** | **~$60-80** | **¥0** |

---

## 附录: 技术选型决策树

```
是否必须用腾讯云技术?
├── 是 (比赛要求)
│   ├── LLM → Hunyuan (Pro/Standard/Lite)
│   ├── 向量DB → 腾讯云 VectorDB
│   ├── 部署 → 腾讯云 CVM/TKE
│   └── Agent框架 → LangGraph (与腾讯云无关, 可叠加)
│
└── 否 (自由选择)
    ├── 追求质量 → OpenAI GPT-4o + LangGraph + Pinecone
    ├── 追求速度 → Groq + CrewAI + Qdrant
    └── 追求成本 → Together AI + LangGraph + ChromaDB
```

---

> **报告总结**: 对于 RydeResolve-Agent 这个多Agent争议调解系统，最优方案是 **方案A(腾讯云全栈)**：保持Hunyuan作为LLM引擎，升级ChromaDB到腾讯云VectorDB获得混合搜索能力，升级Agent框架到LangGraph以更好表达6-Agent并行-汇聚架构，前端增加shadcn/ui+Vercel AI SDK获得生产级Dashboard和AI流式能力，加Langfuse实现全链路可观测性。这套组合既满足比赛要求，又在技术先进性上有充分竞争力。
