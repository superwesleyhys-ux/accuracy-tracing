"""Reproduce the offline release checks and write explicitly scoped reports."""
from collections import Counter
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from newsverify.comparison import compare
from newsverify.evaluation import evaluate
from newsverify.trace_demo import run_demo


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    groups = Counter(test.id().split(".")[0] for test in flatten(suite))
    transcript = io.StringIO()
    result = unittest.TextTestRunner(stream=transcript, verbosity=2).run(suite)
    (reports / "test-output-v0.2.txt").write_text(transcript.getvalue(), encoding="utf-8")
    read = lambda name: json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
    trace = run_demo()
    metrics = evaluate(read("evaluation_gold.json"), read("evaluation_predictions.json"))
    comparison = compare(read("evaluation_gold.json"), read("comparison_baseline.json"),
                         read("comparison_candidate.json"), bootstrap_samples=100, seed=0)
    for name, payload in (("trace-demo-v0.2.json", trace), ("all-metrics-v0.2.json", metrics),
                          ("comparison-v0.2.json", comparison)):
        (reports / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    packaging_path = reports / "package-smoke-v0.2.json"
    packaging = json.loads(packaging_path.read_text()) if packaging_path.exists() else {"status": "not_run"}
    validation = {
        "release": "0.2.0", "generated_at": datetime.now(timezone.utc).isoformat(),
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "successful": result.wasSuccessful(), "test_groups": dict(groups),
        "metric_contracts_checked": ["VP", "FR", "TR", "SR", "EN", "CA", "HFAR"],
        "trace_demo_usage": trace["usage"], "trace_demo_provenance": trace["provenance_status"],
        "trace_demo_fact_status": trace["fact_status"], "trace_demo_stop": trace["stop_reason"],
        "packaging": packaging, "all_data_synthetic": True,
        "live_news_requests": 0, "model_api_calls": 0, "realworld_accuracy_measured": False,
        "external_project_move": "not_performed_no_interface", "external_repository_publish": False,
    }
    (reports / "validation-v0.2.json").write_text(json.dumps(validation, indent=2) + "\n")
    lines = ["# Accuracy Tracing v0.2：实际验收记录", "", f"生成时间：{validation['generated_at']}", "",
             "本报告只描述实际运行的离线测试。没有调用新闻检索服务或模型 API，没有测得真实新闻准确率。", "",
             "## 运行结果", "", f"- 测试：{result.testsRun} 项；失败 {len(result.failures)}；错误 {len(result.errors)}；跳过 {len(result.skipped)}。",
             f"- 安装包检查：{packaging['status']}。", "",
             "| 测试组 | 数量 |", "|---|---:|"]
    lines += [f"| {name} | {count} |" for name, count in sorted(groups.items())]
    lines += ["", "七项主指标均与独立手算样例对照；边界测试覆盖零分母、缺少概率、漏样本、重复样本、错误来源路径和未审定证据。",
              "", "## 双回环演示", "", f"- 检索轮次：{trace['usage']['rounds']}。",
              f"- 不同材料版本：{trace['usage']['unique_versions']}。",
              f"- 分解调用：{trace['usage']['decomposition_calls']}，包括受到新材料影响的旧版本重开。",
              f"- 验证调用：{trace['usage']['verification_calls']}。",
              f"- 演示状态：`{trace['provenance_status']}` / `{trace['fact_status']}` / `{trace['stop_reason']}`。",
              "", "第三轮材料由验证缺口触发，先进入分解器再参与验证。语义结论来自演示标注，不是通用模型的实测判断。",
              "", "## 指标算术样例", "", "以下分数属于四条故意含错的手写预测，只检查评分器，不代表项目或任何模型的性能。", "",
              "| 指标 | 手写样例计算值 |", "|---|---:|"]
    lines += [f"| {key} | {metrics['metrics'][key]['value']:.6f} |" for key in validation["metric_contracts_checked"]]
    lines += ["", "比例和概率质量范围为0到1；HFAR越低越好。综合指数使用暂定权重，不能作为发布通过证明。",
              "", "## 比较工具", "", "两组相同手写预测，在相同声明预算下得到可计算指标差值0。运行100次、随机种子0的事件聚类bootstrap；分母为0的重采样会使相应区间不可计算。没有进行真实模型消融实验。",
              "", "## 尚未完成", "", "- 真实新闻检索适配器及通用语义模型接入。",
              "- 严格历史语义隔离、真实token/延迟计量和运行记录的独立检查。",
              "- 来源图到固定目标评估schema的通用导出。",
              "- 人工审定、隐藏且按事件/时间分离的真实新闻测试集。",
              "- 等预算四变体实验、上线阈值选择及生产稳定性测试。",
              "- 截图中应用项目的聊天迁移：当前没有对应接口，未执行。",
              "", "源码、完整执行清单和该报告已经形成可交接版本；这些未完成项在执行清单中有接口与验收要求。", ""]
    (reports / "VALIDATION_V0.2.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
