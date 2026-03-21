"""Command-line interface for TargetRecon.

Usage::

    $ targetrecon EGFR
    $ targetrecon P00533 --format html json sdf --output ./reports/
    $ targetrecon BRAF --max-resolution 3.0 --min-pchembl 6.0
    $ targetrecon ui                    # Launch web interface
    $ targetrecon ui --port 8502        # Custom port
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click


class BioactivitiesType(click.ParamType):
    """Accepts a positive integer or 'all' (meaning no limit → None)."""
    name = "INT|all"

    def convert(self, value, param, ctx):
        if value is None:
            return value
        if str(value).lower() == "all":
            return None
        try:
            v = int(value)
            if v <= 0:
                self.fail(f"'{value}' must be a positive integer or 'all'", param, ctx)
            return v
        except (ValueError, TypeError):
            self.fail(f"'{value}' is not a valid integer or 'all'", param, ctx)

from targetrecon import __version__


class TargetReconCLI(click.Group):
    """Custom group that treats unknown subcommands as target queries.

    This allows both ``targetrecon EGFR`` (direct query) and
    ``targetrecon ui`` (launch web interface) to work.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # If first arg is not a known command, treat it as a query → run
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            args = ["run"] + args
        # If no args, show help
        if not args:
            args = ["--help"]
        return super().parse_args(ctx, args)


@click.group(cls=TargetReconCLI, invoke_without_command=True)
@click.version_option(__version__, "-v", "--version")
@click.pass_context
def main(ctx: click.Context) -> None:
    """TargetRecon — Drug target intelligence in one command.

    \b
    Run a reconnaissance:
      targetrecon EGFR
      targetrecon P00533 --format html json sdf

    \b
    Launch the web interface:
      targetrecon ui
      targetrecon ui --port 8502
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.argument("query")
@click.option(
    "-f",
    "--format",
    "formats",
    multiple=True,
    type=click.Choice(["json", "html", "sdf"], case_sensitive=False),
    default=["html", "json", "sdf"],
    help="Output formats (default: html json).",
)
@click.option(
    "-o",
    "--output",
    "output_dir",
    type=click.Path(),
    default=".",
    help="Output directory (default: current directory).",
)
@click.option(
    "--max-resolution",
    type=float,
    default=4.0,
    show_default=True,
    help="Max PDB resolution in Å.",
)
@click.option(
    "--max-bioactivities",
    type=BioactivitiesType(),
    default=1000,
    show_default=True,
    help="Max bioactivity records from ChEMBL (default: 1000). Use 'all' for no limit.",
)
@click.option(
    "--min-pchembl",
    type=float,
    default=None,
    help="Minimum pChEMBL value filter.",
)
@click.option(
    "--top-ligands",
    type=int,
    default=20,
    show_default=True,
    help="Number of top ligands for SDF export.",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    default=False,
    help="Suppress progress messages.",
)
def run(
    query: str,
    formats: tuple[str, ...],
    output_dir: str,
    max_resolution: float,
    max_bioactivities: int | None,
    min_pchembl: float | None,
    top_ligands: int,
    quiet: bool,
) -> None:
    """Run target reconnaissance.

    QUERY can be a gene name (EGFR), UniProt accession (P00533),
    or ChEMBL target ID (CHEMBL203).

    \b
    Examples:
      targetrecon EGFR
      targetrecon P00533 --format html json sdf
      targetrecon BRAF --min-pchembl 7.0 --max-resolution 2.5
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console(stderr=True)

    # Banner
    if not quiet:
        banner = Text()
        banner.append("TargetRecon", style="bold cyan")
        banner.append(f" v{__version__}", style="dim")
        banner.append("\nDrug target intelligence aggregator", style="dim")
        console.print(Panel(banner, border_style="cyan", padding=(0, 2)))
        console.print()

    # Run
    from targetrecon.core import recon_async, save_html, save_json, save_sdf

    try:
        report = asyncio.run(
            recon_async(
                query,
                max_pdb_resolution=max_resolution,
                max_bioactivities=max_bioactivities,
                min_pchembl=min_pchembl,
                verbose=not quiet,
            )
        )
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    # Check if we got any data
    if report.uniprot is None:
        console.print(f"\n[red]Could not resolve '{query}' to a valid protein target.[/red]")
        console.print("Try a gene name (EGFR), UniProt accession (P00533), or ChEMBL ID (CHEMBL203).")
        sys.exit(1)

    # Output
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    gene = report.uniprot.gene_name or report.query if report.uniprot else report.query
    base = gene.replace(" ", "_")

    saved: list[str] = []
    for fmt in formats:
        if fmt.lower() == "json":
            p = save_json(report, out / f"{base}_report.json")
            saved.append(str(p))
        elif fmt.lower() == "html":
            p = save_html(report, out / f"{base}_report.html")
            saved.append(str(p))
        elif fmt.lower() == "sdf":
            p = save_sdf(report, out / f"{base}_top_ligands.sdf", top_n=top_ligands)
            saved.append(str(p))

    if not quiet:
        console.print()
        console.print("[green]Report saved:[/green]")
        for s in saved:
            console.print(f"  -> {s}")
        console.print()


@main.command()
@click.option("--port", type=int, default=8501, help="Port for the web server.")
@click.option("--no-browser", is_flag=True, default=False, help="Don't auto-open browser.")
def ui(port: int, no_browser: bool) -> None:
    """Launch the interactive web interface.

    \b
    Examples:
      targetrecon ui
      targetrecon ui --port 8502
      targetrecon ui --no-browser
    """
    import subprocess

    from rich.console import Console

    console = Console(stderr=True)
    console.print(f"[cyan]Launching TargetRecon UI on port {port}...[/cyan]")

    app_path = Path(__file__).parent / "app.py"

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    if no_browser:
        cmd.append("--server.headless=true")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        console.print("\n[dim]Shutting down...[/dim]")
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)


