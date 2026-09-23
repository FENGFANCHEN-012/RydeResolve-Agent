# 开发日志 — 关键节点记录

> **最后更新**: 2026-09-23
>
> 本日志记录每次 session 的关键节点、决策、问题和下一步。
> 最近一次更新同步了 teammate (Zhilin-sp) 在 `feature/rider-advocate-agent` 和 `feature/driver-advocate-agent` 分支上完成的两个 agent 真实 LLM 实现。

---

## Session 1: 2026-09-21（billy 单人 session）

### 节点 1: 项目初始化
- **时间**: 上午
- **内容**: 创建项目结构，初始化 Git 仓库
- **文件**: `src/`, `frontend/`, `data/`, `.env.example`
- **提交**: 初始提交

### 节点 2: 基础 RAG 管道
- **时间**: 上午
- **内容**: 实现文档解析、向量检索、问答
- **新增文件**:
  - `src/rag/document_parser.py` — PDF/DOCX/TXT/MD 解析
  - `src/rag/embedding.py` — Hunyuan embedding + hash fallback
  - `src/rag/indexer.py` — ChromaDB 索引
  - `src/rag/retriever.py` — 向量检索
  - `src/rag/qa_engine.py` — RAG 问答
  - `src/core/llm_client.py` — OpenAI 兼容 LLM 客户端
  - `src/api/main.py` — FastAPI 端点
  - `frontend/index.html` — 前端 UI
- **提交**: `b787fbb` — feat: add RAG pipeline, frontend UI, and accuracy testing

### 节点 3: 端到端测试
- **时间**: 中午
- **内容**: 测试上传、检索、问答全流程
- **结果**: ✅ 全部通过（但 embedding 是 hash 模式，相似度为 0）

### 节点 4: 迁移到 Google Gemini
- **时间**: 下午
- **原因**: 腾讯混元 API Key 获取困难，模型已下线
- **变更**:
  - `src/config.py` — 改为 Gemini 配置
  - `src/core/llm_client.py` — 改为 Gemini SDK
  - `src/rag/embedding.py` — 改为 Gemini embedding
  - `.env` — 更新 API Key
- **问题**: ChromaDB dimension mismatch（1024 -> 3072）
- **解决**: 删除旧 collection，重新索引
- **提交**: `233a01f` — feat: migrate LLM and embedding from Hunyuan to Google Gemini

### 节点 5: 高级检索管道（5 个优化）
- **时间**: 下午
- **内容**: 实现 5 个 RAG 检索优化技术
- **新增文件**:
  - `src/rag/query_rewriter.py` — Query Rewriting
  - `src/rag/hybrid_search.py` — Hybrid Search (Vector + BM25)
  - `src/rag/reranker.py` — Re-ranking
  - `src/rag/smart_chunker.py` — Smart Chunking
  - `src/rag/confidence_scorer.py` — Confidence Scoring
  - `src/rag/advanced_retriever.py` — Advanced Retriever orchestrator
  - `src/rag/advanced_qa_engine.py` — Advanced QA Engine
- **API 变更**:
  - `/api/rag/search?advanced=true` — 支持高级检索
  - `/api/rag/ask?advanced=true` — 支持高级问答（默认开启）
- **测试结果**:
  - "What is the refund policy?" → Confidence: 0.81, Should answer: True
  - "What is the weather today?" → Confidence: 0.18, Should answer: False
- **提交**: `7922d15` — feat: add advanced RAG retrieval pipeline

### 节点 6: 真实 Ryde 政策文档入库
- **时间**: 晚上
- **内容**: 用真实 Ryde 官方政策替换之前的虚构政策
- **变更**:
  - 改写 6 篇老政策（cancellation / dispute_refund / driver_guidelines / rider_code / safety / terms_of_use）
  - 新增 5 篇政策（privacy_policy、driver_performance_standards、ratings_moderation_policy、dispute_appeals_policy、dispute_resolution_guide）
  - `dispute_resolution_guide.md` 把 7 个 hackathon 场景映射到官方条款
  - 修了一个 indexing 脚本的 bug（`index_policies` -> `index_documents`）
  - 12 个文档入 ChromaDB，41 个 chunks，验证 RAG 检索 OK
- **政策来源**:
  - Terms of Use: https://rydesharing.com/terms-of-use/
  - Privacy Policy: https://rydesharing.com/privacy-policy/
  - Code of Conduct: https://rydesharing.com/code-of-conduct/
  - Help Center: https://help.rydesharing.com/hc/en-us
- **提交**: `1d5afed` — feat: replace fictional policies with real Ryde policies from official sources

