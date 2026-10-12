# 法庭机制启发式改进方案

## 一、真实法庭审理流程 vs 当前系统

### 真实法庭流程（民事诉讼）

```
1. 立案 (Filing)
   → 法院接收诉状，确定管辖权，缴纳诉讼费

2. 案件分流 (Case Management)
   → 小额诉讼 → 简易程序（快速通道）
   → 复杂案件 → 普通程序
   → 紧急案件 → 临时禁令/保全

3. 送达与答辩 (Service & Answer)
   → 被告收到通知，有权提交答辩状
   → 可提出管辖权异议、反诉

4. 证据开示/发现程序 (Discovery)
   → 双方交换证据清单
   → 书面质询 (Interrogatories)
   → 文件请求 (Document Requests)
   → 口头取证 (Depositions)
   → **法官可强制要求出示证据**

5. 庭前会议 (Pretrial Conference)
   → 法官主持，明确争议焦点
   → 整理无争议事实 (Stipulations)
   → 排除无关证据 (Motions in Limine)
   → **缩小审理范围**

6. 即决判决/简易判决 (Summary Judgment)
   → 若一方证据明显不足，法官可直接判决
   → 无需完整庭审

7. 庭审 (Trial)
   → 开场陈述 (Opening Statements)
   → 原告举证 (Plaintiff's Case)
   → 被告举证 (Defendant's Case)
   → 交叉质证 (Cross-examination)
   → 总结陈词 (Closing Arguments)
   → **法官可主动提问、要求补充证据**

8. 裁决 (Judgment)
   → 法官/陪审团评议
   → 书面判决理由
   → 损害赔偿计算

9. 上诉 (Appeal)
   → 法律问题上诉
   → 不重新审理事实

10. 执行 (Enforcement)
    → 强制执行判决
```

### 当前 RydeResolve 流程

```
1. Collector    → 收集争议数据
2. Classifier   → 分类 + 紧急度
3. Case Brief   → 事实摘要 + 条款检索
4. Fraud        → 欺诈检测
5. Safety       → 安全审查
6. Debate       → 双方辩论（固定轮次）
7. Arbitrator   → Judge 裁决
8. Fairness     → 公平性审查
9. Executor     → 执行
```

---

## 二、法庭之长 → 我们要借鉴的

### 2.1 证据开示 (Discovery) — 当前最弱环节

**法庭机制**：
- 双方必须主动披露所有相关证据
- 法官可强制要求出示特定证据
- 隐瞒证据可导致制裁

**当前系统问题**：
- Evidence pool 是双方各自查找，不是强制披露
- 没有"证据清单"概念
- Judge 不会主动要求补充证据

**改进方案**：
```python
# 新增 Discovery Phase
class DiscoveryAgent:
    """强制证据开示阶段"""
    
    async def conduct_discovery(self, context):
        # 1. 根据争议类型，生成强制披露清单
        #    e.g., no_show → 必须披露: GPS到达记录、等待时间、聊天记录
        # 2. 检查哪些数据缺失
        # 3. 标记 "必须但缺失" → 影响举证责任分配
        
        required_evidence = self._get_required_evidence(dispute_type)
        disclosed = self._check_disclosed(context, required_evidence)
        missing = [e for e in required_evidence if not disclosed[e]]
        
        return {
            "disclosed": disclosed,      # 已披露的证据
            "missing": missing,          # 缺失的证据
            "burden_shift": self._compute_burden_shift(missing),  # 举证责任
        }
```

### 2.2 庭前会议 (Pretrial Conference) — 完全缺失

**法庭机制**：
- 法官主持，明确"真正的争议点"是什么
- 排除双方无争议的事实
- 缩小审理范围

**当前系统问题**：
- Debate 直接开始，没有"争议焦点整理"
- 双方在无关事实上浪费 token
- Judge 需要从头理解争议

**改进方案**：
```python
# 新增 Pretrial Agent
class PretrialAgent:
    """庭前会议：整理争议焦点"""
    
    async def identify_issues(self, context, passenger_analysis, driver_analysis):
        # 1. 找出双方同意的点 (Stipulations)
        # 2. 找出双方真正争议的点 (Contested Issues)
        # 3. 排除与裁决无关的论点
        # 4. 输出 "Issues for Trial"
        
        return {
            "stipulations": [...],      # 双方同意的事实
            "contested_issues": [...],  # I1, I2, I3... 真正的争议点
            "irrelevant": [...],        # 可以忽略的论点
        }
```

### 2.3 即决判决 (Summary Judgment) — 完全缺失

**法庭机制**：
- 如果一方没有任何可争议的事实/法律依据，法官可直接判决
- 节省完整庭审的资源

**当前系统问题**：
- 所有 case 都走完整 debate → Judge 流程
- 简单 case（如 clear no-show）浪费 LLM 调用

**改进方案**：
```python
# 在 Classifier 后增加 Summary Judgment 检查
async def check_summary_judgment(context, classification):
    # Simple cases: clear evidence + clear policy → no debate needed
    # e.g., GPS shows driver never arrived + waiting time < threshold
    
    if classification.complexity == "SIMPLE" and classification.confidence > 0.95:
        # 直接裁决，跳过 debate
        return SummaryJudgment(verdict=..., refund=...)
    
    # 否则进入正常 debate
    return None
```

### 2.4 法官主动调查权 (Inquisitorial Power) — 当前缺失

**法庭机制**（大陆法系尤其明显）：
- 法官不完全是被动听审，可以主动提问
- 可以要求补充证据
- 可以传唤证人

**当前系统问题**：
- Judge 只看现有材料，不会说"我需要看这个"
- 没有法官-证人的直接互动

