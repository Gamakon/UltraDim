# UltraDim

**Szybka analityczna baza wektorowa dla zbiorów danych o ekstremalnej wymiarowości.**<br>
**Sprawdzona przy 30 milionach wymiarów, z celem miliarda.**

*Ten dokument jest polskim tłumaczeniem [README w języku angielskim](../README.md). Ścieżki i odnośniki wskazują pliki w repozytorium.*

*Pierwszy raz z tym tematem? [Dla osób nietechnicznych: czym są wysokowymiarowe dane rzadkie?](pl_WHAT_IS_HIGH_DIMENSIONAL_SPARSE_DATA.md)*

UltraDim przechowuje, przeszukuje, mapuje, klasyfikuje i grupuje wektory daleko poza granicami wymiarowości konwencjonalnych baz wektorowych: dane gęste do ~256 000 wymiarów, dane rzadkie do dziesiątek milionów, co potwierdzono w uruchomieniach produkcyjnych przy **30 000 000 wymiarów** na rzeczywistych korpusach chemicznych, z demonstracjami przy 100 milionach wymiarów. Jest napisana w języku Rust, akcelerowana na GPU przez Metal w macOS i Vulkan w Linuksie, i sterowana z Pythona.

UltraDim jest dostarczana jako skompilowany pakiet Pythona (wheel) dla macOS na Apple Silicon, Linux x86_64 i Linux arm64, dla Pythona 3.12. Bieżące wydanie to 0.4.0, na stronie [Releases](../../../releases). Użytek niekomercyjny jest bezpłatny na licencji PolyForm Noncommercial License 1.0.0. Użytek komercyjny wymaga licencji od Gamakon Ltd. Tekst licencji znajduje się w [`LICENSE`](../LICENSE); nota objaśniająca obie ścieżki to [`LICENSES/LICENSE.md`](../LICENSES/LICENSE.md).

<p align="center">
  <img src="../figures/chembl_50k_30m_bloommap.svg" width="820" alt="BloomMap 50 000 cząsteczek ChEMBL pogrupowanych przy 30 000 000 wymiarów">
</p>
<p align="center"><i>Przestrzeń chemiczna jako BloomMap: 50 000 cząsteczek ChEMBL, pogrupowanych hierarchicznie przy ich natywnej szerokości 30 000 000 wymiarów.</i></p>

---

## Funkcje

