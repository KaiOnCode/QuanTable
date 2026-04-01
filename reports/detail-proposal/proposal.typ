#import "@preview/fletcher:0.5.8" as fletcher: diagram, edge, node

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
//  Abstract
// ═══════════════════════════════════════════
#heading(numbering: none)[Abstract]

Agentic-Quant is a multi-agent stock analysis framework built on LangGraph. Five AI agents --- market analyst, news analyst, fundamentals analyst, risk analyst, and portfolio manager --- work in a structured pipeline to produce trading recommendations from real-time market data. The system already supports data retrieval from Yahoo Finance and Google News, technical charting, historical backtesting, and a Streamlit-based web interface. This proposal describes five planned extensions: persistent context management, a human-in-the-loop approval mechanism, a simulated broker engine, multi-channel notification, and decision-flow visualization. Together, these additions aim to turn Agentic-Quant from a single-query advisory tool into a continuously running, auditable trading assistant.

#v(0.5em)
*Keywords:* Multi-Agent System, LangGraph, LLM-driven Quantitative Analysis, Decision-Flow Visualization, Autonomous Trading, Human-in-the-Loop

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

This project addresses the above gaps through five objectives:

+ Build a persistent context layer that retains agent reports, tool logs, and past decisions across sessions.
+ Implement a human-in-the-loop mechanism that routes high-risk or conflicting decisions to human review.
+ Develop a broker simulation engine that executes virtual trades and feeds results back to the agents.
+ Integrate messaging channels (WhatsApp, Telegram) for mobile monitoring and approval.
+ Create a decision-flow visualization that traces how each agent contributes to the final recommendation.

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
  diagram(
    node-stroke: 0.7pt,
    node-inset: 8pt,
    spacing: (18mm, 14mm),
    node((0, 1), [*START*], corner-radius: 3pt, fill: luma(240)),
    node((1, 0), [Market \ Analyst], corner-radius: 3pt),
    node((1, 1), [News \ Analyst], corner-radius: 3pt),
    node((1, 2), [Fundamentals \ Analyst], corner-radius: 3pt),
    node((2, 1), [Risk \ Analyst], corner-radius: 3pt, fill: luma(240)),
    node((3, 1), [PM \ Agent], corner-radius: 3pt, fill: luma(240)),
    node((4, 1), [*END*], corner-radius: 3pt, fill: luma(240)),
    edge((0, 1), (1, 0), "-|>"),
    edge((0, 1), (1, 1), "-|>"),
    edge((0, 1), (1, 2), "-|>"),
    edge((1, 0), (2, 1), "-|>"),
    edge((1, 1), (2, 1), "-|>"),
    edge((1, 2), (2, 1), "-|>"),
    edge((2, 1), (3, 1), "-|>"),
    edge((3, 1), (4, 1), "-|>"),
  ),
  caption: [Agent workflow. Three analysts run in parallel; the risk analyst waits for all reports before proceeding to the PM.],
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

== Data Pipeline

A unified `DataService` class provides three data sources:

- *Yahoo Finance* for real-time prices, technical indicators, and basic financials.
- *Google News* for news headlines and article links.
- *AkShare* for historical point-in-time fundamental data, with a focus on China A-shares.

A macro calendar module is in early development for economic event tracking. Retrieval failures trigger fallback logic; additional providers (e.g., Alpha Vantage) are planned as backup sources.

== Web Interface

The Streamlit-based frontend offers three functions: stock analysis with configurable parameters, historical backtesting with performance charts (Plotly), and technical chart overlays with selectable indicators. Results can be exported as PDF reports.

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
  [1], [Context management and persistent storage], [2026-04-15], [150],
  [2], [Human-in-the-loop approval mechanism], [2026-05-01], [120],
  [3], [Broker mock engine and backtesting loop], [2026-05-25], [200],
  [4], [Decision-flow visualization], [2026-06-10], [150],
  [5], [Multi-channel notification (WhatsApp / Telegram)], [2026-06-20], [100],
  [6], [System integration and end-to-end evaluation], [2026-07-05], [160],
  [7], [Final report and demo preparation], [2026-07-20], [120],
  table.cell(colspan: 3, align: right)[*Total*], [*1000*],
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
