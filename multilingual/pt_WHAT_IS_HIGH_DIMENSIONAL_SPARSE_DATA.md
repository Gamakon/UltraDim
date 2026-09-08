# Para os não técnicos: o que são dados esparsos de elevada dimensionalidade?

Vou tentar explicar a um público não técnico como criam dados esparsos de elevada dimensionalidade a toda a hora, porque este é um conceito importante.

Ora bem, tenho a certeza de que já foi às compras a um grande supermercado, e vou assumir que já deitou uma olhadela ao seu talão.

Isto são dados esparsos de elevada dimensionalidade.

A pergunta é: porquê?

Cada artigo nas prateleiras da loja tem um código de barras. É assim que as suas compras são lidas quando paga, certo?

A caixa eletrónica e o leitor têm uma tabela de consulta de códigos de barras, e essa tabela de consulta indica o código de barras numérico, a descrição do produto legível por humanos, o preço a que é vendido e talvez se está sujeito a imposto sobre vendas, entre outras coisas. Esta tabela pode ser bastante grande, porque descreve tudo o que a loja vende.

Ora, se eu tivesse todos os dados dos talões de Todos os clientes e quisesse comparar o seu comportamento de compra com o de outras pessoas, construiria a seguinte matriz muito, muito grande

(que pode imaginar como uma folha de cálculo enorme):

Temos uma coluna para cada código de barras. Temos uma linha para cada cliente. Vai ser uma folha de cálculo Muito Grande! Imagine que há qualquer coisa como 300 000 códigos de barras num grande Walmart, por exemplo (colunas). Poderá haver 15 milhões de clientes (linhas).

Ora, voltando ao seu talão do supermercado, imagine que desce até encontrar o seu número de cliente nessa folha de cálculo, e depois percorre as colunas pondo um zero se não comprou aquele produto, ou pondo o número de artigos que comprou com esse mesmo código de barras.

Provavelmente não comprou 300 000 coisas na sua ida às compras, por isso é bastante óbvio que a maioria das células teria um zero no seu caso, e o mesmo acontece com toda a gente. Se comprou 4 latas de sopa, aquela coluna na sua linha teria uma contagem de 4 na célula, o que significa que comprou 4 latas dessa sopa.

Usamos a palavra Esparso para descrever esta situação em que a maioria das células está a zero para toda a gente. Usamos a expressão «elevada dimensionalidade» para nos referirmos ao número muito elevado de colunas (produtos).

É assim que os dados esparsos de elevada dimensionalidade são criados por si a toda a hora!

A nossa base de dados permite-nos pesquisar esse conjunto de dados para encontrar a pessoa que é o seu vizinho mais próximo, ou seja, a pessoa cujo cabaz de compras é mensuravelmente o mais parecido com o seu. Fazemo-lo calculando o ângulo do cosseno entre o seu vetor de compras e o de cada um dos outros clientes. Conseguimos fazê-lo em milissegundos, mesmo com 40 milhões de clientes e 350 000 dimensões, recorrendo a alguns truques matemáticos muito complexos.

Isto significa que o UltraDim consegue detetar vizinhos quase duplicados, recomendar produtos usados por Pessoas-Como-Você, identificar anomalias (sem vizinhos próximos), construir segmentações de clientes para personalizar a experiência do cliente e fazer melhor CRM, e até classificar mudanças no comportamento de compra ao longo do tempo à medida que, talvez, a fase da vida muda.

E o UltraDim faz isto sobre os dados nativos, não sobre um resumo que degrada a análise.

Podemos, claro, indexar conjuntos de dados de IA, ou seja, embeddings de texto e de documentos, e fazer pesquisa aumentada por recuperação, que é o que RAG significa. Mas os dados de baixa dimensionalidade, abaixo de 10 000 dimensões, já podem ser pesquisados hoje com ferramentas tradicionais. O nosso verdadeiro valor está nesse novo território para lá disso, onde as nossas ferramentas lhe dão a capacidade de tomar melhores decisões estratégicas.

## Onde mais se encontram dados esparsos de elevada dimensionalidade?

Este tipo de conjunto de dados vê-se EM TODO O LADO, e é resumido em relatórios que escondem o seu valor.

O seu genoma. Dados de clientes. Dados de cibersegurança. Redes IoT. Dados de contadores de energia. Dados de gémeos digitais. Dados de transações de compra. Dados de cadeias de abastecimento. Dados da bolsa de valores. Conjuntos de dados químicos. Conjuntos de dados de física. Conjuntos de dados de drones e robôs, incluindo os sensores a bordo. Dados de escolha de filmes. Dados de pesquisa semântica. Dados meteorológicos. A lista é interminável.

Imaginamos um futuro, uma fronteira, onde computadores e pessoas colaboram, e a nossa missão na Gamakon é ajudá-lo a *Navegar a Fronteira*.