### 节点 7: Mock 假 Dispute Dataset
- **时间**: 晚上
- **提交**: `b39980a` — feat: cherry-pick agent implementations and mock data from feature branches
- **包含**:
  - `data/mock_disputes/no_show_01.json`
  - `data/mock_disputes/no_show_02.json`
  - `data/mock_disputes/route_deviation_01.json`
  - `data/mock_disputes/route_deviation_02.json`
  - `data/mock_disputes/README.md`（明确标注是合成 hackathon demo 数据）

### 节点 8: Session 总结 & 交接文档
- **时间**: 傍晚
- **内容**: 创建交接文档
- **新增文件**:
  - `SESSION_SUMMARY.md` — Session 技术总结
  - `docs/01_PROJECT_REQUIREMENTS.md` — 项目要求
  - `docs/02_TECH_RESEARCH.md` — 技术调研
  - `docs/03_DEVELOPMENT_LOG.md` — 开发日志（本文件）
  - `docs/04_SCORING_GUIDE.md` — 评分指南
  - `docs/05_NEXT_STEPS.md` — 下一步工作清单
- **提交**: `bc43021` — docs: add session summary for transfer

---

## Session 2: 2026-09-22（billy + Zhilin-sp 多人 session）

#### 🚨 **重要决定：放弃 Tencent Hunyuan，统一用 Google Gemini**
理由：Hunyuan API 难以获取 + 接口不稳定 + Gemini 已有免费额度。

### 节点 9: Classifier Agent 升级 — 关键词 → LLM
- **作者**: billy
- **提交**: `1de51e7` — feat: upgrade classifier from keyword-based to LLM-based with P0 safety fallback
- **变更**:
  - 双重策略：P0 安全关键词快速扫描（离线、即时） + Gemini LLM 分类
  - 输入丰富：trip / payment / chat log / GPS / ratings 都喂给 LLM
  - LLM 失败时安全 fallback（返回 requires_human=true）
  - LLM 输出做模糊匹配验证
- **效果**: 比关键词方法准确率显著更高

### 节点 10: Ryde Platform API 集成（contract layer）
- **作者**: billy
- **提交**: `3a4fd51` — feat: integrate Ryde platform API for rich dispute context
- **新增**: `src/integrations/ryde_api.py` — RydeAPIClient
  - ⚠️ **重要说明**：**这是一个 contract layer**，**不是真实 API 调用**。代码里所有 `_get_mock_order()` / `_get_default_mock_order()` 都是从 `data/mock_disputes/*.json` 或硬编码 mock 数据里读出来的，`base_url="https://api.rydesharing.com/v1"` **从来没有被真实调用过**。Ryde Technologies 没有公开 API / MCP server（已确认：https://www.rydesharing.com/ 无 developer portal）。
  - 保留原因：统一接口契约，未来 Ryde 一旦给 API access，只需要替换 `_get_mock_order` 改成 HTTP call，**所有上层代码（Collector / Orchestrator / API）完全不动**。
- **Pydantic models**:
  - `TripDetails`、`PaymentDetails`、`ChatMessage`、`GPSPoint`、`UserProfile`、`EvidenceItem`
- **CollectorAgent 升级**:
  - 现在通过 RydeAPIClient 拉平台数据
  - DisputeContext 富化：trip / payment / chat / GPS / profiles
  - 支持 evidence 上传和 language 选择
  - 容错：API 失败时降级为基础 context

### 节点 11: Rider Advocate Agent — 真实 LLM 实现
- **作者**: Zhilin-sp（teammate）
- **提交**: `b95a406` — feat: implement evidence-grounded rider advocate agent
- **变更**: `src/agents/passenger.py` 从 stub 变成完整 LLM 调用
  - RAG 检索政策条款
  - 强 system prompt（带"never assume passenger correct"规则 + JSON 输出格式）
  - `_parse_llm_json()` 处理 markdown code fence + fallback
  - `_sanitize_policy_references()` 删掉不在 retrieved set 里的引用（防幻觉）
  - `_evidence_only_result()` 当 policies 为空时返回安全 fallback
  - `rebut()` 处理 opponent_argument 当作 untrusted content（防 prompt injection）
- **测试**: 新增 `tests/test_passenger_agent.py`（516 行测试）

### 节点 12: Driver Advocate Agent — 真实 LLM 实现
- **作者**: Zhilin-sp（teammate）
- **提交**: `bfde2a6` — feat: implement evidence-grounded driver advocate agent
- **变更**: `src/agents/driver.py` 和 Passenger Agent 对称
  - 同样的 evidence-grounded + policy-sanitize 机制
  - 同样的 prompt injection 防御
  - 测试：`tests/test_driver_agent.py`（644 行）

### 节点 13: 合并 + 测试 fix
- **提交**: `5e807a4` — fix: merge remote test suites and fix compatibility issues
- **提交**: `849d94a` — feat: merge enhanced evidence-grounded agents from feature/rider-advocate-agent
- **PR**: `#4` (feature/rider-advocate-agent) 和 `#5` (feature/driver-advocate-agent)

