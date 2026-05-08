"""TargetRecon MCP server — drug-target intelligence tools for Claude Code."""
from __future__ import annotations

import json
from mcp.server.fastmcp import FastMCP

from targetrecon.agent_chat import (
    _tool_search_target,
    _tool_get_top_ligands,
    _tool_get_pdb_structures,
    _tool_get_protein_interactions,
    _tool_search_compound,
    _tool_run_python,
)

mcp = FastMCP(
    "targetrecon",
    instructions=(
        "You are a specialized AI assistant embedded in TargetRecon, a drug-target intelligence platform used by medicinal chemists and drug discovery scientists.\n\n"
        "You have access to real-time tools that query UniProt, PDB, AlphaFold, ChEMBL, and STRING-DB, as well as cheminformatics tools powered by RDKit (scaffold analysis, drug-likeness, similarity search). ALWAYS use tools to get data — never generate, estimate, or recall numbers, properties, structures, or analysis results from your training knowledge. Every number in your response must come from a tool result.\n\n"
        "Guidelines:\n"
        "- Use **bold** for gene names, `code` for IDs (UniProt, PDB, ChEMBL), and tables for comparisons\n"
        "- After tool results, provide expert drug discovery interpretation: what the data means clinically, structurally, or for lead optimization\n"
        "- When comparing targets, run search_target for each target first, then use run_python to build the comparison table\n"
        "- If the user explicitly asks about a protein target (not a compound), run search_target — do NOT proactively run search_target for targets discovered incidentally from search_compound results\n"
        "- For any molecular computation (properties, scaffolds, fingerprints, similarity, clustering), always use run_python with RDKit — never estimate from SMILES or training knowledge\n"
        "- For file listing, use run_python with os.listdir('.') to see session files\n"
        "- To filter raw bioactivity records (per-assay, not per-compound), use get_top_ligands with raw_records=true\n"
        "- NEVER generate, guess, recall, or invent any numbers — every value must come directly from a tool result or run_python output\n"
        "- For plots, correlations, custom statistics, fingerprint clustering, similarity matrices, or any analysis not covered by other tools — silently call run_python without telling the user; never ask them to run a script themselves\n"
        "- When creating plots, always save as PNG using a bare filename (e.g. plt.savefig('plot.png')) — files are saved to $PWD/tmp. Always call plt.tight_layout() before savefig. For heatmaps use a large enough figure (e.g. figsize=(10,8)) and rotate x-axis labels (plt.xticks(rotation=45, ha='right')) to prevent label overlap.\n"
        "- If run_python returns an error, fix the script and call run_python again immediately — never tell the user there was an error, just fix and retry silently\n"
        "- Be concise but scientifically rigorous; use bullet points for findings\n"
        "- Suggest follow-up analyses the user might not have considered"
    ),
)

# Per-server session state — shared across all tool calls in one MCP session
_report_cache: dict = {}
_MCP_SID = "mcp"


def _fmt(result: dict) -> str:
    result.pop("_action_links", None)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def search_target(
    query: str,
    min_pchembl: float | None = None,
    max_pdb_resolution: float = 4.0,
    max_bioactivities: int = 1000,
) -> str:
    """Run full drug-target intelligence search for a protein.

    Fetches UniProt annotation (function, GO terms, diseases, subcellular location),
    PDB crystal structures, AlphaFold model, ChEMBL bioactivities, ligand summaries,
    and STRING-DB protein interactions. Results are cached for follow-up tool calls.

    Args:
        query: Gene name (EGFR, BRAF), UniProt accession (P00533), or ChEMBL ID (CHEMBL203)
        min_pchembl: Minimum pChEMBL potency filter (7.0 = 100 nM cutoff)
        max_pdb_resolution: Maximum PDB resolution in Angstroms (default 4.0)
        max_bioactivities: Max ChEMBL bioactivity records (default 1000, 0 = unlimited)
    """
    inputs = {
        "query": query,
        "min_pchembl": min_pchembl,
        "max_pdb_resolution": max_pdb_resolution,
        "max_bioactivities": max_bioactivities or 1000,
    }
    result = await _tool_search_target(inputs, _report_cache)
    return _fmt(result)


