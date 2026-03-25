# Agentic-Quant Detailed Proposal — Content Organization Plans

> Context: We need to submit a Detailed Project Proposal for COMP7705 by 2026.3.27. HKU has no official formatting constraints, but referencing a previous cohort's template (Detection and Localization of Spoofing and Jamming Signals), we aim to produce a well-structured, substantive English proposal.

---

## Analysis of the Example Proposal

The previous cohort's Detail-Proposal-Example (9 pages) follows this structure:

| Section | Content |
|---------|---------|
| **Cover Page** | Project title, mentor, group members (with student IDs and emails) |
| **Abstract** | ~150-word summary + Keywords |
| **1. Introduction** | 1.1 Background + 1.2 Research Objectives |
| **2. Literature Review** | Organized by subtopics (2.1 Mitigation for Spoofing, 2.2 Detecting Jamming) |
| **3. Proposed Methodology** | 3.1 Data Source + 3.2 Tools + 3.3 Data Processing (multiple subsections) |
| **4. Milestones** | Table format: tasks, estimated completion dates, learning hours |
| **Deliverables** | Bullet list |
| **References** | IEEE format, 11 references |

**Key Difference**: The example project starts from scratch with ML model training. Agentic-Quant, by contrast, already has substantial working code (28 Python files, a complete LangGraph pipeline, Streamlit UI). Our future work centers on feature enhancement and system integration.

---

## Typst + IEEE Citation Approach

Typst natively supports BibTeX (`.bib`) files and the IEEE citation style. The workflow:

1. Prepare a standard `.bib` file (identical format to LaTeX)
2. Cite in document body with `@label` syntax
3. Place `#bibliography("refs.bib", style: "ieee")` at the end

Typst automatically generates numeric citations [1], [2], [3] and arranges the References section in citation order.

---

## Plan A: Engineering-Oriented Structure (Recommended)

> **Design Philosophy**: Emphasize the "implemented → planned" progression to demonstrate project maturity and a clear roadmap.

### Table of Contents

```
Cover Page (Project title, mentor, group members)
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
   3.1 Overall Architecture (LangGraph workflow diagram)
   3.2 Agent Design (5 agents: roles, prompts, tools)
   3.3 Data Pipeline (YFinance, Google News, AkShare)
   3.4 Web Interface (Streamlit dashboard)

4. Proposed Enhancements
   4.1 Context Management and Persistent Memory (SQLite)
   4.2 Human-in-the-Loop Approval Mechanism
   4.3 Broker Mock Engine and Backtesting Loop
   4.4 Multi-Channel Notification (WhatsApp/Telegram)
   4.5 Decision-Flow Visualization

5. Technical Stack

6. Milestones and Timeline

7. Deliverables

References (IEEE, via .bib)
```

### Pros

- **Visible Progress**: Section 3 clearly showcases existing working code and a complete pipeline, boosting reviewer confidence
- **Clear Roadmap**: Section 4 aligns directly with the `curr-desc-and-future-roadmap.pdf` plan, demonstrating systematic planning
- **Balanced**: Literature Review maintains sufficient depth (4 subsections) without overshadowing the engineering narrative
- **Engineering-Oriented**: Fits the nature of a Graduation Project, which leans toward engineering

### Cons

- **Longer**: Expected 12-15 pages
- **Less Academic**: The system design section may read more like technical documentation if overdetailed
- **Research Gap Not Prominent**: The articulation of academic innovation may be less systematic

---

## Plan B: Research-Oriented Structure

> **Design Philosophy**: Expand the Literature Review to highlight Research Gaps and position the project as an academic contribution.

### Table of Contents

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

### Pros

- **Strong Academic Tone**: Best choice if Prof. Wu Chuan prioritizes research depth
- **Strong Logical Chain**: 2.5 Research Gaps → 3. Proposed Framework creates a natural causal flow
- **Full Utilization of Literature**: Can leverage all 21 surveyed papers thoroughly
- **Reusable for Publication**: If a paper submission is planned later, this structure translates directly

### Cons

- **Weak on Implementation Details**: Existing features are not prominently showcased
- **Overly Theoretical**: May not sufficiently demonstrate hands-on engineering capabilities
- **Misaligned with Project Nature**: The project is fundamentally a software engineering effort, not a pure research endeavor

---

## Plan C: Lean and Pragmatic Structure

> **Design Philosophy**: Maximize conciseness and efficiency, targeting 8-10 pages for a format-lenient requirement.

### Table of Contents

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

### Pros

- **Most Concise**: Highest writing efficiency, ideal for tight deadlines
- **Low Reading Burden**: Reviewers can quickly grasp the key points
- **Flexible**: Well-suited for a lenient formatting environment

### Cons

- **Compressed Literature Review**: Only 2 subsections may appear insufficiently thorough
- **Lacks Depth**: Technical detail may be insufficient for reviewers to assess feasibility
- **Low Differentiation**: May appear simplistic compared to other teams' proposals

---

## Overall Recommendation

**Recommended: Plan A (Engineering-Oriented Structure)** for the following reasons:

1. **Existing Codebase**: With 28 Python files, a complete LangGraph pipeline, and a Streamlit UI already in place, this is our strongest differentiator from the example — and it should be prominently displayed
2. **Roadmap Alignment**: The four major upgrade directions from `curr-desc-and-future-roadmap.pdf` (context management, HITL, broker simulation, channel notification) map seamlessly to Plan A's Section 4
3. **Adequate Literature Depth**: 4 subsections covering core areas, drawing from 15-18 of the 21 surveyed papers
4. **Engineering-Academic Balance**: Demonstrates both technical capability and scholarly grounding

**Alternative**: If Prof. Wu Chuan explicitly prefers academic rigor, consider Plan B. If time is extremely tight, fall back to Plan C.
