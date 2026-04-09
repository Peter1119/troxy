#!/usr/bin/env python3
"""Run evaluation scenarios against troxy tools."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import yaml
except ImportError:
    print("pyyaml required: uv add pyyaml --dev")
    sys.exit(1)

from troxy.mcp.server import TOOLS


def run_scenario(scenario_path: str, fixtures_dir: str) -> dict:
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)

    fixture_path = os.path.join(fixtures_dir, scenario["fixture"])
    if not os.path.exists(fixture_path):
        return {"name": scenario["name"], "passed": False, "error": "Fixture not found"}

    results = []
    for step in scenario.get("steps", []):
        tool_name = step["tool"]
        args = step.get("args", {})

        if tool_name not in TOOLS:
            results.append({"tool": tool_name, "error": f"Unknown tool"})
            continue

        output = TOOLS[tool_name]["handler"](fixture_path, args)
        step_result = {"tool": tool_name, "output_length": len(output)}

        if "expect_count" in step:
            data = json.loads(output)
            if isinstance(data, list):
                step_result["count"] = len(data)
                step_result["count_ok"] = len(data) == step["expect_count"]

        if "expect_contains" in step:
            step_result["contains_ok"] = step["expect_contains"] in output

        if "expect_count_gte" in step:
            data = json.loads(output)
            if isinstance(data, list):
                step_result["count"] = len(data)
                step_result["count_ok"] = len(data) >= step["expect_count_gte"]

        results.append(step_result)

    all_passed = all(
        r.get("count_ok", True) and r.get("contains_ok", True) and "error" not in r
        for r in results
    )

    return {"name": scenario["name"], "passed": all_passed, "steps": results}


def main():
    eval_dir = Path(__file__).parent
    fixtures_dir = eval_dir / "fixtures"
    scenarios_dir = eval_dir / "scenarios"

    if not fixtures_dir.exists():
        print("Run eval/fixtures/create_fixtures.py first.")
        sys.exit(1)

    total = 0
    passed = 0
    for scenario_file in sorted(scenarios_dir.glob("*.yaml")):
        result = run_scenario(str(scenario_file), str(fixtures_dir))
        total += 1
        status = "PASS" if result["passed"] else "FAIL"
        if result["passed"]:
            passed += 1
        print(f"  [{status}] {result['name']}")
        if not result["passed"]:
            for step in result.get("steps", []):
                if not step.get("count_ok", True) or not step.get("contains_ok", True) or "error" in step:
                    print(f"         {step}")

    print(f"\n{passed}/{total} scenarios passed.")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
