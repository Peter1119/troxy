"""troxy CLI — shared utilities."""

import os

import click

from troxy.core.db import default_db_path


def _parse_since(since: str | None) -> float | None:
    """Parse since string like '5m', '1h', '90s', '2d' to seconds.

    Raises click.BadParameter on invalid input (was silent None before).
    """
    if not since:
        return None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if since[-1] in units:
        try:
            value = float(since[:-1])
            if value < 0:
                raise ValueError("negative")
            return value * units[since[-1]]
        except ValueError:
            pass
    raise click.BadParameter(
        f"Invalid time format: {since!r}. Use Ns, Nm, Nh, or Nd (e.g. 30s, 5m, 1h, 2d)."
    )


def _common_options(f):
    """Shared --db and --no-color options for subcommands."""
    f = click.option("--db", default=None, help="Database path")(f)
    f = click.option("--no-color", is_flag=True, help="Disable color output")(f)
    return f


def _resolve_db(db: str | None) -> str:
    return db or default_db_path()


def _apply_no_color(no_color: bool) -> None:
    if no_color:
        os.environ["NO_COLOR"] = "1"
