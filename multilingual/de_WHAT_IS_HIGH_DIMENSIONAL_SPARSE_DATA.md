# Für Nicht-Techniker: Was sind hochdimensionale dünnbesetzte Daten?

Ich versuche, einem nicht-technischen Publikum zu erklären, wie es ständig hochdimensionale dünnbesetzte Daten erzeugt, denn das ist ein wichtiges Konzept.

Nun, ich bin sicher, Sie waren schon einmal in einem großen Supermarkt einkaufen, und ich nehme an, Sie haben einen Blick auf Ihren Kassenbon geworfen.

Das sind hochdimensionale dünnbesetzte Daten.

Die Frage ist: Warum?

Jeder Artikel in den Regalen des Geschäfts hat einen Barcode. So werden Ihre Einkäufe beim Bezahlen gescannt, nicht wahr?

Die elektronische Kasse und der Scanner haben eine Nachschlagetabelle mit Barcodes, und diese Nachschlagetabelle führt den numerischen Barcode auf, die für Menschen lesbare Beschreibung des Produkts, den Preis, zu dem es verkauft wird, vielleicht auch, ob Umsatzsteuer anfällt, sowie weitere Dinge. Diese Tabelle kann recht groß sein, da sie alles beschreibt, was im Geschäft verkauft wird.

Wenn ich nun alle Kassenbon-Daten Aller Kunden hätte und Ihr Einkaufsverhalten mit dem anderer Leute vergleichen wollte, würde ich die folgende sehr, sehr große Matrix aufbauen

(die Sie sich als eine sehr große Tabellenkalkulation vorstellen können):

Wir haben eine Spalte für jeden Barcode. Wir haben eine Zeile für jeden Kunden. Das wird eine Sehr Große Tabelle! Stellen Sie sich vor, in einem großen Walmart gibt es zum Beispiel etwa 300.000 Barcodes (Spalten). Es könnte 15 Millionen Kunden geben (Zeilen).

Kommen wir nun auf Ihren Kassenbon zurück: Stellen Sie sich vor, Sie scrollen in dieser Tabelle nach unten, bis Sie Ihre Kundennummer finden, und gehen dann die Spalten entlang und tragen eine Null ein, wenn Sie das Produkt nicht gekauft haben, oder die Anzahl der Artikel, die Sie mit genau diesem Barcode gekauft haben.

Sie haben bei Ihrem Einkauf wahrscheinlich keine 300.000 Dinge gekauft, also ist es ziemlich offensichtlich, dass die meisten Zellen für Sie eine Null enthalten, und das gilt für alle anderen genauso. Wenn Sie 4 Dosen Suppe gekauft haben, stünde in dieser einen Spalte Ihrer Zeile die Zahl 4, was bedeutet, dass Sie 4 Dosen dieser Suppe gekauft haben.

Wir verwenden das Wort dünnbesetzt (Sparse), um diese Situation zu beschreiben, in der die meisten Zellen bei allen Null sind. Wir verwenden den Ausdruck „hochdimensional“, um auf die sehr hohe Anzahl von Spalten (Produkte) zu verweisen.

So erzeugen Sie alle ständig hochdimensionale dünnbesetzte Daten!

Unsere Datenbank erlaubt es uns, diesen Datensatz zu durchsuchen, um die Person zu finden, die Ihr nächster Nachbar ist, also die Person, deren Einkaufskorb Ihrem messbar am ähnlichsten ist. Wir tun das, indem wir den Kosinuswinkel zwischen Ihrem Einkaufsvektor und dem jedes anderen Kunden berechnen. Das schaffen wir in Millisekunden, selbst wenn es 40 Millionen Kunden und 350.000 Dimensionen gibt, mit einigen sehr komplexen mathematischen Tricks.

Das bedeutet, dass UltraDim nahezu doppelte Nachbarn erkennen, Produkte empfehlen kann, die Leute-Wie-Sie verwenden, Anomalien identifizieren kann (keine nahen Nachbarn), Kundensegmentierungen aufbauen kann, um das Kundenerlebnis maßzuschneidern und besseres CRM zu betreiben, und sogar Veränderungen im Einkaufsverhalten im Laufe der Zeit klassifizieren kann, etwa wenn sich die Lebensphase ändert.

Und UltraDim tut das auf den nativen Daten, nicht auf einer Zusammenfassung, die die Analyse verschlechtert.

Wir können natürlich auch KI-Datensätze indexieren, also Embeddings von Texten und Dokumenten, und eine durch Abruf erweiterte Suche durchführen, was RAG bedeutet. Aber niedrigdimensionale Daten, unter 10.000 Dimensionen, lassen sich heute mit herkömmlichen Werkzeugen durchsuchen. Unser eigentlicher Wert liegt in dem neuen Gebiet jenseits davon, wo unsere Werkzeuge Ihnen die Möglichkeit geben, bessere strategische Entscheidungen zu treffen.

## Wo sonst finden sich hochdimensionale dünnbesetzte Daten?

Diese Art von Datensatz findet sich ÜBERALL, und sie wird in Berichten zusammengefasst, die den Wert verbergen.

Ihr Genom. Kundendaten. Cyberdaten. IoT-Netzwerke. Daten von Energiezählern. Daten digitaler Zwillinge. Kauftransaktionsdaten. Lieferkettendaten. Börsendaten. Chemische Datensätze. Physikalische Datensätze. Drohnen- und Roboterdatensätze, einschließlich der Sensoren an Bord. Daten zur Filmauswahl. Daten der semantischen Suche. Wetterdaten. Die Liste ist endlos.

Wir stellen uns eine Zukunft vor, eine Grenze des Bekannten, an der Computer und Menschen zusammenarbeiten, und unsere Mission bei Gamakon ist es, Ihnen zu helfen, *die Grenze des Bekannten zu erkunden*.
