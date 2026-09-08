# Dla osób nietechnicznych: czym są wysokowymiarowe dane rzadkie?

Spróbuję wyjaśnić odbiorcom nietechnicznym, jak sami nieustannie tworzą wysokowymiarowe dane rzadkie, bo to ważne pojęcie.

Otóż jestem pewien, że robiliście zakupy spożywcze w dużym supermarkecie, i zakładam, że zerknęliście na swój paragon.

To są właśnie wysokowymiarowe dane rzadkie.

Pytanie brzmi: dlaczego?

Każdy produkt na półkach sklepu ma kod kreskowy. Tak przecież skanuje się zakupy przy płaceniu, prawda?

Elektroniczna kasa i skaner mają tablicę przeglądową kodów kreskowych, a ta tablica opisuje numeryczny kod kreskowy, czytelny dla człowieka opis produktu, cenę, po jakiej jest sprzedawany, i być może to, czy podlega podatkowi od sprzedaży, a także inne rzeczy. Może być ona całkiem duża, bo opisuje wszystko, co sklep sprzedaje.

A teraz, gdybym miał wszystkie dane z paragonów Wszystkich klientów i chciał porównać Wasze zachowania zakupowe z innymi ludźmi, zbudowałbym następującą bardzo, bardzo dużą macierz

(którą można sobie wyobrazić jako bardzo duży arkusz kalkulacyjny):

Mamy kolumnę dla każdego kodu kreskowego. Mamy wiersz dla każdego klienta. Będzie to jeden Bardzo Duży arkusz! Wyobraźcie sobie, że w dużym Walmarcie jest na przykład coś około 300 000 kodów kreskowych (kolumny). Klientów może być 15 milionów (wiersze).

Wracając teraz do Waszego paragonu ze sklepu spożywczego, wyobraźcie sobie, że przewijacie w dół, aby znaleźć swój identyfikator klienta w tym arkuszu, a potem przechodzicie przez kolejne kolumny, wpisując zero, jeśli nie kupiliście danego produktu, albo liczbę kupionych sztuk, które mają ten sam kod kreskowy.

Prawdopodobnie nie kupiliście 300 000 rzeczy podczas jednych zakupów, więc jest dość oczywiste, że w większości komórek w Waszym wierszu będzie zero, i tak samo jest u wszystkich innych. Jeśli kupiliście 4 puszki zupy, w tej jednej kolumnie w Waszym wierszu komórka będzie miała liczbę 4, co oznacza, że kupiliście 4 puszki tej zupy.

Słowem Rzadkie opisujemy tę sytuację, w której większość komórek u wszystkich jest zerowa. Wyrażenia „wysokowymiarowe” używamy w odniesieniu do bardzo dużej liczby kolumn (produktów).

Właśnie tak wysokowymiarowe dane rzadkie są tworzone przez Was nieustannie!

Nasza baza danych pozwala nam przeszukać ten zbiór, aby znaleźć osobę, która jest Waszym najbliższym sąsiadem, czyli osobę, której koszyk zakupowy jest mierzalnie najbardziej podobny do Waszego. Robimy to, obliczając kąt kosinusowy między Waszym wektorem zakupów a wektorem każdego innego klienta. Potrafimy to zrobić w milisekundach, nawet jeśli klientów jest 40 milionów, a wymiarów 350 000, przy użyciu bardzo złożonych sztuczek matematycznych.

Oznacza to, że UltraDim potrafi wykrywać sąsiadów będących niemal duplikatami, polecać produkty używane przez Ludzi-Takich-Jak-Wy, identyfikować anomalie (brak bliskich sąsiadów), budować segmentacje klientów, aby dopasować doświadczenie klienta i prowadzić lepszy CRM, a nawet klasyfikować zmiany zachowań kupujących w czasie, na przykład wraz ze zmianą ich etapu życia.

I UltraDim robi to na danych natywnych, a nie na podsumowaniu, które pogarsza analizę.

Możemy oczywiście indeksować zbiory danych AI, czyli osadzenia (embeddingi) tekstów i dokumentów, i wykonywać wyszukiwanie wspomagane wyszukiwaniem informacji, co właśnie oznacza RAG. Ale dane niskowymiarowe, poniżej 10 000 wymiarów, można dziś przeszukiwać tradycyjnymi narzędziami. Nasza prawdziwa wartość leży w tym nowym terytorium poza tą granicą, gdzie nasze narzędzia dają Wam możliwość podejmowania lepszych decyzji strategicznych.

## Gdzie jeszcze spotyka się wysokowymiarowe dane rzadkie?

Ten typ zbioru danych jest spotykany WSZĘDZIE i jest streszczany do raportów, które ukrywają jego wartość.

Wasz genom. Dane o klientach. Dane cybernetyczne. Sieci IoT. Dane z liczników energii. Dane cyfrowych bliźniaków. Dane o transakcjach zakupowych. Dane łańcucha dostaw. Dane giełdowe. Zbiory danych chemicznych. Zbiory danych fizycznych. Zbiory danych z dronów i robotów, w tym z czujników pokładowych. Dane o wyborach filmów. Dane wyszukiwania semantycznego. Dane pogodowe. Lista nie ma końca.

Wyobrażamy sobie przyszłość, pogranicze, gdzie komputery i ludzie współpracują, a naszą misją w Gamakon jest pomóc Wam *Nawigować po Pograniczu*.
