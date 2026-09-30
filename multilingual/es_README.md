# UltraDim

**Una base de datos vectorial analítica rápida, concebida para conjuntos de datos de dimensionalidad extrema.**<br>
**Probada a 30 millones de dimensiones, con el objetivo de llegar a mil millones.**

*Este documento es la traducción al español del [README en inglés](../README.md). Las rutas y los enlaces apuntan a los archivos del repositorio.*

*¿Es nuevo en esto? [Para los no técnicos: ¿qué son los datos dispersos de alta dimensionalidad?](es_WHAT_IS_HIGH_DIMENSIONAL_SPARSE_DATA.md)*

UltraDim almacena, busca, cartografía, clasifica y agrupa vectores mucho más allá de los límites dimensionales de las bases de datos vectoriales convencionales: datos densos hasta ~256 000 dimensiones, datos dispersos hasta decenas de millones, probado en ejecuciones de producción a **30 000 000 de dimensiones** sobre corpus reales de química, con demostraciones a 100 millones de dimensiones. Está escrita en Rust, acelerada por GPU mediante Metal en macOS y Vulkan en Linux, y se maneja desde Python.

UltraDim se distribuye como un paquete Python compilado (wheel) para macOS en Apple Silicon, Linux x86_64 y Linux arm64, para CPython 3.12 o posterior — una compilación por plataforma sirve para todas las versiones posteriores, y el paquete no tiene dependencias. La versión actual es la 0.5.0, en la página de [Releases](../../../releases). Otras plataformas — Windows, Mac Intel — están disponibles bajo petición: escriba a jesung@gamakon.ai o andrew@gamakon.ai. El uso no comercial es gratuito bajo la licencia PolyForm Noncommercial 1.0.0. El uso comercial requiere una licencia de Gamakon Ltd. El texto de la licencia es [`LICENSE`](../LICENSE); el aviso que explica ambas modalidades es [`LICENSES/LICENSE.md`](../LICENSES/LICENSE.md).

<p align="center">
  <img src="../figures/chembl_50k_30m_bloommap.svg" width="820" alt="BloomMap de 50 000 moléculas de ChEMBL agrupadas a 30 000 000 de dimensiones">
</p>
<p align="center"><i>El espacio químico como BloomMap: 50 000 moléculas de ChEMBL, agrupadas jerárquicamente a sus 30 000 000 de dimensiones nativas.</i></p>

---

## Funciones

