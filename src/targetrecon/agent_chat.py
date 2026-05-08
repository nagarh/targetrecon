"""AI Agent: streaming Claude tool-use orchestrator for TargetRecon."""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path
from typing import Any, AsyncGenerator

import anthropic

# ── Conversation store ────────────────────────────────────────────────────────
_conversation_store: dict[str, list[dict]] = {}
_store_lock = threading.Lock()
MAX_HISTORY_MSGS = 40   # keep last 20 turns (user+assistant pairs)


def get_conversation(conv_id: str) -> list[dict]:
    with _store_lock:
        return list(_conversation_store.get(conv_id, []))


def save_turn(conv_id: str, new_messages: list[dict]) -> None:
    with _store_lock:
        if conv_id not in _conversation_store:
            _conversation_store[conv_id] = []
        _conversation_store[conv_id].extend(new_messages)
        if len(_conversation_store[conv_id]) > MAX_HISTORY_MSGS:
            _conversation_store[conv_id] = _conversation_store[conv_id][-MAX_HISTORY_MSGS:]


def clear_conversation(conv_id: str) -> None:
    with _store_lock:
        _conversation_store.pop(conv_id, None)


# ── Session working directories (for run_python file output) ──────────────────
_session_workdirs: dict[str, Path] = {}
_workdirs_lock = threading.Lock()


def get_session_workdir(sid: str) -> Path:
    """Return (creating if needed) a temp directory for this session's script output."""
    with _workdirs_lock:
        if sid not in _session_workdirs or not _session_workdirs[sid].exists():
            d = Path(tempfile.mkdtemp(prefix=f"tr_{sid[:8]}_"))
            _session_workdirs[sid] = d
        return _session_workdirs[sid]


def cleanup_session_workdir(sid: str) -> None:
    """Delete the session workdir — called when the session expires."""
    with _workdirs_lock:
        d = _session_workdirs.pop(sid, None)
    if d and d.exists():
        shutil.rmtree(d, ignore_errors=True)


