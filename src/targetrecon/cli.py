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
      targetrecon batch --file targets.txt
      targetrecon batch --file targets.txt --format html sdf --min-pchembl 6.0
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
                min_pchembl=min_pchembl, verbose=False,
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


@main.command()
@click.argument("targets", nargs=-1, required=False)
@click.option("-i", "--input", "targets_file", type=click.Path(exists=True),
              help="Text file with one target per line.")
@click.option("-o", "--output", "output_dir", type=click.Path(), default=".",
              show_default=True, help="Output directory.")
@click.option("-f", "--format", "fmt", type=click.Choice(["sdf", "csv"], case_sensitive=False),
              default="sdf", show_default=True, help="Export format.")
@click.option("--min-pchembl", type=float, default=None, help="Min pChEMBL filter.")
@click.option("--max-nm", type=float, default=None, help="Max activity value in nM.")
@click.option("--activity-type", type=str, default=None,
              help="Filter by activity type (e.g. IC50, Ki).")
@click.option("--top", type=int, default=50, show_default=True,
              help="Max ligands per target.")
@click.option("-q", "--quiet", is_flag=True, default=False)
def export(
    targets: tuple[str, ...],
    targets_file: str | None,
    output_dir: str,
    fmt: str,
    min_pchembl: float | None,
    max_nm: float | None,
    activity_type: str | None,
    top: int,
    quiet: bool,
) -> None:
    """Export filtered ligand sets for one or more targets.

    Pulls bioactivities from ChEMBL + BindingDB, applies filters,
    and writes SDF or CSV. One file per target.

    \b
    Examples:
      targetrecon export EGFR --format sdf --min-pchembl 7.0 --top 50
      targetrecon export EGFR BRAF CDK2 --format csv --min-pchembl 6.0
      targetrecon export --file targets.txt --format sdf --max-nm 100
    """
    import csv
    from rich.console import Console
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

    queries = list(dict.fromkeys(queries))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    from targetrecon.core import recon_async, save_sdf

    for q in queries:
        if not quiet:
            console.print(f"[cyan]Fetching[/cyan] {q} ...", end=" ")
        try:
            report = asyncio.run(recon_async(q, verbose=False))
            if report.uniprot is None:
                console.print(f"[red]✗ Could not resolve '{q}'[/red]")
                continue

            gene = report.uniprot.gene_name or q
            base = gene.replace(" ", "_")

            # Filter ligands
            ligands = [l for l in report.ligand_summary if l.smiles]
            if min_pchembl is not None:
                ligands = [l for l in ligands if l.best_pchembl and l.best_pchembl >= min_pchembl]
            if max_nm is not None:
                ligands = [l for l in ligands if l.best_activity_value_nM and l.best_activity_value_nM <= max_nm]
            if activity_type:
                ligands = [l for l in ligands if l.best_activity_type.upper() == activity_type.upper()]
            ligands = ligands[:top]

            if fmt == "sdf":
                p = save_sdf(report, out / f"{base}_ligands.sdf",
                             top_n=top, min_pchembl=min_pchembl,
                             max_nm=max_nm, activity_type=activity_type)
                if not quiet:
                    console.print(f"[green]✓[/green]  {len(ligands)} ligands → {p}")
            else:
                p = out / f"{base}_ligands.csv"
                with open(p, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["smiles", "name", "chembl_id", "activity_type",
                                     "activity_nM", "pchembl", "num_assays", "sources"])
                    for l in ligands:
                        writer.writerow([l.smiles, l.name or "", l.chembl_id or "",
                                         l.best_activity_type, l.best_activity_value_nM,
                                         l.best_pchembl, l.num_assays, ",".join(l.sources)])
                if not quiet:
                    console.print(f"[green]✓[/green]  {len(ligands)} ligands → {p}")

        except Exception as exc:
            console.print(f"[red]✗ {exc}[/red]")


if __name__ == "__main__":
    main()