### 节点 14: 风格对齐 remote main
- **作者**: billy
- **提交**: `22fe25d`, `d389a04`, `62f95e7`, `ca72712`, `1b4c7db`, `5dee6e9`, `f4e5c32`, `4df47ec`
- **内容**: 把 arbitrator / debate / driver / collector / passenger 的 docstring / prompt 跟 remote main 对齐

---

## Session 3: 2026-09-23（当前 session）

### 节点 15: 状态盘点
- **作者**: billy（当前 user）
- **触发**: user 询问 "什么完成了什么没有完成"
- **盘点**:
  - ✅ 完整 LLM 集成：Collector / Classifier / Passenger / Driver / Policy / Debate / Orchestrator / Confidence
  - ✅ RAG 5 大优化
  - ✅ 真实 Ryde 政策（12 篇）
  - ✅ Mock disputes（4 个 case）
  - ✅ Tests（passenger / driver / policy / classifier / rag）
  - 🔴 **未完成**：Arbitrator (`src/agents/arbitrator.py`) 仍是 stub — `confidence=0.0`、`rationale=""`，永远触发 escalation
  - 🟠 **部分完成**：Executor (`src/agents/executor.py`) 只有 actions_taken 列表，没真实调用平台 API
  - 🔴 **未做**：Frontend 完整 dashboard（目前 `frontend/index.html` 只有 RAG 4 tab，没有 dispute filing / live debate / verdict display）
  - 🟡 **未做**：Demo script、Architecture diagram、Multilingual notifications

### 节点 16: Teammate 未提交修改 — DESIGN.md + Frontend 改版
- **作者**: 另一位 teammate（uncommitted changes）
- **变更**:
  - `frontend/index.html` 全面重写 CSS（1502 行 diff）
    - 标题：`RydeResolve-Agent — RAG Knowledge Base` → `RydeResolve-Agent — Dispute Resolution Dashboard`
    - 引入 Rubik / Space Grotesk Google Fonts
    - 新增 `:root` token 系统（Brand & Accent / Surface / Hairline / Text / Rounded / Spacing / Shadows）
    - 颜色方案换成 deep purple-violet (`--primary: #150f23`) + electric lime (`--accent-lime: #c2ef4e`) + hot pink (`--accent-pink: #fa7faa`)
    - 添加 `body::before` starfield 装饰层
    - Top bar 改为 56px 高 + lime status dot
    - 标签从 `<div>` 改成 `<button>`（无障碍）
    - 注释掉的旧主题保留在 diff 里
  - 新增 `DESIGN.md`（387 行）— 设计 tokens 文档，Sentri-Inspired design language
- **状态**: ⚠️ **uncommitted**（不在任何 branch，未 push），需要确认是否要 commit / 是否要保留

### 节点 17: 关键判断（user 提出）
- **话题**: Ryde API 链接是否有意义？
- **结论**:
  - Ryde Technologies **不公开 API / MCP server**（已确认）
  - 代码里的 `RydeAPIClient` **100% 是 mock**，URL 没真实调用
  - 但保留价值：统一契约层 / 接口契约清晰 / 未来易替换
  - **不要**在 demo 文本里叫它"Ryde API 集成"，要叫"simulated integration contract"
- **建议**: 改 `ryde_api.py` docstring + README + 演示脚本里的措辞

---

## 关键决策记录（更新版）

### 决策 1: 为什么选 Gemini 而不是腾讯混元？
- **时间**: 2026-09-21 下午
- **选项**: 腾讯混元 vs Google Gemini
- **选择**: Google Gemini
- **原因**:
  1. 腾讯混元 OpenAI 兼容接口已下线
  2. TokenHub 需要重新申请，流程复杂
  3. Gemini 免费额度充足，API Key 容易获取
  4. 国际站访问稳定
- **影响**: 需要重写 llm_client.py 和 embedding.py

### 决策 2: 为什么选 ChromaDB 本地模式？
- **时间**: 2026-09-21 上午
- **选项**: ChromaDB Docker vs 本地持久化
- **选择**: 本地持久化
- **原因**:
  1. 无需 Docker，部署简单
  2. 数据存在本地文件，不怕丢失
  3. 性能足够（数据量小）
- **影响**: 不能多实例共享，但比赛场景够用

### 决策 3: 为什么做 5 个 RAG 优化？
- **时间**: 2026-09-21 下午
- **选择**: Query Rewrite + Hybrid Search + Re-ranking + Smart Chunking + Confidence Scoring
- **原因**: 比赛评分看重技术深度 + 多 Agent 需要高质量检索

### 决策 4: 为什么 Agent 用"advocate perspective"设计而不是中立 judge？
- **时间**: 2026-09-22
- **选择**: Passenger Agent 和 Driver Agent **双方各 advocate 自己的立场** + Arbitrator 综合
- **原因**:
  1. 多 Agent 辩论能暴露矛盾证据，更公平
  2. 比单 LLM 直接裁决更能展示 reasoning chain
  3. 每个 advocate 强制要求列出 `contradictory_evidence`，避免一边倒
