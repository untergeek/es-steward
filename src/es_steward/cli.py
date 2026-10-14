"""es-steward command line."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import click
from elastic_transport import ApiError, TransportError

from es_steward import JOURNAL, __version__
from es_steward.services import (
    NoIndicesError,
    alias_prefix_filters,
    run_alias,
    run_allocation,
    run_close,
    run_cluster_routing,
    run_cold2frozen,
    run_create_index,
    run_delete,
    run_delete_snapshots,
    run_forcemerge,
    run_index_settings,
    run_open,
    run_promote,
    run_redact,
    run_reindex,
    run_replicas,
    run_restore,
    run_rollover,
    run_show,
    run_shrink,
    run_snapshot,
)

T = TypeVar("T")


def cli_guard(fn: Callable[[], T]) -> T:
    """Run an action; map expected failures to ClickException."""
    try:
        return fn()
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except ApiError as exc:
        raise click.ClickException(str(exc)) from exc
    except TransportError as exc:
        raise click.ClickException("elasticsearch unavailable") from exc


def cli_done(status: str, line: str) -> None:
    """Print the status line; non-COMPLETED workbooks exit 1."""
    click.echo(line)
    if status != "COMPLETED":
        raise SystemExit(1)


def cli_mutate(fn: Callable[[], T], *, empty: str = "no indices") -> T:
    """Run ``fn`` through ``cli_guard``; empty selection echoes ``empty`` and exits 1.

    Args:
        fn: Action callable (no arguments).
        empty: Stderr line when ``NoIndicesError`` is raised.

    Returns:
        Whatever ``fn`` returns after ``cli_guard``.
    """
    try:
        return cli_guard(fn)
    except NoIndicesError:
        click.echo(empty, err=True)
        raise SystemExit(1) from None


def prefix_config_dry_run(fn: Callable[..., T]) -> Callable[..., T]:
    """Attach ``--prefix``, ``--config``, and ``--dry-run`` (HEAD defaults).

    Args:
        fn: Click command function.

    Returns:
        ``fn`` with the three options registered.
    """
    fn = click.option(
        "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
    )(fn)
    fn = click.option("--config", default=None, help="YAML client config path.")(fn)
    fn = click.option("--prefix", required=True, help="Index name prefix selector.")(fn)
    return fn


@click.group()
@click.version_option(version=__version__, prog_name="es-steward")
def main() -> None:
    """Steward: Elasticsearch index hygiene."""


@main.command("journal")
def journal_cmd() -> None:
    """Print the tracking index name."""
    click.echo(JOURNAL)


@main.command("import-yaml")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
def import_yaml_cmd(path: str) -> None:
    """Print Steward filters for a Curator 8 actions YAML (one-way).

    Omitted or blank filter keys use Curator 8 defaults (opened/closed/count
    exclude=True; age/period source=name), not Steward Python model defaults.
    """
    import json

    from es_steward.yaml_import import load_actions, to_json

    try:
        payload = to_json(load_actions(path))
    except (OSError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(payload, indent=2))


@main.command("show")
@click.option("--prefix", required=True, help="Index name prefix selector.")
@click.option("--size-gt", type=float, default=None, help="Keep primary size > N GiB.")
@click.option("--config", default=None, help="YAML client config path.")
def show_cmd(prefix: str, size_gt: float | None, config: str | None) -> None:
    """Print resolved index names (selectors + optional size)."""
    for name in run_show(config, prefix, size_gt):
        click.echo(name)


@main.command("promote")
@click.option("--prefix", required=True, help="Index name prefix selector.")
@click.option("--size-gt", type=float, default=None, help="Keep primary size > N GiB.")
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def promote_cmd(
    prefix: str, size_gt: float | None, config: str | None, dry_run: bool
) -> None:
    """Advance matching ILM-managed indices one phase."""
    status, count = cli_mutate(lambda: run_promote(config, prefix, size_gt, dry_run))
    cli_done(status, f"{status} {count} indices")


@main.command("delete")
@prefix_config_dry_run
def delete_cmd(prefix: str, config: str | None, dry_run: bool) -> None:
    """Delete matching indices."""
    status, count = cli_mutate(lambda: run_delete(config, prefix, dry_run))
    cli_done(status, f"{status} {count} indices")


@main.command("close")
@prefix_config_dry_run
def close_cmd(prefix: str, config: str | None, dry_run: bool) -> None:
    """Close matching indices."""
    status, count = cli_mutate(lambda: run_close(config, prefix, dry_run))
    cli_done(status, f"{status} {count} indices")


@main.command("open")
@prefix_config_dry_run
def open_cmd(prefix: str, config: str | None, dry_run: bool) -> None:
    """Open matching indices."""
    status, count = cli_mutate(lambda: run_open(config, prefix, dry_run))
    cli_done(status, f"{status} {count} indices")


@main.command("forcemerge")
@click.option("--prefix", required=True, help="Index name prefix selector.")
@click.option(
    "--max-num-segments",
    required=True,
    type=click.IntRange(min=1),
    help="Target segments per shard.",
)
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def forcemerge_cmd(
    prefix: str, max_num_segments: int, config: str | None, dry_run: bool
) -> None:
    """Forcemerge matching indices."""
    status, count = cli_mutate(
        lambda: run_forcemerge(config, prefix, max_num_segments, dry_run)
    )
    cli_done(status, f"{status} {count} indices")


@main.command("allocation")
@click.option("--prefix", required=True, help="Index name prefix selector.")
@click.option("--key", required=True, help="Allocation attribute key.")
@click.option("--value", default=None, help="Allocation attribute value.")
@click.option(
    "--allocation-type",
    type=click.Choice(["require", "include", "exclude"], case_sensitive=True),
    default="require",
    show_default=True,
    help="Allocation filter type.",
)
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def allocation_cmd(
    prefix: str,
    key: str,
    value: str | None,
    allocation_type: str,
    config: str | None,
    dry_run: bool,
) -> None:
    """Set allocation filters on matching indices."""
    status, count = cli_mutate(
        lambda: run_allocation(config, prefix, key, dry_run, value, allocation_type)
    )
    cli_done(status, f"{status} {count} indices")


@main.command("replicas")
@click.option("--prefix", required=True, help="Index name prefix selector.")
@click.option(
    "--count",
    required=True,
    type=click.IntRange(min=0),
    help="Replica count (>= 0).",
)
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def replicas_cmd(prefix: str, count: int, config: str | None, dry_run: bool) -> None:
    """Set replica count on matching indices."""
    status, n = cli_mutate(lambda: run_replicas(config, prefix, count, dry_run))
    cli_done(status, f"{status} {n} indices")


@main.command("shrink")
@click.option("--prefix", required=True, help="Index name prefix selector.")
@click.option(
    "--shrink-node", required=True, help="Node that holds every shard before shrink."
)
@click.option(
    "--delete-after/--no-delete-after",
    default=True,
    show_default=True,
    help="Delete the source index after shrink (library default).",
)
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def shrink_cmd(
    prefix: str,
    shrink_node: str,
    delete_after: bool,
    config: str | None,
    dry_run: bool,
) -> None:
    """Shrink matching indices onto one node."""
    status, count = cli_mutate(
        lambda: run_shrink(
            config, prefix, shrink_node, dry_run, delete_after=delete_after
        )
    )
    cli_done(status, f"{status} {count} indices")


@main.command("rollover")
@click.option("--name", required=True, help="Write alias to rollover.")
@click.option("--conditions", required=True, help="Rollover conditions JSON object.")
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def rollover_cmd(name: str, conditions: str, config: str | None, dry_run: bool) -> None:
    """Rollover one write alias if conditions are met."""
    import json

    try:
        parsed = json.loads(conditions)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"invalid --conditions JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise click.ClickException("--conditions must be a JSON object")
    status, count, raw = cli_guard(lambda: run_rollover(config, name, parsed, dry_run))
    line = f"{status} {count} aliases"
    if raw is not None:
        line += f" rolled_over={str(raw['rolled_over']).lower()}"
        if "new_index" in raw:
            line += f" new_index={raw['new_index']}"
    cli_done(status, line)


@main.command("reindex")
@click.option("--prefix", required=True, help="Source index name prefix selector.")
@click.option("--dest", required=True, help="Destination index name.")
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def reindex_cmd(prefix: str, dest: str, config: str | None, dry_run: bool) -> None:
    """Reindex matching sources into dest."""
    status, count = cli_mutate(lambda: run_reindex(config, prefix, dest, dry_run))
    cli_done(status, f"{status} {count} indices")


@main.command("index-settings")
@click.option("--prefix", required=True, help="Index name prefix selector.")
@click.option("--settings", required=True, help="Index settings JSON object.")
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def index_settings_cmd(
    prefix: str, settings: str, config: str | None, dry_run: bool
) -> None:
    """Put index settings on matching indices."""
    import json

    try:
        parsed = json.loads(settings)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"invalid --settings JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise click.ClickException("--settings must be a non-empty JSON object")
    status, count = cli_mutate(
        lambda: run_index_settings(config, prefix, parsed, dry_run)
    )
    cli_done(status, f"{status} {count} indices")


@main.command("cluster-routing")
@click.option(
    "--routing-type",
    required=True,
    type=click.Choice(["allocation", "rebalance"], case_sensitive=True),
    help="allocation or rebalance.",
)
@click.option("--value", required=True, help="Type-specific enable value.")
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def cluster_routing_cmd(
    routing_type: str, value: str, config: str | None, dry_run: bool
) -> None:
    """Set transient cluster routing enable."""
    status, count = cli_guard(
        lambda: run_cluster_routing(config, routing_type, value, dry_run)
    )
    cli_done(status, f"{status} {count} cluster")


@main.command("cold2frozen")
@click.option("--prefix", required=True, help="Index name prefix selector.")
@click.option(
    "--delete-after/--no-delete-after",
    default=True,
    show_default=True,
    help="Delete the source index after mount (library default).",
)
@click.option(
    "--transfer-aliases/--no-transfer-aliases",
    default=True,
    show_default=True,
    help="Move aliases from source to the frozen mount (library default).",
)
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def cold2frozen_cmd(
    prefix: str,
    delete_after: bool,
    transfer_aliases: bool,
    config: str | None,
    dry_run: bool,
) -> None:
    """Mount matching cold indices as frozen partial mounts."""
    status, count = cli_mutate(
        lambda: run_cold2frozen(
            config,
            prefix,
            dry_run,
            delete_after=delete_after,
            transfer_aliases=transfer_aliases,
        )
    )
    cli_done(status, f"{status} {count} indices")


@main.command("create-index")
@click.option("--name", required=True, help="Index name to create.")
@click.option(
    "--ignore-existing",
    is_flag=True,
    default=False,
    help="Treat already-exists as success.",
)
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def create_index_cmd(
    name: str, ignore_existing: bool, config: str | None, dry_run: bool
) -> None:
    """Create one index."""
    status, count = cli_guard(
        lambda: run_create_index(config, name, dry_run, ignore_existing)
    )
    cli_done(status, f"{status} {count} indices")


@main.command("delete-snapshots")
@click.option("--repository", required=True, help="Snapshot repository.")
@click.option("--prefix", required=True, help="Snapshot name prefix selector.")
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def delete_snapshots_cmd(
    repository: str, prefix: str, config: str | None, dry_run: bool
) -> None:
    """Delete matching snapshots."""
    status, count = cli_mutate(
        lambda: run_delete_snapshots(config, repository, prefix, dry_run),
        empty="no snapshots",
    )
    cli_done(status, f"{status} {count} snapshots")


@main.command("snapshot")
@click.option("--repository", required=True, help="Snapshot repository.")
@click.option("--snapshot", required=True, help="Snapshot name (literal).")
@prefix_config_dry_run
def snapshot_cmd(
    repository: str, snapshot: str, prefix: str, config: str | None, dry_run: bool
) -> None:
    """Create one snapshot of matching indices."""
    status, count = cli_mutate(
        lambda: run_snapshot(config, repository, snapshot, prefix, dry_run)
    )
    cli_done(status, f"{status} {count} indices")


@main.command("restore")
@click.option("--repository", required=True, help="Snapshot repository.")
@click.option("--snapshot", required=True, help="Snapshot name (literal).")
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
def restore_cmd(
    repository: str, snapshot: str, config: str | None, dry_run: bool
) -> None:
    """Restore one snapshot (all indices)."""
    status, _ = cli_guard(lambda: run_restore(config, repository, snapshot, dry_run))
    cli_done(status, status)


@main.command("alias")
@click.option("--name", required=True, help="Alias name.")
@click.option("--add-prefix", default=None, help="Prefix of indices to add.")
@click.option("--remove-prefix", default=None, help="Prefix of indices to remove.")
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Do not call ES mutations."
)
@click.option(
    "--extra-settings",
    default=None,
    help="JSON object merged into each add action (is_write_index, filter, …).",
)
def alias_cmd(
    name: str,
    add_prefix: str | None,
    remove_prefix: str | None,
    config: str | None,
    dry_run: bool,
    extra_settings: str | None,
) -> None:
    """Add and/or remove matching indices on one alias."""
    if not add_prefix and not remove_prefix:
        raise click.ClickException("need --add-prefix and/or --remove-prefix")
    add_filters, remove_filters = alias_prefix_filters(add_prefix, remove_prefix)
    parsed_extra = None
    if extra_settings:
        import json

        try:
            parsed_extra = json.loads(extra_settings)
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"invalid --extra-settings JSON: {exc}") from exc
        if not isinstance(parsed_extra, dict):
            raise click.ClickException("--extra-settings must be a JSON object")
    status, count = cli_mutate(
        lambda: run_alias(
            config, name, add_filters, remove_filters, dry_run, parsed_extra
        )
    )
    cli_done(status, f"{status} {count} indices")


@main.command("redact")
@click.option("--prefix", required=True, help="Index name prefix selector.")
@click.option("--query", required=True, help="Query DSL as a JSON object.")
@click.option(
    "--field",
    "fields",
    multiple=True,
    required=True,
    help="Dotted field to overwrite. Repeatable.",
)
@click.option("--message", default="REDACTED", help="Replacement value.")
@click.option("--config", default=None, help="YAML client config path.")
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help="Mutate documents and journal. Default is dry-run with persist=False.",
)
def redact_cmd(
    prefix: str,
    query: str,
    fields: tuple[str, ...],
    message: str,
    config: str | None,
    execute: bool,
) -> None:
    """Overwrite matching fields on open indices (hot update_by_query)."""
    import json

    try:
        parsed = json.loads(query)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"invalid --query JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise click.ClickException("--query must be a non-empty JSON object")
    status, count, dry_run = cli_mutate(
        lambda: run_redact(config, prefix, parsed, list(fields), message, execute)
    )
    cli_done(status, f"{status} {count} indices dry_run={dry_run}")


@main.command("tui")
def tui_cmd() -> None:
    """Interactive Steward TUI (install es-steward[tui])."""
    from es_steward.tui_app import StewardApp

    StewardApp().run()
