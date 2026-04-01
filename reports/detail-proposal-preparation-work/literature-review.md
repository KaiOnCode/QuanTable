# Literature Review: LLM-based Multi-Agent Systems for Quantitative Financial Analysis

**Project:** Agentic-Quant — A Multi-Agent Framework for Reasoning-Based Quantitative Analysis  
**Course:** COMP7705, The University of Hong Kong  
**Date:** March 2026  
**Search Period:** 2022–2026  
**Databases Searched:** Google Scholar, arXiv, Semantic Scholar, ACM Digital Library, ACL Anthology, Springer Nature, IEEE Xplore

---

## Table of Contents

1. [Multi-Agent Systems (MAS) for Finance](#1-multi-agent-systems-mas-for-finance)
2. [LLM-driven Quantitative Analysis](#2-llm-driven-quantitative-analysis)
3. [LLM Agent Orchestration Frameworks](#3-llm-agent-orchestration-frameworks)
4. [Autonomous Trading Systems with AI](#4-autonomous-trading-systems-with-ai)
5. [Decision-Flow Visualization and Explainability](#5-decision-flow-visualization-and-explainability)
6. [Human-in-the-Loop (HITL) AI Trading](#6-human-in-the-loop-hitl-ai-trading)
7. [Retrieval-Augmented Generation (RAG) in Finance](#7-retrieval-augmented-generation-rag-in-finance)
8. [Sentiment Analysis for Financial Markets](#8-sentiment-analysis-for-financial-markets)
9. [Summary and Research Gaps](#9-summary-and-research-gaps)
10. [References](#10-references)

---

## 1. Multi-Agent Systems (MAS) for Finance

This section reviews recent work on using multiple AI agents for collaborative financial decision-making, directly relevant to Agentic-Quant's multi-agent architecture (market analyst, news analyst, fundamentals analyst, risk analyst, portfolio manager).

### 1.1 TradingAgents: Multi-Agents LLM Financial Trading Framework

- **Authors:** Yijia Xiao, Edward Sun, Di Luo, Wei Wang
- **Year:** 2024
- **Venue:** arXiv preprint (under review, OpenReview submission)
- **DOI:** [10.48550/arXiv.2412.20138](https://doi.org/10.48550/arXiv.2412.20138)

**Summary:** TradingAgents simulates real-world trading firm dynamics with specialized LLM-powered agents including fundamental analysts, sentiment analysts, technical analysts, and traders with varied risk profiles. The system features Bull and Bear researcher agents that debate market conditions, a risk management team monitoring exposure, and traders synthesizing insights from debates and historical data. Experiments demonstrate notable improvements in cumulative returns, Sharpe ratio, and maximum drawdown compared to baseline models.

**Relevance to Agentic-Quant:** Directly mirrors the Agentic-Quant architecture with its role-based agent decomposition (analyst teams, risk management, portfolio manager). The dialectical debate mechanism between Bull/Bear agents provides a blueprint for implementing adversarial reasoning in Agentic-Quant's decision pipeline.

### 1.2 FinCon: A Synthesized LLM Multi-Agent System with Conceptual Verbal Reinforcement for Enhanced Financial Decision Making

- **Authors:** Yangyang Yu, Zhiyuan Yao, Haohang Li, Zhiyang Deng, Yupeng Cao, Zhi Chen, Jordan W. Suchow, Rong Liu, Zhenyu Cui, Zhaozhuo Xu, Denghui Zhang, Koduvayur Subbalakshmi, Guojun Xiong, Yueru He, Jimin Huang, Dong Li, Qianqian Xie
- **Year:** 2024
- **Venue:** NeurIPS 2024 (Poster)
- **DOI:** [10.48550/arXiv.2407.06567](https://doi.org/10.48550/arXiv.2407.06567)

**Summary:** FinCon introduces a manager-analyst communication hierarchy inspired by real-world investment firm structures. The system features conceptual verbal reinforcement (CVRF), where learned beliefs serve as reinforcement for future agent behavior and can be selectively propagated to relevant nodes. A risk-control component with episodic self-critiquing mechanisms updates systematic investment beliefs. The framework demonstrates strong generalization across single stock trading and portfolio management tasks.

**Relevance to Agentic-Quant:** The manager-analyst hierarchy directly parallels Agentic-Quant's portfolio manager orchestrating multiple analyst agents. The CVRF mechanism offers a principled approach for agents to learn from past decisions, applicable to Agentic-Quant's iterative decision refinement process.

### 1.3 TradingGroup: A Multi-Agent Trading System with Self-Reflection and Data-Synthesis

- **Authors:** Feng Tian, Flora D. Salim, Hao Xue
- **Year:** 2025
- **Venue:** arXiv preprint
- **DOI:** [10.48550/arXiv.2508.17565](https://doi.org/10.48550/arXiv.2508.17565)

**Summary:** TradingGroup consists of five specialized agents: News Sentiment Agent, Financial Report Agent, Stock Forecasting Agent, Style Preference Agent, and Trading Decision Agent. The system features self-reflection mechanisms that allow agents to distill past successes and failures for improved decision-making, plus an end-to-end data-synthesis pipeline that automatically generates high-quality post-training data. Backtesting across five real-world stock datasets shows superior performance over rule-based, ML, RL, and existing LLM-based strategies.

**Relevance to Agentic-Quant:** The five-agent decomposition (news, financial reports, forecasting, style preference, trading decision) closely matches Agentic-Quant's agent roles. The self-reflection mechanism is particularly relevant for Agentic-Quant's design goal of transparent, explainable decision-making.

### 1.4 FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design

- **Authors:** Yangyang Yu, Haohang Li, Zhi Chen, Yuechen Jiang, Yang Li, Denghui Zhang, Rong Liu, Jordan W. Suchow, Khaldoun Khashanah
- **Year:** 2023
- **Venue:** AAAI Spring Symposium on Human-Like Learning 2024; ICLR Workshop on LLM Agents 2024
- **DOI:** [10.48550/arXiv.2311.13743](https://doi.org/10.48550/arXiv.2311.13743)

**Summary:** FinMem introduces a three-module architecture (Profiling, Memory, Decision-making) for LLM-based financial trading. The memory module features layered message processing aligned with human trader cognitive structures, providing an adjustable cognitive span that retains critical information beyond typical human perceptual limits. Testing on real-world datasets demonstrated leading trading performance compared to various algorithmic agents.

**Relevance to Agentic-Quant:** FinMem's layered memory architecture is applicable to Agentic-Quant's agents for maintaining context across multiple analysis sessions. The character-based profiling module informs how Agentic-Quant can customize each agent's risk tolerance and analytical style.

### 1.5 FinRobot: An Open-Source AI Agent Platform for Financial Applications using Large Language Models

- **Authors:** Hongyang Yang, Boyu Zhang, Neng Wang, Cheng Guo, Xiaoli Zhang, Likun Lin, Junlin Wang, Tianyu Zhou, Mao Guan, Runjia Zhang, Christina Dan Wang
- **Year:** 2024
- **Venue:** arXiv preprint
- **DOI:** [10.48550/arXiv.2405.14767](https://doi.org/10.48550/arXiv.2405.14767)

**Summary:** FinRobot is an open-source platform with a four-layer architecture: Financial AI Agents layer (formulates Financial Chain-of-Thought), Financial LLM Algorithms layer, LLMOps/DataOps layer, and Multi-source LLM Foundation Models layer. A key implementation employs three specialized agents (Data-CoT, Concept-CoT, Thesis-CoT) for equity research and valuation, delivering analysis comparable to major brokerage firms.

**Relevance to Agentic-Quant:** FinRobot's layered architecture and Financial Chain-of-Thought approach provides a reference implementation for Agentic-Quant's reasoning pipeline. The open-source nature and multi-agent CoT decomposition align with Agentic-Quant's design philosophy.

---

## 2. LLM-driven Quantitative Analysis

This section covers papers on using Large Language Models for stock analysis, financial reasoning, and chain-of-thought approaches in quantitative finance.

### 2.1 Can Large Language Models Beat Wall Street? Evaluating GPT-4's Impact on Financial Decision-Making with MarketSenseAI

- **Authors:** Georgios Fatouros, Konstantinos Metaxas, John Soldatos, Dimosthenis Kyriazis
- **Year:** 2024
- **Venue:** Neural Computing and Applications (Springer)
- **DOI:** [10.1007/s00521-024-10613-4](https://doi.org/10.1007/s00521-024-10613-4)

**Summary:** MarketSenseAI integrates GPT-4's reasoning with Chain of Thought and In-Context Learning to analyze market trends, news, fundamentals, and macroeconomic factors for stock selection. Empirical testing on S&P 100 stocks over 15 months yielded excess alpha of 10–30% and cumulative returns up to 72%, while maintaining a risk profile comparable to the broader market. The study demonstrates that AI-generated explanations significantly impact signal accuracy and reliability.

**Relevance to Agentic-Quant:** MarketSenseAI validates the core hypothesis of Agentic-Quant — that LLMs with structured reasoning can generate actionable investment signals. The multi-factor analysis approach (trends, news, fundamentals, macro) maps directly to Agentic-Quant's analyst agents.

### 2.2 BloombergGPT: A Large Language Model for Finance

- **Authors:** Shijie Wu, Ozan Irsoy, Steven Lu, Vadim Dabravolski, Mark Dredze, Sebastian Gehrmann, Prabhanjan Kambadur, David Rosenberg, Gideon Mann
- **Year:** 2023
- **Venue:** arXiv preprint
- **DOI:** [10.48550/arXiv.2303.17564](https://doi.org/10.48550/arXiv.2303.17564)

**Summary:** BloombergGPT is a 50-billion-parameter language model trained on a mixed dataset of 363 billion tokens from Bloomberg's proprietary financial data and 345 billion tokens from general-purpose datasets. The model outperforms similarly-sized open models on financial NLP tasks by significant margins while maintaining competitive performance on general-purpose benchmarks. This represents the largest domain-specific training dataset constructed for a financial LLM.

**Relevance to Agentic-Quant:** BloombergGPT demonstrates the value of domain-specific financial training data for LLM performance. Agentic-Quant can leverage insights from this work by incorporating domain-adapted models or fine-tuning strategies for its analyst agents.

### 2.3 FinGPT: Open-Source Financial Large Language Models

- **Authors:** Hongyang Yang, Xiao-Yang Liu, Christina Dan Wang
- **Year:** 2023
- **Venue:** FinLLM Workshop @ IJCAI 2023 (Macao)
- **DOI:** [10.48550/arXiv.2306.06031](https://doi.org/10.48550/arXiv.2306.06031)

**Summary:** FinGPT takes a data-centric, open-source approach to building financial LLMs, contrasting with proprietary models like BloombergGPT. The framework features an automatic data curation pipeline and lightweight low-rank adaptation techniques, addressing challenges of high temporal sensitivity and low signal-to-noise ratios in financial data. Applications include robo-advising, algorithmic trading, and sentiment analysis.

**Relevance to Agentic-Quant:** FinGPT's open-source philosophy and lightweight adaptation techniques are directly applicable to Agentic-Quant, which can use LoRA-based fine-tuning to specialize LLMs for different agent roles without prohibitive training costs.

### 2.4 The New Quant: A Survey of Large Language Models in Financial Prediction and Trading

- **Authors:** Weilong Fu
- **Year:** 2025
- **Venue:** arXiv preprint
- **DOI:** [10.48550/arXiv.2510.05533](https://doi.org/10.48550/arXiv.2510.05533)

**Summary:** This comprehensive survey synthesizes over fifty primary studies on LLMs in quantitative investing. It proposes a task-centered taxonomy spanning sentiment extraction, numerical reasoning, multimodal understanding, RAG, time series prompting, and agentic systems. The survey identifies critical production challenges including temporal leakage, hallucination, data coverage, deployment economics, and governance, and recommends standardized evaluation and auditable pipelines.

**Relevance to Agentic-Quant:** Provides a systematic taxonomy that positions Agentic-Quant within the broader landscape of LLM-based quantitative systems. The identified challenges (hallucination, temporal leakage) directly inform risk mitigation strategies for Agentic-Quant's deployment.

---

## 3. LLM Agent Orchestration Frameworks

This section reviews academic work on agentic AI frameworks, tool-augmented LLMs, and graph-based orchestration — relevant to Agentic-Quant's use of LangGraph for multi-agent coordination.

### 3.1 AGORA: Unifying Language Agent Algorithms with Graph-based Orchestration Engine for Reproducible Agent Research

- **Authors:** Qianqian Zhang, Jiajia Liao, Heting Ying, Yibo Ma, Haozhan Shen, Jingcheng Li, Peng Liu, Lu Zhang, Chunxin Fang, Kyusong Lee, Ruochen Xu, Tiancheng Zhao
- **Year:** 2025
- **Venue:** ACL 2025 (System Demonstrations), Vienna, Austria
- **DOI:** [10.18653/v1/2025.acl-demo.11](https://doi.org/10.18653/v1/2025.acl-demo.11)

**Summary:** AGORA presents a modular architecture with a graph-based workflow engine, efficient memory management, and clean component abstraction for building LLM agents. It implements a comprehensive suite of reusable agent algorithms with a rigorous evaluation framework. Key finding: while sophisticated reasoning approaches can enhance agent capabilities, simpler methods like Chain-of-Thought often exhibit robust performance with significantly lower computational overhead.

**Relevance to Agentic-Quant:** AGORA's graph-based orchestration engine is architecturally analogous to Agentic-Quant's use of LangGraph. The modular design principles and evaluation framework provide best practices for Agentic-Quant's agent workflow implementation.

### 3.2 FinAgent: A Multimodal Foundation Agent for Financial Trading: Tool-Augmented, Diversified, and Generalist

- **Authors:** Wentao Zhang, Lingxuan Zhao, Haochong Xia, Shuo Sun, Jiaze Sun, Molei Qin, Xinyi Li, Yuqing Zhao, Yilei Zhao, Xinyu Cai, Longtao Zheng, Xinrun Wang, Bo An
- **Year:** 2024
- **Venue:** KDD 2024 (30th ACM SIGKDD), Barcelona, Spain
- **DOI:** [10.1145/3637528.3671801](https://doi.org/10.1145/3637528.3671801)

**Summary:** FinAgent is the first advanced multimodal foundation agent for financial trading, featuring a market intelligence module that processes numerical, textual, and visual data, a dual-level reflection module for rapid market adaptation, and a diversified memory retrieval system. The tool-augmented approach integrates established trading strategies and expert insights. FinAgent achieves over 36% average improvement on profit metrics across 6 financial datasets compared to 12 baselines.

**Relevance to Agentic-Quant:** FinAgent's tool-augmented design validates the approach of equipping LLM agents with external tools (APIs, data sources) that Agentic-Quant employs. The multimodal processing capability (text + numerical + visual) extends beyond Agentic-Quant's current design and suggests future enhancement directions.

### 3.3 Large Language Model Agents in Finance: A Survey Bridging Research, Practice, and Real-World Deployment

- **Authors:** Yifei Dong, Fengyi Wu, Kunlin Zhang, Yilong Dai, Sanjian Zhang, Wanghao Ye, Sihan Chen, Zhi-Qi Cheng
- **Year:** 2025
- **Venue:** Findings of EMNLP 2025, Suzhou, China
- **DOI:** [10.18653/v1/2025.findings-emnlp.972](https://aclanthology.org/2025.findings-emnlp.972/)

**Summary:** This survey provides a systematic dual-perspective review bridging financial practice and LLM research across five core domains: Data Analysis, Investment Research, Trading, Investment Management, and Risk Management. It catalogs over 30 financial benchmarks and 20 representative models, identifying key challenges including numerical reasoning limitations, prompt sensitivity, and lack of real-time adaptability. Emerging directions include continual adaptation, coordination-aware multi-agent systems, and privacy-compliant deployment.

**Relevance to Agentic-Quant:** This survey positions Agentic-Quant within the broader research landscape and highlights the gap that coordination-aware multi-agent systems (like Agentic-Quant) aim to fill. The identified benchmarks provide evaluation standards for Agentic-Quant's performance assessment.

---

## 4. Autonomous Trading Systems with AI

This section reviews AI-powered trading systems, with focus on reinforcement learning for portfolio management and autonomous decision-making.

### 4.1 The Evolution of Reinforcement Learning in Quantitative Finance: A Survey

- **Authors:** Nikolaos Pippas, Elliot A. Ludvig, Cagatay Turkay
- **Year:** 2024 (arXiv); 2025 (journal publication)
- **Venue:** ACM Computing Surveys, Vol. 57, No. 11
- **DOI:** [10.1145/3733714](https://doi.org/10.1145/3733714)

**Summary:** This comprehensive survey critically evaluates 167 publications on RL applications in finance spanning over 25 years (1996–2022). It covers portfolio management, trading systems, and option pricing, examining advanced techniques including transfer learning, meta-learning, and multi-agent solutions. The work translates RL concepts into investing language—defining state (market information), action (trading decisions), and reward (profit/returns)—to bridge academic ML and practical portfolio management.

**Relevance to Agentic-Quant:** Provides a historical foundation and benchmark comparison for Agentic-Quant's LLM-based approach versus traditional RL-based trading systems. The multi-agent RL section is particularly relevant for understanding how Agentic-Quant's cooperative agent design compares to competitive multi-agent RL approaches.

### 4.2 FinAgent: A Multimodal Foundation Agent for Financial Trading

*(See Section 3.2 for full details)*

**Additional relevance to autonomous trading:** FinAgent's dual-level reflection module (rapid adaptation) and diversified memory retrieval represent state-of-the-art in autonomous trading agent design, providing both short-term reactivity and long-term strategy learning.

### 4.3 FinCon: A Synthesized LLM Multi-Agent System with Conceptual Verbal Reinforcement

*(See Section 1.2 for full details)*

**Additional relevance to autonomous trading:** FinCon's episodic self-critiquing mechanism represents a novel form of verbal reinforcement learning that bridges the gap between traditional RL and LLM-based autonomous trading, enabling strategy improvement without gradient-based updates.

---

## 5. Decision-Flow Visualization and Explainability

This section covers explainability and visualization of AI decision processes in finance — directly relevant to Agentic-Quant's "Decision-Flow Visualization" design goal.

### 5.1 Explainable Post Hoc Portfolio Management Financial Policy of a Deep Reinforcement Learning Agent

- **Authors:** Alejandra de la Rica Escudero, Eduardo C. Garrido-Merchan, Maria Coronado-Vaca
- **Year:** 2024
- **Venue:** PLOS ONE (also arXiv:2407.14486)
- **DOI:** [10.1371/journal.pone.0315528](https://doi.org/10.1371/journal.pone.0315528)

**Summary:** This paper presents the first explainable post-hoc portfolio management approach for Deep Reinforcement Learning agents. It combines Proximal Policy Optimization (PPO) with model-agnostic explainability techniques including feature importance, SHAP, and LIME to make investment decisions interpretable at prediction time. The methodology successfully identifies key features influencing investment decisions, enabling real-time explanation of agent actions.

**Relevance to Agentic-Quant:** Directly applicable to Agentic-Quant's decision-flow visualization feature. The SHAP/LIME-based post-hoc explanation techniques can be adapted to visualize how each Agentic-Quant agent contributes to final trading decisions, enhancing transparency and user trust.

### 5.2 Beyond the Black Box: Interpretability of LLMs in Finance

- **Authors:** Hariom Tatsat, Ariye Shater
- **Year:** 2025
- **Venue:** arXiv preprint (from Barclays)
- **DOI:** [10.48550/arXiv.2505.24650](https://doi.org/10.48550/arXiv.2505.24650)

**Summary:** This paper presents the first application of mechanistic interpretability in the finance domain, reverse-engineering LLMs' internal mechanisms by dissecting activations and circuits. It demonstrates practical applications including trading strategies, sentiment analysis, bias detection, and hallucination detection. The work emphasizes how mechanistic interpretability can address regulatory compliance requirements in the highly regulated financial sector.

**Relevance to Agentic-Quant:** Provides a deeper interpretability methodology beyond post-hoc explanations for understanding *how* LLM agents make financial decisions internally. This aligns with Agentic-Quant's goal of building transparent, auditable decision flows, and addresses regulatory concerns for real-world deployment.

### 5.3 Modeling News Interactions and Influence for Financial Market Prediction (FININ)

- **Authors:** Mengyu Wang, Shay B. Cohen, Tiejun Ma
- **Year:** 2024
- **Venue:** Findings of EMNLP 2024
- **DOI:** [10.18653/v1/2024.findings-emnlp.189](https://doi.org/10.18653/v1/2024.findings-emnlp.189)

**Summary:** FININ introduces a novel approach that models interactions among news items themselves (not just news-to-price connections), integrating multi-modal information from market data and news. Tested on 2.7 million news articles over 15 years for S&P 500 and NASDAQ 100, FININ reveals insights including delayed market pricing of news, long memory effects, and limitations of sentiment analysis alone for extracting predictive signals.

**Relevance to Agentic-Quant:** FININ's approach to modeling news interactions (rather than treating news items independently) offers a more sophisticated framework for Agentic-Quant's news analyst agent, enabling it to capture inter-news relationships and temporal dynamics that simple sentiment scoring misses.

---

## 6. Human-in-the-Loop (HITL) AI Trading

This section reviews semi-autonomous trading systems with human oversight, relevant to Agentic-Quant's design for human verification of AI-generated trading decisions.

### 6.1 Alpha-GPT 2.0: Human-in-the-Loop AI for Quantitative Investment

- **Authors:** Hang Yuan, Saizhuo Wang, Jian Guo
- **Year:** 2024
- **Venue:** arXiv preprint (HKUST and IDEA Research)
- **DOI:** [10.48550/arXiv.2402.09746](https://doi.org/10.48550/arXiv.2402.09746)

**Summary:** Alpha-GPT 2.0 introduces a human-in-the-loop framework for quantitative investment that emphasizes iterative, interactive collaboration between human researchers and AI throughout the entire investment pipeline. Rather than fully automating the process, it integrates human insights to guide AI systems in alpha mining and model searching, while AI experimental results inspire human researchers. The cyclical, multi-round interactive process addresses limitations of purely automated approaches, which are computationally intensive with diminishing returns.

**Relevance to Agentic-Quant:** Directly validates Agentic-Quant's design philosophy of keeping humans in the decision loop. Alpha-GPT 2.0's iterative human-AI collaboration framework provides a model for how Agentic-Quant's Streamlit interface can enable users to review, modify, and approve AI-generated trading recommendations before execution.

### 6.2 FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design

*(See Section 1.4 for full details)*

**Additional HITL relevance:** FinMem's adjustable cognitive span and character-based profiling enable human users to configure agent behavior parameters, representing a form of indirect human-in-the-loop control over autonomous trading decisions.

### 6.3 TradingAgents: Multi-Agents LLM Financial Trading Framework

*(See Section 1.1 for full details)*

**Additional HITL relevance:** TradingAgents' Fund Manager approval layer serves as an explicit checkpoint where human oversight can be injected into the multi-agent decision pipeline, demonstrating how Agentic-Quant's portfolio manager role can incorporate human verification.

---

## 7. Retrieval-Augmented Generation (RAG) in Finance

This section reviews the use of RAG for financial document analysis, relevant to Agentic-Quant's potential integration of real-time financial data retrieval.

### 7.1 AlphaFin: Benchmarking Financial Analysis with Retrieval-Augmented Stock-Chain Framework

- **Authors:** Xiang Li, Zhenyu Li, Chen Shi, Yong Xu, Qing Du, Mingkui Tan, Jun Huang, Wei Lin
- **Year:** 2024
- **Venue:** LREC-COLING 2024, Torino, Italy
- **DOI:** [10.48550/arXiv.2403.12582](https://doi.org/10.48550/arXiv.2403.12582)

**Summary:** AlphaFin introduces both a benchmark dataset and a Stock-Chain method that integrates RAG with LLMs for financial analysis. The framework combines three types of data — traditional research datasets, real-time financial data, and handwritten chain-of-thought data — to improve LLM performance on stock trend prediction and financial question answering while reducing hallucinations.

**Relevance to Agentic-Quant:** AlphaFin's RAG + CoT approach is directly applicable to Agentic-Quant's fundamentals analyst agent, which needs to retrieve and reason over real-time financial data. The Stock-Chain framework provides a template for structuring retrieval-augmented reasoning in financial contexts.

### 7.2 RAG-IT: Retrieval-Augmented Instruction Tuning for Automated Financial Analysis

- **Authors:** Van-Duc Le, Hai-Thien To, Tien-Cuong Bui
- **Year:** 2024
- **Venue:** arXiv preprint
- **DOI:** [10.48550/arXiv.2412.08179](https://doi.org/10.48550/arXiv.2412.08179)

**Summary:** RAG-IT combines retrieval augmentation with instruction-based fine-tuning for automated earnings report analysis. The framework constructs a comprehensive financial instruction dataset from extensive financial documents and earnings reports, achieving performance comparable to GPT-3.5 on financial report generation tasks while using smaller, more efficient models.

**Relevance to Agentic-Quant:** RAG-IT's instruction-tuning approach for financial document analysis can enhance Agentic-Quant's fundamentals analyst agent with better earnings report comprehension. The instruction dataset construction methodology is applicable to training Agentic-Quant's specialized agents.

### 7.3 FinGPT: Open-Source Financial Large Language Models

*(See Section 2.3 for full details)*

**Additional RAG relevance:** FinGPT's automatic data curation pipeline for financial data addresses the same data acquisition challenges that Agentic-Quant faces when implementing RAG for real-time market data retrieval.

---

## 8. Sentiment Analysis for Financial Markets

This section reviews news and social media sentiment analysis for trading, relevant to Agentic-Quant's news analyst agent.

### 8.1 Enhanced Financial Sentiment Analysis and Trading Strategy Development Using Large Language Models

- **Authors:** Kemal Kirtac, Guido Germano
- **Year:** 2024
- **Venue:** WASSA 2024 (14th Workshop on Computational Approaches to Subjectivity, Sentiment, & Social Media Analysis), Bangkok, Thailand
- **Link:** [ACL Anthology](https://aclanthology.org/2024.wassa-1.1/)

**Summary:** This study compares multiple LLMs (OPT, BERT, FinBERT, LLAMA 3, RoBERTa) for financial sentiment analysis on 965,375 U.S. financial news articles (2010–2023). The GPT-3-based OPT model achieves 74.4% accuracy in predicting stock market returns, with an OPT-based self-financing trading strategy yielding a Sharpe ratio of 3.05 and 355% gains (August 2021–July 2023), far outperforming dictionary-based methods (Sharpe ratio 1.23).

**Relevance to Agentic-Quant:** Provides empirical evidence for LLM superiority over traditional sentiment methods, validating the use of LLMs in Agentic-Quant's news analyst agent. The model comparison results inform the choice of LLM backbone for sentiment analysis tasks.

### 8.2 FinSoSent: Advancing Financial Market Sentiment Analysis through Pretrained Large Language Models

- **Authors:** Josiel Delgadillo, Johnson Kinyua, Charles Mutigwe
- **Year:** 2024
- **Venue:** Big Data and Cognitive Computing, Vol. 8, Issue 8, Article 87 (MDPI)
- **DOI:** [10.3390/bdcc8080087](https://doi.org/10.3390/bdcc8080087)

**Summary:** FinSoSent is a domain-specific LLM pretrained on financial news and fine-tuned on financial social media corpora from StockTwits and X (Twitter). Through over 860 experiments with different hyperparameters, FinSoSent demonstrates state-of-the-art performance in financial sentiment analysis, outperforming existing models. Ensemble experiments combining FinSoSent with other models show slight additional improvements through majority voting.

**Relevance to Agentic-Quant:** FinSoSent's domain-specific pretraining approach can be adopted for Agentic-Quant's news analyst agent. The multi-platform data coverage (news + social media) aligns with Agentic-Quant's goal of comprehensive market sentiment analysis.

### 8.3 Modeling News Interactions and Influence for Financial Market Prediction (FININ)

*(See Section 5.3 for full details)*

**Additional sentiment relevance:** FININ's finding that traditional sentiment analysis has limitations in extracting predictive power from news motivates Agentic-Quant's approach of using more sophisticated LLM reasoning beyond simple sentiment scoring.

---

## 9. Summary and Research Gaps

### Key Findings Across the Literature

| Theme | Key Insight | Implication for Agentic-Quant |
| ------- | ------------- | ------------------------------- |
| Multi-Agent Architecture | Role-based agent decomposition (analyst teams, risk management, portfolio manager) is the dominant paradigm | Validates Agentic-Quant's core design |
| LLM Reasoning | Chain-of-Thought prompting significantly improves financial analysis quality | Should be integrated into all agent reasoning pipelines |
| Agent Orchestration | Graph-based workflow engines outperform chain-based approaches for complex multi-agent coordination | LangGraph is a well-justified technology choice |
| Autonomous Trading | LLM-based agents increasingly outperform traditional RL and rule-based systems | Positions Agentic-Quant at the frontier of trading system design |
| Explainability | Post-hoc methods (SHAP, LIME) and mechanistic interpretability are emerging standards | Critical for Agentic-Quant's decision-flow visualization |
| Human Oversight | Iterative human-AI collaboration yields better results than full automation | Supports Agentic-Quant's human-in-the-loop design |
| RAG Integration | RAG + CoT reduces hallucination and improves factual accuracy in financial analysis | Should be a core component of analyst agents |
| Sentiment Analysis | LLMs significantly outperform traditional NLP methods for financial sentiment | Validates using LLM-powered news analysis agents |

### Identified Research Gaps

1. **Limited integration of multi-agent coordination with decision visualization:** Most existing systems focus on either agent collaboration OR explainability, but not both simultaneously. Agentic-Quant's combination of multi-agent reasoning with decision-flow visualization addresses this gap.

2. **Lack of standardized evaluation benchmarks for multi-agent financial systems:** While individual components have benchmarks, end-to-end evaluation of multi-agent financial systems remains ad-hoc.

3. **Insufficient study of human-in-the-loop mechanisms in multi-agent financial settings:** Alpha-GPT 2.0 demonstrates HITL for single-agent systems, but HITL integration with multi-agent orchestration is under-explored.

4. **Limited real-time deployment studies:** Most papers evaluate on historical backtesting; real-time deployment with live market data remains rare.

5. **Cross-market generalization:** Most studies focus on U.S. equities; generalization to other markets (Hong Kong, China A-shares, crypto) is under-studied.

---

## 10. References

[1] Y. Xiao, E. Sun, D. Luo, and W. Wang, "TradingAgents: Multi-Agents LLM Financial Trading Framework," *arXiv preprint arXiv:2412.20138*, 2024.

[2] Y. Yu et al., "FinCon: A Synthesized LLM Multi-Agent System with Conceptual Verbal Reinforcement for Enhanced Financial Decision Making," in *Proc. NeurIPS 2024*, 2024.

[3] F. Tian, F. D. Salim, and H. Xue, "TradingGroup: A Multi-Agent Trading System with Self-Reflection and Data-Synthesis," *arXiv preprint arXiv:2508.17565*, 2025.

[4] Y. Yu et al., "FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design," *arXiv preprint arXiv:2311.13743*, 2023.

[5] H. Yang et al., "FinRobot: An Open-Source AI Agent Platform for Financial Applications using Large Language Models," *arXiv preprint arXiv:2405.14767*, 2024.

[6] G. Fatouros, K. Metaxas, J. Soldatos, and D. Kyriazis, "Can Large Language Models Beat Wall Street? Evaluating GPT-4's Impact on Financial Decision-Making with MarketSenseAI," *Neural Computing and Applications*, Springer, 2024. DOI: 10.1007/s00521-024-10613-4.

[7] S. Wu et al., "BloombergGPT: A Large Language Model for Finance," *arXiv preprint arXiv:2303.17564*, 2023.

[8] H. Yang, X.-Y. Liu, and C. D. Wang, "FinGPT: Open-Source Financial Large Language Models," in *FinLLM Workshop @ IJCAI 2023*, 2023.

[9] W. Fu, "The New Quant: A Survey of Large Language Models in Financial Prediction and Trading," *arXiv preprint arXiv:2510.05533*, 2025.

[10] Q. Zhang et al., "AGORA: Unifying Language Agent Algorithms with Graph-based Orchestration Engine for Reproducible Agent Research," in *Proc. ACL 2025 (System Demonstrations)*, Vienna, Austria, 2025. DOI: 10.18653/v1/2025.acl-demo.11.

[11] W. Zhang et al., "A Multimodal Foundation Agent for Financial Trading: Tool-Augmented, Diversified, and Generalist," in *Proc. KDD 2024*, Barcelona, Spain, 2024. DOI: 10.1145/3637528.3671801.

[12] Y. Dong et al., "Large Language Model Agents in Finance: A Survey Bridging Research, Practice, and Real-World Deployment," in *Findings of EMNLP 2025*, Suzhou, China, 2025.

[13] N. Pippas, E. A. Ludvig, and C. Turkay, "The Evolution of Reinforcement Learning in Quantitative Finance: A Survey," *ACM Computing Surveys*, vol. 57, no. 11, 2025. DOI: 10.1145/3733714.

[14] A. de la Rica Escudero, E. C. Garrido-Merchan, and M. Coronado-Vaca, "Explainable Post Hoc Portfolio Management Financial Policy of a Deep Reinforcement Learning Agent," *PLOS ONE*, 2024. DOI: 10.1371/journal.pone.0315528.

[15] H. Tatsat and A. Shater, "Beyond the Black Box: Interpretability of LLMs in Finance," *arXiv preprint arXiv:2505.24650*, 2025.

[16] M. Wang, S. B. Cohen, and T. Ma, "Modeling News Interactions and Influence for Financial Market Prediction," in *Findings of EMNLP 2024*, 2024. DOI: 10.18653/v1/2024.findings-emnlp.189.

[17] H. Yuan, S. Wang, and J. Guo, "Alpha-GPT 2.0: Human-in-the-Loop AI for Quantitative Investment," *arXiv preprint arXiv:2402.09746*, 2024.

[18] X. Li et al., "AlphaFin: Benchmarking Financial Analysis with Retrieval-Augmented Stock-Chain Framework," in *Proc. LREC-COLING 2024*, Torino, Italy, 2024.

[19] V.-D. Le, H.-T. To, and T.-C. Bui, "RAG-IT: Retrieval-Augmented Instruction Tuning for Automated Financial Analysis," *arXiv preprint arXiv:2412.08179*, 2024.

[20] K. Kirtac and G. Germano, "Enhanced Financial Sentiment Analysis and Trading Strategy Development Using Large Language Models," in *Proc. WASSA 2024*, Bangkok, Thailand, 2024.

[21] J. Delgadillo, J. Kinyua, and C. Mutigwe, "FinSoSent: Advancing Financial Market Sentiment Analysis through Pretrained Large Language Models," *Big Data and Cognitive Computing*, vol. 8, no. 8, art. 87, 2024. DOI: 10.3390/bdcc8080087.

---

*Note: All papers listed in this review have been verified through web searches on arXiv, Google Scholar, ACL Anthology, ACM Digital Library, and Springer Nature. DOIs are provided where available and have been confirmed to resolve to the correct publications. Some preprints may have been updated or published in venues not yet reflected in this review.*
