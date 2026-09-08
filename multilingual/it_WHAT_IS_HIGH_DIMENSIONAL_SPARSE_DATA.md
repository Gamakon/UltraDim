# Per chi non è del mestiere: che cosa sono i dati sparsi ad alta dimensionalità?

Proverò a spiegare a un pubblico non tecnico come crea in continuazione dati sparsi ad alta dimensionalità, perché si tratta di un concetto importante.

Ora, sono sicuro che siete andati a fare la spesa in un grande supermercato, e darò per scontato che abbiate dato un'occhiata allo scontrino.

Questi sono dati sparsi ad alta dimensionalità.

La domanda è: perché?

Ogni articolo sugli scaffali del negozio ha un codice a barre. È così che passate la spesa allo scanner quando pagate, giusto?

La cassa elettronica e lo scanner hanno una tabella di consultazione dei codici a barre, e quella tabella riporta il codice a barre numerico, la descrizione del prodotto comprensibile a una persona, il prezzo a cui viene venduto, magari se è soggetto a imposta sulle vendite, oltre ad altre cose. Potrebbe essere piuttosto grande, dato che descrive tutto ciò che vendono nel negozio.

Ora, se avessi tutti i dati degli scontrini di Tutti i clienti, e volessi confrontare il vostro comportamento di spesa con quello di altre persone, costruirei la seguente matrice davvero, davvero grande

(che potete immaginare come un foglio di calcolo enorme):

Abbiamo una colonna per ogni codice a barre. Abbiamo una riga per ogni cliente. Sarà un foglio di calcolo Davvero Grande! Immaginate che in un grande Walmart ci siano qualcosa come 300.000 codici a barre, per esempio (colonne). Potrebbero esserci 15 milioni di clienti (righe).

Ora, tornando al vostro scontrino della spesa, immaginate di scorrere verso il basso fino a trovare il vostro ID cliente in quel foglio di calcolo, e poi di spostarvi lungo le colonne mettendo uno zero se non avete comprato quel prodotto, oppure mettendo il numero di articoli che avete comprato con quello stesso codice a barre.

Probabilmente non avete comprato 300.000 cose nella vostra visita al supermercato, quindi è abbastanza ovvio che la maggior parte delle celle conterrebbe uno zero per voi, e lo stesso vale per tutti gli altri. Se avete comprato 4 lattine di zuppa, quell'unica colonna sulla vostra riga avrebbe un conteggio di 4 nella cella, il che significa che avete comprato 4 lattine di quella zuppa.

Usiamo la parola Sparso per descrivere questa situazione in cui la maggior parte delle celle è zero per tutti. Usiamo l'espressione "ad alta dimensionalità" per riferirci al numero altissimo di colonne (prodotti).

Ecco come i dati sparsi ad alta dimensionalità vengono creati da tutti voi in continuazione!

La nostra base di dati ci permette di cercare in quell'insieme di dati per trovare la persona che è il vostro vicino più prossimo, cioè la persona il cui carrello della spesa è misurabilmente il più simile al vostro. Lo facciamo calcolando l'angolo coseno tra il vostro vettore di spesa e quello di ogni altro cliente. Possiamo farlo in millisecondi, anche se ci sono 40 milioni di clienti e 350.000 dimensioni, grazie ad alcuni trucchi matematici molto complessi.

Questo significa che UltraDim può individuare vicini quasi duplicati, raccomandare prodotti usati da Persone-Come-Voi, identificare anomalie (nessun vicino prossimo), costruire segmentazioni dei clienti per personalizzare l'esperienza del cliente e fare un CRM migliore, e persino classificare i cambiamenti nel comportamento d'acquisto nel tempo quando, magari, cambia la fase della vita.

E UltraDim lo fa sui dati nativi, non su un riassunto che degrada l'analisi.

Possiamo naturalmente indicizzare insiemi di dati per l'IA, cioè embedding di testi e documenti, e fare ricerca aumentata dal recupero, che è ciò che significa RAG. Ma i dati a bassa dimensionalità, sotto le 10.000 dimensioni, si possono cercare già oggi con strumenti tradizionali. Il nostro vero valore sta in quel nuovo territorio al di là di essa, dove i nostri strumenti vi danno la capacità di prendere decisioni strategiche migliori.

## Dove altro si trovano dati sparsi ad alta dimensionalità?

Questo tipo di insieme di dati si vede OVUNQUE, e viene riassunto in rapporti che ne nascondono il valore.

Il vostro genoma. Dati sui clienti. Dati di sicurezza informatica. Reti IoT. Dati dei contatori di energia. Dati dei gemelli digitali. Dati delle transazioni d'acquisto. Dati della catena di approvvigionamento. Dati del mercato azionario. Insiemi di dati chimici. Insiemi di dati di fisica. Insiemi di dati di droni e robot, compresi i sensori di bordo. Dati sulle scelte di film. Dati di ricerca semantica. Dati meteorologici. L'elenco è infinito.

Immaginiamo un futuro, una frontiera, in cui computer e persone collaborano, e la nostra missione in Gamakon è aiutarvi a *Navigare la Frontiera*.
