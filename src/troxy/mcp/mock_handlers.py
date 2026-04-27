"""MCP mock and scenario handler functions."""

import json

from troxy.core.db import get_connection
from troxy.core.mock import add_mock_rule, list_mock_rules, remove_mock_rule, toggle_mock_rule, mock_from_flow


def _normalize_sequence_steps(raw_steps: list) -> list[dict]:
    """Normalize MCP sequence steps to internal scenarios step format."""
    result = []
    for step in raw_steps:
        ns: dict = {"status_code": step["status_code"]}
        body = step.get("body") or step.get("response_body")
        if body is not None:
            ns["response_body"] = body
        raw_headers = step.get("headers") or step.get("response_headers")
        if raw_headers is not None:
            ns["response_headers"] = (
                json.loads(raw_headers) if isinstance(raw_headers, str) else raw_headers
            )
        result.append(ns)
    return result


def handle_mock_add(db_path: str, args: dict) -> str:
    # Accept both "sequence" (Designer DX) and "script" (legacy)
    sequence = args.get("sequence") or args.get("script")
    if sequence:
        from troxy.core.scenarios import add_scenario
        steps = _normalize_sequence_steps(sequence)
        rule_id = add_scenario(
            db_path,
            domain=args.get("domain"),
            path_pattern=args.get("path_pattern"),
            method=args.get("method"),
            name=args.get("name"),
            steps=steps,
            loop=bool(args.get("loop", False)),
        )
        return json.dumps({"rule_id": rule_id, "type": "scenario"})
    rule_id = add_mock_rule(
        db_path,
        domain=args.get("domain"),
        path_pattern=args.get("path_pattern"),
        method=args.get("method"),
        status_code=args.get("status_code", 200),
        response_headers=args.get("headers"),
        response_body=args.get("body"),
        name=args.get("name"),
    )
    return json.dumps({"rule_id": rule_id})


def handle_mock_list(db_path: str, args: dict) -> str:
    from troxy.core.scenarios import list_scenarios
    rules = list_mock_rules(db_path)
    for r in rules:
        r["sequence_steps"] = None
        r["script_steps"] = None  # alias for backward compat
        r["current_step"] = None
    scenarios = list_scenarios(db_path)
    scenario_items = []
    for s in scenarios:
        scenario_items.append({
            "id": s["id"],
            "name": s.get("name"),
            "domain": s.get("domain"),
            "path_pattern": s.get("path_pattern"),
            "method": s.get("method"),
            "enabled": s["enabled"],
            "created_at": s["created_at"],
            "status_code": None,
            "response_body": None,
            "response_headers": None,
            "sequence_steps": s["total_steps"],
            "script_steps": s["total_steps"],  # alias for backward compat
            "current_step": s["current_step"],
            "loop": s["loop"],
        })
    combined = rules + scenario_items
    combined.sort(key=lambda x: x.get("created_at") or 0)
    return json.dumps(combined, indent=2, default=str)


def handle_mock_remove(db_path: str, args: dict) -> str:
    remove_mock_rule(db_path, args["id"])
    return json.dumps({"removed": args["id"]})


def handle_mock_toggle(db_path: str, args: dict) -> str:
    toggle_mock_rule(db_path, args["id"], enabled=args.get("enabled", True))
    return json.dumps({"toggled": args["id"]})


def handle_mock_from_flow(db_path: str, args: dict) -> str:
    rule_id = mock_from_flow(
        db_path,
        args["flow_id"],
        status_code=args.get("status_code"),
        response_body=args.get("body"),
        response_headers=args.get("headers"),
        name=args.get("name"),
    )
    enabled = args.get("enabled", True)
    if enabled is False:
        toggle_mock_rule(db_path, rule_id, enabled=False)
    return json.dumps({"rule_id": rule_id})


def handle_mock_reset(db_path: str, args: dict) -> str:
    from troxy.core.scenarios import reset_scenario, resolve_scenario_ref
    ref = args.get("id") or args.get("name")
    if ref is None:
        return json.dumps({"error": "provide 'id' or 'name'"})
    try:
        sid = resolve_scenario_ref(db_path, ref)
        reset_scenario(db_path, sid)
        return json.dumps({"reset": sid})
    except ValueError as e:
        return json.dumps({"error": str(e)})


def handle_mock_update(db_path: str, args: dict) -> str:
    """Partial update for a mock rule or scenario rule."""
    ref = args.get("id") or args.get("name")
    if ref is None:
        return json.dumps({"error": "provide 'id' or 'name'"})

    # Try scenario first
    from troxy.core.scenarios import resolve_scenario_ref
    try:
        sid = resolve_scenario_ref(db_path, ref)
    except ValueError:
        sid = None

    if sid is not None:
        return _update_scenario(db_path, sid, args)
    # Fall back to mock_rule
    try:
        rule_id = int(ref)
    except (ValueError, TypeError):
        from troxy.core.mock import resolve_mock_ref
        try:
            rule_id = resolve_mock_ref(db_path, ref)
        except ValueError as e:
            return json.dumps({"error": str(e)})
    return _update_mock_rule(db_path, rule_id, args)


def _update_scenario(db_path: str, scenario_id: int, args: dict) -> str:
    conn = get_connection(db_path)
    updates = []
    params = []
    raw_seq = args.get("sequence") or args.get("script")
    if raw_seq is not None:
        steps = _normalize_sequence_steps(raw_seq)
        updates.append("steps = ?")
        params.append(json.dumps(steps))
        updates.append("current_step = 0")
    if "loop" in args:
        updates.append("loop = ?")
        params.append(int(args["loop"]))
    if "enabled" in args:
        updates.append("enabled = ?")
        params.append(int(args["enabled"]))
    if "new_name" in args:
        updates.append("name = ?")
        params.append(args["new_name"])
    if updates:
        params.append(scenario_id)
        conn.execute(f"UPDATE mock_scenarios SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    conn.close()
    return json.dumps({"updated": scenario_id, "type": "scenario"})


def _update_mock_rule(db_path: str, rule_id: int, args: dict) -> str:
    conn = get_connection(db_path)
    updates = []
    params = []
    if "status_code" in args:
        updates.append("status_code = ?")
        params.append(args["status_code"])
    if "body" in args:
        updates.append("response_body = ?")
        params.append(args["body"])
    if "headers" in args:
        updates.append("response_headers = ?")
        params.append(args["headers"])
    if "enabled" in args:
        updates.append("enabled = ?")
        params.append(int(args["enabled"]))
    if "new_name" in args:
        updates.append("name = ?")
        params.append(args["new_name"])
    if updates:
        params.append(rule_id)
        conn.execute(f"UPDATE mock_rules SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    conn.close()
    return json.dumps({"updated": rule_id, "type": "rule"})
