"""troxy CLI — mock subcommands."""

import json as _json
import sys

import click

from troxy.core.db import init_db
from troxy.cli.utils import _resolve_db, _apply_no_color


@click.group("mock")
def mock_group():
    """Manage mock rules."""


@mock_group.command("add")
@click.option("--db", default=None, help="Database path")
@click.option("-d", "--domain", default=None, help="Domain to match")
@click.option("-p", "--path", "path_pattern", default=None, help="Path pattern to match")
@click.option("-m", "--method", default=None, help="HTTP method to match")
@click.option("-s", "--status", "status_code", default=200, type=int, help="Response status code")
@click.option("--header", "headers", multiple=True, help="Response header (Key: Value)")
@click.option("--body", "response_body", default=None, help="Response body")
def mock_add_cmd(db, domain, path_pattern, method, status_code, headers, response_body):
    """Add a mock rule."""
    from troxy.core.mock import add_mock_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    response_headers = None
    if headers:
        hdict = {}
        for h in headers:
            if ":" in h:
                k, v = h.split(":", 1)
                hdict[k.strip()] = v.strip()
        response_headers = _json.dumps(hdict)
    rule_id = add_mock_rule(
        db_path,
        domain=domain,
        path_pattern=path_pattern,
        method=method,
        status_code=status_code,
        response_headers=response_headers,
        response_body=response_body,
    )
    click.echo(f"Mock rule {rule_id} added.")


@mock_group.command("list")
@click.option("--db", default=None, help="Database path")
@click.option("--no-color", is_flag=True, help="Disable color output")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def mock_list_cmd(db, no_color, as_json):
    """List mock rules."""
    from troxy.core.mock import list_mock_rules
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    rules = list_mock_rules(db_path)
    if as_json:
        click.echo(_json.dumps(rules, indent=2, ensure_ascii=False, default=str))
        return
    if not rules:
        click.echo("No mock rules.")
        return
    for r in rules:
        status_label = "enabled" if r["enabled"] else "disabled"
        click.echo(f"[{r['id']}] {r['domain']} {r['path_pattern']} "
                   f"-> {r['status_code']} ({status_label})")


@mock_group.command("remove")
@click.option("--db", default=None, help="Database path")
@click.argument("rule_id", type=int)
def mock_remove_cmd(db, rule_id):
    """Remove a mock rule."""
    from troxy.core.mock import remove_mock_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    remove_mock_rule(db_path, rule_id)
    click.echo(f"Mock rule {rule_id} removed.")


@mock_group.command("disable")
@click.option("--db", default=None, help="Database path")
@click.argument("rule_id", type=int)
def mock_disable_cmd(db, rule_id):
    """Disable a mock rule."""
    from troxy.core.mock import toggle_mock_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    toggle_mock_rule(db_path, rule_id, enabled=False)
    click.echo(f"Mock rule {rule_id} disabled.")


@mock_group.command("enable")
@click.option("--db", default=None, help="Database path")
@click.argument("rule_id", type=int)
def mock_enable_cmd(db, rule_id):
    """Enable a mock rule."""
    from troxy.core.mock import toggle_mock_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    toggle_mock_rule(db_path, rule_id, enabled=True)
    click.echo(f"Mock rule {rule_id} enabled.")


@mock_group.command("from-flow")
@click.option("--db", default=None, help="Database path")
@click.argument("flow_id", type=int)
@click.option("-s", "--status", "status_code", default=None, type=int,
              help="Override response status code")
def mock_from_flow_cmd(db, flow_id, status_code):
    """Create a mock rule from an existing flow."""
    from troxy.core.mock import mock_from_flow
    db_path = _resolve_db(db)
    init_db(db_path)
    try:
        rule_id = mock_from_flow(db_path, flow_id, status_code=status_code)
        click.echo(f"Mock rule {rule_id} created from flow {flow_id}.")
    except ValueError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
