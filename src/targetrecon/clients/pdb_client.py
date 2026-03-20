"""RCSB PDB Search + Data API client."""
from __future__ import annotations

import httpx

from targetrecon.clients.http import build_client, safe_get
from targetrecon.models import ExperimentalMethod, PDBLigand, PDBStructure

SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
ENTRY_URL = "https://data.rcsb.org/rest/v1/core/entry"

METHOD_MAP = {
    "X-RAY DIFFRACTION": ExperimentalMethod.XRAY,
    "ELECTRON MICROSCOPY": ExperimentalMethod.CRYO_EM,
    "SOLUTION NMR": ExperimentalMethod.NMR,
    "NEUTRON DIFFRACTION": ExperimentalMethod.NEUTRON,
}

# Common solvent/buffer molecules to exclude from ligand list
_EXCLUDE_IDS = frozenset({
    "HOH", "DOD", "EDO", "GOL", "SO4", "PO4", "CL", "NA", "MG", "ZN",
    "CA", "K", "MN", "FE", "CU", "NI", "CO", "CD", "DMS", "MSE", "ACT",
    "BME", "PEG", "MPD", "IOD", "BR", "FMT", "AZI", "NI", "SEP", "TPO",
    "NO3", "IOD", "IMD", "TRS", "TAR", "SUC", "MLI", "PE4", "P33",
})


async def fetch_structures_for_uniprot(
    uniprot_id: str,
    max_results: int = 50,
    max_resolution: float = 4.0,
) -> list[PDBStructure]:
    # Build query with resolution pre-filter so RCSB returns only valid entries
    query_payload = {
        "query": {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                        "operator": "exact_match",
                        "value": uniprot_id,
                    },
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entry_info.resolution_combined",
                        "operator": "less_or_equal",
                        "value": max_resolution,
                    },
                },
            ],
        },
        "return_type": "entry",
        "request_options": {
            "sort": [
                {"sort_by": "rcsb_entry_info.resolution_combined", "direction": "asc"}
            ],
            "paginate": {"start": 0, "rows": max_results},
        },
    }

    async with build_client(timeout=30.0) as client:
        try:
            resp = await client.post(SEARCH_URL, json=query_payload)
            resp.raise_for_status()
            search_data = resp.json()
        except Exception:
            search_data = {}

    pdb_ids = [r["identifier"] for r in (search_data.get("result_set") or [])]

    # If pre-filtered search returned nothing (e.g. all NMR), fall back to
    # unfiltered search and do resolution check client-side
    if not pdb_ids:
        fallback_payload = {
            "query": {
                "type": "terminal",
                "service": "text",
                "parameters": {
                    "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                    "operator": "exact_match",
                    "value": uniprot_id,
                },
            },
            "return_type": "entry",
            "request_options": {"paginate": {"start": 0, "rows": max_results * 3}},
        }
        async with build_client(timeout=30.0) as client:
            try:
                resp = await client.post(SEARCH_URL, json=fallback_payload)
                resp.raise_for_status()
                fallback_data = resp.json()
                pdb_ids = [r["identifier"] for r in (fallback_data.get("result_set") or [])]
            except Exception:
                return []

    structures = []
    async with build_client(timeout=15.0) as client:
        for pdb_id in pdb_ids:
            if len(structures) >= max_results:
                break
            s = await _fetch_structure_detail(client, pdb_id, max_resolution)
            if s is not None:
                structures.append(s)

    return structures


async def _fetch_structure_detail(
    client: httpx.AsyncClient,
    pdb_id: str,
    max_resolution: float,
) -> PDBStructure | None:
    data = await safe_get(client, f"{ENTRY_URL}/{pdb_id}")
    if not data:
        return None

    # Resolution
    resolution: float | None = None
    entry_info = data.get("rcsb_entry_info", {})
    res_val = entry_info.get("resolution_combined")
    if isinstance(res_val, list) and res_val:
        try:
            resolution = float(res_val[0])
        except (ValueError, TypeError):
            pass
    elif res_val is not None:
        try:
            resolution = float(res_val)
        except (ValueError, TypeError):
            pass

    if resolution is not None and resolution > max_resolution:
        return None

    # Method
    method_str = ""
    exptl = data.get("exptl", [])
    if exptl:
        method_str = exptl[0].get("method", "").upper()
    method = METHOD_MAP.get(method_str, ExperimentalMethod.OTHER)

    # Release date
    release_date = data.get("rcsb_accession_info", {}).get("deposit_date")

    # Title
    title = data.get("struct", {}).get("title", "")

    # Ligands from nonpolymer_bound_components
    ligands = []
    nonpoly = entry_info.get("nonpolymer_bound_components", [])
    if nonpoly:
        seen: set[str] = set()
        for comp_id in nonpoly:
            if comp_id not in _EXCLUDE_IDS and comp_id not in seen:
                seen.add(comp_id)
                ligands.append(PDBLigand(ligand_id=comp_id))

    return PDBStructure(
        pdb_id=pdb_id,
        method=method,
        resolution=resolution,
        release_date=release_date,
        title=title,
        ligands=ligands,
    )
