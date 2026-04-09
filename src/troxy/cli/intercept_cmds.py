"""troxy CLI — intercept subcommands."""

import json as _json
import sys

import click

from troxy.core.db import init_db
from troxy.cli.utils import _resolve_db, _apply_no_color


@click.group("intercept")
def intercept_group():
    """Manage intercept rules."""


@intercept_group.command("add")
@click.option("--db", default=None, help="Database path")
@click.option("-d", "--domain", default=None, help="Domain to match")
@click.option("-p", "--path", "path_pattern", default=None, help="Path pattern to match")
@click.option("-m", "--method", default=None, help="HTTP method to match")
def intercept_add_cmd(db, domain, path_pattern, method):
    """Add an intercept rule."""
    from troxy.core.intercept import add_intercept_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    rule_id = add_intercept_rule(db_path, domain=domain, path_pattern=path_pattern, method=method)
    click.echo(f"Intercept rule {rule_id} added.")


@intercept_group.command("list")
@click.option("--db", default=None, help="Database path")
@click.option("--no-color", is_flag=True, help="Disable color output")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def intercept_list_cmd(db, no_color, as_json):
    """List intercept rules."""
    from troxy.core.intercept import list_intercept_rules
    _apply_no_color(no_color)
    db_path = _resolve_db(db)
    init_db(db_path)
    rules = list_intercept_rules(db_path)
    if as_json:
        click.echo(_json.dumps(rules, indent=2, ensure_ascii=False, default=str))
        return
    if not rules:
        click.echo("No intercept rules.")
        return
    for r in rules:
        status_label = "enabled" if r["enabled"] else "disabled"
        method_label = r["method"] or "*"
        click.echo(f"[{r['id']}] {r['domain']} {r['path_pattern']} "
                   f"method={method_label} ({status_label})")


@intercept_group.command("remove")
@click.option("--db", default=None, help="Database path")
@click.argument("rule_id", type=int)
def intercept_remove_cmd(db, rule_id):
    """Remove an intercept rule."""
    from troxy.core.intercept import remove_intercept_rule
    db_path = _resolve_db(db)
    init_db(db_path)
    remove_intercept_rule(db_path, rule_id)
    click.echo(f"Intercept rule {rule_id} removed.")
