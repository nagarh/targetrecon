"""UniProt REST API client."""
from __future__ import annotations

from targetrecon.clients.http import build_client, safe_get
from targetrecon.models import GoTerm, UniProtInfo

UNIPROT_API = "https://rest.uniprot.org/uniprotkb"


async def fetch_uniprot(uniprot_id: str) -> UniProtInfo | None:
    url = f"{UNIPROT_API}/{uniprot_id}.json"
    async with build_client() as client:
        data = await safe_get(client, url)
    if not data:
        return None
    # Handle inactive (merged/demerged) entries — follow to the canonical accession
    if "inactiveReason" in data:
        targets = data["inactiveReason"].get("mergeDemergeTo", [])
        if targets:
            # For demerged entries pick the first canonical target
            async with build_client() as client:
                canonical_data = await safe_get(client, f"{UNIPROT_API}/{targets[0]}.json")
            if canonical_data and "inactiveReason" not in canonical_data:
                return _parse_uniprot(canonical_data)
        return None
    return _parse_uniprot(data)


async def search_gene(gene_name: str, organism: str = "Homo sapiens") -> str | None:
    """Search for gene name → best reviewed UniProt accession."""
    url = f"{UNIPROT_API}/search"
    # Try reviewed human entries first
    for query in [
        f'(gene_exact:"{gene_name}") AND (organism_name:"{organism}") AND (reviewed:true)',
        f'(gene:"{gene_name}") AND (reviewed:true)',
        f'(gene:"{gene_name}")',
    ]:
        params = {"query": query, "format": "json", "size": "1", "fields": "accession"}
        async with build_client() as client:
            data = await safe_get(client, url, params=params)
        if data and data.get("results"):
            return data["results"][0]["primaryAccession"]
    return None


def _parse_uniprot(data: dict) -> UniProtInfo:
    return UniProtInfo(
        uniprot_id=data.get("primaryAccession", ""),
        gene_name=_extract_gene_name(data),
        protein_name=_extract_protein_name(data),
        organism=data.get("organism", {}).get("scientificName", ""),
        sequence_length=data.get("sequence", {}).get("length", 0),
        chembl_id=_extract_chembl_id(data),
        function_description=_extract_function(data),
        subcellular_locations=_extract_subcellular(data),
        disease_associations=_extract_diseases(data),
        keywords=_extract_keywords(data),
        go_terms=_extract_go_terms(data),
    )


def _extract_gene_name(data: dict) -> str | None:
    for gene in data.get("genes", []):
        gn = gene.get("geneName", {})
        if gn and gn.get("value"):
            return gn["value"]
    return None


def _extract_protein_name(data: dict) -> str:
    pn = data.get("proteinDescription", {})
    rec = pn.get("recommendedName", {})
    if rec:
        fn = rec.get("fullName", {})
        if fn:
            return fn.get("value", "")
    for sub in pn.get("submissionNames", []):
        fn = sub.get("fullName", {})
        if fn:
            return fn.get("value", "")
    return ""


def _extract_chembl_id(data: dict) -> str | None:
    for ref in data.get("uniProtKBCrossReferences", []):
        if ref.get("database") == "ChEMBL":
            return ref.get("id")
    return None


def _extract_function(data: dict) -> str | None:
    for comment in data.get("comments", []):
        if comment.get("commentType") == "FUNCTION":
            texts = comment.get("texts", [])
            if texts:
                return texts[0].get("value", "")
    return None


def _extract_subcellular(data: dict) -> list[str]:
    locs = []
    for comment in data.get("comments", []):
        if comment.get("commentType") == "SUBCELLULAR LOCATION":
            for subloc in comment.get("subcellularLocations", []):
                loc = subloc.get("location", {})
                if loc.get("value"):
                    locs.append(loc["value"])
    return locs


def _extract_diseases(data: dict) -> list[str]:
    diseases = []
    for comment in data.get("comments", []):
        if comment.get("commentType") == "DISEASE":
            disease = comment.get("disease", {})
            name = (
                disease.get("diseaseId")
                or disease.get("diseaseAcronym")
                or ""
            )
            if name:
                desc = disease.get("description", "")
                diseases.append(f"{name}: {desc}" if desc else name)
    return diseases


def _extract_keywords(data: dict) -> list[str]:
    return [kw.get("name", "") for kw in data.get("keywords", []) if kw.get("name")]


def _extract_go_terms(data: dict) -> list[GoTerm]:
    category_map = {
        "C": "cellular_component",
        "F": "molecular_function",
        "P": "biological_process",
    }
    go_terms = []
    for ref in data.get("uniProtKBCrossReferences", []):
        if ref.get("database") == "GO":
            go_id = ref.get("id", "")
            props = {p.get("key"): p.get("value") for p in ref.get("properties", [])}
            term_str = props.get("GoTerm", "")
            if ":" in term_str:
                cat_code, term_name = term_str.split(":", 1)
                category = category_map.get(cat_code, "other")
                go_terms.append(GoTerm(go_id=go_id, term=term_name, category=category))
    return go_terms
