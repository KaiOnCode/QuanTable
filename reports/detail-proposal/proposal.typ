// ── Page & typography ──
#set page(paper: "a4", margin: (x: 2.5cm, y: 2.5cm))
#set text(size: 11pt)
#set par(justify: true, leading: 0.65em)
#set heading(numbering: "1.")
#show heading.where(level: 1): it => {
  v(0.6em)
  text(size: 14pt, weight: "bold", it)
  v(0.3em)
}
#show heading.where(level: 2): it => {
  v(0.4em)
  text(size: 12pt, weight: "bold", it)
  v(0.2em)
}

// ── Cover page ──
#page(numbering: none)[
  #align(center)[
    #v(1.5cm)
    #text(size: 12pt)[The University of Hong Kong]
    #v(0cm)
    #text(size: 12pt)[School of Computing and Data Science]
    #v(1.8cm)
    #text(size: 13pt, weight: "bold")[Detail Project Proposal for COMP7705]
    #v(1.8cm)
    #text(size: 20pt, weight: "bold")[
      Agentic-Quant: A Multi-Agent Framework \ for Reasoning-Based Quantitative Analysis
    ]
    #v(2.5cm)
    #text(size: 12pt)[*Mentor:* Prof. Wu, Chuan]
    #v(2cm)
    #text(size: 12pt, weight: "bold")[Group Members]
    #v(0.5cm)
    #table(
      columns: 3,
      align: center,
      stroke: 0.5pt,
      inset: 8pt,
      table.header([*Full Name*], [*Student ID*], [*Email*]),
      [Ying Tingkai], [3036657615], [tkying2025\@connect.hku.hk],
      [Wang Wenhan], [3036656398], [u3665639\@connect.hku.hk],
      [Cao Yujuncheng], [3036654819], [U3665481\@connect.hku.hk],
      [Wang Pengcheng], [3036656427], [u3665642\@connect.hku.hk],
      [Gao Ziteng], [3036654259], [U3665425\@connect.hku.hk],
    )
    #v(2cm)
    #text(size: 12pt)[March 2026]
  ]
]

// ── Start page numbering ──
#set page(numbering: "1")
#counter(page).update(1)

// ═══════════════════════════════════════════
//  Abstract (Revised Version)
// ═══════════════════════════════════════════
#heading(numbering: none)[Abstract]

Current large language model (LLM) frameworks for financial analysis often operate as stateless, single-turn systems, leading to a significant loss of historical context and a lack of verifiable execution loops. While existing multi-agent architectures provide role specialization, they frequently function as isolated advisory tools that fail to evaluate past performance or manage high-risk decisions requiring human oversight. This proposal introduces *Agentic-Quant*, a comprehensive multi-agent framework built on LangGraph designed to bridge the gap between autonomous reasoning and practical quantitative trading.

The system coordinates five specialized AI agents—market analyst, news analyst, fundamentals analyst, risk analyst, and portfolio manager—within a structured, graph-based pipeline. Beyond simple data retrieval from Yahoo Finance and Google News, Agentic-Quant implements a persistent context layer using SQLite to maintain a continuous "institutional memory" of agent reports and past decisions. To ensure safety and reliability, the framework incorporates a human-in-the-loop (HITL) approval mechanism that routes high-risk or conflicting signals to human reviewers via integrated WhatsApp and Telegram channels. Furthermore, a simulated broker engine is integrated to execute virtual trades and provide empirical feedback, transforming the system from a theoretical advisor into a closed-loop trading assistant. Combined with decision-flow visualization for end-to-end auditability, Agentic-Quant offers a scalable and interpretable solution for LLM-driven quantitative investment.

#v(0.5em)
*Keywords:* Multi-Agent System, LangGraph, LLM-driven Quantitative Analysis, Persistent Context, Human-in-the-Loop, Broker Simulation, Decision-Flow Visualization

// ═══════════════════════════════════════════
//  1  Introduction
// ═══════════════════════════════════════════
= Introduction

== Background and Motivation