- **影响**: 需要专门加 `_sanitize_policy_references()` 防 hallucinated policy references

### 决策 5: 为什么 Mock Ryde API 保留为 contract layer？
- **时间**: 2026-09-22
- **选择**: 保留 `src/integrations/ryde_api.py` 当作 contract layer，**不**叫它"集成 Ryde API"
- **原因**:
  1. Ryde 不公开 API / MCP（已确认）
  2. 代码 100% 从 `data/mock_disputes/*.json` 读数据，URL 没真实调用
  3. 但 Pydantic models（TripDetails / PaymentDetails 等）反映了真实 Ryde 平台结构，未来易替换
  4. judge 会查 — 必须诚实标注"simulated"

---

## 当前 Pipeline 状态

```
Report -> [Collector] -> [Classifier]
                    |
   ┌────────────────┼────────────────┐
   |                |                |
[Passenger Agent]  [Driver Agent]  [Policy Agent (RAG)]
   |                |                |
   └────────────────┼────────────────┘
                    |
            [Debate Engine] ← 真实跑通
                    |
            [Arbitrator]  ← 🔴 仍是 stub
                    |
            Confidence check
                    |
            [Executor]  ← 🟠 仅 actions_taken 列表
```

---

## 待解决问题（更新版）

| # | 问题 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | Arbitrator 仍是 stub（`confidence=0.0`） | 🔴 P0 | 未开始 |
| 2 | Frontend 没有 dispute filing / live debate / verdict | 🔴 P0 | 部分（teammate 已改 RAG 部分 CSS 风格） |
| 3 | Executor 没真实调用 / 没 multilingual notification | 🟠 P1 | 未开始 |
| 4 | Smart Chunker 未集成到 Indexer | 🟡 P2 | 未开始 |
| 5 | BM25 索引没有缓存 | 🟡 P2 | 未开始 |
| 6 | Demo script 没写 | 🟡 P2 | 未开始 |
| 7 | Architecture diagram 没做 | 🟡 P2 | 未开始 |
| 8 | Ryde API 措辞改"simulated" | 🟢 容易 | 待执行 |
| 9 | teammate 的 `DESIGN.md` + frontend CSS 重写未 commit | 🟡 | 待决定 |

---

## 代码统计（更新版）

| 指标 | 数值 |
|------|------|
| Python 文件数 | 33 |
| 测试文件数 | 6 |
| 总代码行数 | ~8000+ |
| Git 提交数 | 23+ |
| Agents 实现 | 7/7（Arbitrator stub） |
| RAG 优化 | 5/5 |
| Mock disputes | 4 |
| 真实政策文档 | 12 |
| Frontend 页面 | 1 (index.html, RAG-only) |

---

## 参考资源

| 资源 | 链接 | 用途 |
|------|------|------|
| Gemini API | https://aistudio.google.com/app/apikey | API Key |
| Gemini Docs | https://ai.google.dev/gemini-api/docs | 文档 |
| ChromaDB | https://docs.trychroma.com | Vector DB |
| FastAPI | https://fastapi.tiangolo.com | Web 框架 |
| Ryde Policies | https://rydesharing.com/policies/ | 真实政策来源 |
| TRTC Agent Skills | https://github.com/Tencent-RTC/agent-skills | 腾讯云技能 |

---

## Session 接力说明（给下一个 session）

### 🚨 必须做的 P0
1. **实现 Arbitrator LLM 推理** — 把 `arbitrate()` 从 stub 变 real，当前 `confidence=0.0` 让系统跑不通
2. **Frontend dispute dashboard** — Dispute filing form + Live debate view + Verdict display

### 🟠 重要但不阻塞
3. Executor 加真实 notification 生成（即使 mock send）
4. Multilingual notification（EN/CN/MS/Tamil）
5. Demo script（`docs/demo_script.md`）

### 🟢 简单 / 文档类
6. 改 `ryde_api.py` 措辞为 "simulated integration contract"
7. 决定 teammate 的 `DESIGN.md` + frontend CSS 重写是否要保留
8. 改 `docs/05_NEXT_STEPS.md` 里过时的 agent 命名（rider_agent / driver_agent / judge_agent）

### 关键文件清单（交接用）
- `src/agents/arbitrator.py` — **stub，要做**
- `src/agents/executor.py` — 部分 stub
- `src/core/orchestrator.py` — 完整 pipeline 已串好
- `src/integrations/ryde_api.py` — 改措辞
- `frontend/index.html` — teammate 已改 RAG 部分，需加 dispute 端到端 UI
- `DESIGN.md` — teammate 新加，未 commit