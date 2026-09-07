# UltraDim

**A fast Analytical Vector Store for datasets of extreme dimensionality.**<br>
**Proven at 30 million dimensions, aiming at a billion.**

*🇫🇷 Une version française de ce document se trouve [en bas de page](#ultradim-version-française).*

UltraDim stores, searches, maps, and clusters vectors far beyond the dimensional limits of conventional vector databases: dense data to ~256,000 dimensions, sparse data to tens of millions — proven in production runs at **30,000,000 dimensions** on real chemistry corpora. It is built in Rust, GPU-accelerated on Apple Silicon (Metal) and Vulkan/DX12 platforms, and driven from Python.

The engine is currently in **private early access for scientific research groups**. This repository hosts the programme documents — the code is delivered to participating groups through the [Early Access Programme](EARLY_ACCESS.md).

<p align="center">
  <img src="figures/chembl_50k_30m_bloommap.svg" width="820" alt="BloomMap of 50,000 ChEMBL molecules clustered at 30,000,000 dimensions">
</p>
<p align="center"><i>Chemical space as a BloomMap: 50,000 ChEMBL molecules, hierarchically clustered at their native 30,000,000-dimensional width.</i></p>

---

## Features

- **Native-width ingest** — dense vectors to ~256,000 dimensions; sparse vectors to tens of millions (30M proven), with memory that scales with your non-zeros, not your declared width
- **Self-verifying search** — exact-reranked true-cosine scores, with on-demand recall certificates measured against exact brute force
- **High-throughput dense search** — 1,339 queries/sec at p50 2.99 ms on DBpedia-1M, precision@10 = 0.9945
- **Native UMAP maps** — deterministic, cached, server-side fits at any width; new points placed in milliseconds; incremental re-fit at ~1.5% of rebuild cost; output to 2-D, mid-dimensional (up to 256 components), or spherical
- **k-NN graph builds with quality gates** — every graph carries a measured recall number; maps refuse to fit on graphs below 0.99
- **Clustering at any width** — GPU-resident spherical k-means and hierarchical clustering, with dimension-corrected quality scores comparable across widths
- **Streaming anomaly maps** — score arriving points for novelty against a fitted map, live
- **Factorisation and recommendation** — decode held-out values directly from the index; a parameter-free neighbourhood method competitive with trained baselines on a public benchmark
- **Synthetic data services** — uniform hypersphere banks and k-NN minority-class augmentation for imbalanced datasets
- **BloomMap visualisation** — publication-grade poster rendering of hierarchical clusterings
- **Data operations** — exports to CSV, JSON, Parquet, and Arrow; collection analytics; in-server text embedding
- **Two ways to run** — a gRPC server with a Python client, or an embedded Python wheel with no server at all
- **Provenance throughout** — versioned parameters, seeds, row accounting, and exportable results, so every analytical output can be examined and repeated

## What you can do with it

**Search ultra-wide data, and trust the answers.** UltraDim handles your data at its native width — molecular fingerprints, retail baskets, one-hot genomics, text embeddings — with no feature hashing or truncation on your side. Search results are exact-reranked: the scores you receive are true cosines against your raw vectors, and the index measures its own candidate recall against exact brute-force answers on demand, so every corpus ships with a quality certificate rather than a hope.

**Build living 2-D maps of 30M-dimensional data.** UMAP maps are computed natively on the server — so map-building works at widths where standard tooling cannot load the data at all. Maps are living objects: new points are placed on an existing map in milliseconds, small batches fold in at roughly 1.5% of a rebuild's cost, and the map's version history doubles as a drift detector for your data stream.

<p align="center">
  <img src="figures/umap_chembl_30m.png" width="410" alt="UMAP of 50,000 ChEMBL molecules at 30M dimensions, graph recall 0.9996">
  <img src="figures/umap_mnist_70k.png" width="410" alt="UMAP of MNIST 70,000 digits">
</p>
<p align="center"><i>Left: 50,000 ChEMBL molecules mapped at 30,000,000 raw dimensions — the neighbour graph beneath the map measured recall 0.9996 against the exact oracle. Right: the MNIST 70K sanity map from the same pipeline.</i></p>

**Cluster and score at any width.** Spherical k-means and hierarchical clustering run GPU-resident at extreme dimensionality, with dimension-corrected quality scores that remain comparable across widths — so "is this clustering real?" has a statistical answer at 30M dimensions, not just at 300.

**Run analytics that use the width instead of fighting it.** Anomaly scoring over ultra-wide feature spaces; factorisation that decodes held-out values directly from the index; synthetic data generation and minority-class augmentation; collection analytics; exports for downstream tooling.

<p align="center">
  <img src="figures/stream_anomaly_map.png" width="560" alt="Streaming anomaly map: 987,442 fitted DBpedia articles with 2,904 arrivals coloured by novelty">
</p>
<p align="center"><i>Streaming anomaly detection on a living map: 987,442 fitted DBpedia articles (grey) with 2,904 newly arriving points ringed and coloured by measured novelty — familiar arrivals in green, anomalies in red.</i></p>

<p align="center">
  <img src="figures/stream_dichotomy.png" width="410" alt="Novelty score dichotomy between familiar and novel arrivals">
  <img src="figures/chembl_support_saturation.png" width="410" alt="ChEMBL feature-support saturation across corpus growth">
</p>
<p align="center"><i>Left: the novelty score cleanly separates familiar from novel arrivals. Right: corpus analytics at 30M dimensions — feature-support saturation as the ChEMBL corpus grows.</i></p>

## Measured performance

All numbers are from gated experiment runs against exact brute-force oracles, on a single Apple M3 Max, quality and latency reported together.

| Corpus | Width | Rows | Quality | Latency / throughput |
|---|---|---|---|---|
| ChEMBL molecules (sparse) | 30,000,000 | 500,000 | recall@10 = 0.9992 | 56 ms per query |
| ChEMBL molecules (sparse, fast profile) | 30,000,000 | 500,000 | recall@10 = 0.9964 | 29 ms per query |
| DBpedia embeddings (dense) | 1,536 | 1,000,000 | precision@10 = 0.9945 | 1,339 queries/sec at p50 2.99 ms |
| Retail baskets (sparse) | 100,000 | 100,000 | recall@10 = 0.9851 | p50 17.5 ms |
| Synthetic structured (sparse) | 1,800,000 | 50,000 | recall@10 = 1.000 | p50 15.7 ms |

Width is cheap: taking a corpus from 1M to 10M dimensions adds ~0.08 GiB of resident memory, because sparse storage scales with your non-zeros, not your declared width.

## Early Access Programme

UltraDim is being evaluated with research groups on real scientific workloads — molecular representations, genomic and epigenomic profiles, and large observational matrices. A strong candidate project has a corpus that is high-dimensional, large, sparse, or expensive to analyse with current tools; a defensible vector representation and metric; and a concrete retrieval, cohort, clustering, or visualisation question.

**[How to join the Early Access Programme →](EARLY_ACCESS.md)** — or write to **andrew@gamakon.ai**

## Documents

| Document | Contents |
|---|---|
| [UltraDim Overview](docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research* — motivation, research questions, evaluation principles, and the early-access programme (non-confidential, June 2026) |
| [Testimonials](TESTIMONIALS.md) | What participating groups say |

## About

UltraDim is developed and licensed by **Gamakon Ltd**. The engine is original work by Gamakon throughout: storage, the ultra-dimensional index, filtering, analytics, and the mapping layers are all written in-house in Rust, with no third-party database code or dependency. We are launching commercial access to the database shortly — please [contact us](mailto:andrew@gamakon.ai) for details.

### Origin Story

*How it came about*

Internally, the UltraDim database uses an entirely new form of vector index, developed by Andrew Morgan — author of *Mastering Spark for Data Science*. He invented this index to build and test his ideas for solving the ARC-AGI challenge; that work is still ongoing.

Drawing on thirty years of data science engineering, Andrew implemented it using a long list of optimisations that, along with the new index, allow you to replace a large Spark cluster with a Mac laptop.

Andrew used AI to help, but explains this was extremely frustrating. "AI hates to innovate. As it had never seen this index design before, it continually struggled to contribute anything useful, often wilfully reverting the code back to older ideas." A year of persistent frustration later, the result is a system we're genuinely proud of. We hope you enjoy it, and that you use it to build something remarkable.

---

# UltraDim (version française)

**Un magasin de vecteurs analytique rapide, conçu pour les jeux de données d'une dimensionnalité extrême.**<br>
**Éprouvé à 30 millions de dimensions, avec le milliard en ligne de mire.**

UltraDim stocke, recherche, cartographie et regroupe des vecteurs bien au-delà des limites dimensionnelles des bases de données vectorielles classiques : données denses jusqu'à ~256 000 dimensions, données creuses jusqu'à des dizaines de millions — éprouvé en production à **30 000 000 de dimensions** sur de véritables corpus de chimie. Le moteur est écrit en Rust, accéléré par GPU sur Apple Silicon (Metal) ainsi que sur les plateformes Vulkan/DX12, et se pilote depuis Python.

Le moteur est actuellement en **accès anticipé privé, réservé aux groupes de recherche scientifique**. Ce dépôt héberge les documents du programme — le code est fourni aux groupes participants dans le cadre du [Programme d'accès anticipé](EARLY_ACCESS.md).

<p align="center">
  <img src="figures/chembl_50k_30m_bloommap.svg" width="820" alt="BloomMap de 50 000 molécules ChEMBL regroupées à 30 000 000 de dimensions">
</p>
<p align="center"><i>L'espace chimique sous forme de BloomMap : 50 000 molécules ChEMBL, regroupées hiérarchiquement à leur largeur native de 30 000 000 de dimensions.</i></p>

---

## Fonctionnalités

- **Ingestion à la largeur native** — vecteurs denses jusqu'à ~256 000 dimensions ; vecteurs creux jusqu'à des dizaines de millions (30 M éprouvés), avec une empreinte mémoire proportionnelle à vos valeurs non nulles, et non à la largeur déclarée
- **Recherche autovérifiée** — scores de cosinus exacts obtenus par reclassement, avec des certificats de rappel mesurés à la demande contre une recherche exhaustive exacte
- **Recherche dense à haut débit** — 1 339 requêtes/s à 2,99 ms au p50 sur DBpedia-1M, précision@10 = 0,9945
- **Cartes UMAP natives** — ajustements déterministes, mis en cache et exécutés côté serveur à n'importe quelle largeur ; nouveaux points placés en quelques millisecondes ; réajustement incrémental à ~1,5 % du coût d'une reconstruction ; sortie en 2-D, en dimension intermédiaire (jusqu'à 256 composantes) ou sphérique
- **Construction de graphes k-NN avec seuils de qualité** — chaque graphe porte une mesure de rappel ; les cartes refusent de s'ajuster sur un graphe en dessous de 0,99
- **Regroupement à n'importe quelle largeur** — k-means sphérique et regroupement hiérarchique résidents en GPU, avec des scores de qualité corrigés de la dimension, comparables d'une largeur à l'autre
- **Cartes d'anomalies en flux** — évaluation de la nouveauté des points entrants contre une carte ajustée, en direct
- **Factorisation et recommandation** — décodage des valeurs retenues directement depuis l'index ; une méthode de voisinage sans paramètre, compétitive face à des références entraînées sur un banc d'essai public
- **Services de données synthétiques** — banques d'hypersphères uniformes et augmentation k-NN des classes minoritaires pour les jeux de données déséquilibrés
- **Visualisation BloomMap** — rendu d'affiches de qualité publication pour les regroupements hiérarchiques
- **Opérations sur les données** — exports vers CSV, JSON, Parquet et Arrow ; analyses de collections ; génération d'embeddings de texte dans le serveur
- **Deux modes d'exécution** — un serveur gRPC avec un client Python, ou un paquet Python embarqué, sans serveur du tout
- **Traçabilité de bout en bout** — paramètres versionnés, graines aléatoires, comptage des lignes et résultats exportables, afin que chaque sortie analytique puisse être examinée et reproduite

## Ce que vous pouvez en faire

**Rechercher dans des données ultra-larges, et vous fier aux réponses.** UltraDim traite vos données à leur largeur native — empreintes moléculaires, paniers d'achat, génomique en encodage one-hot, embeddings de texte — sans hachage de caractéristiques ni troncature de votre côté. Les résultats de recherche sont reclassés exactement : les scores que vous recevez sont de vrais cosinus calculés sur vos vecteurs bruts, et l'index mesure à la demande son propre rappel de candidats contre les réponses exhaustives exactes ; chaque corpus est ainsi livré avec un certificat de qualité plutôt qu'avec un espoir.

**Construire des cartes 2-D vivantes de données à 30 M de dimensions.** Les cartes UMAP sont calculées nativement sur le serveur — la construction de cartes fonctionne donc à des largeurs où les outils standard ne parviennent même pas à charger les données. Ces cartes sont des objets vivants : de nouveaux points sont placés sur une carte existante en quelques millisecondes, de petits lots s'y intègrent pour environ 1,5 % du coût d'une reconstruction, et l'historique des versions de la carte fait office de détecteur de dérive pour votre flux de données.

<p align="center">
  <img src="figures/umap_chembl_30m.png" width="410" alt="UMAP de 50 000 molécules ChEMBL à 30 M de dimensions, rappel du graphe 0,9996">
  <img src="figures/umap_mnist_70k.png" width="410" alt="UMAP des 70 000 chiffres MNIST">
</p>
<p align="center"><i>À gauche : 50 000 molécules ChEMBL cartographiées à 30 000 000 de dimensions brutes — le graphe de voisinage sous-jacent affiche un rappel mesuré de 0,9996 face à l'oracle exact. À droite : la carte de contrôle MNIST 70K, issue du même pipeline.</i></p>

**Regrouper et évaluer à n'importe quelle largeur.** Le k-means sphérique et le regroupement hiérarchique s'exécutent en résidence GPU à une dimensionnalité extrême, avec des scores de qualité corrigés de la dimension qui restent comparables d'une largeur à l'autre — ainsi, la question « ce regroupement est-il réel ? » reçoit une réponse statistique à 30 M de dimensions, et pas seulement à 300.

**Mener des analyses qui exploitent la largeur au lieu de la combattre.** Détection d'anomalies dans des espaces de caractéristiques ultra-larges ; factorisation décodant les valeurs retenues directement depuis l'index ; génération de données synthétiques et augmentation des classes minoritaires ; analyses de collections ; exports vers les outils en aval.

<p align="center">
  <img src="figures/stream_anomaly_map.png" width="560" alt="Carte d'anomalies en flux : 987 442 articles DBpedia ajustés, avec 2 904 arrivées colorées selon leur nouveauté">
</p>
<p align="center"><i>Détection d'anomalies en flux sur une carte vivante : 987 442 articles DBpedia ajustés (en gris) et 2 904 points nouvellement arrivés, cerclés et colorés selon leur nouveauté mesurée — arrivées familières en vert, anomalies en rouge.</i></p>

<p align="center">
  <img src="figures/stream_dichotomy.png" width="410" alt="Dichotomie des scores de nouveauté entre arrivées familières et nouvelles">
  <img src="figures/chembl_support_saturation.png" width="410" alt="Saturation du support des caractéristiques ChEMBL à mesure que le corpus grandit">
</p>
<p align="center"><i>À gauche : le score de nouveauté sépare nettement les arrivées familières des nouvelles. À droite : analyse de corpus à 30 M de dimensions — la saturation du support des caractéristiques à mesure que le corpus ChEMBL grandit.</i></p>

## Performances mesurées

Tous les chiffres proviennent d'expériences contrôlées, exécutées contre des oracles exhaustifs exacts sur un seul Apple M3 Max ; qualité et latence sont rapportées ensemble.

| Corpus | Largeur | Lignes | Qualité | Latence / débit |
|---|---|---|---|---|
| Molécules ChEMBL (creux) | 30 000 000 | 500 000 | rappel@10 = 0,9992 | 56 ms par requête |
| Molécules ChEMBL (creux, profil rapide) | 30 000 000 | 500 000 | rappel@10 = 0,9964 | 29 ms par requête |
| Embeddings DBpedia (denses) | 1 536 | 1 000 000 | précision@10 = 0,9945 | 1 339 requêtes/s à 2,99 ms au p50 |
| Paniers d'achat (creux) | 100 000 | 100 000 | rappel@10 = 0,9851 | p50 17,5 ms |
| Données structurées synthétiques (creuses) | 1 800 000 | 50 000 | rappel@10 = 1,000 | p50 15,7 ms |

La largeur coûte peu : faire passer un corpus de 1 M à 10 M de dimensions n'ajoute que ~0,08 Gio de mémoire résidente, car le stockage creux évolue avec vos valeurs non nulles, et non avec la largeur déclarée.

## Programme d'accès anticipé

UltraDim est évalué avec des groupes de recherche sur de véritables charges de travail scientifiques — représentations moléculaires, profils génomiques et épigénomiques, et grandes matrices d'observation. Un projet candidat solide dispose d'un corpus à haute dimensionnalité, volumineux, creux ou coûteux à analyser avec les outils actuels ; d'une représentation vectorielle et d'une métrique défendables ; ainsi que d'une question concrète de recherche, de cohorte, de regroupement ou de visualisation.

**[Comment rejoindre le Programme d'accès anticipé →](EARLY_ACCESS.md)** — ou écrivez à **andrew@gamakon.ai**

## Documents

| Document | Contenu |
|---|---|
| [Présentation d'UltraDim](docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research* — motivations, questions de recherche, principes d'évaluation et programme d'accès anticipé (document non confidentiel, juin 2026, en anglais) |
| [Témoignages](TESTIMONIALS.md) | Ce qu'en disent les groupes participants |

## À propos

UltraDim est développé et distribué sous licence par **Gamakon Ltd**. Le moteur est entièrement l'œuvre originale de Gamakon : le stockage, l'index ultra-dimensionnel, le filtrage, l'analyse et les couches de cartographie sont tous écrits en interne en Rust, sans aucun code ni dépendance de base de données tierce. Nous lancerons prochainement l'accès commercial à la base de données — [contactez-nous](mailto:andrew@gamakon.ai) pour en savoir plus.

### Genèse du projet

*Comment tout a commencé*

En interne, la base de données UltraDim repose sur une forme entièrement nouvelle d'index vectoriel, mise au point par Andrew Morgan — auteur de *Mastering Spark for Data Science*. Il a inventé cet index pour construire et éprouver ses idées de résolution du défi ARC-AGI ; ces travaux se poursuivent encore aujourd'hui.

Fort de trente années d'ingénierie en science des données, Andrew l'a implémenté à l'aide d'une longue liste d'optimisations qui, conjuguées au nouvel index, permettent de remplacer un large cluster Spark par un ordinateur portable Mac.

Andrew s'est fait aider par l'IA, mais explique que l'expérience fut extrêmement frustrante. « L'IA déteste innover. N'ayant jamais rencontré ce type d'index auparavant, elle peinait constamment à apporter quoi que ce soit d'utile, revenant souvent délibérément à d'anciennes idées dans le code. » Après une année de frustration persistante, le résultat est un système dont nous sommes véritablement fiers. Nous espérons qu'il vous plaira et qu'il vous servira à bâtir quelque chose de remarquable.