Large language models have introduced new ways to analyze financial markets. Unlike rule-based or statistical models, LLMs can read earnings reports, news articles, and analyst commentary, then produce structured reasoning in natural language. Recent studies show that LLM-based systems can generate stock signals with measurable alpha over market benchmarks @fatouros_can_2025.

However, a thorough investment decision involves multiple distinct tasks: reading price charts, tracking news, reviewing company fundamentals, assessing risk, and making a final call. Asking a single model to handle all of these creates a bottleneck --- the model must switch between roles, hold excessive context, and cannot specialize. Multi-agent systems solve this by assigning each task to a dedicated agent @xiao_tradingagents:_2025 @yu_fincon:_2024. Role specialization and parallel execution lead to better results and more transparent reasoning.

Agentic-Quant adopts this approach using LangGraph, a graph-based workflow engine that supports parallel branching, conditional routing, and tool integration. The framework runs five agents in a structured pipeline and has produced working results. This proposal describes the current state and outlines five extensions toward a complete trading assistant.

== Problem Statement

Most LLM-based financial tools operate as stateless, single-turn systems: the user submits a query, the model responds, and all context is lost. This creates three practical limitations:

+ *No memory.* The system cannot track past recommendations or evaluate their outcomes.
+ *No oversight.* High-risk decisions --- such as large position changes when signals conflict --- proceed without human review.
+ *No execution loop.* The system remains advisory only, with no mechanism to validate decisions against actual market outcomes.

== Research Objectives

This project aims to address the limitations of stateless, advisory-only LLM financial tools by developing a comprehensive, multi-agent trading assistant. The research is structured around eight core objectives:

+ *Develop a multi-source data ingestion engine* that integrates disparate financial streams, including real-time market metrics from Yahoo Finance, global news sentiment from Google News, and historical point-in-time fundamental data.
+ *Architect a modular multi-agent orchestration framework* using LangGraph to distribute specialized analytical tasks—market, news, fundamentals, and risk analysis—across a collaborative team of autonomous LLM agents.
+ *Build an interactive web-based dashboard* to provide users with intuitive access to agent-driven insights, technical visualizations, and historical backtesting performance.
+ *Construct a persistent context layer* that retains agent reports, tool logs, and past decisions across sessions, enabling the system to maintain long-term "institutional memory" and multi-session reasoning.
+ *Implement a human-in-the-loop (HITL) gatekeeping mechanism* that identifies high-risk or conflicting decisions and routes them to human review for safety and policy refinement.
+ *Develop a high-fidelity broker simulation engine* that executes virtual trades based on agent decisions and feeds performance outcomes back into the system to close the execution-feedback loop.
+ *Integrate multi-channel notification systems* via Telegram and WhatsApp APIs to facilitate real-time market alerts and remote human-in-the-loop approval requests.
+ *Create an interactive decision-flow visualization module* that traces the entire reasoning chain—from raw data retrieval to final broker execution—to ensure system interpretability and auditability.

// ═══════════════════════════════════════════
//  2  Literature Review
// ═══════════════════════════════════════════
= Literature Review

== Multi-Agent Systems for Financial Analysis

Several recent systems apply multi-agent architectures to trading. TradingAgents @xiao_tradingagents:_2025 assigns roles --- fundamental analyst, sentiment analyst, technical analyst --- to separate LLM agents, with Bull and Bear researchers debating market conditions before a fund manager makes the final call. Experiments show improvements in cumulative return and Sharpe ratio over single-agent baselines.

FinCon @yu_fincon:_2024, presented at NeurIPS 2024, uses a manager-analyst hierarchy modeled on real investment firms. It introduces _conceptual verbal reinforcement_: agents update beliefs from past outcomes and propagate them to relevant peers. A risk-control component critiques decisions at the episode level. The system generalizes across single-stock trading and portfolio management.

TradingGroup @tian_tradinggroup:_2025 deploys five agents (news sentiment, financial report, forecasting, style preference, and trading decision) with a self-reflection loop that distills past successes and failures. Backtests on five stock datasets outperform rule-based, ML, RL, and other LLM-based methods. FinMem @yu_finmem:_2023 adds a layered memory module aligned with human cognitive structures, enabling agents to retain critical information beyond typical context windows.

