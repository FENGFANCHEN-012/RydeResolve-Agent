# 下一步工作清单

## 高优先级（必须完成）

### 1. 多 Agent 辩论机制
- **文件**: `src/core/orchestrator.py`, `src/agents/`
- **描述**: 实现 Rider Agent、Driver Agent、Judge Agent 的辩论流程
- **关键逻辑**:
  1. Orchestrator 接收争议报告
  2. 分析争议类型（分类器）
  3. 并行调用 Rider Agent 和 Driver Agent 收集观点
  4. Judge Agent 综合双方观点 + RAG 政策检索
  5. 输出裁决 + 推理链
- **参考**: AutoGen 多 Agent 架构

### 2. 多语言支持
- **文件**: `src/core/translator.py`, `frontend/index.html`
- **描述**: 支持英语、中文、马来语、泰米尔语
- **实现方式**:
  - 检测用户输入语言
  - 用 Gemini 翻译为非英语查询
  - 检索后翻译回答
- **测试**: 用四种语言分别测试问答

### 3. 争议分类器
- **文件**: `src/core/classifier.py`
- **描述**: 自动分类争议类型（路线偏离、未出现收费等）
- **输入**: 用户争议描述
- **输出**: 争议类型 + 置信度
- **实现**: 用 Gemini 做 zero-shot 分类

---

## 中优先级（强烈建议）

### 4. 集成 Smart Chunker
- **文件**: `src/rag/indexer.py`
- **描述**: 将语义边界切分集成到索引流程
- **当前**: 使用固定 500 词切分
- **目标**: 使用段落/句子边界切分
- **影响**: 需要重新索引所有文档

### 5. BM25 索引缓存
- **文件**: `src/rag/hybrid_search.py`
- **描述**: 缓存 BM25 索引，只在文档变更时重建
- **当前**: 每次搜索都重建索引
- **优化**: 添加 `invalidate_index()` 调用点

### 6. 单元测试
- **文件**: `tests/`
- **描述**: 为核心模块写 pytest 测试
- **优先级**:
  1. `test_document_parser.py`
  2. `test_embedding.py`
  3. `test_retriever.py`
  4. `test_qa_engine.py`
  5. `test_confidence_scorer.py`

### 7. 错误处理增强
- **文件**: 所有 API 端点
- **描述**: 添加更完善的错误处理和用户提示
- **当前问题**:
  - 文件上传超时没有友好提示
  - LLM API 失败时没有降级策略
  - ChromaDB 连接失败时崩溃

---

## 低优先级（有时间再做）

### 8. 演示视频制作
- **时长**: 3-5 分钟
- **内容**:
  1. 项目介绍（30s）
  2. 架构展示（1min）
  3. 功能演示（2min）
  4. 技术亮点（1min）
- **工具**: OBS / Screen Recorder

### 9. PPT 制作
- **页数**: 10-15 页
- **内容**:
  1. 封面
  2. 问题背景
  3. 解决方案概述
  4. 架构图
  5. 技术细节
  6. 演示截图
  7. 创新点
  8. 商业价值
  9. 未来规划
  10. 感谢

### 10. 在线 Demo 部署
- **方案**: Cloud Studio / Vercel + Render
- **步骤**:
  1. Docker 化应用
  2. 部署到云平台
  3. 配置域名
  4. 测试访问

### 11. 性能优化
- **文件**: `src/rag/`
- **描述**: 优化检索速度
- **措施**:
  - 异步并行检索
  - 缓存热门查询
  - 减少 LLM 调用次数

### 12. 日志和监控
- **文件**: `src/core/logger.py`
- **描述**: 添加结构化日志
- **内容**:
  - 请求/响应日志
  - 错误日志
  - 性能指标（延迟、吞吐量）

---

## 文件结构规划

```
RydeResolve-Agent/
├── src/
│   ├── api/
│   │   └── main.py              # FastAPI 入口
│   ├── config.py                # 配置
│   ├── core/
│   │   ├── llm_client.py        # LLM 客户端
│   │   ├── orchestrator.py      # 多 Agent 协调器 [TODO]
│   │   ├── classifier.py        # 争议分类器 [TODO]
│   │   └── logger.py            # 日志 [TODO]
│   ├── agents/
│   │   ├── rider_agent.py       # 乘客 Agent [TODO]
│   │   ├── driver_agent.py      # 司机 Agent [TODO]
│   │   └── judge_agent.py       # 法官 Agent [TODO]
│   └── rag/
│       ├── document_parser.py   # 文档解析
│       ├── embedding.py         # Embedding
│       ├── indexer.py           # 索引 [需要集成 Smart Chunker]
│       ├── retriever.py         # 基础检索
│       ├── advanced_retriever.py # 高级检索
│       ├── qa_engine.py         # 基础问答
│       ├── advanced_qa_engine.py # 高级问答
│       ├── query_rewriter.py    # 查询重写
│       ├── hybrid_search.py     # 混合检索 [需要缓存优化]
│       ├── reranker.py          # 重排序
│       ├── smart_chunker.py     # 智能切分 [需要集成]
│       └── confidence_scorer.py # 置信度评分
├── frontend/
│   └── index.html               # 前端
├── tests/                       # 单元测试 [TODO]
├── docs/                        # 交接文档
│   ├── 01_PROJECT_REQUIREMENTS.md
│   ├── 02_TECH_RESEARCH.md
│   ├── 03_DEVELOPMENT_LOG.md
│   ├── 04_SCORING_GUIDE.md
│   └── 05_NEXT_STEPS.md
├── data/
│   ├── policies/                # 政策文档
│   └── uploads/                 # 上传文件
├── chroma_data/                 # 向量数据库
├── .env                         # 环境变量
├── .env.example                 # 环境变量模板
├── README.md                    # 项目说明 [需要完善]
├── SESSION_SUMMARY.md           # Session 总结
└── requirements.txt             # 依赖 [需要整理]
```

---

## 关键联系人 & 资源

| 资源 | 链接/位置 |
|------|----------|
| GitHub 仓库 | https://github.com/FENGFANCHEN-012/RydeResolve-Agent |
| Gemini API Key | https://aistudio.google.com/app/apikey |
| Gemini 文档 | https://ai.google.dev/gemini-api/docs |
| 比赛官网 | [待补充] |
| 腾讯云控制台 | https://console.tencentcloud.com |
| TRTC Agent Skills | https://github.com/Tencent-RTC/agent-skills |

---

## 风险 & 应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Gemini API 限额用完 | 高 | 准备备用 API Key，或切换到 OpenAI |
| 多 Agent 实现复杂 | 高 | 先实现简化版（2 个 Agent + Judge） |
| 演示视频时间不够 | 中 | 提前准备脚本，分段录制 |
| 部署环境不稳定 | 中 | 准备本地演示作为备份 |
| 多语言翻译质量差 | 低 | 用 Gemini 翻译，质量通常够用 |

---

## 每日检查清单

### 开发日
- [ ] 代码提交到 Git
- [ ] 测试通过
- [ ] 文档更新
- [ ] 无敏感信息泄露

### 比赛前
- [ ] 所有功能测试通过
- [ ] 演示视频完成
- [ ] PPT 完成
- [ ] 在线 Demo 可访问
- [ ] README 完整
- [ ] 依赖清单完整
