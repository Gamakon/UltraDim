# UltraDim

**Ein schneller analytischer Vektorspeicher für Datensätze extremer Dimensionalität.**<br>
**Erprobt bei 30 Millionen Dimensionen, mit dem Ziel einer Milliarde.**

*Dieses Dokument ist die deutsche Übersetzung des [englischen README](../README.md). Pfade und Links verweisen auf die Dateien des Repositorys.*

*Neu hier? [Für Nicht-Techniker: Was sind hochdimensionale dünnbesetzte Daten?](de_WHAT_IS_HIGH_DIMENSIONAL_SPARSE_DATA.md)*

UltraDim speichert, durchsucht, kartiert, klassifiziert und clustert Vektoren weit jenseits der dimensionalen Grenzen herkömmlicher Vektordatenbanken: dichte Daten bis ~256.000 Dimensionen, dünnbesetzte Daten bis in die zweistelligen Millionen, erprobt in Produktionsläufen bei **30.000.000 Dimensionen** auf realen Chemiekorpora, mit Demonstrationen bei 100 Millionen Dimensionen. Es ist in Rust geschrieben, GPU-beschleunigt über Metal auf macOS und Vulkan auf Linux, und wird aus Python heraus gesteuert.

UltraDim wird als kompiliertes Python-Paket (wheel) für macOS auf Apple Silicon, Linux x86_64 und Linux arm64 ausgeliefert, für Python 3.12. Die aktuelle Version ist 0.4.0, auf der Seite [Releases](../../../releases). Die nichtkommerzielle Nutzung ist unter der PolyForm Noncommercial License 1.0.0 kostenlos. Die kommerzielle Nutzung erfordert eine Lizenz von Gamakon Ltd. Der Lizenztext ist [`LICENSE`](../LICENSE); der Hinweis, der beide Wege erläutert, ist [`LICENSES/LICENSE.md`](../LICENSES/LICENSE.md).

<p align="center">
  <img src="../figures/chembl_50k_30m_bloommap.svg" width="820" alt="BloomMap von 50.000 ChEMBL-Molekülen, geclustert bei 30.000.000 Dimensionen">
</p>
<p align="center"><i>Der chemische Raum als BloomMap: 50.000 ChEMBL-Moleküle, hierarchisch geclustert bei ihrer nativen Breite von 30.000.000 Dimensionen.</i></p>

---

## Funktionen

- **Ultra-dimensionales Laden von Daten** — Ingest großer dichter Vektoren, erprobt bis ~256.000 Dimensionen; oder großer dünnbesetzter Vektoren, erprobt bis 30 M und mit 100 M demonstriert. Ihr Bedarf an RAM und Festplatte wächst mit Ihren Nicht-Null-Werten, nicht mit der rohen Vektorgröße.
- **Selbstverifizierende Suche** — exakte, echte Kosinuswerte, mit auf Anfrage erstellten Recall-Zertifikaten, gemessen gegen eine exakte erschöpfende Suche
- **Dichte Suche mit hohem Durchsatz** — 1.339 Anfragen/s bei p50 2,99 ms auf DBpedia-1M, Precision@10 = 0,9945
- **Native UMAP-Karten** — deterministische, zwischengespeicherte, serverseitige Fits bei jeder Breite (Breite meint die Anzahl der Dimensionen); neue Punkte werden in Millisekunden platziert; inkrementelles Nachfitten zu ~1,5 % der Kosten eines Neuaufbaus; Ausgabe in 2-D, in mittlerer Dimension (bis 256 Komponenten) oder sphärisch
- **k-NN-Graphenbau mit Qualitätsschwellen** — jeder Graph trägt einen gemessenen Recall-Wert; Karten verweigern das Fitten auf Graphen unter 0,99
- **Clustering für ultra-dimensionale Daten, selbst bei 30 Millionen Dimensionen** — GPU-residentes sphärisches k-Means und hierarchisches Clustering, mit dimensionskorrigierten Qualitätswerten, die über Breiten hinweg vergleichbar sind
- **Neuheitserkennung im Datenstrom** — Neuankömmlinge werden gegen die bestehende hochdimensionale Nächste-Nachbarn-Struktur bewertet und anschließend auf einer lebenden UMAP-Karte platziert, sodass anomale und aufkommende Populationen sichtbar werden; die Datenstrom-Abbildung unten ist ein kurzes Skript über die RPC zur Kartentransformation
- **Faktorisierung und Empfehlung** — zurückgehaltene Werte direkt aus dem Index dekodieren; ein parameterfreies Nachbarschaftsverfahren, das auf einem öffentlichen Benchmark mit trainierten Referenzverfahren konkurriert
- **Dienste für synthetische Daten** — gleichverteilte Hypersphären-Banken und k-NN-Anreicherung von Minderheitsklassen für unausgewogene Datensätze
- **BloomMap-Visualisierung** — Poster-Rendering hierarchischer Clusterungen in Publikationsqualität
- **Datenoperationen** — Export nach CSV, JSON und in ein Binärformat; Sammlungsanalytik; Text-Embedding im Server
- **Drei Betriebsarten** — im eigenen Prozess als Python-Paket; als MCP-Server für einen Assistenten; oder als gemeinsam genutzter Server, den viele Clients über einen Port per gRPC erreichen, auf Anfrage erhältlich. Dieselben 204 RPCs in allen drei Fällen.
- **Durchgängige Provenienz** — versionierte Parameter, Seeds, Zeilenbuchführung und exportierbare Ergebnisse, sodass jede analytische Ausgabe geprüft und wiederholt werden kann

