# UltraDim

**A fast Analytical Vector Store for datasets of extreme dimensionality.**<br>
**Proven at 30 million dimensions, aiming at a billion.**

*New to this? [For the non-technical: what is highly dimensional sparse data?](docs/WHAT_IS_HIGH_DIMENSIONAL_SPARSE_DATA.md)*

*🇫🇷 Une version française de ce document se trouve [en bas de page](#ultradim-version-française). Other languages: [العربية](multilingual/ar_README.md) · [বাংলা](multilingual/bn_README.md) · [Български](multilingual/bg_README.md) · [Deutsch](multilingual/de_README.md) · [Español](multilingual/es_README.md) · [हिन्दी](multilingual/hi_README.md) · [Italiano](multilingual/it_README.md) · [Polski](multilingual/pl_README.md) · [Português](multilingual/pt_README.md) · [தமிழ்](multilingual/ta_README.md) · [한국어](multilingual/ko_README.md) · [日本語](multilingual/ja_README.md) · [中文](multilingual/zh_README.md).*

UltraDim stores, searches, maps, classifies and clusters vectors far beyond the dimensional limits of conventional vector databases: dense data to ~256,000 dimensions, sparse data to tens of millions — proven in production runs at **30,000,000 dimensions** on real chemistry corpora, with demonstrations at 100 million dimensions. It is built in Rust, GPU-accelerated through Metal on macOS and Vulkan on Linux, and driven from Python.

UltraDim ships as a compiled Python wheel for macOS on Apple silicon, Linux x86_64 and Linux arm64, for Python 3.12. The current release is 0.4.0, on the [Releases](../../releases) page. Noncommercial use is free under the PolyForm Noncommercial License 1.0.0. Commercial use needs a licence from Gamakon Ltd. The licence text is [`LICENSE`](LICENSE); the notice that explains both tracks is [`LICENSES/LICENSE.md`](LICENSES/LICENSE.md).

<p align="center">
  <img src="figures/chembl_50k_30m_bloommap.svg" width="820" alt="BloomMap of 50,000 ChEMBL molecules clustered at 30,000,000 dimensions">
</p>
<p align="center"><i>Chemical space as a BloomMap: 50,000 ChEMBL molecules, hierarchically clustered at their native 30,000,000-dimensional width.</i></p>

---

## Features

- **Ultra-dimensional data loading** — ingest big dense vectors, tested to ~256,000 dimensions; or big sparse vectors, tested to 30 million with 100M demonstrated. Your RAM and disk requirements scale with your non-zeros, not raw vector size.
- **Self-verifying search** — exact true-cosine scores, with on-demand recall certificates measured against exact brute force
- **High-throughput dense search** — 1,339 queries/sec at p50 2.99 ms on DBpedia-1M, precision@10 = 0.9945
- **Native UMAP maps** — deterministic, cached, fast UMAP implementation for ultra-dimensional datasets. New unseen points scored in milliseconds; incremental re-fit included at ~1.5% of a rebuild cost; outputs between 2-D and 256-D supporting visualisation and dimensionality reduction.
- **k-NN graph builds with quality thresholds** — every graph carries a measured recall number; maps refuse to fit on graphs below 0.99
- **Clustering for ultra-dimensional data, even 30 million dimensions** — GPU-resident spherical k-means and hierarchical clustering, with dimension-corrected quality scores comparable across widths
- **Streaming high-d anomaly detection** — score arrivals against the existing high-dimensional nearest-neighbour structure, then place them on a living UMAP so anomalous and emerging populations become visible; the streaming figure below is a short script over the map-transform RPC
- **Factorisation and recommendation** — decode held-out values directly from the index; a parameter-free neighbourhood method competitive with trained baselines on a public benchmark
- **Generate synthetic data on hyperspheres** — the code offers wgpu generation of Muller-Marsaglia uniform points on the hypersphere surface where our data index exists. It is part of an experimental method to re-balance datasets by applying a real point's minority label to its k closest synthetic neighbours.
- **BloomMap visualisation** — publication-grade poster rendering of hierarchical clusterings
- **Data operations** — exports to CSV, JSON and a binary format; collection analytics; in-server text embedding
- **Three ways to run** — in your own process as a Python wheel; as an MCP server for an assistant; or as a shared server that many clients reach over a port by gRPC, available on request. The same 204 RPCs on all three.
- **Provenance throughout** — versioned parameters, seeds, row accounting, and exportable results, so every analytical output can be examined and repeated

## Get it

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install ./UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl      # numpy comes with it
```

```python
import ultradim
db = ultradim.UltraDim("./db")
print(len(db.capabilities()))          # 204
db.call_json("RpcName", '{...}')       # any of them
```

The database runs inside your process. There is no server to start and no port to open. A GPU is used when one is present (Metal on macOS, Vulkan on Linux). Without a GPU, UltraDim loads, indexes and searches sparse and dense data, builds neighbour graphs and density lineages, and measures recall. UMAP fits, k-means clustering and k-means lineages need a GPU and return an error without one. Measured in [`docs/GPU_SETTINGS.md`](docs/GPU_SETTINGS.md).

An MCP server, `mcp/ultradim_mcp_server_v0_4_0.py`, wraps the same wheel as 46 tools so an assistant can create collections, ingest, index, search, cluster and map without you writing Python. Its guide is [`mcp/README.md`](mcp/README.md).

A client-server version is available. One UltraDim server runs on a host and is shared by many clients over a port. Clients write and query over gRPC. gRPC is a compact binary protocol, so ingest of wide vectors is fast on the wire. It is the same engine as the wheel, with the same 204 RPCs. Get in touch to obtain it. That includes noncommercial organisations who need it: we can help you install it and set it up. jesung@gamakon.ai or andrew@gamakon.ai.

## Run it with an AI assistant

The repository ships an MCP server, `mcp/ultradim_mcp_server_v0_4_0.py`, that exposes the database as 46 tools to Claude Code, Codex, or any assistant that speaks MCP. The assistant then runs the database on your behalf: it creates the family, ingests your vectors, builds the index, searches, clusters and maps, and reads the results back to you. You describe the study; it does the calls.

Install the wheel, clone this repository, and open an assistant session in the clone. For Claude Code the `.mcp.json` at the root registers the server; for Codex add to `~/.codex/config.toml`:

```toml
[mcp_servers.ultradim]
command = "python3.12"
args = ["/path/to/UltraDim/mcp/ultradim_mcp_server_v0_4_0.py", "--db", "/path/to/your/db"]
```

`command` must be the Python that has the wheel installed. Then ask, in words: "load the vectors in this file into UltraDim, make them searchable, and show me a map." The assistant's first call should be the `whats_available` tool, which lists every tool and the happy path live from the wheel. The full guide is [`mcp/README.md`](mcp/README.md).

## What you can do with it

**Search ultra-wide data, and trust the answers.** UltraDim handles your data at its native width — molecular fingerprints, retail baskets, one-hot genomics, text embeddings — with no feature hashing or truncation on your side. The scores you receive are true cosines against your raw vectors, and the index measures its own candidate recall against exact brute-force answers on demand, so every corpus ships with a quality certificate rather than a hope.

**Build living 2-D maps of 30M-dimensional data.** UMAP maps are computed natively on the server — so map-building works at widths where standard tooling cannot load the data at all. Maps are living objects: new points are placed on an existing map in milliseconds, small batches fold in at roughly 1.5% of a rebuild's cost, and the map's version history doubles as a drift detector for your data stream.

<p align="center">
  <img src="figures/umap_chembl_30m.png" width="410" alt="UMAP of 50,000 ChEMBL molecules at 30M dimensions, graph recall 0.9996">
  <img src="figures/umap_mnist_70k.png" width="410" alt="UMAP of MNIST 70,000 digits">
</p>
<p align="center"><i>Left: 50,000 ChEMBL molecules mapped at 30,000,000 raw dimensions — the neighbour graph beneath the map measured recall 0.9996 against the exact oracle. Right: the MNIST 70K sanity map from the same pipeline.</i></p>

<p align="center">
  <img src="figures/forex_umap_2007_2026.gif" width="560" alt="The foreign-exchange market as a living map, 2007 to 2026, one point per trading day">
</p>
<p align="center"><i>Thirty years of the foreign-exchange market on one map. Each point is one trading day, described by the standardised returns of 1,992 currency pairs that day, and days that moved alike sit together. The map was fitted on the first 3,000 days and every later day was placed into it as it arrived, every session from January 1996 to April 2026, coloured by year. What the map shows is that the dynamics of the market change from year to year, and often wildly. A trading strategy built on one year's days has little scope beyond it before it loses value. The first ten years built the base map, so the animation shows 2007 to 2026; the <a href="figures/forex_market_full_1996_2026.mp4">full run from 1996</a> is an eight-minute video. Learn to make one of these diagrams yourself from our example, <a href="examples/04_living_map_animation.py">examples/04_living_map_animation.py</a>.</i></p>

**Cluster and score at any width.** Spherical k-means and hierarchical clustering run GPU-resident at extreme dimensionality, with dimension-corrected quality scores that remain comparable across widths — so "is this clustering real?" has a statistical answer at 30M dimensions, not just at 300.

**Run analytics that use the width instead of fighting it.** Novelty scoring of arrivals on a fitted map; factorisation that decodes held-out values directly from the index; synthetic data generation and minority-class augmentation; collection analytics; exports for downstream tooling.

<p align="center">
  <img src="figures/stream_anomaly_map.png" width="560" alt="Streaming anomaly map: 987,442 fitted DBpedia articles with 2,904 arrivals coloured by novelty">
</p>
<p align="center"><i>Streaming novelty detection, shown on a living map: 987,442 fitted DBpedia articles (grey) with 2,904 newly arriving points ringed and coloured by measured novelty — familiar arrivals in green, anomalies in red.</i></p>

<p align="center">
  <img src="figures/stream_dichotomy.png" width="410" alt="Novelty score dichotomy between familiar and new arrivals">
  <img src="figures/chembl_support_saturation.png" width="410" alt="ChEMBL feature-support saturation across corpus growth">
</p>
<p align="center"><i>Left: the novelty score cleanly separates familiar from new arrivals. Right: corpus analytics at 30M dimensions — feature-support saturation as the ChEMBL corpus grows.</i></p>

## Measured performance

All numbers are from controlled experiment runs against exact brute-force oracles, on a single Apple M3 Max, quality and latency reported together.

| Corpus | Width | Rows | Quality | Latency / throughput |
|---|---|---|---|---|
| ChEMBL molecules (sparse) | 30,000,000 | 500,000 | recall@10 = 0.9992 | 56 ms per query |
| ChEMBL molecules (sparse, fast profile) | 30,000,000 | 500,000 | recall@10 = 0.9964 | 29 ms per query |
| DBpedia embeddings (dense) | 1,536 | 1,000,000 | precision@10 = 0.9945 | 1,339 queries/sec at p50 2.99 ms |
| Retail baskets (sparse) | 100,000 | 100,000 | recall@10 = 0.9851 | p50 17.5 ms |
| Synthetic structured (sparse) | 1,800,000 | 50,000 | recall@10 = 1.000 | p50 15.7 ms |

Width costs little: taking a corpus from 1M to 10M dimensions adds ~0.08 GiB of resident memory, because sparse storage scales with your non-zeros, not your declared width.

## Working with research groups

UltraDim is used by research groups on real scientific workloads — molecular representations, genomic and epigenomic profiles, and large observational matrices. Research use is free under the noncommercial licence; download the wheel and start. A good project has a corpus that is high-dimensional, large, sparse, or slow to analyse with current tools; a defensible vector representation and metric; and a retrieval, cohort, clustering, or visualisation question.

**[Working with research groups →](RESEARCH_GROUPS.md)** — or write to **andrew@gamakon.ai** for help with your corpus, or about commercial use.

## Documents

| Document | Contents |
|---|---|
| [UltraDim Overview](docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research* — motivation, research questions, evaluation principles (non-confidential, June 2026) |
| [Testimonials](TESTIMONIALS.md) | What participating groups say |
| [User guide](docs/UltraDim_User_Guide.md) | Install, a dense quickstart, a sparse worked example, recall, maps, clustering, the RPC list, the auto-tuner |
| [Tuning guide](docs/UltraDim_Tuning_Guide.md) | What moves recall, what does not, what to do when recall falls below tolerance |
| [Replacing and deleting rows](docs/SPARSE_UPSERT_SEMANTICS.md) | Row ids, facets, retries, durability |
| [Running with and without a GPU](docs/GPU_SETTINGS.md) | What needs a GPU, measured; the two settings |
| [MCP server guide](mcp/README.md) | Install, upgrade, every tool, the happy path, release notes |
| [Changelog](CHANGELOG.md) | Every release, 0.1 to 0.4.0 |

## About

UltraDim is developed and licensed by **Gamakon Ltd**. Noncommercial use is free under the PolyForm Noncommercial License 1.0.0. A client-server version is available on request, including to noncommercial organisations who need it; we can help you install and set it up. Write to [jesung@gamakon.ai](mailto:jesung@gamakon.ai) or [andrew@gamakon.ai](mailto:andrew@gamakon.ai).

### Origin Story

*How it came about*

Internally, the UltraDim database uses an entirely new form of vector index, developed by Andrew Morgan — author of *Mastering Spark for Data Science*. He invented this index to build and test his ideas for solving the ARC-AGI challenge; that work is still ongoing.

Drawing on thirty years of data science engineering, Andrew implemented it using a long list of optimisations that, along with the new index, allow you to replace a large Spark cluster with a Mac laptop.

Andrew used AI to help, but explains this was extremely frustrating. "AI hates to innovate. As it had never seen this index design before, it continually struggled to contribute anything useful, often wilfully reverting the code back to older ideas." A year of persistent frustration later, the result is a system we're genuinely proud of. We hope you enjoy it, and that you use it to build something remarkable.

---

# UltraDim (version française)

**Une base de données vectorielle analytique rapide, conçue pour les jeux de données d'une dimensionnalité extrême.**<br>
**Éprouvé à 30 millions de dimensions, avec le milliard en ligne de mire.**

*Nouveau dans ce domaine ? [Pour les non-spécialistes : qu'est-ce que des données creuses de haute dimension ?](multilingual/fr_WHAT_IS_HIGH_DIMENSIONAL_SPARSE_DATA.md)*

UltraDim stocke, recherche, cartographie, classifie et regroupe des vecteurs bien au-delà des limites dimensionnelles des bases de données vectorielles classiques : données denses jusqu'à ~256 000 dimensions, données creuses jusqu'à des dizaines de millions — éprouvé en production à **30 000 000 de dimensions** sur de véritables corpus de chimie, avec des démonstrations à 100 millions de dimensions. Le moteur est écrit en Rust, accéléré par GPU via Metal sur macOS et Vulkan sur Linux, et se pilote depuis Python.

UltraDim est livré sous forme de paquet Python compilé (wheel) pour macOS sur Apple Silicon, Linux x86_64 et Linux arm64, pour Python 3.12. La version actuelle est la 0.4.0, sur la page [Releases](../../releases). L'usage non commercial est gratuit, sous la licence PolyForm Noncommercial 1.0.0. L'usage commercial nécessite une licence de Gamakon Ltd. Le texte de la licence est [`LICENSE`](LICENSE) ; la notice qui explique les deux régimes est [`LICENSES/LICENSE.md`](LICENSES/LICENSE.md).

<p align="center">
  <img src="figures/chembl_50k_30m_bloommap.svg" width="820" alt="BloomMap de 50 000 molécules ChEMBL regroupées à 30 000 000 de dimensions">
</p>
<p align="center"><i>L'espace chimique sous forme de BloomMap : 50 000 molécules ChEMBL, regroupées hiérarchiquement à leur largeur native de 30 000 000 de dimensions.</i></p>

---

## Fonctionnalités

- **Chargement de données ultradimensionnelles** — ingérez de grands vecteurs denses, éprouvés jusqu'à ~256 000 dimensions ; ou de grands vecteurs creux, éprouvés jusqu'à 30 millions, avec 100 M démontrés. Vos besoins en RAM et en disque évoluent avec vos valeurs non nulles, et non avec la taille brute du vecteur.
- **Recherche autovérifiée** — scores de cosinus exacts, avec des certificats de rappel mesurés à la demande contre une recherche exhaustive exacte
- **Recherche dense à haut débit** — 1 339 requêtes/s à 2,99 ms au p50 sur DBpedia-1M, précision@10 = 0,9945
- **Cartes UMAP natives** — implémentation UMAP déterministe, mise en cache et rapide pour les jeux de données ultra-dimensionnels. Les nouveaux points inconnus sont placés en quelques millisecondes ; le réajustement incrémental est inclus, à ~1,5 % du coût d'une reconstruction ; sorties de 2-D à 256-D, pour la visualisation comme pour la réduction de dimension.
- **Construction de graphes k-NN avec seuils de qualité** — chaque graphe porte une mesure de rappel ; les cartes refusent de s'ajuster sur un graphe en dessous de 0,99
- **Regroupement pour les données ultradimensionnelles, jusqu'à 30 millions de dimensions** — k-means sphérique et regroupement hiérarchique résidents en GPU, avec des scores de qualité corrigés de la dimension, comparables d'une largeur à l'autre
- **Détection d'anomalies en haute dimension, en flux** — évaluer les arrivées contre la structure de plus proches voisins existante en haute dimension, puis les placer sur une carte UMAP vivante pour rendre visibles les populations anormales et émergentes ; la figure en flux ci-dessous est un court script au-dessus du RPC de transformation de carte
- **Factorisation et recommandation** — décodage des valeurs retenues directement depuis l'index ; une méthode de voisinage sans paramètre, compétitive face à des références entraînées sur un banc d'essai public
- **Générer des données synthétiques sur des hypersphères** — le code offre une génération wgpu de points uniformes de Muller-Marsaglia sur la surface de l'hypersphère où réside notre index de données. Elle fait partie d'une méthode expérimentale de rééquilibrage des jeux de données, qui applique l'étiquette minoritaire d'un point réel à ses k plus proches voisins synthétiques.
- **Visualisation BloomMap** — rendu d'affiches de qualité publication pour les regroupements hiérarchiques
- **Opérations sur les données** — exports vers CSV, JSON et un format binaire ; analyses de collections ; génération d'embeddings de texte dans le serveur
- **Trois modes d'exécution** — dans votre propre processus, sous forme de paquet Python ; comme serveur MCP pour un assistant ; ou comme serveur partagé que de nombreux clients atteignent par gRPC sur un port, disponible sur demande. Les mêmes 204 RPC dans les trois cas.
- **Traçabilité de bout en bout** — paramètres versionnés, graines aléatoires, comptage des lignes et résultats exportables, afin que chaque sortie analytique puisse être examinée et reproduite

## Obtenir UltraDim

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install ./UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl      # numpy est installé avec
```

```python
import ultradim
db = ultradim.UltraDim("./db")
print(len(db.capabilities()))          # 204
db.call_json("RpcName", '{...}')       # n'importe lequel d'entre eux
```

La base de données s'exécute dans votre processus. Il n'y a ni serveur à démarrer ni port à ouvrir. Un GPU est utilisé lorsqu'il y en a un (Metal sur macOS, Vulkan sur Linux). Sans GPU, UltraDim charge, indexe et recherche des données creuses et denses, construit des graphes de voisinage et des lignées de densité, et mesure le rappel. Les ajustements UMAP, le regroupement k-means et les lignées k-means nécessitent un GPU et renvoient une erreur sans lui. Mesuré dans [`docs/GPU_SETTINGS.md`](docs/GPU_SETTINGS.md).

Un serveur MCP, `mcp/ultradim_mcp_server_v0_4_0.py`, enveloppe le même paquet sous forme de 46 outils, afin qu'un assistant puisse créer des collections, ingérer, indexer, rechercher, regrouper et cartographier sans que vous écriviez de Python. Son guide est [`mcp/README.md`](mcp/README.md).

Une version client-serveur est disponible. Un serveur UltraDim s'exécute sur une machine hôte et est partagé par de nombreux clients sur un port. Les clients écrivent et interrogent par gRPC. gRPC est un protocole binaire compact, si bien que l'ingestion de vecteurs larges est rapide sur le réseau. C'est le même moteur que le paquet, avec les mêmes 204 RPC. Contactez-nous pour l'obtenir. Cela vaut aussi pour les organisations non commerciales qui en ont besoin : nous pouvons vous aider à l'installer et à le configurer. jesung@gamakon.ai ou andrew@gamakon.ai.

## L'utiliser avec un assistant IA

Le dépôt fournit un serveur MCP, `mcp/ultradim_mcp_server_v0_4_0.py`, qui expose la base de données sous forme de 46 outils à Claude Code, à Codex ou à tout assistant parlant MCP. L'assistant fait alors fonctionner la base de données à votre place : il crée la famille, ingère vos vecteurs, construit l'index, cherche, regroupe et cartographie, puis vous lit les résultats. Vous décrivez l'étude ; il passe les appels.

Installez le paquet, clonez ce dépôt et ouvrez une session d'assistant dans le clone. Pour Claude Code, le fichier `.mcp.json` à la racine enregistre le serveur ; pour Codex, ajoutez à `~/.codex/config.toml` :

```toml
[mcp_servers.ultradim]
command = "python3.12"
args = ["/chemin/vers/UltraDim/mcp/ultradim_mcp_server_v0_4_0.py", "--db", "/chemin/vers/votre/base"]
```

`command` doit être le Python où le paquet est installé. Puis demandez, en clair : « charge les vecteurs de ce fichier dans UltraDim, rends-les interrogeables et montre-moi une carte ». Le premier appel de l'assistant doit être l'outil `whats_available`, qui liste chaque outil et le chemin nominal directement depuis le paquet. Le guide complet est [`mcp/README.md`](mcp/README.md) (en anglais).

## Ce que vous pouvez en faire

**Rechercher dans des données ultra-larges, et vous fier aux réponses.** UltraDim traite vos données à leur largeur native — empreintes moléculaires, paniers d'achat, génomique en encodage one-hot, embeddings de texte — sans hachage de caractéristiques ni troncature de votre côté. Les scores que vous recevez sont de vrais cosinus calculés sur vos vecteurs bruts, et l'index mesure à la demande son propre rappel de candidats contre les réponses exhaustives exactes ; chaque corpus est ainsi livré avec un certificat de qualité plutôt qu'avec un espoir.

**Construire des cartes 2-D vivantes de données à 30 M de dimensions.** Les cartes UMAP sont calculées nativement sur le serveur — la construction de cartes fonctionne donc à des largeurs où les outils standard ne parviennent même pas à charger les données. Ces cartes sont des objets vivants : de nouveaux points sont placés sur une carte existante en quelques millisecondes, de petits lots s'y intègrent pour environ 1,5 % du coût d'une reconstruction, et l'historique des versions de la carte fait office de détecteur de dérive pour votre flux de données.

<p align="center">
  <img src="figures/umap_chembl_30m.png" width="410" alt="UMAP de 50 000 molécules ChEMBL à 30 M de dimensions, rappel du graphe 0,9996">
  <img src="figures/umap_mnist_70k.png" width="410" alt="UMAP des 70 000 chiffres MNIST">
</p>
<p align="center"><i>À gauche : 50 000 molécules ChEMBL cartographiées à 30 000 000 de dimensions brutes — le graphe de voisinage sous-jacent affiche un rappel mesuré de 0,9996 face à l'oracle exact. À droite : la carte de contrôle MNIST 70K, issue du même pipeline.</i></p>

<p align="center">
  <img src="figures/forex_umap_2007_2026.gif" width="560" alt="Le marché des changes sous forme de carte vivante, de 2007 à 2026, un point par jour de cotation">
</p>
<p align="center"><i>Trente ans du marché des changes sur une seule carte. Chaque point est un jour de cotation, décrit par les rendements standardisés de 1 992 paires de devises ce jour-là, et les jours qui ont évolué de façon semblable sont voisins. La carte a été ajustée sur les 3 000 premiers jours et chaque jour suivant y a été placé à son arrivée, soit chaque séance de janvier 1996 à avril 2026, colorée par année. Ce que la carte montre, c'est que la dynamique du marché change d'une année à l'autre, et souvent fortement. Une stratégie de négociation construite sur les jours d'une année a peu de portée au-delà de celle-ci avant de perdre sa valeur. Les dix premières années ont servi à construire la carte de base, l'animation montre donc 2007 à 2026 ; la <a href="figures/forex_market_full_1996_2026.mp4">série complète depuis 1996</a> est une vidéo de huit minutes. Apprenez à réaliser vous-même l'un de ces diagrammes à partir de notre exemple, <a href="examples/04_living_map_animation.py">examples/04_living_map_animation.py</a>.</i></p>

**Regrouper et évaluer à n'importe quelle largeur.** Le k-means sphérique et le regroupement hiérarchique s'exécutent en résidence GPU à une dimensionnalité extrême, avec des scores de qualité corrigés de la dimension qui restent comparables d'une largeur à l'autre — ainsi, la question « ce regroupement est-il réel ? » reçoit une réponse statistique à 30 M de dimensions, et pas seulement à 300.

**Mener des analyses qui exploitent la largeur au lieu de la combattre.** Évaluation de la nouveauté des arrivées sur une carte ajustée ; factorisation décodant les valeurs retenues directement depuis l'index ; génération de données synthétiques et augmentation des classes minoritaires ; analyses de collections ; exports vers les outils en aval.

<p align="center">
  <img src="figures/stream_anomaly_map.png" width="560" alt="Carte d'anomalies en flux : 987 442 articles DBpedia ajustés, avec 2 904 arrivées colorées selon leur nouveauté">
</p>
<p align="center"><i>Détection de nouveauté en flux, montrée sur une carte vivante : 987 442 articles DBpedia ajustés (en gris) et 2 904 points nouvellement arrivés, cerclés et colorés selon leur nouveauté mesurée — arrivées familières en vert, anomalies en rouge.</i></p>

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

## Travailler avec les groupes de recherche

UltraDim est utilisé par des groupes de recherche sur de véritables charges de travail scientifiques — représentations moléculaires, profils génomiques et épigénomiques, et grandes matrices d'observation. L'usage en recherche est gratuit sous la licence non commerciale ; téléchargez le paquet et commencez. Un bon projet dispose d'un corpus à haute dimensionnalité, volumineux, creux ou lent à analyser avec les outils actuels ; d'une représentation vectorielle et d'une métrique défendables ; ainsi que d'une question de recherche, de cohorte, de regroupement ou de visualisation.

**[Travailler avec les groupes de recherche →](RESEARCH_GROUPS.md)** — ou écrivez à **andrew@gamakon.ai** pour de l'aide sur votre corpus, ou au sujet d'un usage commercial.

## Documents

| Document | Contenu |
|---|---|
| [Présentation d'UltraDim](docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research* — motivations, questions de recherche, principes d'évaluation (document non confidentiel, juin 2026, en anglais) |
| [Témoignages](TESTIMONIALS.md) | Ce qu'en disent les groupes participants |
| [Guide de l'utilisateur](docs/UltraDim_User_Guide.md) | Installation, démarrage dense, exemple creux de bout en bout, rappel, cartes, regroupement, liste des RPC, auto-réglage (en anglais) |
| [Guide de réglage](docs/UltraDim_Tuning_Guide.md) | Ce qui fait bouger le rappel, ce qui ne le fait pas, que faire quand le rappel est hors tolérance (en anglais) |
| [Remplacer et supprimer des lignes](docs/SPARSE_UPSERT_SEMANTICS.md) | Identifiants de ligne, facettes, reprises, durabilité (en anglais) |
| [Avec et sans GPU](docs/GPU_SETTINGS.md) | Ce qui nécessite un GPU, mesuré ; les deux réglages (en anglais) |
| [Guide du serveur MCP](mcp/README.md) | Installation, mise à jour, chaque outil, le chemin nominal, notes de version (en anglais) |
| [Journal des modifications](CHANGELOG.md) | Chaque version, de 0.1 à 0.4.0 (en anglais) |

## À propos

UltraDim est développé et distribué sous licence par **Gamakon Ltd**. L'usage non commercial est gratuit, sous la licence PolyForm Noncommercial 1.0.0. Une version client-serveur est disponible sur demande, y compris pour les organisations non commerciales qui en ont besoin ; nous pouvons vous aider à l'installer et à la configurer. Écrivez à [jesung@gamakon.ai](mailto:jesung@gamakon.ai) ou [andrew@gamakon.ai](mailto:andrew@gamakon.ai).

### Genèse du projet

*Comment tout a commencé*

En interne, la base de données UltraDim repose sur une forme entièrement nouvelle d'index vectoriel, mise au point par Andrew Morgan — auteur de *Mastering Spark for Data Science*. Il a inventé cet index pour construire et éprouver ses idées de résolution du défi ARC-AGI ; ces travaux se poursuivent encore aujourd'hui.

Fort de trente années d'ingénierie en science des données, Andrew l'a implémenté à l'aide d'une longue liste d'optimisations qui, conjuguées au nouvel index, permettent de remplacer un large cluster Spark par un ordinateur portable Mac.

Andrew s'est fait aider par l'IA, mais explique que l'expérience fut extrêmement frustrante. « L'IA déteste innover. N'ayant jamais rencontré ce type d'index auparavant, elle peinait constamment à apporter quoi que ce soit d'utile, revenant souvent délibérément à d'anciennes idées dans le code. » Après une année de frustration persistante, le résultat est un système dont nous sommes véritablement fiers. Nous espérons qu'il vous plaira et qu'il vous servira à bâtir quelque chose de remarquable.
