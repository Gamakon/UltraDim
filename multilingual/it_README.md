# UltraDim

**Un archivio vettoriale analitico veloce, pensato per insiemi di dati di dimensionalità estrema.**<br>
**Collaudato a 30 milioni di dimensioni, con l'obiettivo di arrivare al miliardo.**

*Questo documento è la traduzione in italiano del [README in inglese](../README.md). I percorsi e i collegamenti puntano ai file del repository.*

*È la prima volta che ne sentite parlare? [Per chi non è del mestiere: che cosa sono i dati sparsi ad alta dimensionalità?](it_WHAT_IS_HIGH_DIMENSIONAL_SPARSE_DATA.md)*

UltraDim archivia, cerca, mappa, classifica e raggruppa vettori ben oltre i limiti dimensionali delle basi di dati vettoriali convenzionali: dati densi fino a ~256 000 dimensioni, dati sparsi fino a decine di milioni, collaudato in esecuzioni di produzione a **30 000 000 di dimensioni** su corpus reali di chimica, con dimostrazioni a 100 milioni di dimensioni. È scritto in Rust, accelerato su GPU tramite Metal su macOS e Vulkan su Linux, e si comanda da Python.

UltraDim viene distribuito come pacchetto Python compilato (wheel) per macOS su Apple Silicon, Linux x86_64 e Linux arm64, per Python 3.12. La versione attuale è la 0.4.0, nella pagina [Releases](../../../releases). L'uso non commerciale è gratuito secondo la licenza PolyForm Noncommercial 1.0.0. L'uso commerciale richiede una licenza di Gamakon Ltd. Il testo della licenza è [`LICENSE`](../LICENSE); l'avviso che spiega entrambe le modalità è [`LICENSES/LICENSE.md`](../LICENSES/LICENSE.md).

<p align="center">
  <img src="../figures/chembl_50k_30m_bloommap.svg" width="820" alt="BloomMap di 50 000 molecole di ChEMBL raggruppate a 30 000 000 di dimensioni">
</p>
<p align="center"><i>Lo spazio chimico come BloomMap: 50 000 molecole di ChEMBL, raggruppate gerarchicamente alla loro larghezza nativa di 30 000 000 di dimensioni.</i></p>

---

## Funzionalità

- **Ingestione alla larghezza nativa** (dove per larghezza si intende il numero di dimensioni) — vettori densi fino a ~256 000 dimensioni; vettori sparsi fino a decine di milioni (30 M collaudati, 100 M dimostrati), con una memoria che cresce con i valori non nulli, non con la larghezza dichiarata
- **Ricerca autoverificata** — punteggi di coseno esatti, con certificati di richiamo (recall) misurati su richiesta contro una ricerca esaustiva esatta
- **Ricerca densa ad alto rendimento** — 1 339 interrogazioni/s a 2,99 ms al p50 su DBpedia-1M, precisione@10 = 0,9945
- **Mappe UMAP native** — adattamenti deterministici, in cache e lato server a qualsiasi larghezza; nuovi punti collocati in millisecondi; riadattamento incrementale a ~1,5 % del costo di una ricostruzione; uscita in 2-D, in dimensione intermedia (fino a 256 componenti) o sferica
- **Costruzione di grafi k-NN con soglie di qualità** — ogni grafo porta con sé una misura di richiamo; le mappe rifiutano di adattarsi su grafi sotto 0,99
- **Raggruppamento a qualsiasi larghezza** — k-means sferico e raggruppamento gerarchico residenti su GPU, con punteggi di qualità corretti per la dimensione, confrontabili tra larghezze diverse
- **Rilevamento di novità in flusso** — valutare gli arrivi contro la struttura esistente dei vicini più prossimi in alta dimensione, quindi collocarli su una mappa UMAP viva perché le popolazioni anomale ed emergenti diventino visibili; la figura in flusso più sotto è un breve script sulla RPC di trasformazione della mappa
- **Fattorizzazione e raccomandazione** — decodificare valori trattenuti direttamente dall'indice; un metodo di vicinato privo di parametri, competitivo con riferimenti addestrati su un banco di prova pubblico
- **Servizi di dati sintetici** — banche di ipersfere uniformi e aumento k-NN delle classi minoritarie per insiemi di dati sbilanciati
- **Visualizzazione BloomMap** — resa di poster di qualità da pubblicazione per raggruppamenti gerarchici
- **Operazioni sui dati** — esportazione in CSV, JSON e in un formato binario; analitica delle collezioni; generazione di embedding di testo nel server
- **Tre modi di esecuzione** — nel proprio processo come pacchetto Python; come server MCP per un assistente; oppure come server condiviso a cui molti client accedono tramite gRPC attraverso una porta, disponibile su richiesta. Le stesse 204 RPC in tutti e tre i casi.
- **Tracciabilità da cima a fondo** — parametri versionati, semi, contabilità delle righe e risultati esportabili, in modo che ogni uscita analitica possa essere esaminata e ripetuta