These systems share a common design principle: decompose the analysis task by role, let each agent specialize, and aggregate results through a central decision-maker. Agentic-Quant follows the same pattern.

== LLM-Driven Quantitative Trading

MarketSenseAI @fatouros_can_2025 uses GPT-4 with chain-of-thought prompting to analyze trends, news, fundamentals, and macroeconomic factors. Testing on S\&P 100 stocks over 15 months yielded 10--30\% excess alpha and up to 72\% cumulative returns. The study shows that structured reasoning, not just raw prediction, is key to LLM effectiveness in finance.

BloombergGPT @wu_bloomberggpt:_2023 demonstrates the value of domain-specific training: a 50-billion-parameter model trained on 363 billion tokens of financial data outperforms general-purpose models on financial NLP tasks. FinGPT @yang_fingpt:_2025 takes the opposite approach --- open-source and lightweight, using low-rank adaptation to specialize general models at low cost. Both directions inform the model selection strategy for Agentic-Quant's agents.

A survey covering over fifty studies @fu_new_2025 identifies key challenges for production deployment: temporal data leakage in evaluation, hallucinated facts, limited data coverage, and high inference costs. These concerns directly shape Agentic-Quant's emphasis on data grounding, structured output validation, and cost-aware model selection.

== Agent Orchestration and Decision Visualization

AGORA @zhang_unifying_2025, presented at ACL 2025, provides a graph-based orchestration engine for LLM agents. Its evaluation reveals that simpler reasoning methods like chain-of-thought often match more complex approaches at lower cost --- a practical insight for agent design. FinAgent @zhang_multimodal_2024, from KDD 2024, is a multimodal agent combining numerical, textual, and visual data with tool augmentation and a dual-level reflection module, achieving over 36\% improvement on profit metrics across six datasets.

On explainability, de la Rica Escudero et al. @de-la-rica-escudero_explainable_2025 apply SHAP and LIME to explain portfolio decisions made by deep RL agents in real time. Tatsat and Shater @tatsat_beyond_2025 go further with mechanistic interpretability, reverse-engineering LLM internals to understand financial reasoning. Wang et al. @wang_modeling_2024 show that modeling interactions _among_ news items --- rather than treating each independently --- captures temporal dynamics that simple sentiment scoring misses. These findings motivate Agentic-Quant's decision-flow visualization: making the full reasoning chain from data to decision visible and auditable.

== Human-in-the-Loop and Autonomous Trading

Alpha-GPT 2.0 @yuan_alpha-gpt_2024, from HKUST and IDEA Research, introduces an iterative human-AI collaboration framework for quantitative investment. Rather than full automation, it lets human researchers guide AI in alpha mining while AI results inspire human insight. The paper argues that purely automated approaches face diminishing returns.

A comprehensive survey @pippas_evolution_2025 covering 167 publications on reinforcement learning in quantitative finance maps RL concepts to investing language and evaluates multi-agent RL approaches for portfolio management. This body of work provides the baseline against which LLM-based systems like Agentic-Quant can be compared. A broader survey on LLM agents in finance @dong_large_2025 identifies coordination-aware multi-agent systems as an under-explored direction --- precisely the gap Agentic-Quant aims to fill.

// ═══════════════════════════════════════════
//  3  System Design and Current Implementation
// ═══════════════════════════════════════════
= System Design and Current Implementation

== Overall Architecture

Agentic-Quant uses LangGraph's `StateGraph` to orchestrate five agents. @fig-workflow shows the pipeline. Three analyst agents run in parallel; the risk analyst and PM run sequentially after all upstream reports are available.

#figure(
  image("architecture.pdf", width: 100%),
  caption: [Target system architecture. Solid borders and arrows show existing components; dashed elements indicate planned enhancements.],
) <fig-workflow>

The shared state holds the stock ticker, analysis date, current position, and per-agent message histories. Agents read from and write to this state but do not call each other directly. This keeps them loosely coupled and independently modifiable.

== Agent Design

The five agents serve distinct roles:

