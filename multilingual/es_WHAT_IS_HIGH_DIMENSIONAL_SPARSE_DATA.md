# Para los no técnicos: ¿qué son los datos dispersos de alta dimensionalidad?

Voy a intentar explicar, a un público no técnico, cómo ese público crea datos dispersos de alta dimensionalidad constantemente, porque es un concepto importante.

Bien, seguro que ha hecho la compra en un gran supermercado, y voy a suponer que le ha echado un vistazo a su tique.

Eso son datos dispersos de alta dimensionalidad.

La pregunta es: ¿por qué?

Cada artículo de las estanterías de la tienda tiene un código de barras. Así es como se escanea la compra al pagar, ¿verdad?

La caja electrónica y el escáner tienen una tabla de consulta de códigos de barras, y esa tabla detalla el código de barras numérico, la descripción del producto en lenguaje humano, el precio al que se vende y, quizá, si lleva impuesto sobre las ventas, además de otras cosas. Puede ser bastante grande, porque describe todo lo que se vende en la tienda.

Ahora bien, si yo tuviera los datos de los tiques de Todos los clientes, y quisiera comparar su comportamiento de compra con el de otras personas, construiría la siguiente matriz enorme, enorme

(que puede imaginarse como una hoja de cálculo muy grande):

Tenemos una columna por cada código de barras. Tenemos una fila por cada cliente. ¡Será una hoja de cálculo Muy Grande! Imagine que en un Walmart grande hay algo así como 300 000 códigos de barras, por ejemplo (columnas). Podría haber 15 millones de clientes (filas).

Ahora, volviendo a su tique de la compra, imagine que baja por esa hoja de cálculo hasta encontrar su identificador de cliente, y luego recorre las columnas poniendo un cero si no compró ese producto, o poniendo el número de artículos que sí compró con ese mismo código de barras.

Probablemente no compró 300 000 cosas en su visita a la tienda, así que es bastante evidente que la mayoría de las celdas tendrían un cero en su caso, y lo mismo ocurre con todos los demás. Si compró 4 latas de sopa, esa única columna de su fila tendría un recuento de 4 en la celda, lo que significa que compró 4 latas de esa sopa.

Usamos la palabra Disperso para describir esta situación en la que la mayoría de las celdas son cero para todo el mundo. Usamos la expresión «alta dimensionalidad» para referirnos al número altísimo de columnas (productos).

¡Así es como usted crea datos dispersos de alta dimensionalidad constantemente!

Nuestra base de datos nos permite buscar en ese conjunto de datos a la persona que es su vecino más próximo, es decir, la persona cuya cesta de la compra es, de forma medible, la más parecida a la suya. Lo hacemos calculando el ángulo del coseno entre su vector de compra y el de cada uno de los demás clientes. Podemos hacerlo en milisegundos, incluso con 40 millones de clientes y 350 000 dimensiones, gracias a unos trucos matemáticos muy complejos.

Esto significa que UltraDim puede detectar vecinos casi duplicados, recomendar productos que usan Personas-Como-Usted, identificar anomalías (sin vecinos próximos), construir segmentaciones de clientes para adaptar la experiencia del cliente y hacer un mejor CRM, e incluso clasificar los cambios en el comportamiento de compra a lo largo del tiempo, a medida que, quizá, cambia su etapa de la vida.

Y UltraDim lo hace sobre los datos nativos, no sobre un resumen que degrada el análisis.

Por supuesto, podemos indexar conjuntos de datos de IA, es decir, embeddings de textos y documentos, y hacer búsqueda aumentada por recuperación, que es lo que significa RAG. Pero los datos de baja dimensionalidad, por debajo de 10 000 dimensiones, ya pueden buscarse hoy con herramientas tradicionales. Nuestro verdadero valor está en ese territorio nuevo que hay más allá, donde nuestras herramientas le dan la capacidad de tomar mejores decisiones estratégicas.

## ¿Dónde más se encuentran datos dispersos de alta dimensionalidad?

Este tipo de conjunto de datos se ve EN TODAS PARTES, y se resume en informes que ocultan su valor.

Su genoma. Datos de clientes. Datos de ciberseguridad. Redes IoT. Datos de contadores de energía. Datos de gemelos digitales. Datos de transacciones de compra. Datos de la cadena de suministro. Datos bursátiles. Conjuntos de datos químicos. Conjuntos de datos de física. Conjuntos de datos de drones y robots, incluidos sus sensores de a bordo. Datos de elección de películas. Datos de búsqueda semántica. Datos meteorológicos. La lista es interminable.

Imaginamos un futuro, una frontera, en el que los ordenadores y las personas colaboran, y nuestra misión en Gamakon es ayudarle a *Navegar la Frontera*.