# ── Tool definitions ──────────────────────────────────────────────────────────
TOOL_DEFS = [
    {
        "name": "search_target",
        "description": (
            "Run a full drug-target intelligence search for a protein target. "
            "Fetches UniProt annotation (function, GO terms, diseases, subcellular location, keywords), "
            "PDB crystal structures, AlphaFold model, ChEMBL bioactivities, ligand summaries, and STRING-DB "
            "protein interactions. Results are cached server-side for all follow-up queries. "
            "Always call this before get_top_ligands, get_pdb_structures, or get_protein_interactions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gene name (EGFR, BRAF), UniProt accession (P00533), or ChEMBL target ID (CHEMBL203)"
                },
                "min_pchembl": {
                    "type": "number",
                    "description": "Minimum pChEMBL potency filter (e.g. 7.0 = 100 nM cutoff). Optional."
                },
                "max_pdb_resolution": {
                    "type": "number",
                    "description": "Maximum PDB resolution in Angstroms (default 4.0). Optional."
                },
                "max_bioactivities": {"type": "integer", "description": "Max bioactivity records from ChEMBL (default 1000, null = unlimited)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_top_ligands",
        "description": (
            "Return ligands or raw bioactivity records for a cached target. "
            "Default mode (raw_records=false): returns top deduplicated ligands from ligand_summary, "
            "sorted by pChEMBL, with optional filters. "
            "Raw mode (raw_records=true): returns individual assay records with statistics "
            "(count, mean/min/max pChEMBL) — use this for potency distribution analysis or "
            "when you need per-assay data rather than per-compound aggregates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Target gene name or ID (must be cached via search_target)"},
                "top_n": {"type": "integer", "description": "Number of results to return (default 10, max 50)"},
                "min_pchembl": {"type": "number", "description": "Minimum pChEMBL filter"},
                "max_pchembl": {"type": "number", "description": "Maximum pChEMBL filter (raw_records mode only)"},
                "activity_type": {"type": "string", "description": "Filter by assay type: IC50, Ki, Kd, EC50, etc."},
                "source": {"type": "string", "enum": ["ChEMBL", "all"], "description": "Data source filter (default all)"},
                "raw_records": {"type": "boolean", "description": "If true, return raw per-assay bioactivity records with statistics instead of deduplicated ligands (default false)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_pdb_structures",
        "description": (
            "Return PDB crystal structures for a cached target with optional filters. "
            "Shows resolution, method, deposition date, and bound ligands."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Target gene name or ID (must be cached)"},
                "method": {
                    "type": "string",
                    "enum": ["X-RAY DIFFRACTION", "ELECTRON MICROSCOPY", "SOLUTION NMR", "all"],
                    "description": "Filter by experimental method (default all)"
                },
                "max_resolution": {"type": "number", "description": "Maximum resolution in Angstroms"},
                "with_ligands_only": {"type": "boolean", "description": "Only return structures that have bound ligands"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_protein_interactions",
        "description": (
            "Return STRING-DB protein-protein interaction partners for a cached target. "
            "Includes combined confidence score. Useful for pathway and off-target analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Target gene name or ID (must be cached)"},
                "min_score": {"type": "number", "description": "Minimum STRING confidence score 0–1 (default 0.7)"},
                "top_n": {"type": "integer", "description": "Number of top partners to return (default 10)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_compound",
        "description": (
            "Search ChEMBL for a compound by name, SMILES, or ChEMBL molecule ID and retrieve "
            "all protein targets it has been tested against. "
            "Use for reverse lookups: 'What targets does erlotinib hit?' or 'What is the target profile of CHEMBL553?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Compound name (erlotinib, imatinib), ChEMBL molecule ID (CHEMBL553), or SMILES string"
                },
                "mode": {
                    "type": "string",
                    "enum": ["name", "chembl_id", "smiles"],
                    "description": "Search mode: name lookup, ChEMBL ID lookup, or SMILES exact match (default: auto-detect)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "run_python",
        "description": (
            "Write and execute an arbitrary Python script for custom cheminformatics, statistics, "
            "or data analysis on the cached target data. "
            "Use this for: Murcko scaffold decomposition, drug-likeness properties (MW/LogP/TPSA/Ro5), "
            "Morgan fingerprint similarity search, target comparison (call search_target for each target first, "
            "then compare via run_python), file listing (os.listdir('.')), and any custom analysis. "
            "Pre-injected variables available in the script: "
            "`target` (str), "
            "`ligands` (list of dicts, each with: smiles, name, chembl_id, pchembl, activity_type, value_nM, num_assays, sources — NO pre-computed properties; use RDKit to compute mw/logp/tpsa/etc from smiles), "
            "`bioactivities` (list of dicts, each with: smiles, name, source, activity_type, value, pchembl_value). "
            "Available packages: rdkit (Chem, Descriptors, rdMolDescriptors, AllChem, MurckoScaffold), pandas, numpy, scipy, matplotlib (Agg backend already set — use plt.savefig not plt.show). "
            "Always print results to stdout. For plots: save as PNG with a bare filename, always call plt.tight_layout() before savefig, use large enough figsize for heatmaps (e.g. figsize=(10,8)), rotate x-axis tick labels on heatmaps (rotation=45, ha='right') to prevent overlap. Never mention the image URL in your response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Target gene name or ID (cached via search_target). Optional — omit for pure compound/cheminformatics scripts that don't need target data."},
                "script": {"type": "string", "description": "Complete Python script to execute. Use print() to output results."},
                "description": {"type": "string", "description": "One-line description of what this script does"},
            },
            "required": ["script", "description"]
        }
    },
]

TOOL_DISPLAY = {
    "search_target": "Running full target recon",
    "get_top_ligands": "Fetching ligands",
    "get_pdb_structures": "Querying PDB structures",
    "get_protein_interactions": "Querying STRING-DB interactions",
    "search_compound": "Searching ChEMBL compound database",
    "run_python": "Executing Python script",
}

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a specialized AI assistant embedded in TargetRecon, a drug-target intelligence platform used by medicinal chemists and drug discovery scientists.

You have access to real-time tools that query UniProt, PDB, AlphaFold, ChEMBL, and STRING-DB, as well as cheminformatics tools powered by RDKit (scaffold analysis, drug-likeness, similarity search). ALWAYS use tools to get data — never generate, estimate, or recall numbers, properties, structures, or analysis results from your training knowledge. Every number in your response must come from a tool result.

Guidelines:
- Use **bold** for gene names, `code` for IDs (UniProt, PDB, ChEMBL), and tables for comparisons
- After tool results, provide expert drug discovery interpretation: what the data means clinically, structurally, or for lead optimization
- When comparing targets, run search_target for each target first, then use run_python to build the comparison table
- If a user explicitly asks about a protein target (not a compound), run search_target — do NOT proactively run search_target for targets discovered incidentally from search_compound results
- For any molecular computation (properties, scaffolds, fingerprints, similarity, clustering), always use run_python with RDKit — never estimate from SMILES or training knowledge
- For file listing, use run_python with os.listdir('.') to see session files
- To filter raw bioactivity records (per-assay, not per-compound), use get_top_ligands with raw_records=true
- NEVER generate, guess, recall, or invent any numbers — every value must come directly from a tool result or run_python output
- For plots, correlations, custom statistics, fingerprint clustering, similarity matrices, or any analysis not covered by other tools — silently call run_python without telling the user; never ask them to run a script themselves
- When creating plots, always save as PNG using a bare filename (e.g. plt.savefig('plot.png')) — NEVER use /mnt/data/ or any absolute path. Do NOT reference or mention the image URL in your response — the plot will appear as a button automatically. Always call plt.tight_layout() before savefig. For heatmaps use a large enough figure (e.g. figsize=(10,8)) and rotate x-axis labels (plt.xticks(rotation=45, ha='right')) to prevent label overlap.
- If run_python returns an error, fix the script and call run_python again immediately — never tell the user there was an error, just fix and retry silently
- Be concise but scientifically rigorous; use bullet points for findings
- Suggest follow-up analyses the user might not have considered

Currently cached targets: {cached_queries}
{context_hint}"""


# ── Tool implementations ──────────────────────────────────────────────────────
async def _tool_search_target(inputs: dict, report_cache: dict) -> dict:
    from targetrecon.core import recon_async

    query = inputs["query"].strip()
    min_pchembl = inputs.get("min_pchembl")
    max_res = float(inputs.get("max_pdb_resolution", 4.0))
    max_bioactivities = inputs.get("max_bioactivities", 1000)

    report = await recon_async(
        query,
        max_pdb_resolution=max_res,
        min_pchembl=min_pchembl if min_pchembl else None,
        max_bioactivities=max_bioactivities,
        verbose=False,
    )

    key = query.upper()
    report_cache[key] = report

    if report.uniprot is None:
        return {"error": f"Could not resolve '{query}' to a protein target."}

    u = report.uniprot
    best = report.best_ligand

    go_by_cat: dict[str, list] = {}
    for g in u.go_terms:
        go_by_cat.setdefault(g.category, []).append(g.term)

    result = {
        "target": query,
        "uniprot_id": u.uniprot_id,
        "gene_name": u.gene_name,
        "protein_name": u.protein_name,
        "organism": u.organism,
        "sequence_length": u.sequence_length,
        "chembl_id": u.chembl_id,
        "pdb_structures": report.num_pdb_structures,
        "alphafold_available": report.alphafold is not None,
        "alphafold_plddt": round(report.alphafold.mean_plddt, 1) if report.alphafold and report.alphafold.mean_plddt else None,
        "total_bioactivities": report.num_bioactivities,
        "unique_ligands": report.num_unique_ligands,
        "best_ligand": {
            "name": best.name or best.chembl_id,
            "pchembl": best.best_pchembl,
            "activity_type": best.best_activity_type,
            "value_nM": best.best_activity_value_nM,
        } if best else None,
        "function": u.function_description,
        "disease_associations": u.disease_associations,
        "subcellular_locations": u.subcellular_locations,
        "keywords": u.keywords[:15],
        "go_biological_process": go_by_cat.get("biological_process", [])[:10],
        "go_molecular_function": go_by_cat.get("molecular_function", [])[:8],
        "go_cellular_component": go_by_cat.get("cellular_component", [])[:5],
        "_action_links": [
            {"label": "View full report", "href": f"/recon/run?q={query}", "external": False, "report": True},
        ]
    }
    return result


async def _tool_get_top_ligands(inputs: dict, report_cache: dict) -> dict:
    query = inputs["query"].strip().upper()
    report = report_cache.get(query)
    if not report:
        return {"error": f"No cached data for '{inputs['query']}'. Run search_target first."}

    raw_records = bool(inputs.get("raw_records", False))
    min_pc = inputs.get("min_pchembl")
    atype = (inputs.get("activity_type") or "").upper()
    source = (inputs.get("source") or "all").lower()
    top_n = int(inputs.get("top_n", 15 if raw_records else 10))

    if raw_records:
        records = list(report.bioactivities)
        max_pc = inputs.get("max_pchembl")
        if min_pc:
            records = [r for r in records if r.pchembl_value and r.pchembl_value >= min_pc]
        if max_pc:
            records = [r for r in records if r.pchembl_value and r.pchembl_value <= max_pc]
        if atype:
            records = [r for r in records if (r.activity_type or "").upper() == atype]
        if source != "all":
            records = [r for r in records if r.source.lower() == source]
        pchembl_vals = [r.pchembl_value for r in records if r.pchembl_value]
        stats = {
            "count": len(records),
            "mean_pchembl": round(sum(pchembl_vals) / len(pchembl_vals), 2) if pchembl_vals else None,
            "max_pchembl": round(max(pchembl_vals), 2) if pchembl_vals else None,
            "min_pchembl": round(min(pchembl_vals), 2) if pchembl_vals else None,
        }
        records_sorted = sorted(records, key=lambda r: r.pchembl_value or 0, reverse=True)
        top_records = [
            {"smiles": r.smiles, "activity_type": r.activity_type, "value_nM": r.value,
             "pchembl": r.pchembl_value, "source": r.source}
            for r in records_sorted[:top_n]
        ]
        return {
            "target": inputs["query"],
            "statistics": stats,
            "top_records": top_records,
            "_action_links": [{"label": "View full report", "href": f"/recon/run?q={inputs['query']}", "external": False}],
        }

    ligands = list(report.ligand_summary)
    top_n = min(top_n, 50)
    if min_pc:
        ligands = [l for l in ligands if l.best_pchembl and l.best_pchembl >= min_pc]
    if atype:
        ligands = [l for l in ligands if l.best_activity_type.upper() == atype]
    if source != "all":
        ligands = [l for l in ligands if source in [s.lower() for s in l.sources]]
    ligands = ligands[:top_n]

    rows = []
    action_links = []
    for i, l in enumerate(ligands):
        rows.append({
            "rank": i + 1,
            "name": l.name or "—",
            "chembl_id": l.chembl_id or "—",
            "pchembl": l.best_pchembl,
            "activity_type": l.best_activity_type,
            "value_nM": l.best_activity_value_nM,
            "num_assays": l.num_assays,
            "sources": l.sources,
            "smiles": l.smiles,
        })
        if l.chembl_id:
            action_links.append({
                "label": l.chembl_id,
                "href": f"https://www.ebi.ac.uk/chembl/compound_report_card/{l.chembl_id}",
                "external": True,
            })

    action_links.append({"label": "Download SDF", "href": f"/export/sdf?q={query}", "external": False})

    return {
        "target": inputs["query"],
        "total_matching": len(ligands),
        "ligands": rows,
        "_action_links": action_links[:6],
    }


async def _tool_get_pdb_structures(inputs: dict, report_cache: dict) -> dict:
    query = inputs["query"].strip().upper()
    report = report_cache.get(query)
    if not report:
        return {"error": f"No cached data for '{inputs['query']}'. Run search_target first."}

    structs = list(report.pdb_structures)
    method = (inputs.get("method") or "all").upper()
    max_res = inputs.get("max_resolution")
    ligands_only = inputs.get("with_ligands_only", False)

    if method != "ALL":
        structs = [s for s in structs if s.method.value == method]
    if max_res:
        structs = [s for s in structs if s.resolution and s.resolution <= max_res]
    if ligands_only:
        structs = [s for s in structs if s.ligands]

    rows = []
    action_links = []
    for s in structs[:20]:
        rows.append({
            "pdb_id": s.pdb_id,
            "method": s.method.value,
            "resolution_A": s.resolution,
            "date": s.release_date,
            "ligands": [l.ligand_id for l in s.ligands],
            "title": s.title[:80] if s.title else "",
        })
        action_links.append({
            "label": s.pdb_id,
            "href": f"https://www.rcsb.org/structure/{s.pdb_id}",
            "external": True,
        })

    return {
        "target": inputs["query"],
        "total_matching": len(structs),
        "structures": rows,
        "_action_links": action_links[:8],
    }




async def _tool_get_protein_interactions(inputs: dict, report_cache: dict) -> dict:
    query = inputs["query"].strip().upper()
    report = report_cache.get(query)

    min_score = float(inputs.get("min_score", 0.7))
    top_n = int(inputs.get("top_n", 10))

    if report and report.interactions:
        interactions = report.interactions
    else:
        # Fetch fresh if not cached
        from targetrecon.resolver import resolve_ids
        from targetrecon.clients.string_db import fetch_interactions
        uniprot_id, _ = await resolve_ids(inputs["query"])
        if not uniprot_id:
            return {"error": f"Could not resolve '{inputs['query']}'."}
        raw = await fetch_interactions(uniprot_id, limit=30)
        from targetrecon.models import ProteinInteraction
        interactions = [ProteinInteraction(**i) for i in (raw or [])]

    filtered = [i for i in interactions if i.score >= min_score]
    filtered.sort(key=lambda x: x.score, reverse=True)
    filtered = filtered[:top_n]

    rows = [{"partner": i.gene_b, "score": round(i.score, 3)} for i in filtered]

    return {
        "target": inputs["query"],
        "total_partners_above_threshold": len(filtered),
        "interactions": rows,
        "_action_links": [],
    }


async def _tool_search_compound(inputs: dict, report_cache: dict) -> dict:
    import httpx, urllib.parse
    from targetrecon.resolver import fetch_compound_targets

    query = inputs["query"].strip()
    mode = inputs.get("mode", "auto")

    # Auto-detect mode
    if mode == "auto":
        if query.upper().startswith("CHEMBL") and query[6:].isdigit():
            mode = "chembl_id"
        elif any(c in query for c in "=#@/\\()[]"):
            mode = "smiles"
        else:
            mode = "name"

    hits = []
    try:
        if mode == "chembl_id":
            mol_id = query.upper()
            url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/{mol_id}.json"
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url)
            if r.status_code == 200:
                m = r.json()
                hits = [{"chembl_id": m.get("molecule_chembl_id"), "name": m.get("pref_name"), "similarity": 1.0}]
            else:
                return {"error": f"ChEMBL molecule {mol_id} not found."}

        elif mode == "name":
            url = f"https://www.ebi.ac.uk/chembl/api/data/molecule.json"
            params = {"pref_name__icontains": query, "limit": "5"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, params=params)
            mols = r.json().get("molecules", []) if r.status_code == 200 else []
            if not mols:
                # try synonym search
                params2 = {"molecule_synonyms__synonym__icontains": query, "limit": "5"}
                async with httpx.AsyncClient(timeout=15) as client:
                    r2 = await client.get(url, params=params2)
                mols = r2.json().get("molecules", []) if r2.status_code == 200 else []
            hits = [{"chembl_id": m.get("molecule_chembl_id"), "name": m.get("pref_name"), "similarity": None} for m in mols]

        elif mode == "smiles":
            try:
                from rdkit import Chem
                mol = Chem.MolFromSmiles(query)
                if mol:
                    query = Chem.MolToSmiles(mol)
            except Exception:
                pass
            encoded = urllib.parse.quote(query, safe="")
            url = f"https://www.ebi.ac.uk/chembl/api/data/molecule.json?smiles={encoded}&limit=5"
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url)
            mols = r.json().get("molecules", []) if r.status_code == 200 else []
            hits = [{"chembl_id": m.get("molecule_chembl_id"), "name": m.get("pref_name"), "similarity": 1.0} for m in mols]

    except Exception as exc:
        return {"error": str(exc)}

    if not hits:
        return {"error": f"No compounds found for '{query}'."}

    # For each hit, fetch target profile
    action_links = []
    result_compounds = []
    for h in hits[:3]:
        cid = h["chembl_id"]
        if not cid:
            continue
        targets = await fetch_compound_targets(cid, limit=10)
        targets = [t for t in targets if t.uniprot_id]
        result_compounds.append({
            "chembl_id": cid,
            "name": h.get("name"),
            "targets": [
                {
                    "gene": t.gene_name or "—",
                    "target_name": t.target_name,
                    "uniprot": t.uniprot_id,
                    "best_pchembl": t.best_pchembl,
                    "assays": t.num_activities,
                }
                for t in targets
            ]
        })
        action_links.append({
            "label": cid,
            "href": f"https://www.ebi.ac.uk/chembl/compound_report_card/{cid}",
            "external": True,
        })
        if targets:
            best_t = targets[0]
            q_t = best_t.gene_name or best_t.uniprot_id or best_t.target_chembl_id
            action_links.append({
                "label": f"Analyse {best_t.gene_name or q_t}",
                "href": f"/recon/run?q={q_t}",
                "external": False,
            })

    return {"compounds": result_compounds, "_action_links": action_links[:6]}




_EXEC_TIMEOUT = int(os.environ.get("TARGETRECON_EXEC_TIMEOUT", "60"))
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".gif"}
_DATA_EXTS  = {".csv", ".tsv", ".txt", ".json", ".sdf", ".mol"}


async def _tool_run_python(inputs: dict, report_cache: dict) -> dict:
    query = inputs.get("query", "").strip().upper()
    report = report_cache.get(query) if query else None

    script = inputs.get("script", "")
    description = inputs.get("description", "custom script")
    sid = inputs.get("__sid__", "")
    if not script:
        return {"error": "No script provided."}

    # Per-session working directory so files persist and are user-isolated.
    # MCP sessions: prefer TARGETRECON_WORKDIR env var, then $PWD/tmp — files land where user runs Claude Code.
    if sid == "mcp":
        workdir = Path(os.environ.get("TARGETRECON_WORKDIR", "") or (Path(os.getcwd()) / "tmp"))
        workdir.mkdir(parents=True, exist_ok=True)
    elif sid:
        workdir = get_session_workdir(sid)
    else:
        workdir = Path(tempfile.mkdtemp(prefix="tr_tmp_"))
    before = set(workdir.iterdir())

    gene = (report.uniprot.gene_name if report and report.uniprot else None) or query or "compound"

    def _clean_smiles(smi: str) -> str:
        """Strip extended SMILES notation (|...|) — RDKit doesn't need it."""
        if smi and " |" in smi:
            smi = smi[:smi.index(" |")]
        return smi or ""

    ligands_data = [
        {
            "smiles": _clean_smiles(l.smiles or ""), "name": l.name, "chembl_id": l.chembl_id,
            "pchembl": l.best_pchembl, "activity_type": l.best_activity_type,
            "value_nM": l.best_activity_value_nM, "num_assays": l.num_assays,
            "sources": l.sources,
        }
        for l in (report.ligand_summary if report else [])
    ]
    bio_data = [
        {
            "smiles": b.smiles, "name": b.name, "source": b.source,
            "activity_type": b.activity_type, "value": b.value,
            "pchembl_value": b.pchembl_value,
        }
        for b in (report.bioactivities if report else [])
    ]

    prelude = (
        "import json, math, collections, itertools\n"
        "try:\n    import pandas as pd\nexcept ImportError: pass\n"
        "try:\n    import numpy as np\nexcept ImportError: pass\n"
        "try:\n    import scipy\nexcept ImportError: pass\n"
        "try:\n    import matplotlib\n    matplotlib.use('Agg')\n    import matplotlib.pyplot as plt\nexcept ImportError: pass\n"
        "try:\n    from rdkit import Chem, DataStructs\n"
        "    from rdkit.Chem import Descriptors, rdMolDescriptors, AllChem\n"
        "    from rdkit.Chem.Scaffolds import MurckoScaffold\n"
        "except ImportError: pass\n"
        f"target = {gene!r}\n"
        f"ligands = json.loads({json.dumps(json.dumps(ligands_data))})\n"
        f"bioactivities = json.loads({json.dumps(json.dumps(bio_data))})\n"
        "# ── user script ──\n"
    )
    full_script = prelude + textwrap.dedent(script)

    print(f"[run_python] starting: {description!r}, query={query}, ligands={len(ligands_data)}", flush=True)
    try:
        # Write to a temp file — more reliable than -c for large injected data
        script_file = workdir / "_tr_script.py"
        script_file.write_text(full_script, encoding="utf-8")
        _cmd = [sys.executable, str(script_file)]
        _kw = dict(capture_output=True, text=True, timeout=_EXEC_TIMEOUT, cwd=str(workdir))
        proc = await asyncio.to_thread(subprocess.run, _cmd, **_kw)
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        success = proc.returncode == 0
        print(f"[run_python] rc={proc.returncode}, stdout={len(stdout)}b, stderr={len(stderr)}b", flush=True)
        if not success:
            print(f"[run_python] STDERR:\n{stderr[:1000]}", flush=True)

        # Detect new files created by the script
        after = set(workdir.iterdir())
        new_files = sorted(after - before, key=lambda f: f.name)

        result: dict = {"description": description, "success": success}
        if stdout:
            result["output"] = stdout[:4000]
        if stderr and not success:
            # Only surface stderr as error when script actually failed
            result["error"] = stderr[:1500]
        elif stderr:
            # Script succeeded but had warnings — log quietly, don't mark as failure
            result["warnings"] = stderr[:500]
        if not success and not stderr:
            result["error"] = f"Script exited with code {proc.returncode} — no output or error captured."
        if not stdout and not stderr and not new_files and success:
            result["output"] = "(no output — add print() statements to see results)"

        # Build action links for new files
        action_links = []
        image_urls = []
        for f in new_files:
            ext = f.suffix.lower()
            url = f"/agent/files/{sid}/{f.name}" if sid else f"/agent/files/tmp/{f.name}"
            if ext in _IMAGE_EXTS:
                action_links.append({"label": f"View {f.name}", "href": url, "external": False, "is_image": True})
                action_links.append({"label": f"⬇ Download {f.name}", "href": url, "external": False})
                image_urls.append(url)
            elif ext in _DATA_EXTS:
                action_links.append({"label": f"Download {f.name}", "href": url, "external": False})

        if image_urls:
            result["images_saved"] = [Path(u).name for u in image_urls]

        result["_action_links"] = action_links
        return result

    except subprocess.TimeoutExpired:
        return {"error": f"Script timed out after {_EXEC_TIMEOUT}s. Simplify or reduce data size."}
    except Exception as exc:
        return {"error": f"Execution error: {exc}"}



TOOL_REGISTRY = {
    "search_target": _tool_search_target,
    "get_top_ligands": _tool_get_top_ligands,
    "get_pdb_structures": _tool_get_pdb_structures,
    "get_protein_interactions": _tool_get_protein_interactions,
    "search_compound": _tool_search_compound,
    "run_python": _tool_run_python,
}


# ── OpenAI-format tool definitions (used by OpenAI + Groq) ───────────────────
TOOL_DEFS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": td["name"],
            "description": td["description"],
            "parameters": td["input_schema"],
        },
    }
    for td in TOOL_DEFS
]

# ── SSE helper ────────────────────────────────────────────────────────────────
def _sse(event_type: str, payload: dict) -> str:
    payload["type"] = event_type
    return f"data: {json.dumps(payload)}\n\n"


# ── Shared tool executor ──────────────────────────────────────────────────────
async def _exec_tool(tool_name: str, tool_inputs: dict, report_cache: dict, tool_id: str, q: queue.Queue, sid: str = "") -> str:
    tool_func = TOOL_REGISTRY.get(tool_name)
    if not tool_func:
        result: dict = {"error": f"Unknown tool: {tool_name}"}
        elapsed = 0.0
    else:
        try:
            t0 = time.time()
            tool_inputs["__sid__"] = sid  # inject session ID for tools that need it
            result = await tool_func(tool_inputs, report_cache)
            elapsed = round(time.time() - t0, 1)
        except Exception as exc:
            result = {"error": str(exc)}
            elapsed = 0.0

    action_links = result.pop("_action_links", [])
    # Append session ID to internal export links (skip /agent/files/ — sid already in path)
    if sid:
        for lnk in action_links:
            if not lnk.get("external") and "href" in lnk and "/agent/files/" not in lnk["href"]:
                sep = "&" if "?" in lnk["href"] else "?"
                lnk["href"] = f"{lnk['href']}{sep}sid={sid}"
    # Include script source for run_python so the UI can show it; keep other inputs out of SSE
    inputs_preview = {}
    if tool_name == "run_python":
        inputs_preview = {
            "script": tool_inputs.get("script", ""),
            "description": tool_inputs.get("description", ""),
        }
    q.put(_sse("tool_result", {
        "tool_name": tool_name,
        "tool_id": tool_id,
        "elapsed": elapsed,
        "content": result,
        "action_links": action_links,
        "inputs_preview": inputs_preview,
    }))
    return json.dumps(result)


def _build_system(context_query: str | None, report_cache: dict) -> str:
    cached = [k for k in report_cache if report_cache[k] is not None]
    context_hint = (
        f"The user is currently viewing the report for **{context_query}** — its data is already cached."
        if context_query else ""
    )
    return SYSTEM_PROMPT.format(
        cached_queries=", ".join(cached) if cached else "none yet",
        context_hint=context_hint,
    )


# ── Anthropic streaming agent ─────────────────────────────────────────────────
async def _run_anthropic(
    message: str, conv_id: str, context_query: str | None,
    report_cache: dict, q: queue.Queue, model: str, api_key: str, sid: str = "",
) -> None:
    client = anthropic.AsyncAnthropic(api_key=api_key)
    system = _build_system(context_query, report_cache)

    history = get_conversation(conv_id)
    history.append({"role": "user", "content": message})
    new_messages: list[dict] = [{"role": "user", "content": message}]

    for _ in range(10):
        # Pending tool calls accumulated during streaming — executed AFTER stream closes
        pending_tools: list[dict] = []  # [{id, name, inputs}]
        current_text = ""
        current_tool_id: str | None = None
        current_tool_name: str | None = None
        current_tool_json = ""
        stop_reason = None

        try:
            async with client.messages.stream(
                model=model, max_tokens=8192, system=system,
                messages=history, tools=TOOL_DEFS,
            ) as stream:
                async for event in stream:
                    etype = event.type
                    if etype == "content_block_start":
                        cb = event.content_block
                        if cb.type == "tool_use":
                            current_tool_id = cb.id
                            current_tool_name = cb.name
                            current_tool_json = ""
                            q.put(_sse("tool_start", {
                                "tool_name": cb.name, "tool_id": cb.id,
                                "display_message": TOOL_DISPLAY.get(cb.name, cb.name),
                            }))
                        else:
                            current_text = ""
                    elif etype == "content_block_delta":
                        d = event.delta
                        if d.type == "text_delta":
                            current_text += d.text
                            q.put(_sse("text_delta", {"delta": d.text}))
                        elif d.type == "input_json_delta":
                            current_tool_json += d.partial_json
                    elif etype == "content_block_stop":
                        if current_tool_name and current_tool_id:
                            try:
                                inputs = json.loads(current_tool_json) if current_tool_json else {}
                            except Exception:
                                inputs = {}
                            pending_tools.append({"id": current_tool_id, "name": current_tool_name, "inputs": inputs})
                            current_tool_name = None
                            current_tool_id = None
                    elif etype == "message_delta":
                        stop_reason = getattr(event.delta, "stop_reason", None)
        except Exception as exc:
            q.put(_sse("error", {"message": str(exc)}))
            q.put(None)
            return

        # Rescue incomplete tool block — stream ended before content_block_stop fired
        if current_tool_name and current_tool_id:
            print(f"[agent] rescuing incomplete tool block: {current_tool_name}", flush=True)
            try:
                inputs = json.loads(current_tool_json) if current_tool_json else {}
            except Exception:
                inputs = {}
            pending_tools.append({"id": current_tool_id, "name": current_tool_name, "inputs": inputs})
            stop_reason = "tool_use"  # force continuation

        # Execute tools after stream closes — avoids blocking inside the stream context
        if pending_tools:
            print(f"[agent] executing {len(pending_tools)} tool(s): {[t['name'] for t in pending_tools]}", flush=True)
            # Build assistant content: preserve any text + tool_use blocks (required by API)
            asst_content: list[dict] = []
            if current_text:
                asst_content.append({"type": "text", "text": current_text})
            asst_content += [
                {"type": "tool_use", "id": t["id"], "name": t["name"], "input": t["inputs"]}
                for t in pending_tools
            ]
            history.append({"role": "assistant", "content": asst_content})
            new_messages.append({"role": "assistant", "content": asst_content})
            tool_results = []
            try:
                for t in pending_tools:
                    print(f"[agent] calling _exec_tool({t['name']})", flush=True)
                    result_str = await _exec_tool(t["name"], t["inputs"], report_cache, t["id"], q, sid)
                    print(f"[agent] _exec_tool({t['name']}) done, result len={len(result_str)}", flush=True)
                    tool_results.append({"type": "tool_result", "tool_use_id": t["id"], "content": result_str})
            except Exception as exc:
                print(f"[agent] _exec_tool EXCEPTION: {exc}", flush=True)
                q.put(_sse("error", {"message": str(exc)}))
                q.put(None)
                return
            history.append({"role": "user", "content": tool_results})
            new_messages.append({"role": "user", "content": tool_results})

        if stop_reason != "tool_use":
            history.append({"role": "assistant", "content": current_text or ""})
            new_messages.append({"role": "assistant", "content": current_text or ""})
            save_turn(conv_id, new_messages)
            q.put(_sse("done", {"full_text": current_text}))
            q.put(None)
            return

    q.put(_sse("done", {"full_text": ""}))
    q.put(None)


# ── OpenAI / Groq streaming agent ─────────────────────────────────────────────
async def _run_openai_compat(
    message: str, conv_id: str, context_query: str | None,
    report_cache: dict, q: queue.Queue, model: str, api_key: str, provider: str, sid: str = "",
) -> None:
    if provider == "groq":
        import groq as groq_sdk
        client = groq_sdk.AsyncGroq(api_key=api_key)
    else:
        import openai as openai_sdk
        client = openai_sdk.AsyncOpenAI(api_key=api_key)

    system = _build_system(context_query, report_cache)
    history: list[dict] = [{"role": "system", "content": system}]
    history += get_conversation(conv_id)
    history.append({"role": "user", "content": message})
    new_messages: list[dict] = [{"role": "user", "content": message}]

    for _ in range(6):
        # Accumulate streaming response
        current_text = ""
        tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, args}
        finish_reason = None

        try:
            stream = await client.chat.completions.create(
                model=model, max_tokens=4096,
                messages=history, tools=TOOL_DEFS_OPENAI, stream=True,
            )
            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue
                delta = choice.delta
                # Text
                if delta.content:
                    current_text += delta.content
                    q.put(_sse("text_delta", {"delta": delta.content}))
                # Tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "args": ""}
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                                q.put(_sse("tool_start", {
                                    "tool_name": tc.function.name or "",
                                    "tool_id": tc.id,
                                    "display_message": TOOL_DISPLAY.get(tc.function.name or "", tc.function.name or ""),
                                }))
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["args"] += tc.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
        except Exception as exc:
            q.put(_sse("error", {"message": str(exc)}))
            q.put(None)
            return

        if finish_reason == "tool_calls" and tool_calls_acc:
            # Build assistant message with tool_calls
            assistant_tool_calls = []
            for idx in sorted(tool_calls_acc):
                tc = tool_calls_acc[idx]
                assistant_tool_calls.append({
                    "id": tc["id"], "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["args"]},
                })
            asst_msg: dict = {"role": "assistant", "content": current_text or None, "tool_calls": assistant_tool_calls}
            history.append(asst_msg)
            new_messages.append(asst_msg)

            # Execute each tool
            for tc in assistant_tool_calls:
                tool_name = tc["function"]["name"]
                tool_id = tc["id"]
                try:
                    inputs = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                except Exception:
                    inputs = {}
                result_str = await _exec_tool(tool_name, inputs, report_cache, tool_id, q, sid)
                tool_msg = {"role": "tool", "tool_call_id": tool_id, "content": result_str}
                history.append(tool_msg)
                new_messages.append(tool_msg)
        else:
            # Final text response
            history.append({"role": "assistant", "content": current_text or ""})
            new_messages.append({"role": "assistant", "content": current_text or ""})
            save_turn(conv_id, new_messages)
            q.put(_sse("done", {"full_text": current_text}))
            q.put(None)
            return

    q.put(_sse("done", {"full_text": ""}))
    q.put(None)


# ── Dispatcher ────────────────────────────────────────────────────────────────
async def _run_agent(
    message: str, conv_id: str, context_query: str | None,
    report_cache: dict, q: queue.Queue,
    provider: str = "anthropic", model: str = "claude-sonnet-4-6", api_key: str = "", sid: str = "",
) -> None:
    if not api_key:
        raise ValueError("No API key provided. Please enter your own API key in the AI panel.")
    if provider == "anthropic":
        await _run_anthropic(message, conv_id, context_query, report_cache, q, model, api_key, sid)
    else:
        await _run_openai_compat(message, conv_id, context_query, report_cache, q, model, api_key, provider, sid)


# ── Sync SSE bridge (Flask-compatible) ───────────────────────────────────────
def sse_generator(
    message: str,
    conv_id: str,
    context_query: str | None,
    report_cache: dict,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    api_key: str = "",
    sid: str = "",
):
    """Synchronous generator that bridges async _run_agent → Flask SSE."""
    q: queue.Queue = queue.Queue()

    def _thread():
        asyncio.run(_run_agent(message, conv_id, context_query, report_cache, q, provider, model, api_key, sid))

    threading.Thread(target=_thread, daemon=True).start()

    while True:
        item = q.get()
        if item is None:
            break
        yield item
