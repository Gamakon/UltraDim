#!/usr/bin/env python3
"""Chemotype Galaxy — build the D3 data file ENTIRELY from the existing BloomMap
inputs (no clustering, no corpus read, no new server call). It consumes the four
committed BloomMap JSONs for the 50k/30M ChEMBL tree:

  bloommap.tree.json     — the divisive hierarchy (address, depth, size, log10_lift)
  bloommap.volumes.json  — per-leaf population
  bloommap.meta.json     — leaf_exemplars (chembl_id, smiles, centroid_cosine)

and emits ONE self-contained file, galaxy.json, with:
  - the full node tree (for the radial layout + the descend-by-depth animation),
  - per leaf: population, exemplar ChEMBL id + SMILES + cosine,
  - a STRUCTURAL CLASS derived from the SMILES string by transparent substructure
    heuristics (peptide / glycoside / long-chain lipid / quinolone / coumarin /
    steroid / sulfonamide / porphyrin / fused-heteroaromatic / small aromatic).
    This labels the molecule TYPE honestly from the structure already in the file;
    it never invents a clinical use. A later enrichment pass (research_uses.py)
    may add a real known-use string per ChEMBL id; if present it is merged, with
    the structural class always retained as the fallback.

Run: /opt/anaconda3/bin/python3 BloomMap/galaxy/build_galaxy.py
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data", "chembl_50k_30m")
OUT = os.path.join(HERE, "galaxy.json")
USES = os.path.join(HERE, "uses.json")  # optional enrichment (research_uses.py)


def structural_class(smiles: str) -> dict:
    """Transparent, offline structural-family label from a SMILES string.
    Returns {class, evidence} — evidence is the rule that fired, so the label is
    auditable and never a black box. Order = most specific first."""
    s = smiles
    # peptide backbone: two or more amide bonds linking chiral alpha carbons
    amide = len(re.findall(r"C\(=O\)N", s)) + len(re.findall(r"NC\(=O\)", s))
    chiral = s.count("[C@@H]") + s.count("[C@H]")
    # longest run of aliphatic chain carbons (CCCCC...) = lipid/surfactant tail
    longest_chain = max((len(m) for m in re.findall(r"C{6,}", s.replace("(", "").replace(")", ""))), default=0)
    # pyranose sugar ring: O[C@H]...CO with several ring hydroxyls
    sugar = bool(re.search(r"O[C@@H]\d?O[C@H]", s)) or (s.count("[C@@H](O)") + s.count("[C@H](O)") >= 3 and "OC" in s)
    has_tetrazole = "n[nH]n" in s or "nnn" in s
    has_sulfonamide = "S(=O)(=O)N" in s or "NS(=O)(=O)" in s
    has_coumarin = bool(re.search(r"oc\d?.*c\(=O\)|c\(=O\).*oc", s)) and "o" in s
    has_quinolone = bool(re.search(r"nc\d?ccc.*c\(=O\)n", s)) or bool(re.search(r"c\(=O\)n.*nc\d?ccc", s))
    porphyrin = s.count("[nH]") >= 3 and s.count("n") >= 4 and "cc" in s

    if amide >= 3 and chiral >= 3:
        return {"class": "Peptide / peptidomimetic", "evidence": f"{amide} amide bonds, {chiral} stereocentres"}
    if sugar and ("OC" in s):
        return {"class": "Glycoside / sugar-bearing", "evidence": "pyranose ring + multiple hydroxyls"}
    if longest_chain >= 10:
        return {"class": "Long-chain lipid / surfactant", "evidence": f"aliphatic chain run ≥{longest_chain} C"}
    if porphyrin:
        return {"class": "Porphyrin / tetrapyrrole", "evidence": "≥3 pyrrole NH in a fused macrocycle"}
    if has_quinolone:
        return {"class": "Quinolone / fused lactam", "evidence": "fused pyridinone ring system"}
    if has_coumarin:
        return {"class": "Coumarin / chromone", "evidence": "benzopyranone core"}
    if has_sulfonamide:
        return {"class": "Sulfonamide", "evidence": "ArSO₂N group"}
    if has_tetrazole:
        return {"class": "Tetrazole-bearing (biphenyl sartan-like)", "evidence": "tetrazole ring"}
    # default: count aromatic rings to distinguish poly-aromatic scaffolds
    arom = len(re.findall(r"c\d", s))
    if arom >= 6:
        return {"class": "Poly-aromatic scaffold", "evidence": f"{arom} aromatic ring-closures"}
    return {"class": "Small aromatic / heterocycle", "evidence": "single/few aromatic rings"}


def main():
    tree = json.load(open(os.path.join(DATA, "bloommap.tree.json")))
    vols = json.load(open(os.path.join(DATA, "bloommap.volumes.json")))
    meta = json.load(open(os.path.join(DATA, "bloommap.meta.json")))
    ex = meta["leaf_exemplars"]
    addr_to_leafnum = {v: k for k, v in meta["leaf_number_to_address"].items()}

    uses = {}
    if os.path.exists(USES):
        uses = json.load(open(USES))  # {chembl_id: {known_use, source}}

    members = {}
    MEMBERS = os.path.join(HERE, "members.json")
    if os.path.exists(MEMBERS):
        members = json.load(open(MEMBERS))  # {Lxx: {n_members, top:[{chembl_id,smiles}]}}

    classes = {}

    def annotate(node):
        if node.get("is_leaf"):
            ln = node.get("leaf_number")
            lid = f"L{int(ln):02d}" if ln is not None else None
            e = ex.get(lid, {}) if lid else {}
            smi = e.get("smiles", "")
            sc = structural_class(smi) if smi else {"class": "unknown", "evidence": ""}
            classes.setdefault(sc["class"], 0)
            classes[sc["class"]] += 1
            cid = e.get("chembl_id", "")
            node["leaf_id"] = lid
            node["chembl_id"] = cid
            node["smiles"] = smi
            node["centroid_cosine"] = e.get("centroid_cosine")
            node["structural_class"] = sc["class"]
            node["class_evidence"] = sc["evidence"]
            u = uses.get(cid)
            node["known_use"] = u.get("known_use") if u else None
            node["use_source"] = u.get("source") if u else None
            mem = members.get(lid) if lid else None
            node["members"] = mem.get("top") if mem else []
            node["n_members"] = mem.get("n_members") if mem else node.get("size")
        for c in node.get("children", []):
            annotate(c)

    annotate(tree)

    out = {
        "domain": meta["domain"],
        "n_rows": meta["n_rows"],
        "n_dims": meta["n_dims"],
        "n_leaves": meta["n_leaves"],
        "max_depth": _max_depth(tree),
        "class_histogram": dict(sorted(classes.items(), key=lambda kv: -kv[1])),
        "tree": tree,
    }
    json.dump(out, open(OUT, "w"), indent=1)
    print(f"wrote {OUT}")
    print(f"  {out['n_leaves']} leaves, max depth {out['max_depth']}, "
          f"{len(classes)} structural classes")
    for k, v in out["class_histogram"].items():
        print(f"    {v:>2}  {k}")
    if uses:
        n_used = sum(1 for L in _leaves(tree) if L.get("known_use"))
        print(f"  known-use enrichment present: {n_used}/{out['n_leaves']} leaves")
    else:
        print("  (no uses.json yet — run research_uses.py to enrich)")


def _max_depth(n):
    return max([n["depth"]] + [_max_depth(c) for c in n.get("children", [])])


def _leaves(n):
    return [n] if n.get("is_leaf") else [x for c in n.get("children", []) for x in _leaves(c)]


if __name__ == "__main__":
    main()