**改进方案**：
```python
# Judge 增加主动调查能力
class ArbitrationAgent:
    async def arbitrate(self, ...):
        # 第一轮：基于现有证据初步判断
        preliminary = await self._preliminary_assessment(...)
        
        # 如果证据不足，发出调查令
        if preliminary.gaps:
            investigation_orders = self._issue_investigation_orders(preliminary.gaps)
            # 执行调查（查更多数据、请求补充材料）
            new_evidence = await self._execute_orders(investigation_orders)
            # 重新裁决
            return await self._final_ruling(..., new_evidence)
```

### 2.5 调解优先 (Mediation First) — 完全缺失

**法庭机制**：
- 很多司法管辖区要求先调解
- 调解成功 → 和解协议，无需判决
- 调解失败 → 才进入庭审

**适用场景**：
- 金额小、双方各退一步可解决的 case
- 清洁费争议（司机要 $200，乘客愿出 $100）

**改进方案**：
```python
# 新增 Mediation Agent
class MediationAgent:
    """尝试促成双方和解"""
    
    async def mediate(self, context):
        # 1. 分析双方底线
        # 2. 提出中间方案
        # 3. 若双方都接受 → 和解
        # 4. 否则 → 返回 debate
        
        settlement = self._propose_settlement(passenger_ask, driver_ask)
        if self._both_accept(passenger_ask, driver_ask, settlement):
            return Settlement(terms=settlement)
        return None
```

### 2.6 举证责任 (Burden of Proof) — 当前模糊

**法庭机制**：
- 谁主张谁举证
- 举证不能 → 承担败诉风险
- 证据优势标准 (Preponderance of Evidence)

**当前系统问题**：
- Judge 没有明确的"举证责任"概念
- 当证据缺失时，不知道应该偏向哪一方

**改进方案**：
在 Judge system prompt 中明确：
```markdown
Burden of Proof Rules:
- The party who filed the dispute bears the burden of proving their claim.
- If a key fact is disputed and the filer cannot prove it with records, the claim fails on that point.
- The respondent (driver) must prove affirmative defenses with records.
- When evidence is equally balanced, the burden carrier loses.
```

---

## 三、法庭之短 → 我们要避免的

### 3.1 极度缓慢
- **法庭**：数月到数年
- **我们**：目标 < 2 分钟
- **策略**：自动化所有程序性步骤，并行执行

### 3.2 高昂费用
- **法庭**：律师费、法庭费、专家证人费
- **我们**：LLM API 费用
- **策略**：简单 case 跳过 debate（Summary Judgment）

### 3.3 形式化冗余
- **法庭**：大量程序性文件、重复陈述
- **我们**：结构化 JSON 输出，无冗余
- **策略**：保持现有简洁风格

### 3.4 人为偏见
- **法庭**：法官/陪审团的个人偏见
- **我们**：LLM 的 training bias
- **策略**：多模型交叉验证、结构化决策框架

### 3.5 程序滥用
- **法庭**：拖延战术、证据突袭
- **我们**：LLM 可能虚构证据
- **策略**：严格证据验证、虚假证据检测

---

## 四、完整改进后流程

```
START
  → Collector (收集)
  → Classifier (分类 + 复杂度评估)
    ├── complexity=SIMPLE + confidence>0.95
    │     → Summary Judgment (直接裁决) → Executor → END
    ├── 双方可能和解
    │     → Mediation (调解)
    │         ├── 和解成功 → Executor → END
    │         └── 调解失败 → 继续
    └── 正常流程
          → Case Brief (事实摘要)
          → Discovery (强制证据开示)
              ├── 关键证据缺失
              │     → Investigation Orders (调查令)
              │     → 补充证据
              └── 证据完整
          → Fraud + Safety (风险审查)
          → Pretrial (庭前会议)
              ├── 整理争议焦点 (Issues I1, I2...)
              ├── 排除无关论点
              └── 标记无争议事实
          → Debate (辩论，动态轮次)
              ├── 每轮后检查：是否有 NEW_POINT
              ├── 无新论点 → 提前结束
              └── 有新论点 → 继续 (最多 N 轮)
          → Arbitrator (裁决)
              ├── 第一轮：初步判断
              ├── 证据不足 → 主动调查
              └── 最终裁决
          → Fairness (公平性审查)
          → Executor (执行) → END
```

---

## 五、优先级与实现计划

### P0 (立即做，1-2天)
1. **Summary Judgment**：简单 case 跳过 debate（节省 40% token）
2. **举证责任规则**：加入 Judge prompt（提高 no_show 准确率）
3. **Discovery 强制清单**：标记缺失证据（减少误判）

### P1 (本周做，2-3天)
4. **Pretrial 争议焦点**：减少 debate 噪音
5. **动态辩论终止**：NEW_POINT=no 时提前结束

### P2 (下周做)
6. **Judge 主动调查**：证据 gap 时自动补查
7. **调解 Agent**：小额 case 优先调解

### P3 (可选)
8. **证据权重评估**：给不同来源的证据打可信度分
9. **交叉引用验证**：多个证据指向同一事实时增强可信度

---

## 六、预期收益

| 改进项 | 准确率提升 | 成本降低 | 延迟降低 |
|--------|-----------|---------|---------|
| Summary Judgment | +2% | -40% token | -30% |
| 举证责任规则 | +5% (no_show) | 0 | 0 |
| Discovery 清单 | +3% | -5% | 0 |
| Pretrial 焦点 | +2% | -15% token | -10% |
| 动态终止 | +1% | -20% token | -20% |
| **合计** | **+10-13%** | **-50% token** | **-40%** |

当前 sealed set 57% → 目标 70%+ (仍有 LLM 波动，但系统性提升)