- **Ładowanie danych ultrawymiarowych** — przyjmowanie dużych wektorów gęstych, przetestowane do ~256 000 wymiarów; lub dużych wektorów rzadkich, przetestowane do 30 M, ze 100 M zademonstrowanymi. Zapotrzebowanie na pamięć RAM i dysk rośnie wraz z liczbą wartości niezerowych, a nie z surowym rozmiarem wektora.
- **Samoweryfikujące się wyszukiwanie** — dokładne wyniki prawdziwego kosinusa, z certyfikatami pełności (recall) mierzonymi na żądanie względem dokładnego przeszukiwania wyczerpującego
- **Wysokoprzepustowe wyszukiwanie gęste** — 1 339 zapytań/s przy p50 2,99 ms na DBpedia-1M, precyzja@10 = 0,9945
- **Natywne mapy UMAP** — deterministyczne, buforowane dopasowania po stronie serwera przy dowolnej szerokości (szerokość oznacza liczbę wymiarów); nowe punkty umieszczane w milisekundach; przyrostowe ponowne dopasowanie za ~1,5 % kosztu przebudowy; wynik w 2-D, w wymiarze pośrednim (do 256 składowych) lub sferyczny
- **Budowa grafów k-NN z progami jakości** — każdy graf niesie zmierzoną wartość pełności; mapy odmawiają dopasowania na grafach poniżej 0,99
- **Grupowanie danych ultrawymiarowych, nawet przy 30 milionach wymiarów** — sferyczne k-średnich i grupowanie hierarchiczne rezydujące na GPU, z miarami jakości skorygowanymi o wymiar, porównywalnymi między szerokościami
- **Strumieniowe wykrywanie anomalii w wysokich wymiarach** — ocena nadchodzących punktów względem istniejącej wysokowymiarowej struktury najbliższych sąsiadów, a następnie umieszczenie ich na żywej mapie UMAP, tak aby populacje anomalne i wyłaniające się stały się widoczne; poniższa figura strumieniowa to krótki skrypt nad RPC transformacji mapy
- **Faktoryzacja i rekomendacja** — dekodowanie wartości wstrzymanych bezpośrednio z indeksu; bezparametrowa metoda sąsiedztwa konkurencyjna wobec trenowanych punktów odniesienia na publicznym benchmarku
- **Generowanie danych syntetycznych na hipersferach** — kod oferuje generowanie w wgpu jednorodnych punktów metodą Muller-Marsaglia na powierzchni hipersfery, na której istnieje nasz indeks danych. Stanowi to część eksperymentalnej metody ponownego równoważenia zbiorów danych przez nadanie etykiety mniejszościowej rzeczywistego punktu jego k najbliższym syntetycznym sąsiadom.
- **Wizualizacja BloomMap** — renderowanie plakatów jakości publikacyjnej z grupowań hierarchicznych
- **Operacje na danych** — eksport do CSV, JSON i formatu binarnego; analityka kolekcji; osadzanie tekstu (embedding) po stronie serwera
- **Trzy sposoby uruchomienia** — we własnym procesie jako pakiet Pythona; jako serwer MCP dla asystenta; lub jako serwer współdzielony, do którego wielu klientów łączy się przez port za pomocą gRPC, dostępny na życzenie. Te same 204 RPC we wszystkich trzech.
- **Pochodzenie danych na każdym etapie** — wersjonowane parametry, ziarna losowości, rozliczanie wierszy i eksportowalne wyniki, tak aby każdy wynik analityczny można było zbadać i powtórzyć

