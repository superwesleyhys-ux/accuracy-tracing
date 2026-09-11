"""Reproduce the current offline release checks without rewriting old reports."""
from collections import Counter
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factcircuit import __version__
from factcircuit.comparison import compare
from factcircuit.evaluation import evaluate
from factcircuit.trace_demo import run_demo
from scripts.smoke_first_run import smoke_first_run


TAG = "v" + __version__
HISTORICAL_DATA = ROOT / "experiments" / "historical-2023"
HISTORICAL_AUDIT_NAME = f"historical-2023-audit-{TAG}.json"
HISTORICAL_CASE_COUNT = 8


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def _run(command, *, cwd=ROOT):
    return subprocess.run(
        [str(item) for item in command], cwd=cwd, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def package_smoke():
    """Build the real wheel, install it in isolation, and test source-only stages."""
    result = {
        "status": "failed",
        "version": __version__,
        "distribution_scope": "core CLI/trace engine in wheel; staged experiments from source checkout",
    }
    with tempfile.TemporaryDirectory(prefix="factcircuit-release-") as temporary:
        temporary_path = Path(temporary)
        wheelhouse = temporary_path / "wheelhouse"
        wheelhouse.mkdir()
        built = _run([
            sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
            "--disable-pip-version-check", "--wheel-dir", wheelhouse,
        ])
        if built.returncode:
            result["failure_stage"] = "wheel_build"
            result["output_tail"] = built.stdout[-2000:]
            return result
        wheels = sorted(wheelhouse.glob(
            f"factcircuit-{__version__}-*.whl"))
        if len(wheels) != 1:
            result["failure_stage"] = "wheel_selection"
            result["wheel_count"] = len(wheels)
            return result
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
        required = {
            "factcircuit/__init__.py", "factcircuit/cli.py",
            "factcircuit/decisions.py", "factcircuit/provenance.py",
            "factcircuit/retrieval.py",
            "newsverify/__init__.py", "newsverify/cli.py",
            "newsverify/decisions.py", "newsverify/provenance.py",
            "newsverify/retrieval.py",
        }
        missing = sorted(required - names)
        if missing:
            result["failure_stage"] = "wheel_contents"
            result["missing"] = missing
            return result

        environment = temporary_path / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python = (environment / "Scripts" / "python.exe"
                  if sys.platform == "win32" else environment / "bin" / "python")
        installed = _run([
            python, "-m", "pip", "install", "--no-deps",
            "--disable-pip-version-check", wheel,
        ], cwd=temporary_path)
        if installed.returncode:
            result["failure_stage"] = "wheel_install"
            result["output_tail"] = installed.stdout[-2000:]
            return result
        imported = _run([
            python, "-c",
            ("import factcircuit, newsverify; "
             "assert factcircuit.__version__ == newsverify.__version__ == "
             + repr(__version__)),
        ], cwd=temporary_path)
        demo = _run([python, "-m", "factcircuit", "demo"], cwd=temporary_path)
        source_staged = _run([
            sys.executable, "experiments/loop_compare.py", "--help",
        ])
        if imported.returncode or demo.returncode or source_staged.returncode:
            result["failure_stage"] = "installed_or_source_smoke"
            result["output_tail"] = (
                imported.stdout + demo.stdout + source_staged.stdout)[-2000:]
            return result
        result.update({
            "status": "passed",
            "wheel": wheel.name,
            "wheel_required_files": sorted(required),
            "installed_version": __version__,
            "installed_core_demo": "passed",
            "source_staged_help": "passed",
        })
    return result


def historical_benchmark_audit(output_path):
    """Run and persist the frozen historical-2023 contract audit.

    This invokes the public CLI with the four fixed benchmark artifacts.  The
    release wrapper adds scope metadata so the resulting report cannot be
    mistaken for a live model comparison or an accuracy measurement.
    """
    command = [
        sys.executable, "experiments/historical_compare.py", "audit",
        "--inputs", HISTORICAL_DATA / "inputs.json",
        "--sources", HISTORICAL_DATA / "sources.json",
        "--gold", HISTORICAL_DATA / "gold.json",
        "--freeze", HISTORICAL_DATA / "freeze.json",
    ]
    completed = _run(command)
    try:
        payload = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        payload = {
            "status": "failed",
            "failure_stage": "historical_contract_audit",
            "output_tail": completed.stdout[-2000:],
        }
    if completed.returncode:
        payload.update({
            "status": "failed",
            "failure_stage": "historical_contract_audit",
            "return_code": completed.returncode,
        })
    elif (payload.get("status") != "passed"
          or payload.get("case_count") != HISTORICAL_CASE_COUNT):
        payload.update({
            "status": "failed",
            "failure_stage": "historical_contract_expectation",
        })

    passed = payload.get("status") == "passed"
    payload.update({
        "corpus_description": (
            "8 real-world 2023 propositions with declared official-source "
            "claim and outcome evidence"
        ),
        "corpus_synthetic": False,
        "release_validation_scope": {
            "contract_audit_performed": passed,
            "remote_artifacts_independently_authenticated": False,
            "live_model_ab_performed": False,
            "accuracy_measured": False,
        },
    })
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    return payload


def main():
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    groups = Counter(test.id().split(".")[0] for test in flatten(suite))
    transcript = io.StringIO()
    test_result = unittest.TextTestRunner(
        stream=transcript, verbosity=2).run(suite)
    (reports / f"test-output-{TAG}.txt").write_text(
        transcript.getvalue(), encoding="utf-8")

    read = lambda name: json.loads(
        (ROOT / "examples" / name).read_text(encoding="utf-8"))
    trace = run_demo()
    metrics = evaluate(
        read("evaluation_gold.json"), read("evaluation_predictions.json"))
    comparison = compare(
        read("evaluation_gold.json"), read("comparison_baseline.json"),
        read("comparison_candidate.json"), bootstrap_samples=100, seed=0)
    for name, payload in (
            (f"trace-demo-{TAG}.json", trace),
            (f"all-metrics-{TAG}.json", metrics),
            (f"comparison-{TAG}.json", comparison)):
        (reports / name).write_text(json.dumps(
            payload, ensure_ascii=False, indent=2,
            allow_nan=False) + "\n", encoding="utf-8")

    packaging = package_smoke()
    (reports / f"package-smoke-{TAG}.json").write_text(
        json.dumps(packaging, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    first_run = smoke_first_run()
    (reports / f"first-run-{TAG}.json").write_text(
        json.dumps(first_run, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    historical_audit = historical_benchmark_audit(
        reports / HISTORICAL_AUDIT_NAME)
    validation = {
        "release": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tests_run": test_result.testsRun,
        "failures": len(test_result.failures),
        "errors": len(test_result.errors),
        "skipped": len(test_result.skipped),
        "successful": test_result.wasSuccessful(),
        "test_groups": dict(groups),
        "metric_contracts_checked": ["VP", "FR", "TR", "SR", "EN", "CA", "HFAR"],
        "trace_demo_usage": trace["usage"],
        "trace_demo_provenance": trace["provenance_status"],
        "trace_demo_fact_status": trace["fact_status"],
        "trace_demo_stop": trace["stop_reason"],
        "packaging": packaging,
        "installed_first_run": first_run,
        "all_data_synthetic": False,
        "offline_demo_data_synthetic": True,
        "historical_2023_audit": {
            "status": historical_audit["status"],
            "artifact": f"reports/{HISTORICAL_AUDIT_NAME}",
            "benchmark_id": historical_audit.get("benchmark_id"),
            "case_count": historical_audit.get("case_count"),
            "claim_window": historical_audit.get("claim_window"),
            "evidence_cutoff": historical_audit.get("evidence_cutoff"),
            "labels": historical_audit.get("labels"),
            "corpus_synthetic": False,
            "declared_official_source_evidence": True,
            "contract_audit_performed": (
                historical_audit["status"] == "passed"),
            "remote_artifacts_independently_authenticated": False,
        },
        "live_news_requests": 0,
        "model_api_calls": 0,
        "staged_model_run_performed": False,
        "live_model_ab_performed": False,
        "realworld_accuracy_measured": False,
    }
    (reports / f"validation-{TAG}.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    lines = [
        f"# FactCircuit {TAG}：发布验收记录", "",
        f"生成时间：{validation['generated_at']}", "",
        "本报告描述当前源码的离线测试、安装烟测，以及 historical-2023 真实命题语料的合同审计。没有调用新闻检索服务或模型 API，没有执行 live staged/monolithic A/B，也没有测得真实准确率。", "",
        "## 运行结果", "",
        f"- 测试：{test_result.testsRun} 项；失败 {len(test_result.failures)}；错误 {len(test_result.errors)}；跳过 {len(test_result.skipped)}。",
        f"- 核心 wheel 安装检查：{packaging['status']}。",
        f"- 仓库目录外首次运行检查：{first_run['status']}；含完整示例、缩小预算示例和旧命令兼容。",
        "- staged 分阶段运行时：源码 checkout 导入/CLI 帮助烟测；本次没有执行模型推理。", "",
        "| 测试组 | 数量 |", "|---|---:|",
    ]
    lines += [f"| {name} | {count} |" for name, count in sorted(groups.items())]
    lines += [
        "", "## Historical-2023 合同审计", "",
        f"- 状态：`{historical_audit['status']}`；语料：{historical_audit.get('case_count', 0)} 条 2023 年真实世界命题。",
        f"- 标签：true {historical_audit.get('labels', {}).get('true', 0)} 条 / false {historical_audit.get('labels', {}).get('false', 0)} 条。",
        f"- 推理证据截止：`{historical_audit.get('evidence_cutoff', 'unknown')}`。",
        f"- 审计产物：`reports/{HISTORICAL_AUDIT_NAME}`。", "",
        "这 8 条语料使用声明为官方来源的命题与定论材料；本次检查覆盖时间窗、角色隔离、内部内容哈希、gold 隔离及冻结校验和等合同。它不会重新抓取并独立认证远端原件，也没有运行任何模型，因此本节不能单独产生 staged/monolithic live A/B 或准确率结论。",
        "", "## 已发布的两题模型对比（独立运行）", "",
        "仓库另行保留了一次已完成的 frozen post-hoc 两题对比。它不属于上述离线验收命令；原始 calls、retrieval、trace、配置、状态和评分均随报告公开。", "",
        "| 指标 | Original monolithic | PR1 staged |", "|---|---:|---:|",
        "| Accuracy | 1/2 (50%) | 2/2 (100%) |",
        "| True recall | 0/1 | 1/1 |",
        "| False recall | 1/1 | 1/1 |",
        "| Abstention | 1/2 | 0/2 |",
        "| Model calls | 6 | 33 |",
        "| Total tokens | 15,693 | 49,804 |", "",
        "本次两题中，staged 回环找回了 original 弃权的 Virgin Galactic true 命题；两者都正确否定了 Lucid 产量命题。这只是早期工程信号，不是总体准确率估计：样本仅两题且为事后选择，PR1 使用了 5.5 倍调用和 3.17 倍总 token，因此不能把差异单独归因于拆分提示词。", "",
        "单独的 Lucid `full_evidence_once` 诊断未计入两题分母。Original 返回正确的 false；staged 以 `StagedSemanticError: conclusive probe cannot carry a stop reason` 结束。因此整次 run 状态为 `has_errors`，虽然四个主臂结果都完成且 `scores.json` 为 `scored`。该失败作为 staged 路径仍有脆弱性的证据被完整保留。", "",
        "详见 `reports/historical-2023-pilot2-v3-live-001/SUMMARY.md` 和同目录的 `scores.json`。",
        "", "## 双回环演示", "",
        f"- 检索轮次：{trace['usage']['rounds']}。",
        f"- 不同材料版本：{trace['usage']['unique_versions']}。",
        f"- 分解调用：{trace['usage']['decomposition_calls']}。",
        f"- 验证调用：{trace['usage']['verification_calls']}。",
        f"- 演示状态：`{trace['provenance_status']}` / `{trace['fact_status']}` / `{trace['stop_reason']}`。",
        "", "演示使用程序化 fixture 标注，只验证路由、顺序、预算、状态与审计合同。它不是通用语义模型实测，也不证明拆分提示词提升了准确率。",
        "", "## 指标算术样例", "",
        "以下分数属于四条故意含错的手写预测，只检查评分器，不代表项目或任何模型的性能。", "",
        "| 指标 | 手写样例计算值 |", "|---|---:|",
    ]
    lines += [
        f"| {key} | {metrics['metrics'][key]['value']:.6f} |"
        for key in validation["metric_contracts_checked"]
    ]
    lines += [
        "", "## 仍需外部验证", "",
        "- 真实新闻检索适配器，以及对 historical-2023 远端来源原件的独立重抓取/认证。",
        "- 独立人工 gold、隐藏且按事件/时间隔离的真实新闻测试集。",
        "- 预注册、更大规模且按事件/时间隔离的 staged/monolithic live A/B。",
        "- 等调用、等 token 与分阶段消融，用于区分提示词结构和额外计算量。",
        "- 修复已公开的 staged full-evidence 控制项错误。",
        "- 生产并发、网络故障、成本和长期稳定性测试。", "",
    ]
    (reports / f"VALIDATION_{TAG.upper()}.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    passed = (test_result.wasSuccessful()
              and packaging["status"] == "passed"
              and first_run["status"] == "passed"
              and historical_audit["status"] == "passed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
