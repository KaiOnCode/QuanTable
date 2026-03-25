# Agentic-Quant Detailed Proposal —— 内容组织方案

> 背景：我们需要在 2026.3.27 提交一份 COMP7705 的 Detailed Project Proposal。HKU 对格式并无官方约束，但参照往届学长的模板（Detection and Localization of Spoofing and Jamming Signals），我们需要一份结构合理、内容充实的英文提案。

---

## 往届 Example 结构分析

往届学长的 Detail-Proposal-Example（共 9 页）采用如下结构：

| 章节 | 内容 |
|------|------|
| **封面页** | 项目标题、导师、组员信息（含学号、邮箱） |
| **Abstract** | ~150 字概要 + Keywords |
| **1. Introduction** | 1.1 Background（技术背景）+ 1.2 Research Objectives |
| **2. Literature Review** | 按子主题分节（2.1 Mitigation for Spoofing, 2.2 Detecting Jamming） |
| **3. Proposed Methodology** | 3.1 Data Source + 3.2 Tools + 3.3 Data Processing（含多个子节） |
| **4. Milestones** | 表格：任务、预计完成时间、预计学时 |
| **Deliverables** | 列表形式 |
| **References** | IEEE 格式，11 条参考文献 |

**关键差异**：学长的项目是从零开始的 ML 模型训练任务；而 Agentic-Quant 已有大量可运行代码（28 个 Python 文件、完整 LangGraph pipeline、Streamlit UI），未来的工作重心在于功能增强和系统集成。

---

## Typst + IEEE 引用方案

Typst 原生支持 BibTeX (`.bib`) 文件和 IEEE 引用风格。操作流程：

1. 准备标准 `.bib` 文件（与 LaTeX 格式完全相同）
2. 在文档正文中用 `@label` 引用文献
3. 在文档末尾放置 `#bibliography("refs.bib", style: "ieee")`

Typst 会自动生成 [1], [2], [3] 形式的数字引用，并在 References 部分按引用顺序排列。

---

## 方案 A：面向工程实现的结构（推荐）

> **设计理念**：突出"已实现 → 待完成"的渐进关系，向评审展示项目的成熟度和清晰路线。

### 目录结构

```
Cover Page（项目标题、导师、组员信息）
Abstract + Keywords

1. Introduction
   1.1 Background and Motivation
   1.2 Problem Statement
   1.3 Research Objectives

2. Literature Review
   2.1 Multi-Agent Systems for Financial Analysis
   2.2 LLM-Driven Quantitative Trading
   2.3 Agent Orchestration and Decision Visualization
   2.4 Human-in-the-Loop and Autonomous Trading

3. System Design and Current Implementation
   3.1 Overall Architecture（LangGraph workflow diagram）
   3.2 Agent Design（5 agents: roles, prompts, tools）
   3.3 Data Pipeline（YFinance, Google News, AkShare）
   3.4 Web Interface（Streamlit dashboard）

4. Proposed Enhancements
   4.1 Context Management and Persistent Memory（SQLite）
   4.2 Human-in-the-Loop Approval Mechanism
   4.3 Broker Mock Engine and Backtesting Loop
   4.4 Multi-Channel Notification（WhatsApp/Telegram）
   4.5 Decision-Flow Visualization

5. Technical Stack

6. Milestones and Timeline

7. Deliverables

References（IEEE, via .bib）
```

### 优点

- **进展可视**：第 3 节清晰展示项目已有实质性进展（可运行代码、完整 pipeline），增加评审信心
- **路线清晰**：第 4 节与 `curr-desc-and-future-roadmap.pdf` 严格对齐，体现规划的系统性
- **平衡感**：Literature Review 保持足够深度（4 个子节），但不喧宾夺主
- **工程导向**：符合 Graduation Project 偏工程的性质

### 缺点

- **篇幅较长**：预计 12-15 页
- **学术性偏弱**：系统设计章节如果细节过多会偏向技术文档风格
- **Research Gap 不够突出**：对学术创新点的阐述可能不够系统化

---

## 方案 B：面向学术研究的结构

> **设计理念**：将 Literature Review 做厚，突出 Research Gap 和本项目的创新定位。

### 目录结构

```
Cover Page
Abstract + Keywords

1. Introduction
   1.1 Background
   1.2 Challenges in LLM-based Quantitative Systems
   1.3 Contributions of This Work

2. Related Work
   2.1 Multi-Agent Systems in Finance
   2.2 LLM Reasoning for Financial Decision-Making
   2.3 Explainable AI and Decision Visualization
   2.4 Human-AI Collaboration in Trading
   2.5 Summary and Research Gaps

3. Proposed Framework: Agentic-Quant
   3.1 Design Principles
   3.2 Multi-Agent Architecture
   3.3 LangGraph Workflow Orchestration
   3.4 Decision-Flow Visualization Pipeline
   3.5 Human-in-the-Loop Integration

4. Implementation Plan
   4.1 Technology Stack
   4.2 Development Roadmap
   4.3 Evaluation Methodology

5. Milestones and Deliverables

References
```

### 优点

- **学术气息浓厚**：如果导师 Prof. Wu Chuan 更看重研究深度，这是最佳选择
- **逻辑链强**：2.5 Research Gaps → 3. Proposed Framework 的因果关系非常自然
- **文献利用充分**：可以充分利用已调研的 21 篇文献
- **有利于后续论文写作**：如果未来需要发表论文，此结构可直接复用

### 缺点

- **实现细节弱**：对"已实现功能"的呈现不够突出
- **过于理论化**：可能不能充分展示实际工程能力
- **与项目当前状态脱节**：项目是软件工程项目而非纯研究项目，过于学术化可能不合适

---

## 方案 C：精简务实的结构

> **设计理念**：追求简洁高效，控制在 8-10 页，适合格式宽松的要求。

### 目录结构

```
Cover Page
Abstract + Keywords

1. Introduction and Motivation

2. Literature Review
   2.1 LLM-based Multi-Agent Financial Systems
   2.2 Decision Explainability and Human Oversight

3. System Overview
   3.1 Architecture
   3.2 Current Status

4. Proposed Work
   4.1 Enhanced Context and Memory
   4.2 HITL and Broker Simulation
   4.3 Visualization and Notification

5. Timeline and Deliverables

References
```

### 优点

- **最精简**：写作效率最高，适合时间紧迫的情况
- **阅读负担小**：评审可以快速抓住要点
- **灵活性强**：适合"格式宽松"的要求

### 缺点

- **Literature Review 压缩过大**：仅 2 个子节，可能显得调研不够深入
- **缺乏细节**：技术深度不足，评审可能质疑项目可行性
- **区分度低**：与其他组的 proposal 相比可能显得过于简单

---

## 综合建议

**推荐方案 A（面向工程实现的结构）**，理由如下：

1. **项目已有实质代码**（28 个 Python 文件、完整的 LangGraph pipeline、Streamlit UI），这是区别于 Example 的最大优势，应该充分展示
2. **与路线图高度对齐**：`curr-desc-and-future-roadmap.pdf` 中已详细规划了 4 大升级方向（上下文管理、HITL、券商模拟、渠道通知），方案 A 与之无缝衔接
3. **Literature Review 深度适中**：4 个子节覆盖核心领域，从 21 篇文献中选取 15-18 篇最相关的纳入
4. **工程+学术平衡**：既体现技术能力，又有学术支撑

**备选方案**：如果导师 Prof. Wu Chuan 明确倾向学术性，可考虑方案 B；如果时间极其紧迫，可退而求其次选方案 C。