## Ottenerlo

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install ./UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl      # numpy viene installato insieme
```

```python
import ultradim
db = ultradim.UltraDim("./db")
print(len(db.capabilities()))          # 204
db.call_json("RpcName", '{...}')       # una qualsiasi di esse
```

La base di dati gira dentro il vostro processo. Non c'è alcun server da avviare né porta da aprire. Una GPU viene usata quando è presente (Metal su macOS, Vulkan su Linux). Senza GPU, UltraDim carica, indicizza e cerca dati sparsi e densi, costruisce grafi di vicinato e lignaggi di densità, e misura il richiamo. Gli adattamenti UMAP, il raggruppamento k-means e i lignaggi k-means richiedono una GPU e senza di essa restituiscono un errore. Misurato in [`docs/GPU_SETTINGS.md`](../docs/GPU_SETTINGS.md).

Un server MCP, `mcp/ultradim_mcp_server_v0_4_0.py`, avvolge lo stesso pacchetto sotto forma di 46 strumenti, così che un assistente possa creare collezioni, ingerire, indicizzare, cercare, raggruppare e mappare senza che voi scriviate Python. La sua guida è [`mcp/README.md`](../mcp/README.md).

Esiste una versione client-server. Un server UltraDim gira su una macchina ospite ed è condiviso da molti client attraverso una porta. I client scrivono e interrogano tramite gRPC. gRPC è un protocollo binario compatto, quindi l'ingestione di vettori larghi è veloce in rete. È lo stesso motore del pacchetto, con le stesse 204 RPC. Contattateci per ottenerla. Questo vale anche per le organizzazioni non commerciali che ne hanno bisogno: possiamo aiutarvi a installarla e configurarla. jesung@gamakon.ai o andrew@gamakon.ai.

## Eseguirlo con un assistente di IA

Il repository include un server MCP, `mcp/ultradim_mcp_server_v0_4_0.py`, che espone la base di dati come 46 strumenti a Claude Code, Codex o a qualsiasi assistente che parli MCP. L'assistente fa quindi funzionare la base di dati per conto vostro: crea la famiglia, ingerisce i vostri vettori, costruisce l'indice, cerca, raggruppa e mappa, e vi legge i risultati. Voi descrivete lo studio; lui esegue le chiamate.

Installate il pacchetto, clonate questo repository e aprite una sessione con l'assistente nel clone. Per Claude Code, il file `.mcp.json` nella radice registra il server; per Codex, aggiungete a `~/.codex/config.toml`:

```toml
[mcp_servers.ultradim]
command = "python3.12"
args = ["/percorso/a/UltraDim/mcp/ultradim_mcp_server_v0_4_0.py", "--db", "/percorso/al/vostro/db"]
```

`command` deve essere il Python in cui è installato il pacchetto. Poi chiedete, a parole: «carica i vettori di questo file in UltraDim, rendili ricercabili e mostrami una mappa». La prima chiamata dell'assistente dovrebbe essere lo strumento `whats_available`, che elenca ogni strumento e il percorso nominale direttamente dal pacchetto. La guida completa è [`mcp/README.md`](../mcp/README.md) (in inglese).

## Cosa potete farci

**Cercare in dati ultra-larghi e fidarsi delle risposte.** UltraDim tratta i vostri dati alla loro larghezza nativa — impronte molecolari, carrelli della spesa, genomica in codifica one-hot, embedding di testo — senza hashing delle caratteristiche né troncamento da parte vostra. I punteggi che ricevete sono coseni veri contro i vostri vettori grezzi, e l'indice misura su richiesta il proprio richiamo dei candidati contro le risposte esaustive esatte, così che ogni corpus arrivi con un certificato di qualità e non con una speranza.

**Costruire mappe 2-D vive di dati a 30 M di dimensioni.** Le mappe UMAP vengono calcolate nativamente nel server, perciò la costruzione delle mappe funziona a larghezze alle quali gli strumenti standard non riescono nemmeno a caricare i dati. Le mappe sono oggetti vivi: i nuovi punti vengono collocati su una mappa esistente in millisecondi, i lotti piccoli vengono incorporati a circa l'1,5 % del costo di una ricostruzione, e la cronologia delle versioni della mappa funge anche da rilevatore di deriva per il vostro flusso di dati.

<p align="center">
  <img src="../figures/umap_chembl_30m.png" width="410" alt="UMAP di 50 000 molecole di ChEMBL a 30 M di dimensioni, richiamo del grafo 0,9996">
  <img src="../figures/umap_mnist_70k.png" width="410" alt="UMAP delle 70 000 cifre di MNIST">
</p>
<p align="center"><i>A sinistra: 50 000 molecole di ChEMBL mappate a 30 000 000 di dimensioni grezze; il grafo di vicinato sotto la mappa ha misurato un richiamo di 0,9996 contro l'oracolo esatto. A destra: la mappa di controllo MNIST 70K, prodotta dalla stessa catena di elaborazione.</i></p>

<p align="center">
  <img src="../figures/forex_umap_2007_2026.gif" width="560" alt="Il mercato dei cambi come mappa viva, dal 2007 al 2026, un punto per giorno di contrattazione">
</p>
<p align="center"><i>Trent'anni del mercato dei cambi su una sola mappa. Ogni punto è un giorno di contrattazione, descritto dai rendimenti standardizzati di 1 992 coppie di valute in quel giorno, e i giorni che si sono mossi in modo simile stanno vicini. La mappa è stata adattata sui primi 3 000 giorni e ogni giorno successivo vi è stato collocato al suo arrivo, ogni sessione da gennaio 1996 ad aprile 2026, colorata per anno. Ciò che la mappa mostra è che la dinamica del mercato cambia di anno in anno, e spesso in modo marcato. Una strategia di negoziazione costruita sui giorni di un solo anno ha poco margine oltre quell'anno prima di perdere valore. I primi dieci anni hanno costruito la mappa di base, quindi l'animazione mostra dal 2007 al 2026; la <a href="../figures/forex_market_full_1996_2026.mp4">serie completa dal 1996</a> è un video di otto minuti. Si può imparare a costruire uno di questi diagrammi a partire dal nostro esempio, <a href="../docs/examples/04_living_map_animation.py">docs/examples/04_living_map_animation.py</a>.</i></p>

**Raggruppare e valutare a qualsiasi larghezza.** Il k-means sferico e il raggruppamento gerarchico girano residenti su GPU a dimensionalità estrema, con punteggi di qualità corretti per la dimensione che restano confrontabili tra larghezze diverse; così la domanda «questo raggruppamento è reale?» ha una risposta statistica a 30 M di dimensioni, e non solo a 300.

**Eseguire analisi che sfruttano la larghezza invece di combatterla.** Punteggio di novità degli arrivi su una mappa adattata; fattorizzazione che decodifica valori trattenuti direttamente dall'indice; generazione di dati sintetici e aumento delle classi minoritarie; analitica delle collezioni; esportazioni per gli strumenti a valle.

<p align="center">
  <img src="../figures/stream_anomaly_map.png" width="560" alt="Mappa delle anomalie in flusso: 987 442 articoli di DBpedia adattati, con 2 904 arrivi colorati secondo la loro novità">
</p>
<p align="center"><i>Rilevamento di novità in flusso, mostrato su una mappa viva: 987 442 articoli di DBpedia adattati (in grigio) e 2 904 punti appena arrivati, cerchiati e colorati secondo la novità misurata; arrivi familiari in verde, anomalie in rosso.</i></p>

<p align="center">
  <img src="../figures/stream_dichotomy.png" width="410" alt="Dicotomia del punteggio di novità tra arrivi familiari e nuovi">
  <img src="../figures/chembl_support_saturation.png" width="410" alt="Saturazione del supporto delle caratteristiche di ChEMBL al crescere del corpus">
</p>
<p align="center"><i>A sinistra: il punteggio di novità separa nettamente gli arrivi familiari da quelli nuovi. A destra: analitica di corpus a 30 M di dimensioni; la saturazione del supporto delle caratteristiche al crescere del corpus di ChEMBL.</i></p>

## Prestazioni misurate

Tutte le cifre provengono da esperimenti controllati contro oracoli esaustivi esatti, su un singolo Apple M3 Max; qualità e latenza sono riportate insieme.

| Corpus | Larghezza | Righe | Qualità | Latenza / portata |
|---|---|---|---|---|
| Molecole di ChEMBL (sparso) | 30 000 000 | 500 000 | recall@10 = 0,9992 | 56 ms per interrogazione |
| Molecole di ChEMBL (sparso, profilo veloce) | 30 000 000 | 500 000 | recall@10 = 0,9964 | 29 ms per interrogazione |
| Embedding di DBpedia (denso) | 1 536 | 1 000 000 | precisione@10 = 0,9945 | 1 339 interrogazioni/s a 2,99 ms al p50 |
| Carrelli della spesa (sparso) | 100 000 | 100 000 | recall@10 = 0,9851 | p50 17,5 ms |
| Dati strutturati sintetici (sparso) | 1 800 000 | 50 000 | recall@10 = 1,000 | p50 15,7 ms |

La larghezza costa poco: portare un corpus da 1 M a 10 M di dimensioni aggiunge ~0,08 GiB di memoria residente, perché l'archiviazione sparsa cresce con i valori non nulli, non con la larghezza dichiarata.

## Collaborare con i gruppi di ricerca

UltraDim è utilizzato da gruppi di ricerca su carichi di lavoro scientifici reali: rappresentazioni molecolari, profili genomici ed epigenomici, e grandi matrici osservazionali. L'uso per la ricerca è gratuito secondo la licenza non commerciale; scaricate il pacchetto e iniziate. Un buon progetto ha un corpus ad alta dimensionalità, grande, sparso o lento da analizzare con gli strumenti attuali; una rappresentazione vettoriale e una metrica difendibili; e una domanda di recupero, di coorte, di raggruppamento o di visualizzazione.

**[Collaborare con i gruppi di ricerca →](../RESEARCH_GROUPS.md)** — oppure scrivete a **andrew@gamakon.ai** per ricevere aiuto con il vostro corpus, o per l'uso commerciale.

## Documenti

| Documento | Contenuto |
|---|---|
| [Panoramica di UltraDim](../docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research*: motivazione, domande di ricerca, principi di valutazione (non riservato, giugno 2026, in inglese) |
| [Testimonianze](../TESTIMONIALS.md) | Cosa dicono i gruppi partecipanti |
| [Guida per l'utente](../docs/UltraDim_User_Guide.md) | Installazione, avvio rapido denso, esempio sparso svolto da cima a fondo, richiamo, mappe, raggruppamento, elenco delle RPC, autoregolazione (in inglese) |
| [Guida alla regolazione](../docs/UltraDim_Tuning_Guide.md) | Cosa muove il richiamo, cosa no, e cosa fare quando scende sotto la tolleranza (in inglese) |
| [Sostituire ed eliminare righe](../docs/SPARSE_UPSERT_SEMANTICS.md) | Identificatori di riga, faccette, nuovi tentativi, durabilità (in inglese) |
| [Con e senza GPU](../docs/GPU_SETTINGS.md) | Cosa richiede una GPU, misurato; le due impostazioni (in inglese) |
| [Guida al server MCP](../mcp/README.md) | Installazione, aggiornamento, ogni strumento, il percorso nominale, note di rilascio (in inglese) |
| [Registro delle modifiche](../CHANGELOG.md) | Ogni versione, dalla 0.1 alla 0.4.0 (in inglese) |

## Informazioni

UltraDim è sviluppato e concesso in licenza da **Gamakon Ltd**. L'uso non commerciale è gratuito secondo la licenza PolyForm Noncommercial 1.0.0. Una versione client-server è disponibile su richiesta, anche per le organizzazioni non commerciali che ne hanno bisogno; possiamo aiutarvi a installarla e configurarla. Scrivete a [jesung@gamakon.ai](mailto:jesung@gamakon.ai) o a [andrew@gamakon.ai](mailto:andrew@gamakon.ai).

### Origine

*Come è nato*

Internamente, la base di dati UltraDim utilizza una forma completamente nuova di indice vettoriale, sviluppata da Andrew Morgan, autore di *Mastering Spark for Data Science*. Ha inventato questo indice per costruire e mettere alla prova le sue idee per risolvere la sfida ARC-AGI; quel lavoro è ancora in corso.

Forte di trent'anni di ingegneria nella scienza dei dati, Andrew lo ha implementato con una lunga lista di ottimizzazioni che, insieme al nuovo indice, permettono di sostituire un grande cluster Spark con un portatile Mac.

Andrew si è fatto aiutare dall'IA, ma spiega che è stato estremamente frustrante. «All'IA non piace innovare. Non avendo mai visto prima questo progetto di indice, faticava di continuo a contribuire con qualcosa di utile, e spesso riportava deliberatamente il codice a idee più vecchie.» Dopo un anno di frustrazione persistente, il risultato è un sistema di cui siamo sinceramente orgogliosi. Speriamo che vi piaccia e che lo usiate per costruire qualcosa di straordinario.