- **Carga de datos ultradimensionales** — ingiera vectores densos grandes, probados hasta ~256 000 dimensiones; o vectores dispersos grandes, probados hasta 30 M, con 100 M demostrados. Sus necesidades de RAM y de disco crecen con sus valores no nulos, no con el tamaño bruto del vector.
- **Ordenación exacta de los vecinos más cercanos** — nuestra búsqueda en dos etapas encuentra candidatos y los ordena de forma exacta con un cálculo de coseno verdadero.
- **Funciones integradas para auditar la exhaustividad (recall) y la latencia del índice** — con una función de ajuste automático que recorre las configuraciones.
- **Búsqueda densa de alto rendimiento** — 1 339 consultas/s a 2,99 ms en el p50 sobre DBpedia-1M, precisión@10 = 0,9945
- **Mapas UMAP nativos** — implementación de UMAP determinista, en caché y rápida para conjuntos de datos ultradimensionales. Los nuevos puntos no vistos se puntúan en milisegundos; incluye reajuste incremental a ~1,5 % del coste de una reconstrucción; salidas entre 2-D y 256-D, que sirven tanto para la visualización como para la reducción de dimensionalidad.
- **Construcción de grafos k-NN con umbrales de calidad** — cada grafo lleva una medida de exhaustividad; los mapas se niegan a ajustarse sobre grafos por debajo de 0,99
- **Agrupamiento para datos ultradimensionales, incluso con 30 millones de dimensiones** — k-means esférico y agrupamiento jerárquico rápidos, residentes en GPU, que ofrecen agrupamiento sobre datos brutos de dimensionalidad extrema.
- **Agrupamiento por densidad a lo largo del tiempo, y clasificación** — HDBSCAN en GPU construye un linaje de agrupamiento por densidad sobre una familia y lo hace avanzar a medida que llegan filas nuevas, de modo que puede leer los grupos y cómo se forman, se desplazan y se dividen entre dos instantes. `UltraKnnClassify` etiqueta cada fila nueva con un grupo del linaje vigente.
- **Detección de anomalías en alta dimensión, en flujo** — evaluar las llegadas contra la estructura de vecinos más próximos existente en alta dimensión, y colocarlas después sobre un mapa UMAP vivo para que las poblaciones anómalas y emergentes se hagan visibles; la figura en flujo de más abajo es un breve script sobre la RPC de transformación de mapa
- **Factorización y recomendación** — decodificar valores retenidos directamente desde el índice; un método de vecindad sin parámetros, competitivo con referencias entrenadas en un banco de pruebas público
- **Generación de datos sintéticos sobre hiperesferas** — el código ofrece la generación con wgpu de puntos uniformes de Muller-Marsaglia sobre la superficie de la hiperesfera en la que reside nuestro índice de datos. Forma parte de un método experimental para reequilibrar conjuntos de datos aplicando la etiqueta minoritaria de un punto real a sus k vecinos sintéticos más cercanos.
- **Visualización BloomMap** — renderizado de pósteres con calidad de publicación para agrupamientos jerárquicos
- **Operaciones sobre datos** — exportación a CSV, JSON y un formato binario; analítica de colecciones; generación de embeddings de texto en el servidor
- **Un servidor MCP** — para que cualquier agente o IA pueda ayudarle a usar el sistema y a estudiar sus datos.
- **Tres formas de ejecución** — en su propio proceso como paquete Python; como servidor MCP para un asistente; o como servidor compartido al que muchos clientes acceden por gRPC a través de un puerto, disponible bajo petición. El mismo motor en los tres casos (véase [Arquitectura](#arquitectura)).
- **Trazabilidad de principio a fin** — parámetros versionados, semillas, contabilidad de filas y resultados exportables, de modo que toda salida analítica pueda examinarse y repetirse

## Obtenerla

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install ./ultradim-0.5.0-cp312-abi3-macosx_11_0_arm64.whl      # sin dependencias
```

```python
import ultradim
db = ultradim.UltraDim("./db")
print(len(db.capabilities()))          # 205 servicios (véase Arquitectura)
db.call_json("HealthCheck", "{}")      # llame a cualquiera por su nombre
```

La base de datos se ejecuta dentro de su proceso. No hay ningún servidor que arrancar ni puerto que abrir. Se usa una GPU cuando la hay (Metal en macOS, Vulkan en Linux). Sin GPU, UltraDim carga, indexa y busca datos dispersos y densos, construye grafos de vecindad y linajes de densidad, y mide la exhaustividad. Los ajustes UMAP, el agrupamiento k-means y los linajes k-means necesitan una GPU y devuelven un error sin ella. Medido en [`docs/GPU_SETTINGS.md`](../docs/GPU_SETTINGS.md).

**Windows:** los usuarios de Windows deberían poder ejecutar el paquete de Linux mediante WSL2. Aún no hemos podido probarlo; contáctenos si necesita ayuda con esto.

## Arquitectura

El motor se ejecuta como servidor gRPC, y los clientes — escritos en Rust — lo comparten. El índice se fragmenta por semilla de proyección aleatoria (cuatro por defecto), y la tabla de claves de cada semilla es independiente. La API gRPC ofrece **205 servicios**.

Para la comunidad publicamos una compilación PyO3, hecha con maturin. Incorpora el mismo motor en su proceso Python — sin servidor que arrancar ni puerto que abrir — y se instala con un solo `pip install`. Este repositorio es ese paquete.

El servidor MCP envuelve los 205 servicios en **46 herramientas**, documentadas en [`mcp/README.md`](../mcp/README.md), que cualquier asistente lee como manual para manejar el sistema.

Los despliegues cliente-servidor para empresas — escalado horizontal sobre varios servidores, en el que cada fragmento de semilla se sirve desde su propio servidor — están disponibles bajo petición: jesung@gamakon.ai o andrew@gamakon.ai.

## Qué puede hacer con ella

**Buscar en datos ultraanchos y fiarse de las respuestas.** UltraDim trata sus datos a su dimensionalidad nativa — huellas moleculares, cestas de la compra, genómica en codificación one-hot, embeddings de texto — sin hashing de características ni truncamiento por su parte. Las puntuaciones que recibe son cosenos verdaderos contra sus vectores originales, y el índice mide bajo demanda su propia exhaustividad (recall) de candidatos contra las respuestas exactas por fuerza bruta, de modo que cada corpus viene con un certificado de calidad para esa exhaustividad.

**Construir motores de recomendación en tiempo real.** La capacidad de UltraDim para encontrar los verdaderos vecinos más cercanos a través de dimensiones vastísimas abre vías enteramente nuevas para la construcción de motores de recomendación: podemos consultar directamente la base de datos por las personas-que-compraron-como-usted y fundar sobre ellas una recomendación siempre actualizada. Nuestras pruebas sobre MovieLens-20M muestran Recall@20 = 0,362 sin modelo alguno. Al fusionar nuestros resultados de búsqueda con un decodificador ridge, ese valor ascendió a 0,3900 (IC del 95 % [0,3847, 0,3955]) con NDCG@100 = 0,4229, y se sirvió en unos 17 ms por usuario en un portátil Mac. Las recomendaciones derivan en tiempo real con el cambio del comportamiento de los usuarios.

**Construir mapas 2-D vivos de datos de 30 M de dimensiones.** Los mapas UMAP se calculan de forma nativa en el servidor, por lo que la construcción de mapas funciona con vectores grandes de longitud extrema, donde otras herramientas tienen dificultades incluso para cargar los datos. Los mapas son objetos vivos: los nuevos puntos se colocan sobre un mapa existente en milisegundos, los lotes pequeños se incorporan a aproximadamente el 1,5 % del coste de una reconstrucción, y el historial de versiones del mapa sirve además como detector de deriva para su flujo de datos.

<p align="center">
  <img src="../figures/umap_chembl_30m.png" width="410" alt="UMAP de 50 000 moléculas de ChEMBL a 30 M de dimensiones, exhaustividad del grafo 0,9996">
  <img src="../figures/umap_mnist_70k.png" width="410" alt="UMAP de los 70 000 dígitos de MNIST">
</p>
<p align="center"><i>Analítica de corpus a 30.000.000 de dimensiones: la saturación del soporte de características a medida que crece el corpus de ChEMBL.</i></p>

<p align="center">
  <img src="../figures/forex_umap_2007_2026.gif" width="560" alt="El mercado de divisas como mapa vivo, de 2007 a 2026, un punto por día de cotización">
</p>
<p align="center"><i>Treinta años del mercado de divisas en un solo mapa. Cada punto es un día de cotización, descrito por los rendimientos estandarizados de 1 992 pares de divisas ese día, y los días que se movieron de forma parecida quedan juntos. El mapa se ajustó sobre los primeros 3 000 días y cada día posterior se incorporó a él a su llegada, cada sesión de enero de 1996 a abril de 2026, coloreada por año. Lo que el mapa muestra es que la dinámica del mercado cambia de un año a otro, y a menudo de forma brusca. Una estrategia de negociación construida sobre los días de un año tiene poco alcance más allá de él antes de perder valor. Los primeros diez años construyeron el mapa base, de modo que la animación muestra de 2007 a 2026; la <a href="../figures/forex_market_full_1996_2026.mp4">serie completa desde 1996</a> es un vídeo de ocho minutos. Aprenda a elaborar uno de estos diagramas a partir de nuestro ejemplo, <a href="../examples/04_living_map_animation.py">examples/04_living_map_animation.py</a>.</i></p>

**Agrupar y puntuar vectores de cualquier longitud.** El k-means esférico y el agrupamiento jerárquico se ejecutan residentes en GPU a dimensionalidad extrema, con puntuaciones de calidad corregidas por dimensión que siguen siendo comparables entre dimensionalidades; así, la pregunta «¿es real este agrupamiento?» tiene una respuesta estadística a 30 M de dimensiones, y no solo a 300.

Puntuación de novedad de las llegadas sobre un mapa ajustado; factorización que decodifica valores retenidos directamente desde el índice; generación de datos sintéticos y aumento de clases minoritarias; analítica de colecciones; exportaciones para las herramientas posteriores.

<p align="center">
  <img src="../figures/stream_anomaly_map.png" width="560" alt="Mapa de anomalías en flujo: 987 442 artículos de DBpedia ajustados, con 2 904 llegadas coloreadas según su novedad">
</p>
<p align="center"><i>Detección de novedad en flujo, mostrada sobre un mapa vivo: 987 442 artículos de DBpedia ajustados (en gris) y 2 904 puntos recién llegados, rodeados y coloreados según su novedad medida; llegadas familiares en verde, anomalías en rojo.</i></p>

<p align="center">
  <img src="../figures/chembl_support_saturation.png" width="410" alt="Saturación del soporte de características de ChEMBL a medida que crece el corpus">
</p>
<p align="center"><i>Izquierda: la puntuación de novedad separa con nitidez las llegadas familiares de las nuevas. Derecha: analítica de corpus a 30 M de dimensiones; la saturación del soporte de características a medida que crece el corpus de ChEMBL.</i></p>

## Rendimiento medido

Todas las cifras proceden de experimentos controlados contra oráculos exhaustivos exactos, en un único Apple M3 Max; calidad y latencia se informan juntas.

| Corpus | Dimensionalidad | Filas | Calidad | Latencia / caudal |
|---|---|---|---|---|
| Moléculas de ChEMBL (disperso) | 30 000 000 | 500 000 | recall@10 = 0,9992 | 56 ms por consulta |
| Moléculas de ChEMBL (disperso, perfil rápido) | 30 000 000 | 500 000 | recall@10 = 0,9964 | 29 ms por consulta |
| Embeddings de DBpedia (denso) | 1 536 | 1 000 000 | precisión@10 = 0,9945 | 1 339 consultas/s a 2,99 ms en el p50 |
| Cestas de la compra (disperso) | 100 000 | 100 000 | recall@10 = 0,9851 | p50 17,5 ms |
| Datos estructurados sintéticos (disperso) | 1 800 000 | 50 000 | recall@10 = 1,000 | p50 15,7 ms |

Trabajar en altas dimensiones es eficiente gracias a nuestra ingeniería avanzada. Llevar un corpus de 1 M a 10 M de dimensiones añade ~0,08 GiB de memoria residente, porque el almacenamiento disperso crece con sus valores no nulos, no con la dimensionalidad declarada.

## Trabajar con grupos de investigación

UltraDim es utilizado por grupos de investigación en cargas de trabajo científicas reales: representaciones moleculares, perfiles genómicos y epigenómicos, y grandes matrices de observación. El uso en investigación es gratuito bajo la licencia no comercial; descargue el paquete y empiece. Un buen proyecto tiene un corpus de alta dimensionalidad, grande, disperso o lento de analizar con las herramientas actuales; una representación vectorial y una métrica defendibles; y una pregunta de recuperación, de cohorte, de agrupamiento o de visualización.

**[Trabajar con grupos de investigación →](../RESEARCH_GROUPS.md)** — o escriba a **andrew@gamakon.ai** para recibir ayuda con su corpus, o sobre el uso comercial.

## Documentos

| Documento | Contenido |
|---|---|
| [Presentación de UltraDim](../docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research*: motivación, preguntas de investigación, principios de evaluación (no confidencial, junio de 2026, en inglés) |
| [Testimonios](../TESTIMONIALS.md) | Lo que dicen los grupos participantes |
| [Guía del usuario](../docs/UltraDim_User_Guide.md) | Instalación, inicio rápido denso, ejemplo disperso de principio a fin, exhaustividad, mapas, agrupamiento, lista de RPC, autoajuste (en inglés) |
| [Guía de ajuste](../docs/UltraDim_Tuning_Guide.md) | Qué mueve la exhaustividad, qué no, y qué hacer cuando cae por debajo de la tolerancia (en inglés) |
| [Reemplazar y eliminar filas](../docs/SPARSE_UPSERT_SEMANTICS.md) | Identificadores de fila, facetas, reintentos, durabilidad (en inglés) |
| [Con y sin GPU](../docs/GPU_SETTINGS.md) | Qué necesita una GPU, medido; los dos ajustes (en inglés) |
| [Guía del servidor MCP](../mcp/README.md) | Instalación, actualización, cada herramienta, el camino nominal, notas de versión (en inglés) |
| [Registro de cambios](../CHANGELOG.md) | Cada versión, de la 0.1 a la 0.5.0 (en inglés) |

## Acerca de

UltraDim está desarrollada y licenciada por **Gamakon Ltd**. El uso no comercial es gratuito bajo la licencia PolyForm Noncommercial 1.0.0. Existe una versión cliente-servidor disponible bajo petición, también para las organizaciones no comerciales que la necesiten; podemos ayudarle a instalarla y configurarla. Escriba a [jesung@gamakon.ai](mailto:jesung@gamakon.ai) o a [andrew@gamakon.ai](mailto:andrew@gamakon.ai).

### Origen

*Cómo surgió*

Internamente, la base de datos UltraDim utiliza una forma completamente nueva de índice vectorial, desarrollada por Andrew Morgan, autor de *Mastering Spark for Data Science*. Inventó este índice para construir y poner a prueba sus ideas para resolver el reto ARC-AGI; ese trabajo sigue en marcha.

Con treinta años de ingeniería en ciencia de datos a sus espaldas, Andrew lo implementó con una larga lista de optimizaciones que, junto con el nuevo índice, permiten sustituir un gran clúster de Spark por un portátil Mac.

Andrew se apoyó en la IA, pero explica que fue extremadamente frustrante. «A la IA no le gusta innovar. Como nunca había visto este diseño de índice, le costaba una y otra vez aportar algo útil, y a menudo devolvía deliberadamente el código a ideas antiguas.» Tras un año de frustración persistente, el resultado es un sistema del que estamos genuinamente orgullosos. Esperamos que lo disfrute y que lo use para construir algo extraordinario.
