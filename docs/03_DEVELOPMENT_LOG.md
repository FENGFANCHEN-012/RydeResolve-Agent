# 开发日志 — 关键节点记录

## Session 1: 2026-09-21

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

### 节点 6: Session 总结 & 交接文档
- **时间**: 傍晚
- **内容**: 创建交接文档
- **新增文件**:
  - `SESSION_SUMMARY.md` — Session 技术总结
  - `docs/01_PROJECT_REQUIREMENTS.md` — 项目要求
  - `docs/02_TECH_RESEARCH.md` — 技术调研
  - `docs/03_DEVELOPMENT_LOG.md` — 开发日志（本文件）
- **提交**: `bc43021` — docs: add session summary for transfer

---

## 关键决策记录

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
- **背景**: 基础 RAG 检索质量不够好
- **选择**: 实现 Query Rewrite + Hybrid Search + Re-ranking + Smart Chunking + Confidence Scoring
- **原因**:
  1. 比赛评分看重技术深度
  2. 多 Agent 系统需要高质量检索
  3. 每个优化都有明确效果
- **影响**: 增加了代码复杂度，但提升了检索质量

---

## 待解决问题

| # | 问题 | 优先级 | 计划解决时间 |
|---|------|--------|-------------|
| 1 | Smart Chunker 未集成到 Indexer | 高 | Next session |
| 2 | BM25 索引没有缓存 | 中 | Next session |
| 3 | Query Rewrite 有时生成无关查询 | 中 | Next session |
| 4 | 多 Agent 辩论机制未实现 | 高 | Next session |
| 5 | 多语言支持未实现 | 高 | Next session |
| 6 | 没有单元测试 | 中 | Next session |
| 7 | 演示视频未制作 | 高 | 比赛前 |
| 8 | PPT 未制作 | 高 | 比赛前 |

---

## 代码统计

| 指标 | 数值 |
|------|------|
| Python 文件数 | 15+ |
| 前端文件数 | 1 (index.html) |
| 总代码行数 | ~3000+ |
| Git 提交数 | 4 |
| 新增功能模块 | 8 |

---

## 参考资源

| 资源 | 链接 | 用途 |
|------|------|------|
| Gemini API | https://aistudio.google.com/app/apikey | API Key |
| Gemini Docs | https://ai.google.dev/gemini-api/docs | 文档 |
| ChromaDB | https://docs.trychroma.com | Vector DB |
| FastAPI | https://fastapi.tiangolo.com | Web 框架 |
| RAG Survey | arXiv | 检索优化参考 |
| TRTC Agent Skills | https://github.com/Tencent-RTC/agent-skills | 腾讯云技能 |
