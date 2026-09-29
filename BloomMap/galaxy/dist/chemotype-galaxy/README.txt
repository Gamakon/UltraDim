Chemotype Galaxy — standalone cluster browser
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
