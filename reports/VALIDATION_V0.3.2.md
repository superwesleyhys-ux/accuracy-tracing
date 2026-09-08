# FactCircuit v0.3.2：发布验收记录

生成时间：2026-09-08T18:09:24.801140+00:00

本报告描述当前源码的离线测试、安装烟测，以及 historical-2023 真实命题语料的合同审计。没有调用新闻检索服务或模型 API，没有执行 live staged/monolithic A/B，也没有测得真实准确率。

## 运行结果

- 测试：273 项；失败 0；错误 0；跳过 0。
- 核心 wheel 安装检查：passed。
- 仓库目录外首次运行检查：passed；含完整示例、缩小预算示例和旧命令兼容。
- staged 分阶段运行时：源码 checkout 导入/CLI 帮助烟测；本次没有执行模型推理。

| 测试组 | 数量 |
|---|---:|
| test_brand | 4 |
| test_comparison | 6 |
| test_evaluation | 19 |
| test_harness | 25 |
| test_historical_compare | 22 |
| test_local_model | 10 |
| test_local_replay | 5 |
| test_provenance | 26 |
| test_quickstart | 4 |
| test_release | 4 |
| test_repair | 48 |
| test_semantic_adapter | 18 |
| test_staged_semantic | 58 |
| test_target_plan_grounding | 24 |

## Historical-2023 合同审计

- 状态：`passed`；语料：8 条 2023 年真实世界命题。
- 标签：true 4 条 / false 4 条。
- 推理证据截止：`2024-12-31T23:59:59Z`。
- 审计产物：`reports/historical-2023-audit-v0.3.2.json`。

这 8 条语料使用声明为官方来源的命题与定论材料；本次检查覆盖时间窗、角色隔离、内部内容哈希、gold 隔离及冻结校验和等合同。它不会重新抓取并独立认证远端原件，也没有运行任何模型，因此本节不能单独产生 staged/monolithic live A/B 或准确率结论。

## 已发布的两题模型对比（独立运行）

仓库另行保留了一次已完成的 frozen post-hoc 两题对比。它不属于上述离线验收命令；原始 calls、retrieval、trace、配置、状态和评分均随报告公开。

| 指标 | Original monolithic | PR1 staged |
|---|---:|---:|
| Accuracy | 1/2 (50%) | 2/2 (100%) |
| True recall | 0/1 | 1/1 |
| False recall | 1/1 | 1/1 |
| Abstention | 1/2 | 0/2 |
| Model calls | 6 | 33 |
| Total tokens | 15,693 | 49,804 |

本次两题中，staged 回环找回了 original 弃权的 Virgin Galactic true 命题；两者都正确否定了 Lucid 产量命题。这只是早期工程信号，不是总体准确率估计：样本仅两题且为事后选择，PR1 使用了 5.5 倍调用和 3.17 倍总 token，因此不能把差异单独归因于拆分提示词。

单独的 Lucid `full_evidence_once` 诊断未计入两题分母。Original 返回正确的 false；staged 以 `StagedSemanticError: conclusive probe cannot carry a stop reason` 结束。因此整次 run 状态为 `has_errors`，虽然四个主臂结果都完成且 `scores.json` 为 `scored`。该失败作为 staged 路径仍有脆弱性的证据被完整保留。

详见 `reports/historical-2023-pilot2-v3-live-001/SUMMARY.md` 和同目录的 `scores.json`。

## 双回环演示

- 检索轮次：3。
- 不同材料版本：4。
- 分解调用：6。
- 验证调用：3。
- 演示状态：`original_material_located` / `contradicted` / `complete`。

演示使用程序化 fixture 标注，只验证路由、顺序、预算、状态与审计合同。它不是通用语义模型实测，也不证明拆分提示词提升了准确率。

## 指标算术样例

以下分数属于四条故意含错的手写预测，只检查评分器，不代表项目或任何模型的性能。

| 指标 | 手写样例计算值 |
|---|---:|
| VP | 0.500000 |
| FR | 0.500000 |
| TR | 0.500000 |
| SR | 0.666667 |
| EN | 0.666667 |
| CA | 0.656250 |
| HFAR | 0.500000 |

## 仍需外部验证

- 真实新闻检索适配器，以及对 historical-2023 远端来源原件的独立重抓取/认证。
- 独立人工 gold、隐藏且按事件/时间隔离的真实新闻测试集。
- 预注册、更大规模且按事件/时间隔离的 staged/monolithic live A/B。
- 等调用、等 token 与分阶段消融，用于区分提示词结构和额外计算量。
- 修复已公开的 staged full-evidence 控制项错误。
- 生产并发、网络故障、成本和长期稳定性测试。
