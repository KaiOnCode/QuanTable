# Backtest OOS Robustness Follow-up

状态：future work only。当前 Goal 只证明 deterministic frozen replay 的引擎保真与可复现性；它不评估、也不通过 out-of-sample robustness。

在任何实现前，必须启动一个独立的冻结 planning session，并在该 session 中明确记录并冻结：

- universe、training/validation/test 时间切分，以及禁止信息泄漏的 walk-forward protocol；
- parameter grid、selection objective、交易成本/容量假设与接受阈值；
- bootstrap/Monte Carlo 的数据生成方式、样本数、seed 与可重放 artifact；
- sensitivity 维度、报告格式，以及 Deflated Sharpe Ratio (DSR) 和 Probability of Backtest Overfitting (PBO) 的计算定义；
- 对不足样本、零交易、失败运行与 experimental agent output 的排除/标注规则。

只有上述计划、数据版本和验收标准被冻结后，后续工作才可以实现或报告：walk-forward、parameter sensitivity、bootstrap/Monte Carlo、DSR 或 PBO。

本 Goal 明确不创建这些能力的 API、module、optimizer、partial report 或“已通过”标签。任何现有 deterministic hash、单窗口结果、零交易结果或 agent experiment 都不能替代 OOS 评估。
