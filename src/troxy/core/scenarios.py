"""Scenario (scripted) mock rules — sequential step responses."""

import json
import time

from troxy.core.db import get_connection
from troxy.core.query import get_flow


def _validate_steps(steps: list[dict]) -> None:
    """Raise ValueError if steps list is invalid."""
    if not steps:
        raise ValueError("steps must be a non-empty list")
    for i, step in enumerate(steps):
        if "status_code" not in step:
            raise ValueError(
                f"Step {i} is missing required 'status_code' field: {step!r}"
            )


def add_scenario(
    db_path: str,
    *,
    domain: str | None = None,
    path_pattern: str | None = None,
    method: str | None = None,
    name: str | None = None,
    steps: list[dict],
    loop: bool = False,
) -> int:
    """Add a scenario mock rule. Returns the new scenario ID.

    Raises ValueError if steps is empty, any step lacks status_code,
    or name already exists.
    """
    _validate_steps(steps)
    conn = get_connection(db_path)
    try:
        if name:
            existing = conn.execute(
                "SELECT id FROM mock_scenarios WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                raise ValueError(
                    f"Scenario with name {name!r} already exists (id={existing[0]})"
                )
        cursor = conn.execute(
            """INSERT INTO mock_scenarios
               (name, domain, path_pattern, method, steps, loop, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, domain, path_pattern, method, json.dumps(steps), int(loop), time.time()),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_scenarios(db_path: str, *, enabled_only: bool = False) -> list[dict]:
    """List all scenario mock rules, with computed total_steps field."""
    conn = get_connection(db_path)
    sql = "SELECT * FROM mock_scenarios"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id"
    rows = conn.execute(sql).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["total_steps"] = len(json.loads(d["steps"]))
        result.append(d)
    return result


def remove_scenario(db_path: str, scenario_id: int) -> None:
    """Delete a scenario mock rule."""
    conn = get_connection(db_path)
    conn.execute("DELETE FROM mock_scenarios WHERE id = ?", (scenario_id,))
    conn.commit()
    conn.close()


def toggle_scenario(db_path: str, scenario_id: int, *, enabled: bool) -> None:
    """Enable or disable a scenario mock rule."""
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE mock_scenarios SET enabled = ? WHERE id = ?",
        (int(enabled), scenario_id),
    )
    conn.commit()
    conn.close()


def reset_scenario(db_path: str, scenario_id: int) -> None:
    """Reset current_step to 0."""
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE mock_scenarios SET current_step = 0 WHERE id = ?", (scenario_id,)
    )
    conn.commit()
    conn.close()


def resolve_scenario_ref(db_path: str, ref: str | int) -> int:
    """Resolve a scenario reference (int ID or string name) to scenario ID.

    Raises ValueError if not found.
    """
    conn = get_connection(db_path)
    try:
        scenario_id = int(ref)
        row = conn.execute(
            "SELECT id FROM mock_scenarios WHERE id = ?", (scenario_id,)
        ).fetchone()
    except (ValueError, TypeError):
        row = conn.execute(
            "SELECT id FROM mock_scenarios WHERE name = ?", (str(ref),)
        ).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Scenario {ref!r} not found (pass ID or name)")
    return row[0]


def scenario_from_flows(
    db_path: str,
    flow_ids: list[int],
    *,
    name: str | None = None,
    loop: bool = False,
) -> int:
    """Create a scenario from multiple flows' responses in order.

    Raises ValueError if any flow_id is not found.
    """
    steps = []
    for fid in flow_ids:
        flow = get_flow(db_path, fid)
        if not flow:
            raise ValueError(f"Flow {fid} not found")
        step: dict = {"status_code": flow["status_code"]}
        if flow.get("response_body"):
            step["response_body"] = flow["response_body"]
        if flow.get("response_headers"):
            raw = flow["response_headers"]
            try:
                headers = json.loads(raw) if isinstance(raw, str) else raw
                if headers:
                    step["response_headers"] = headers
            except (json.JSONDecodeError, TypeError):
                pass
        steps.append(step)
    return add_scenario(db_path, name=name, loop=loop, steps=steps)


def get_and_advance_step(db_path: str, scenario_id: int) -> dict | None:
    """Return current step data and atomically advance to the next step.

    Returns None if scenario not found or disabled.
    Uses BEGIN IMMEDIATE to prevent lost updates under concurrent access.
    """
    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT current_step, steps, loop FROM mock_scenarios "
            "WHERE id = ? AND enabled = 1",
            (scenario_id,),
        ).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return None
        steps = json.loads(row["steps"])
        idx = row["current_step"]
        step = steps[idx]
        total = len(steps)
        if row["loop"]:
            next_idx = (idx + 1) % total
        else:
            next_idx = min(idx + 1, total - 1)
        conn.execute(
            "UPDATE mock_scenarios SET current_step = ? WHERE id = ?",
            (next_idx, scenario_id),
        )
        conn.execute("COMMIT")
        return step
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