## Jak ją zdobyć

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install ./UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl      # numpy instaluje się razem z nim
```

```python
import ultradim
db = ultradim.UltraDim("./db")
print(len(db.capabilities()))          # 204
db.call_json("RpcName", '{...}')       # dowolne z nich
```

Baza danych działa wewnątrz Twojego procesu. Nie ma serwera do uruchomienia ani portu do otwarcia. GPU jest używane, gdy jest dostępne (Metal w macOS, Vulkan w Linuksie). Bez GPU UltraDim ładuje, indeksuje i przeszukuje dane rzadkie i gęste, buduje grafy sąsiedztwa i linie gęstości oraz mierzy pełność. Dopasowania UMAP, grupowanie k-średnich i linie k-średnich wymagają GPU i bez niego zwracają błąd. Pomiary w [`docs/GPU_SETTINGS.md`](../docs/GPU_SETTINGS.md).

Serwer MCP, `mcp/ultradim_mcp_server_v0_4_0.py`, opakowuje ten sam pakiet jako 46 narzędzi, tak aby asystent mógł tworzyć kolekcje, ładować, indeksować, wyszukiwać, grupować i mapować bez pisania przez Ciebie kodu w Pythonie. Jego przewodnik to [`mcp/README.md`](../mcp/README.md).

Dostępna jest wersja klient-serwer. Jeden serwer UltraDim działa na hoście i jest współdzielony przez wielu klientów przez port. Klienci zapisują i odpytują przez gRPC. gRPC to zwarty protokół binarny, więc ładowanie szerokich wektorów jest szybkie w sieci. To ten sam silnik co w pakiecie, z tymi samymi 204 RPC. Skontaktuj się z nami, aby ją otrzymać. Dotyczy to również organizacji niekomercyjnych, które jej potrzebują: możemy pomóc w instalacji i konfiguracji. jesung@gamakon.ai lub andrew@gamakon.ai.

## Uruchamianie z asystentem AI

Repozytorium zawiera serwer MCP, `mcp/ultradim_mcp_server_v0_4_0.py`, który udostępnia bazę danych jako 46 narzędzi dla Claude Code, Codex lub dowolnego asystenta obsługującego MCP. Asystent obsługuje wtedy bazę danych w Twoim imieniu: tworzy rodzinę, ładuje Twoje wektory, buduje indeks, wyszukuje, grupuje i mapuje, i odczytuje Ci wyniki. Ty opisujesz badanie; on wykonuje wywołania.

Zainstaluj pakiet, sklonuj to repozytorium i otwórz sesję asystenta w klonie. Dla Claude Code plik `.mcp.json` w katalogu głównym rejestruje serwer; dla Codex dodaj do `~/.codex/config.toml`:

```toml
[mcp_servers.ultradim]
command = "python3.12"
args = ["/sciezka/do/UltraDim/mcp/ultradim_mcp_server_v0_4_0.py", "--db", "/sciezka/do/twojej/bazy"]
```

`command` musi być tym Pythonem, w którym zainstalowano pakiet. Następnie poproś, słowami: „załaduj wektory z tego pliku do UltraDim, uczyń je przeszukiwalnymi i pokaż mi mapę”. Pierwszym wywołaniem asystenta powinno być narzędzie `whats_available`, które wypisuje każde narzędzie i ścieżkę nominalną na żywo z pakietu. Pełny przewodnik to [`mcp/README.md`](../mcp/README.md) (po angielsku).

## Co można z nią zrobić

**Przeszukuj ultraszerokie dane i ufaj odpowiedziom.** UltraDim obsługuje Twoje dane przy ich natywnej szerokości — odciski molekularne, koszyki zakupowe, genomikę w kodowaniu one-hot, osadzenia tekstu — bez haszowania cech ani obcinania po Twojej stronie. Wyniki, które otrzymujesz, to prawdziwe kosinusy względem Twoich surowych wektorów, a indeks mierzy na żądanie własną pełność kandydatów względem dokładnych odpowiedzi z przeszukiwania wyczerpującego, więc każdy korpus otrzymuje certyfikat jakości, a nie nadzieję.

**Buduj żywe mapy 2-D danych o 30 M wymiarów.** Mapy UMAP są obliczane natywnie na serwerze, więc budowanie map działa przy szerokościach, przy których standardowe narzędzia w ogóle nie są w stanie załadować danych. Mapy są żywymi obiektami: nowe punkty są umieszczane na istniejącej mapie w milisekundach, małe partie wtapiają się za około 1,5 % kosztu przebudowy, a historia wersji mapy służy zarazem jako detektor dryfu Twojego strumienia danych.

<p align="center">
  <img src="../figures/umap_chembl_30m.png" width="410" alt="UMAP 50 000 cząsteczek ChEMBL przy 30 M wymiarów, pełność grafu 0,9996">
  <img src="../figures/umap_mnist_70k.png" width="410" alt="UMAP 70 000 cyfr MNIST">
</p>
<p align="center"><i>Po lewej: 50 000 cząsteczek ChEMBL zmapowanych przy 30 000 000 surowych wymiarów; graf sąsiedztwa pod mapą zmierzył pełność 0,9996 względem dokładnej wyroczni. Po prawej: mapa kontrolna MNIST 70K z tego samego potoku.</i></p>

<p align="center">
  <img src="../figures/forex_umap_2007_2026.gif" width="560" alt="Rynek walutowy jako żywa mapa, od 2007 do 2026, jeden punkt na dzień handlowy">
</p>
<p align="center"><i>Trzydzieści lat rynku walutowego na jednej mapie. Każdy punkt to jeden dzień handlowy, opisany standaryzowanymi stopami zwrotu 1 992 par walutowych z tego dnia, a dni o podobnym przebiegu leżą blisko siebie. Mapa została dopasowana na pierwszych 3 000 dniach, a każdy kolejny dzień był do niej wstawiany w miarę napływania, każda sesja od stycznia 1996 do kwietnia 2026, pokolorowana według roku. Mapa pokazuje, że dynamika rynku zmienia się z roku na rok, i to często gwałtownie. Strategia handlowa zbudowana na dniach jednego roku ma niewielki zasięg poza nim, zanim straci wartość. Pierwsze dziesięć lat zbudowało mapę bazową, więc animacja pokazuje lata 2007 do 2026; <a href="../figures/forex_market_full_1996_2026.mp4">pełny przebieg od 1996</a> to ośmiominutowe wideo. Jak samodzielnie sporządzić taki diagram, pokazuje nasz przykład <a href="../examples/04_living_map_animation.py">examples/04_living_map_animation.py</a>.</i></p>

**Grupuj i oceniaj przy dowolnej szerokości.** Sferyczne k-średnich i grupowanie hierarchiczne działają rezydentnie na GPU przy ekstremalnej wymiarowości, z miarami jakości skorygowanymi o wymiar, które pozostają porównywalne między szerokościami; dzięki temu pytanie „czy to grupowanie jest rzeczywiste?” ma statystyczną odpowiedź przy 30 M wymiarów, a nie tylko przy 300.

**Uruchamiaj analizy, które wykorzystują szerokość zamiast z nią walczyć.** Ocena nowości nadchodzących punktów na dopasowanej mapie; faktoryzacja dekodująca wartości wstrzymane bezpośrednio z indeksu; generowanie danych syntetycznych i augmentacja klas mniejszościowych; analityka kolekcji; eksporty dla narzędzi dalszego przetwarzania.

<p align="center">
  <img src="../figures/stream_anomaly_map.png" width="560" alt="Strumieniowa mapa anomalii: 987 442 dopasowanych artykułów DBpedia z 2 904 nadchodzącymi punktami pokolorowanymi według nowości">
</p>
<p align="center"><i>Strumieniowe wykrywanie nowości, pokazane na żywej mapie: 987 442 dopasowanych artykułów DBpedia (na szaro) z 2 904 nowo nadchodzącymi punktami, obwiedzionymi i pokolorowanymi według zmierzonej nowości; znajome przybycia na zielono, anomalie na czerwono.</i></p>

<p align="center">
  <img src="../figures/stream_dichotomy.png" width="410" alt="Dychotomia wyniku nowości między znajomymi a nowymi przybyciami">
  <img src="../figures/chembl_support_saturation.png" width="410" alt="Nasycenie wsparcia cech ChEMBL w miarę wzrostu korpusu">
</p>
<p align="center"><i>Po lewej: wynik nowości czysto oddziela znajome przybycia od nowych. Po prawej: analityka korpusu przy 30 M wymiarów; nasycenie wsparcia cech w miarę wzrostu korpusu ChEMBL.</i></p>

## Zmierzona wydajność

Wszystkie liczby pochodzą z kontrolowanych przebiegów eksperymentalnych względem dokładnych wyroczni z przeszukiwania wyczerpującego, na pojedynczym Apple M3 Max; jakość i opóźnienie raportowane razem.

| Korpus | Szerokość | Wiersze | Jakość | Opóźnienie / przepustowość |
|---|---|---|---|---|
| Cząsteczki ChEMBL (rzadkie) | 30 000 000 | 500 000 | recall@10 = 0,9992 | 56 ms na zapytanie |
| Cząsteczki ChEMBL (rzadkie, profil szybki) | 30 000 000 | 500 000 | recall@10 = 0,9964 | 29 ms na zapytanie |
| Osadzenia DBpedia (gęste) | 1 536 | 1 000 000 | precyzja@10 = 0,9945 | 1 339 zapytań/s przy p50 2,99 ms |
| Koszyki zakupowe (rzadkie) | 100 000 | 100 000 | recall@10 = 0,9851 | p50 17,5 ms |
| Syntetyczne ustrukturyzowane (rzadkie) | 1 800 000 | 50 000 | recall@10 = 1,000 | p50 15,7 ms |

Szerokość kosztuje niewiele: przejście korpusu z 1 M do 10 M wymiarów dodaje ~0,08 GiB pamięci rezydentnej, ponieważ rzadkie przechowywanie rośnie wraz z liczbą wartości niezerowych, a nie z zadeklarowaną szerokością.

## Współpraca z grupami badawczymi

UltraDim jest używana przez grupy badawcze na rzeczywistych obciążeniach naukowych: reprezentacjach molekularnych, profilach genomicznych i epigenomicznych oraz dużych macierzach obserwacyjnych. Użytek badawczy jest bezpłatny na licencji niekomercyjnej; pobierz pakiet i zacznij. Dobry projekt ma korpus wysokowymiarowy, duży, rzadki lub powolny w analizie obecnymi narzędziami; dającą się obronić reprezentację wektorową i metrykę; oraz pytanie dotyczące wyszukiwania, kohorty, grupowania lub wizualizacji.

**[Współpraca z grupami badawczymi →](../RESEARCH_GROUPS.md)** — lub napisz na **andrew@gamakon.ai**, aby uzyskać pomoc z Twoim korpusem lub w sprawie użytku komercyjnego.

## Dokumenty

| Dokument | Zawartość |
|---|---|
| [Przegląd UltraDim](../docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research*: motywacja, pytania badawcze, zasady ewaluacji (niepoufny, czerwiec 2026, po angielsku) |
| [Referencje](../TESTIMONIALS.md) | Co mówią uczestniczące grupy |
| [Przewodnik użytkownika](../docs/UltraDim_User_Guide.md) | Instalacja, szybki start dla danych gęstych, przykład rzadki krok po kroku, pełność, mapy, grupowanie, lista RPC, autotuner (po angielsku) |
| [Przewodnik strojenia](../docs/UltraDim_Tuning_Guide.md) | Co wpływa na pełność, co nie, i co zrobić, gdy pełność spada poniżej tolerancji (po angielsku) |
| [Zastępowanie i usuwanie wierszy](../docs/SPARSE_UPSERT_SEMANTICS.md) | Identyfikatory wierszy, fasety, ponowne próby, trwałość (po angielsku) |
| [Praca z GPU i bez GPU](../docs/GPU_SETTINGS.md) | Co wymaga GPU, zmierzone; dwa ustawienia (po angielsku) |
| [Przewodnik serwera MCP](../mcp/README.md) | Instalacja, aktualizacja, każde narzędzie, ścieżka nominalna, informacje o wydaniu (po angielsku) |
| [Dziennik zmian](../CHANGELOG.md) | Każde wydanie, od 0.1 do 0.4.0 (po angielsku) |

## O projekcie

UltraDim jest rozwijana i licencjonowana przez **Gamakon Ltd**. Użytek niekomercyjny jest bezpłatny na licencji PolyForm Noncommercial License 1.0.0. Wersja klient-serwer jest dostępna na życzenie, również dla organizacji niekomercyjnych, które jej potrzebują; możemy pomóc w instalacji i konfiguracji. Napisz na [jesung@gamakon.ai](mailto:jesung@gamakon.ai) lub [andrew@gamakon.ai](mailto:andrew@gamakon.ai).

### Historia powstania

*Jak do tego doszło*

Wewnętrznie baza danych UltraDim używa zupełnie nowej formy indeksu wektorowego, opracowanej przez Andrew Morgana, autora książki *Mastering Spark for Data Science*. Wynalazł ten indeks, aby budować i testować swoje pomysły na rozwiązanie wyzwania ARC-AGI; ta praca wciąż trwa.

Czerpiąc z trzydziestu lat inżynierii w dziedzinie nauki o danych, Andrew zaimplementował go za pomocą długiej listy optymalizacji, które wraz z nowym indeksem pozwalają zastąpić duży klaster Spark laptopem Mac.

Andrew korzystał z pomocy AI, ale wyjaśnia, że było to niezwykle frustrujące. „AI nie znosi innowacji. Ponieważ nigdy wcześniej nie widziała tego projektu indeksu, nieustannie miała trudności z wniesieniem czegokolwiek użytecznego, często uparcie cofając kod do starszych pomysłów.” Po roku uporczywej frustracji wynikiem jest system, z którego jesteśmy naprawdę dumni. Mamy nadzieję, że będzie się on Wam podobał i że użyjecie go do zbudowania czegoś niezwykłego.