@mcp.tool()
async def get_top_ligands(
    query: str,
    top_n: int = 10,
    min_pchembl: float | None = None,
    max_pchembl: float | None = None,
    activity_type: str | None = None,
    source: str = "all",
    raw_records: bool = False,
) -> str:
    """Return ligands or raw bioactivity records for a cached target.

    Default (raw_records=False): deduplicated ligands sorted by pChEMBL.
    Raw mode (raw_records=True): per-assay records with statistics — use for
    potency distribution analysis. Requires search_target to be called first.

    Args:
        query: Target gene name or ID (must be cached via search_target)
        top_n: Number of results (default 10, max 50)
        min_pchembl: Minimum pChEMBL filter
        max_pchembl: Maximum pChEMBL filter (raw_records mode only)
        activity_type: IC50, Ki, Kd, EC50, etc.
        source: ChEMBL or all
        raw_records: If true, return raw per-assay records with statistics
    """
    inputs = {
        "query": query,
        "top_n": top_n,
        "min_pchembl": min_pchembl,
        "max_pchembl": max_pchembl,
        "activity_type": activity_type,
        "source": source,
        "raw_records": raw_records,
    }
    result = await _tool_get_top_ligands(inputs, _report_cache)
    return _fmt(result)


@mcp.tool()
async def get_pdb_structures(
    query: str,
    method: str = "all",
    max_resolution: float | None = None,
    with_ligands_only: bool = False,
) -> str:
    """Return PDB crystal structures for a cached target.

    Shows resolution, experimental method, deposition date, and bound ligands.
    Requires search_target to be called first.

    Args:
        query: Target gene name or ID (must be cached)
        method: X-RAY DIFFRACTION, ELECTRON MICROSCOPY, SOLUTION NMR, or all
        max_resolution: Maximum resolution in Angstroms
        with_ligands_only: Only return structures with bound ligands
    """
    inputs = {
        "query": query,
        "method": method,
        "max_resolution": max_resolution,
        "with_ligands_only": with_ligands_only,
    }
    result = await _tool_get_pdb_structures(inputs, _report_cache)
    return _fmt(result)


@mcp.tool()
async def get_protein_interactions(
    query: str,
    min_score: float = 0.7,
    top_n: int = 10,
) -> str:
    """Return STRING-DB protein-protein interaction partners for a cached target.

    Includes combined confidence scores. Useful for pathway and off-target analysis.
    Requires search_target to be called first.

    Args:
        query: Target gene name or ID (must be cached)
        min_score: Minimum STRING confidence score 0-1 (default 0.7)
        top_n: Number of top interaction partners to return
    """
    inputs = {"query": query, "min_score": min_score, "top_n": top_n}
    result = await _tool_get_protein_interactions(inputs, _report_cache)
    return _fmt(result)


@mcp.tool()
async def search_compound(
    query: str,
    mode: str = "auto",
) -> str:
    """Search ChEMBL for a compound and retrieve all targets it has been tested against.

    Use for reverse lookups: 'What targets does erlotinib hit?'

    Args:
        query: Compound name (erlotinib), ChEMBL ID (CHEMBL553), or SMILES string
        mode: name, chembl_id, smiles, or auto (default: auto-detect)
    """
    inputs = {"query": query, "mode": mode}
    result = await _tool_search_compound(inputs, _report_cache)
    return _fmt(result)


@mcp.tool()
async def run_python(
    query: str | None,
    script: str,
    description: str,
) -> str:
    """Execute a Python script for custom cheminformatics or data analysis.

    Use for: Murcko scaffold decomposition, drug-likeness properties (MW/LogP/TPSA/Ro5),
    Morgan fingerprint similarity search, target comparison, file listing (os.listdir('.')),
    plots (saved as PNG to working directory), and any custom analysis.

    Pre-injected variables: target (str), ligands (list of dicts with smiles/name/chembl_id/
    pchembl/activity_type/value_nM/num_assays/sources), bioactivities (list of dicts).
    Available packages: rdkit, pandas, numpy, scipy, matplotlib.

    Args:
        query: Target gene name or ID (cached via search_target). Optional — omit for pure compound/cheminformatics scripts that don't need target data.
        script: Complete Python script. Use print() to output results. Save plots/files as bare
                filenames e.g. plt.savefig('plot.png') — files are saved to $PWD/tmp (or
                $TARGETRECON_WORKDIR if set) so they appear in your working directory.
                Always call plt.tight_layout() before savefig.
        description: One-line description of what this script does
    """
    inputs = {
        "query": query,
        "script": script,
        "description": description,
        "__sid__": _MCP_SID,
    }
    result = await _tool_run_python(inputs, _report_cache)
    return _fmt(result)


if __name__ == "__main__":
    mcp.run()
