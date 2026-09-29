#!/usr/bin/env python3
"""Package the Chemotype Galaxy as a standalone, double-clickable app.

The only thing that breaks a plain file:// double-click is the d3.json() fetch
(browsers block local fetches). This script produces a build where the data is
INLINED into the HTML as a <script> variable, so there is no fetch at all and the
app opens by double-clicking index.html with no server. Vendored libs
(d3 / seedrandom / smiles-drawer) load fine from file://.

Output: dist/chemotype-galaxy/  (index.html + lib/ + README) and a .zip of it.
Run: /opt/anaconda3/bin/python3 BloomMap/galaxy/package_standalone.py
"""
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist", "chemotype-galaxy")
ZIP_BASE = os.path.join(HERE, "dist", "chemotype-galaxy")

README = """Chemotype Galaxy — standalone cluster browser
=============================================

An interactive map of 50,000 ChEMBL molecules clustered at 30,000,000 dimensions
(folded Morgan r=2 fingerprints) into 49 chemotype leaves by UltraDim k-means.

HOW TO USE
  Double-click  index.html  (opens in your default browser; no install, no server,
  works fully offline). Click any outer node (a chemotype leaf) to inspect:
    - the cluster's most central molecule, drawn as a 2D structure;
    - its structural class (derived from the SMILES);
    - its known use (ChEMBL-documented assay target / activity);
    - population, cohesion lift, exemplar cosine, SMILES, and a ChEMBL link.

  Inner grey nodes are internal tree splits; depth rings show how deep the
  divisive hierarchy cut. Leaf colour = structural class (see legend).

NOTES
  - All data is embedded in index.html; nothing is fetched.
  - Known-use labels describe documented research/assay activity, NOT approved
    clinical indications (these are research compounds).
  - Built entirely from the BloomMap clustering outputs; no re-clustering.
"""


def main():
    data = json.load(open(os.path.join(HERE, "galaxy.json")))
    html = open(os.path.join(HERE, "galaxy.html")).read()

    # Replace the d3.json(...).then(data => { ... }) fetch with an inline IIFE that
    # uses the embedded GALAXY_DATA. We keep the body identical by binding `data`.
    inline = (
        "const GALAXY_DATA = " + json.dumps(data) + ";\n"
        "(function(){ const data = GALAXY_DATA;\n"
    )
    needle = 'd3.json("galaxy.json").then(data => {'
    assert needle in html, "could not find the d3.json call to inline"
    html = html.replace(needle, inline)
    # close: the original ended with `}).catch(err => {...});` — turn the .then
    # closure end `})` into the IIFE end `})()`; the catch is dropped (no fetch).
    tail = ('}).catch(err => { d3.select("#subtitle").text("failed to load '
            'galaxy.json: "+err); });')
    assert tail in html, "could not find the .then/.catch tail to close"
    html = html.replace(tail, "})();")

    # fresh dist
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(os.path.join(DIST, "lib"))
    open(os.path.join(DIST, "index.html"), "w").write(html)
    for f in ("d3.v6.min.js", "seedrandom.min.js", "smiles-drawer.min.js"):
        shutil.copy(os.path.join(HERE, "lib", f), os.path.join(DIST, "lib", f))
    open(os.path.join(DIST, "README.txt"), "w").write(README)

    zip_path = shutil.make_archive(ZIP_BASE, "zip", os.path.dirname(DIST),
                                   os.path.basename(DIST))
    size = os.path.getsize(zip_path)
    print(f"standalone build -> {DIST}")
    print(f"  index.html ({len(html)//1024} KB, data inlined, zero fetch)")
    print(f"zip -> {zip_path} ({size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
