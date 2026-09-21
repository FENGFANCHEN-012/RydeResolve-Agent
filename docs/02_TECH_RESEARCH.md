# 技术调研 — 所有关键决策记录

## 调研时间线

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-09-21 | 选择 Google Gemini | 腾讯混元 API Key 获取困难，Gemini 免费额度充足 |
| 2026-09-21 | 选择 ChromaDB 本地模式 | 无需 Docker，部署简单 |
| 2026-09-21 | 选择 FastAPI | 异步支持好，自动 Swagger 文档 |
| 2026-09-21 | 选择 Vanilla JS 前端 | 无需构建工具，直接打开 HTML 即可 |

---

## 1. LLM 选型调研

### 候选方案

| 方案 | 费用 | 速度 | 质量 | 可用性 | 结论 |
|------|------|------|------|--------|------|
| **Google Gemini** | 免费额度 | 快 | 好 | ✅ 可用 | **选中** |
| Tencent Hunyuan | 免费额度 | 中等 | 好 | ❌ API Key 难获取 | 放弃 |
| OpenAI GPT-4o | $5/月 | 快 | 很好 | ✅ 可用 | 备选 |
| DeepSeek | 便宜 | 快 | 好 | ✅ 可用 | 备选 |
| Ollama 本地 | 免费 | 慢 | 一般 | ✅ 可用 | 备选 |

### Gemini 关键信息
- **API Key**: https://aistudio.google.com/app/apikey
- **免费额度**:  generous daily limits
- **模型**: `gemini-3.6-flash`（对话）, `gemini-embedding-2`（向量）
- **端点**: Google AI Studio（全球可用）
- **SDK**: `google-generativeai`

### 腾讯混元问题
- 国内站和国际站账号不互通
- 混元 OpenAI 兼容接口已下线
- 迁移到 TokenHub 需要重新申请
- 国际站控制台地址不同

---

## 2. Embedding 选型调研

| 方案 | 维度 | 费用 | 质量 | 结论 |
|------|------|------|------|------|
| **Gemini embedding-2** | 3072 | 免费 | 很好 | **选中** |
| Gemini embedding-001 | 768 | 免费 | 好 | 备选 |
| OpenAI text-embedding-3 | 1536 | 便宜 | 很好 | 备选 |
| 本地模型 |  varies | 免费 | 一般 | 备选 |

### 关键发现
- Gemini embedding-2 维度 3072，语义质量好
- ChromaDB collection 必须和 embedding 维度一致（之前 1024 -> 3072 导致报错）
- 切换 embedding 模型时必须删除旧 collection 重建

---

## 3. Vector Database 选型

| 方案 | 部署难度 | 性能 | 功能 | 结论 |
|------|---------|------|------|------|
| **ChromaDB 本地** | 极低 | 中等 | 够用 | **选中** |
| ChromaDB Docker | 低 | 好 | 够用 | 备选 |
| Pinecone | 低 | 很好 | 丰富 | 需要账号 |
| Weaviate | 中等 | 很好 | 丰富 | 需要 Docker |
| Milvus | 高 | 很好 | 丰富 | 太重 |

### ChromaDB 使用方式
```python
# 本地持久化
client = chromadb.PersistentClient(path="./chroma_data")

# HTTP 模式（需要 Docker）
client = chromadb.HttpClient(host="localhost", port=8200)
```

---

## 4. RAG 检索优化调研

### 调研的 5 个技术

| # | 技术 | 实现复杂度 | 效果 | 是否实现 |
|---|------|-----------|------|---------|
| 1 | Query Rewriting | 低 | 提升召回 | ✅ |
| 2 | Hybrid Search (Vector + BM25) | 中 | 提升召回 | ✅ |
| 3 | Re-ranking | 中 | 提升精度 | ✅ |
| 4 | Smart Chunking | 中 | 提升质量 | 部分实现 |
| 5 | Confidence Scoring | 低 | 提升可靠性 | ✅ |

### 参考来源
- LangChain RAG 最佳实践
- LlamaIndex 检索优化指南
- RAG Flow 论文

---

## 5. 前端技术调研

| 方案 | 复杂度 | 效果 | 结论 |
|------|--------|------|------|
| **Vanilla JS + CSS** | 极低 | 够用 | **选中** |
| React + Vite | 中 | 好 | 不需要构建步骤 |
| Vue 3 | 中 | 好 | 同上 |
| Streamlit | 低 | 一般 | 不够灵活 |

### 选择原因
- 比赛时间有限，不需要构建工具
- 直接打开 HTML 文件即可使用
- 单页应用足够展示功能

---

## 6. 部署方案调研

| 方案 | 难度 | 稳定性 | 结论 |
|------|------|--------|------|
| **本地演示** | 无 | 高 | **当前** |
| Cloud Studio | 低 | 中 | 推荐 |
| Vercel + 后端 | 中 | 高 | 需要分离部署 |
| Docker Compose | 低 | 高 | 推荐 |

### Cloud Studio 部署
- 腾讯云国际站: https://console.tencentcloud.com/cloudstudio
- 支持直接部署 GitHub 仓库
- 有免费额度

---

## 7. 多 Agent 架构调研

### 参考架构

| 架构 | 来源 | 特点 |
|------|------|------|
| **Multi-Agent Debate** | AutoGen | 多个 Agent 辩论达成共识 |
| **Judge-Executor** | MetaGPT | 法官 + 执行者分离 |
| **Role-Play** | CAMEL | 角色扮演模拟 |

### 我们的设计
- **Rider Agent**: 代表乘客利益
- **Driver Agent**: 代表司机利益
- **Judge Agent**: 中立裁决
- **Orchestrator**: 协调调度

### 关键决策
- 使用 **辩论机制** 而非单 Agent 决策（创新点）
- 使用 **RAG Tool** 让 Agent 查询政策（不是硬编码规则）
- 使用 **置信度评分** 决定是否转人工

---

## 8. 文档解析调研

| 格式 | 库 | 状态 |
|------|-----|------|
| PDF | PyPDF2 | ✅ 可用 |
| DOCX | python-docx | ✅ 可用 |
| TXT | 内置 | ✅ 可用 |
| MD | 内置 | ✅ 可用 |
| HTML | BeautifulSoup | ✅ 可用 |
| XLSX | openpyxl | 未测试 |
| PPTX | python-pptx | 未测试 |

---

## 9. 关键错误 & 解决方案

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| ChromaDB dimension mismatch | 旧 collection 是 1024 维，新 embedding 是 3072 维 | 删除旧 collection 重建 |
| Gemini 模型名错误 | `gemini-1.5-flash` 不存在 | 使用 `gemini-3.6-flash` |
| 腾讯混元 401 | SecretKey 不能作为 API Key | 需要混元专用 API Key |
| 腾讯混元 2000 | 模型已下线 | 迁移到 TokenHub |
| Query rewrite JSON 解析失败 | Gemini 返回不完整 JSON | 改用编号列表格式 |
| 文件上传失败 | 前端 multipart 格式问题 | 修复 boundary 和 Content-Type |

---

## 10. API 端点清单

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/rag/upload` | POST | 单文件上传 |
| `/api/rag/upload-multiple` | POST | 批量上传 |
| `/api/rag/search` | GET | 检索（支持 advanced=true） |
| `/api/rag/ask` | POST | 问答（支持 advanced=true） |
| `/api/rag/stats` | GET | 知识库统计 |
| `/api/rag/collections` | GET | 列出 collections |
| `/api/rag/collection` | DELETE | 删除 collection |
| `/api/disputes/resolve` | POST | 争议解决 |