@main.command()
@click.option("--port", type=int, default=5000, show_default=True, help="Port to listen on.")
@click.option("--host", default="0.0.0.0", show_default=True, help="Host to bind.")
@click.option("--debug", is_flag=True, default=False, help="Enable Flask debug mode.")
def serve(port: int, host: str, debug: bool) -> None:
    """Launch the Flask web interface (recommended over 'ui').

    \b
    Examples:
      targetrecon serve
      targetrecon serve --port 8080
    """
    from rich.console import Console
    console = Console(stderr=True)
    console.print(f"[cyan]TargetRecon web app → http://localhost:{port}[/cyan]")

    from targetrecon.webapp import run
    run(host=host, port=port, debug=debug)


@main.command()
@click.argument("targets", nargs=-1, required=False)
@click.option("-i", "--input", "targets_file", type=click.Path(exists=True),
              help="Text file with one target per line (# comments and blank lines ignored).")
@click.option("-o", "--output", "output_dir", type=click.Path(), default="./batch_reports",
              show_default=True, help="Output directory.")
@click.option("-f", "--format", "formats", multiple=True,
              type=click.Choice(["json", "html", "sdf"], case_sensitive=False),
              default=["html", "json", "sdf"], help="Output formats.")
@click.option("--max-resolution", type=float, default=4.0, show_default=True)
@click.option("--max-bioactivities", type=BioactivitiesType(), default=1000, show_default=True,
              help="Max bioactivity records from ChEMBL (default: 1000). Use 'all' for no limit.")
@click.option("--min-pchembl", type=float, default=None)
@click.option("--top-ligands", type=int, default=20, show_default=True)
@click.option("--skip-errors", is_flag=True, default=False,
              help="Continue batch if a single target fails.")
@click.option("-q", "--quiet", is_flag=True, default=False)
def batch(
    targets: tuple[str, ...],
    targets_file: str | None,
    output_dir: str,
    formats: tuple[str, ...],
    max_resolution: float,
    max_bioactivities: int | None,
    min_pchembl: float | None,
    top_ligands: int,
    skip_errors: bool,
    quiet: bool,
) -> None:
    """Run recon on multiple targets and save reports for each.

    Targets can be passed directly or read from a file (one per line).
    Lines starting with # are treated as comments.

    \b
    Examples:
      targetrecon batch EGFR BRAF CDK2
      targetrecon batch -i targets.txt
      targetrecon batch -i targets.txt -f html -f sdf --min-pchembl 6.0
      targetrecon batch EGFR BRAF --skip-errors
    """
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console(stderr=True)

    # Collect queries
    queries: list[str] = list(targets)
    if targets_file:
        for line in Path(targets_file).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                queries.append(line)

    if not queries:
        console.print("[red]No targets provided. Pass targets directly or use --file.[/red]")
        sys.exit(1)

    queries = list(dict.fromkeys(queries))  # deduplicate, preserve order

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not quiet:
        console.print(f"\n[bold cyan]TargetRecon batch[/bold cyan] — {len(queries)} target(s) → [dim]{out}[/dim]\n")

    from targetrecon.core import recon_async, save_html, save_json, save_sdf

    results = []
    for i, q in enumerate(queries, 1):
        if not quiet:
            console.print(f"[cyan][{i}/{len(queries)}][/cyan] {q} ...", end=" ")
        try:
            report = asyncio.run(recon_async(
                q, max_pdb_resolution=max_resolution,
                max_bioactivities=max_bioactivities,
                min_pchembl=min_pchembl,
                verbose=False,
            ))
            if report.uniprot is None:
                raise ValueError(f"Could not resolve '{q}' to a protein target")

            gene = report.uniprot.gene_name or q
            base = gene.replace(" ", "_")
            saved = []
            for fmt in formats:
                if fmt == "json":
                    saved.append(str(save_json(report, out / f"{base}_report.json")))
                elif fmt == "html":
                    saved.append(str(save_html(report, out / f"{base}_report.html")))
                elif fmt == "sdf":
                    saved.append(str(save_sdf(report, out / f"{base}_ligands.sdf", top_n=top_ligands)))

            results.append((q, gene, report.num_pdb_structures, report.num_bioactivities,
                            report.num_unique_ligands, "✓", None))
            if not quiet:
                console.print(f"[green]✓[/green]  {report.num_bioactivities} bioactivities · {report.num_unique_ligands} ligands")

        except Exception as exc:
            results.append((q, "—", 0, 0, 0, "✗", str(exc)))
            if not quiet:
                console.print(f"[red]✗  {exc}[/red]")
            if not skip_errors:
                sys.exit(1)

    if not quiet:
        tbl = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        tbl.add_column("Query"); tbl.add_column("Gene"); tbl.add_column("Structures", justify="right")
        tbl.add_column("Bioactivities", justify="right"); tbl.add_column("Ligands", justify="right")
        tbl.add_column("Status", justify="center")
        for q, gene, pdb, bio, lig, status, err in results:
            style = "green" if status == "✓" else "red"
            tbl.add_row(q, gene, str(pdb), str(bio), str(lig), f"[{style}]{status}[/{style}]")
        console.print()
        console.print(tbl)
        console.print(f"[dim]Reports saved to: {out.resolve()}[/dim]\n")

    failed = sum(1 for r in results if r[5] == "✗")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