- *Market Analyst* retrieves price data and technical indicators (SMA, Bollinger Bands, RSI, MACD) via Yahoo Finance. It identifies trends, support/resistance levels, and momentum signals.
- *News Analyst* fetches recent headlines from Google News, assesses sentiment and relevance, and highlights events that may affect near-term price action.
- *Fundamentals Analyst* pulls financial statements and valuation metrics from Yahoo Finance and AkShare. It evaluates profitability, growth, and valuation relative to sector peers.
- *Risk Analyst* reads the three upstream reports. It identifies conflicting signals, assesses overall risk exposure, and flags potential concerns.
- *Portfolio Manager (PM)* reads all four reports and outputs a structured decision via Pydantic schema: direction (bullish / bearish / neutral), target position, confidence, time horizon, and a reasoning summary.

Each agent runs as a LangGraph node backed by an LLM (currently OpenAI-compatible models). Agents that need external data access tools through LangGraph's `ToolNode` mechanism.

== Data Pipeline and State Persistence

Agentic-Quant employs a unified `DataService` architecture designed to handle multi-modal data streams and maintain a continuous feedback loop. The pipeline integrates three primary external categories with an internal persistence layer:

- *External Market & News Data:* Real-time price action and technical indicators (SMA, RSI, MACD) are ingested via Yahoo Finance. News sentiment and event relevance are parsed from Google News headlines. For deeper fundamental analysis, historical point-in-time data and sector-wide metrics are retrieved through AkShare.
- *Internal Execution Feedback:* Unlike stateless systems, the pipeline incorporates a feedback channel from the Broker Mock Engine. Execution results, including realized profit/loss and slippage, are fed back into the state to inform subsequent agent reasoning.
- *Persistent Context Store:* All ingested data, intermediate agent reports, and final decisions are persisted in a SQLite-based storage layer. This `ContextStore` allows the system to perform context-aware retrieval, where agents can reference previous analysis cycles for the same ticker to ensure temporal consistency in their recommendations.

The data flow is governed by robust fallback logic; retrieval failures in one provider trigger automatic shifts to backup sources, ensuring the high availability required for continuous monitoring.

== Web Dashboard and Human Interaction

The frontend, built on Streamlit, serves as an integrated command center for autonomous analysis and supervised execution. Its functionality is divided into three core modules:

- *Analysis & Strategy Visualization:* Users can configure stock analysis parameters and view real-time technical charts powered by Plotly. The dashboard includes a *Decision-Flow Visualization* module, which renders the LangGraph reasoning chain as an interactive diagram, allowing users to audit exactly how news sentiment or fundamental shifts influenced the final PM decision.
- *HITL Approval Gateway:* To manage high-risk scenarios, the interface features a dedicated Human-in-the-Loop (HITL) panel. Decisions flagged by the Risk Analyst—due to conflicting signals or large position changes—are held in a "Pending" state. Reviewers can approve, reject, or manually adjust trade parameters directly through the UI or via linked messaging channels.
- *Performance & Session Management:* The interface provides a historical view of all past sessions stored in the `ContextStore`. Users can replay past decision cycles, evaluate backtesting performance with interactive equity curves, and export comprehensive analysis summaries as PDF reports.

// ═══════════════════════════════════════════
//  4  Proposed Enhancements
// ═══════════════════════════════════════════
= Proposed Enhancements

== Context Management and Persistent Memory

Currently all context lives in an in-memory Python dictionary and is lost after each run. The planned upgrade introduces a SQLite-based storage layer that persists agent reports, tool call logs with timestamps, PM decisions with reasoning, and per-ticker decision history.

A `ContextStore` abstraction will support swapping between in-memory (development) and SQLite (production) backends without changing application code. With persistent context, the system can replay any past analysis session, retrieve the last _N_ decisions for a given ticker, and remain queryable after restart @yu_finmem:_2023.

== Human-in-the-Loop Approval Mechanism

In the current pipeline, the PM's decision is final. For a practical trading assistant, certain actions require human verification --- especially large position changes, trades against conflicting signals, or decisions based on sparse data @yuan_alpha-gpt_2024.

The HITL module will define trigger policies (e.g., position change above a threshold, analyst disagreement above a tolerance). Flagged decisions are routed to a human reviewer who can approve, reject, or modify parameters. All outcomes are logged and fed back for policy refinement.