## Bezug

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install ./UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl      # numpy wird mitinstalliert
```

```python
import ultradim
db = ultradim.UltraDim("./db")
print(len(db.capabilities()))          # 204
db.call_json("RpcName", '{...}')       # jede davon
```

Die Datenbank läuft innerhalb Ihres Prozesses. Es gibt keinen Server zu starten und keinen Port zu öffnen. Eine GPU wird verwendet, wenn eine vorhanden ist (Metal auf macOS, Vulkan auf Linux). Ohne GPU lädt, indiziert und durchsucht UltraDim dünnbesetzte und dichte Daten, baut Nachbarschaftsgraphen und Dichte-Lineages und misst den Recall. UMAP-Fits, k-Means-Clustering und k-Means-Lineages benötigen eine GPU und liefern ohne sie einen Fehler zurück. Gemessen in [`docs/GPU_SETTINGS.md`](../docs/GPU_SETTINGS.md).

Ein MCP-Server, `mcp/ultradim_mcp_server_v0_4_0.py`, kapselt dasselbe Paket als 46 Werkzeuge, sodass ein Assistent Sammlungen anlegen, ingestieren, indizieren, suchen, clustern und kartieren kann, ohne dass Sie Python schreiben. Seine Anleitung ist [`mcp/README.md`](../mcp/README.md).

Eine Client-Server-Version ist verfügbar. Ein UltraDim-Server läuft auf einem Host und wird von vielen Clients über einen Port gemeinsam genutzt. Die Clients schreiben und fragen per gRPC ab. gRPC ist ein kompaktes Binärprotokoll, daher ist der Ingest breiter Vektoren über das Netz schnell. Es ist dieselbe Engine wie das Paket, mit denselben 204 RPCs. Nehmen Sie Kontakt auf, um sie zu erhalten. Das schließt nichtkommerzielle Organisationen ein, die sie benötigen: Wir können Ihnen bei Installation und Einrichtung helfen. jesung@gamakon.ai oder andrew@gamakon.ai.

## Betrieb mit einem KI-Assistenten

Das Repository enthält einen MCP-Server, `mcp/ultradim_mcp_server_v0_4_0.py`, der die Datenbank als 46 Werkzeuge für Claude Code, Codex oder jeden Assistenten bereitstellt, der MCP spricht. Der Assistent betreibt die Datenbank dann in Ihrem Auftrag: Er legt die Familie an, ingestiert Ihre Vektoren, baut den Index, sucht, clustert und kartiert und liest Ihnen die Ergebnisse vor. Sie beschreiben die Studie; er führt die Aufrufe aus.

Installieren Sie das Paket, klonen Sie dieses Repository und öffnen Sie eine Assistentensitzung im Klon. Für Claude Code registriert die Datei `.mcp.json` im Wurzelverzeichnis den Server; für Codex ergänzen Sie in `~/.codex/config.toml`:

```toml
[mcp_servers.ultradim]
command = "python3.12"
args = ["/pfad/zu/UltraDim/mcp/ultradim_mcp_server_v0_4_0.py", "--db", "/pfad/zu/ihrer/db"]
```

`command` muss das Python sein, in dem das Paket installiert ist. Dann bitten Sie, in Worten: „Lade die Vektoren aus dieser Datei in UltraDim, mache sie durchsuchbar und zeige mir eine Karte.“ Der erste Aufruf des Assistenten sollte das Werkzeug `whats_available` sein, das jedes Werkzeug und den Standardpfad live aus dem Paket auflistet. Die vollständige Anleitung ist [`mcp/README.md`](../mcp/README.md) (auf Englisch).

## Was Sie damit tun können

**Ultrabreite Daten durchsuchen und den Antworten vertrauen.** UltraDim verarbeitet Ihre Daten in ihrer nativen Breite — molekulare Fingerabdrücke, Einkaufskörbe, One-Hot-kodierte Genomik, Text-Embeddings — ohne Feature-Hashing oder Abschneiden auf Ihrer Seite. Die Werte, die Sie erhalten, sind echte Kosinuswerte gegen Ihre Rohvektoren, und der Index misst auf Anfrage seinen eigenen Kandidaten-Recall gegen exakte erschöpfende Antworten, sodass jedes Korpus mit einem Qualitätszertifikat ausgeliefert wird und nicht mit einer Hoffnung.

**Lebende 2-D-Karten von 30-M-dimensionalen Daten bauen.** UMAP-Karten werden nativ auf dem Server berechnet, daher funktioniert der Kartenbau bei Breiten, bei denen gängige Werkzeuge die Daten gar nicht erst laden können. Karten sind lebende Objekte: Neue Punkte werden in Millisekunden auf einer bestehenden Karte platziert, kleine Chargen werden zu etwa 1,5 % der Kosten eines Neuaufbaus eingefaltet, und die Versionsgeschichte der Karte dient zugleich als Drift-Detektor für Ihren Datenstrom.

<p align="center">
  <img src="../figures/umap_chembl_30m.png" width="410" alt="UMAP von 50.000 ChEMBL-Molekülen bei 30 M Dimensionen, Graph-Recall 0,9996">
  <img src="../figures/umap_mnist_70k.png" width="410" alt="UMAP der 70.000 MNIST-Ziffern">
</p>
<p align="center"><i>Links: 50.000 ChEMBL-Moleküle, kartiert bei 30.000.000 Rohdimensionen; der Nachbarschaftsgraph unter der Karte erreichte einen gemessenen Recall von 0,9996 gegen das exakte Orakel. Rechts: die MNIST-70K-Kontrollkarte aus derselben Verarbeitungskette.</i></p>

<p align="center">
  <img src="../figures/forex_umap_2007_2026.gif" width="560" alt="Der Devisenmarkt als lebende Karte, 2007 bis 2026, ein Punkt pro Handelstag">
</p>
<p align="center"><i>Dreißig Jahre Devisenmarkt auf einer Karte. Jeder Punkt ist ein Handelstag, beschrieben durch die standardisierten Renditen von 1.992 Devisenpaaren an diesem Tag, und Tage mit ähnlicher Bewegung liegen beieinander. Die Karte wurde auf den ersten 3.000 Tagen gefittet, und jeder spätere Tag wurde bei seinem Eintreffen in sie eingeordnet, jede Sitzung von Januar 1996 bis April 2026, nach Jahr eingefärbt. Die Karte zeigt, dass sich die Dynamik des Marktes von Jahr zu Jahr ändert, und oft stark. Eine Handelsstrategie, die auf den Tagen eines einzigen Jahres aufbaut, hat über dieses Jahr hinaus wenig Spielraum, bevor sie an Wert verliert. Die ersten zehn Jahre bildeten die Grundkarte, daher zeigt die Animation 2007 bis 2026; der <a href="../figures/forex_market_full_1996_2026.mp4">vollständige Lauf ab 1996</a> ist ein achtminütiges Video. Wie Sie ein solches Diagramm selbst erstellen, zeigt unser Beispiel <a href="../examples/04_living_map_animation.py">examples/04_living_map_animation.py</a>.</i></p>

**Bei jeder Breite clustern und bewerten.** Sphärisches k-Means und hierarchisches Clustering laufen GPU-resident bei extremer Dimensionalität, mit dimensionskorrigierten Qualitätswerten, die über Breiten hinweg vergleichbar bleiben; so hat die Frage „Ist dieses Clustering echt?“ eine statistische Antwort bei 30 M Dimensionen, nicht nur bei 300.

**Analysen ausführen, die die Breite nutzen, statt gegen sie anzukämpfen.** Neuheitsbewertung von Neuankömmlingen auf einer gefitteten Karte; Faktorisierung, die zurückgehaltene Werte direkt aus dem Index dekodiert; Erzeugung synthetischer Daten und Anreicherung von Minderheitsklassen; Sammlungsanalytik; Exporte für nachgelagerte Werkzeuge.

<p align="center">
  <img src="../figures/stream_anomaly_map.png" width="560" alt="Anomaliekarte im Datenstrom: 987.442 gefittete DBpedia-Artikel mit 2.904 Neuankömmlingen, nach Neuheit eingefärbt">
</p>
<p align="center"><i>Neuheitserkennung im Datenstrom, gezeigt auf einer lebenden Karte: 987.442 gefittete DBpedia-Artikel (grau) mit 2.904 neu eintreffenden Punkten, umringt und nach gemessener Neuheit eingefärbt; vertraute Ankömmlinge in Grün, Anomalien in Rot.</i></p>

<p align="center">
  <img src="../figures/stream_dichotomy.png" width="410" alt="Dichotomie des Neuheitswerts zwischen vertrauten und neuen Ankömmlingen">
  <img src="../figures/chembl_support_saturation.png" width="410" alt="Sättigung des ChEMBL-Merkmalsträgers mit wachsendem Korpus">
</p>
<p align="center"><i>Links: Der Neuheitswert trennt vertraute von neuen Ankömmlingen sauber. Rechts: Korpusanalytik bei 30 M Dimensionen; die Sättigung des Merkmalsträgers mit wachsendem ChEMBL-Korpus.</i></p>

## Gemessene Leistung

Alle Zahlen stammen aus kontrollierten Experimentläufen gegen exakte erschöpfende Orakel, auf einem einzelnen Apple M3 Max; Qualität und Latenz werden zusammen berichtet.

| Korpus | Breite | Zeilen | Qualität | Latenz / Durchsatz |
|---|---|---|---|---|
| ChEMBL-Moleküle (dünnbesetzt) | 30.000.000 | 500.000 | Recall@10 = 0,9992 | 56 ms pro Anfrage |
| ChEMBL-Moleküle (dünnbesetzt, schnelles Profil) | 30.000.000 | 500.000 | Recall@10 = 0,9964 | 29 ms pro Anfrage |
| DBpedia-Embeddings (dicht) | 1.536 | 1.000.000 | Precision@10 = 0,9945 | 1.339 Anfragen/s bei p50 2,99 ms |
| Einkaufskörbe (dünnbesetzt) | 100.000 | 100.000 | Recall@10 = 0,9851 | p50 17,5 ms |
| Synthetisch strukturiert (dünnbesetzt) | 1.800.000 | 50.000 | Recall@10 = 1,000 | p50 15,7 ms |

Breite kostet wenig: Ein Korpus von 1 M auf 10 M Dimensionen zu bringen, fügt ~0,08 GiB residenten Speicher hinzu, weil die dünnbesetzte Speicherung mit Ihren Nicht-Null-Werten wächst, nicht mit der deklarierten Breite.

## Zusammenarbeit mit Forschungsgruppen

UltraDim wird von Forschungsgruppen an realen wissenschaftlichen Arbeitslasten eingesetzt: molekulare Repräsentationen, genomische und epigenomische Profile sowie große Beobachtungsmatrizen. Die Forschungsnutzung ist unter der nichtkommerziellen Lizenz kostenlos; laden Sie das Paket herunter und legen Sie los. Ein gutes Projekt hat ein Korpus, das hochdimensional, groß, dünnbesetzt oder mit den heutigen Werkzeugen nur langsam zu analysieren ist; eine vertretbare Vektorrepräsentation und Metrik; und eine Frage zu Retrieval, Kohorten, Clustering oder Visualisierung.

**[Zusammenarbeit mit Forschungsgruppen →](../RESEARCH_GROUPS.md)** — oder schreiben Sie an **andrew@gamakon.ai** für Hilfe mit Ihrem Korpus oder zur kommerziellen Nutzung.

## Dokumente

| Dokument | Inhalt |
|---|---|
| [UltraDim-Überblick](../docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research*: Motivation, Forschungsfragen, Evaluationsprinzipien (nicht vertraulich, Juni 2026, auf Englisch) |
| [Erfahrungsberichte](../TESTIMONIALS.md) | Was teilnehmende Gruppen sagen |
| [Benutzerhandbuch](../docs/UltraDim_User_Guide.md) | Installation, ein dichter Schnellstart, ein durchgerechnetes dünnbesetztes Beispiel, Recall, Karten, Clustering, die RPC-Liste, der Auto-Tuner (auf Englisch) |
| [Tuning-Leitfaden](../docs/UltraDim_Tuning_Guide.md) | Was den Recall bewegt, was nicht, und was zu tun ist, wenn der Recall unter die Toleranz fällt (auf Englisch) |
| [Zeilen ersetzen und löschen](../docs/SPARSE_UPSERT_SEMANTICS.md) | Zeilen-IDs, Facetten, Wiederholungsversuche, Dauerhaftigkeit (auf Englisch) |
| [Betrieb mit und ohne GPU](../docs/GPU_SETTINGS.md) | Was eine GPU braucht, gemessen; die zwei Einstellungen (auf Englisch) |
| [MCP-Server-Anleitung](../mcp/README.md) | Installation, Aktualisierung, jedes Werkzeug, der Standardpfad, Versionshinweise (auf Englisch) |
| [Änderungsprotokoll](../CHANGELOG.md) | Jede Version, von 0.1 bis 0.4.0 (auf Englisch) |

## Über

UltraDim wird von **Gamakon Ltd** entwickelt und lizenziert. Die nichtkommerzielle Nutzung ist unter der PolyForm Noncommercial License 1.0.0 kostenlos. Eine Client-Server-Version ist auf Anfrage erhältlich, auch für nichtkommerzielle Organisationen, die sie benötigen; wir können Ihnen bei Installation und Einrichtung helfen. Schreiben Sie an [jesung@gamakon.ai](mailto:jesung@gamakon.ai) oder [andrew@gamakon.ai](mailto:andrew@gamakon.ai).

### Entstehungsgeschichte

*Wie es dazu kam*

Intern verwendet die UltraDim-Datenbank eine völlig neue Form von Vektorindex, entwickelt von Andrew Morgan, Autor von *Mastering Spark for Data Science*. Er erfand diesen Index, um seine Ideen zur Lösung der ARC-AGI-Challenge zu bauen und zu erproben; diese Arbeit läuft noch.

Aufbauend auf dreißig Jahren Data-Science-Engineering setzte Andrew ihn mit einer langen Liste von Optimierungen um, die es zusammen mit dem neuen Index erlauben, einen großen Spark-Cluster durch ein Mac-Notebook zu ersetzen.

Andrew nahm KI zu Hilfe, erklärt aber, dass dies äußerst frustrierend war. „KI hasst es zu innovieren. Da sie dieses Indexdesign noch nie gesehen hatte, tat sie sich fortwährend schwer, etwas Nützliches beizutragen, und setzte den Code oft mutwillig auf ältere Ideen zurück.“ Nach einem Jahr beharrlicher Frustration ist das Ergebnis ein System, auf das wir aufrichtig stolz sind. Wir hoffen, dass es Ihnen Freude macht und dass Sie damit etwas Bemerkenswertes bauen.