== Broker Mock Engine and Backtesting Loop

To close the gap between analysis and execution, a simulated broker engine will handle basic order types (market and limit), maintain virtual account balances and positions, and track profit/loss over time. The engine exposes a standard gateway interface modeled on real broker APIs (e.g., Moomoo OpenAPI), simplifying future migration to live trading @yang_finrobot:_2024.

This creates a full cycle: agents analyze, PM decides, broker executes, results feed back for the next round. The backtesting loop can also evaluate how well past decisions would have performed, providing a concrete measure of system quality.

== Multi-Channel Notification

The system will integrate with WhatsApp and Telegram via their respective APIs. Planned notifications include: daily market summaries generated by the agents, real-time alerts when significant events are flagged, and HITL approval requests that reviewers can respond to directly from the messaging app.

== Decision-Flow Visualization

Each analysis session produces a chain of intermediate outputs: data retrievals, agent reports, risk assessments, and a final decision. The visualization module will render this chain as an interactive flow diagram in the Streamlit interface, showing how each agent's analysis contributed to the final call. This serves as both an audit trail for users and a debugging tool for developers @de-la-rica-escudero_explainable_2025 @tatsat_beyond_2025.

// ═══════════════════════════════════════════
//  5  Technical Stack
// ═══════════════════════════════════════════
= Technical Stack

#table(
  columns: (1fr, 2fr),
  align: (left, left),
  stroke: 0.5pt,
  inset: 8pt,
  table.header([*Category*], [*Technology*]),
  [Agent orchestration], [LangGraph (StateGraph, ToolNode, MemorySaver)],
  [LLM backend], [OpenAI-compatible API],
  [Data sources], [Yahoo Finance, Google News, AkShare],
  [Web interface], [Streamlit, Plotly],
  [Persistent storage], [SQLite (planned)],
  [Broker simulation], [Custom engine with FastAPI gateway (planned)],
  [Messaging], [WhatsApp Business API, Telegram Bot API (planned)],
  [Structured output], [Pydantic],
  [Package management], [uv],
  [Language], [Python 3.12],
)

// ═══════════════════════════════════════════
//  6  Milestones and Timeline
// ═══════════════════════════════════════════
= Milestones and Timeline

#table(
  columns: (auto, 1fr, auto, auto),
  align: (center, left, center, center),
  stroke: 0.5pt,
  inset: 8pt,
  table.header([*\#*], [*Task*], [*Target Date*], [*Hours*]),
  [1], [Data pipeline (Yahoo Finance, Google News, AkShare)], [2026-02], [80],
  [2], [Agent tools and LangGraph multi-agent workflow], [2026-03], [120],
  [3], [Streamlit web interface and basic backtesting], [2026-03], [100],
  table.cell(colspan: 4, fill: luma(245), align: center)[_Tasks 1--3 completed before proposal submission_],
  [4], [Context management and persistent storage (SQLite)], [2026-04-14], [150],
  [5], [Human-in-the-loop approval mechanism], [2026-05-05], [120],
  [6], [Broker mock engine and backtesting loop], [2026-06-01], [200],
  [7], [Decision-flow visualization], [2026-06-16], [150],
  [8], [Multi-channel notification and system integration], [2026-07-06], [160],
  [9], [Project webpage and end-to-end evaluation], [2026-07-13], [100],
  [10], [Final report and demo preparation], [2026-07-17], [120],
  table.cell(colspan: 3, align: right)[*Total*], [*1300*],
)

// ═══════════════════════════════════════════
//  7  Deliverables
// ═══════════════════════════════════════════
= Deliverables

+ A working multi-agent stock analysis system with persistent context, HITL approval, and broker simulation.
+ A Streamlit-based web dashboard with decision-flow visualization.
+ Multi-channel notification integration (WhatsApp / Telegram).
+ A final report documenting system design, implementation, and evaluation results.
+ A demo video showing the end-to-end workflow.

// ═══════════════════════════════════════════
//  References
// ═══════════════════════════════════════════
#bibliography("citations.bib", title: "References", style: "ieee")
