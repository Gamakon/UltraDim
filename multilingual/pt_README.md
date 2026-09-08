# UltraDim

**Uma base de dados vetorial analítica rápida, concebida para conjuntos de dados de dimensionalidade extrema.**<br>
**Comprovada a 30 milhões de dimensões, com o objetivo de chegar a mil milhões.**

*Este documento é a tradução para português do [README em inglês](../README.md). Os caminhos e as ligações apontam para os ficheiros do repositório.*

*É novo nisto? [Para os não técnicos: o que são dados esparsos de elevada dimensionalidade?](pt_WHAT_IS_HIGH_DIMENSIONAL_SPARSE_DATA.md)*

O UltraDim armazena, pesquisa, cartografa, classifica e agrupa vetores muito para lá dos limites dimensionais das bases de dados vetoriais convencionais: dados densos até ~256 000 dimensões, dados esparsos até dezenas de milhões, comprovado em execuções de produção a **30 000 000 de dimensões** sobre corpora reais de química, com demonstrações a 100 milhões de dimensões. Está escrito em Rust, acelerado por GPU através de Metal em macOS e Vulkan em Linux, e é comandado a partir de Python.

O UltraDim é distribuído como um pacote Python compilado (wheel) para macOS em Apple Silicon, Linux x86_64 e Linux arm64, para Python 3.12. A versão atual é a 0.4.0, na página de [Releases](../../../releases). A utilização não comercial é gratuita ao abrigo da licença PolyForm Noncommercial 1.0.0. A utilização comercial requer uma licença da Gamakon Ltd. O texto da licença é [`LICENSE`](../LICENSE); o aviso que explica ambas as modalidades é [`LICENSES/LICENSE.md`](../LICENSES/LICENSE.md).

<p align="center">
  <img src="../figures/chembl_50k_30m_bloommap.svg" width="820" alt="BloomMap de 50 000 moléculas do ChEMBL agrupadas a 30 000 000 de dimensões">
</p>
<p align="center"><i>O espaço químico como BloomMap: 50 000 moléculas do ChEMBL, agrupadas hierarquicamente à sua largura nativa de 30 000 000 de dimensões.</i></p>

---

## Funcionalidades

- **Ingestão à largura nativa** (largura significa o número de dimensões) — vetores densos até ~256 000 dimensões; vetores esparsos até dezenas de milhões (30 M comprovados, 100 M demonstrados), com uma memória que cresce com os seus valores não nulos, não com a largura declarada
- **Pesquisa autoverificada** — pontuações de cosseno exatas, com certificados de abrangência (recall) medidos a pedido contra uma pesquisa exaustiva exata
- **Pesquisa densa de alto débito** — 1 339 consultas/s a 2,99 ms no p50 sobre o DBpedia-1M, precisão@10 = 0,9945
- **Mapas UMAP nativos** — ajustes determinísticos, em cache e no servidor, a qualquer largura; novos pontos colocados em milissegundos; reajuste incremental a ~1,5 % do custo de uma reconstrução; saída em 2-D, em dimensão intermédia (até 256 componentes) ou esférica
- **Construção de grafos k-NN com limiares de qualidade** — cada grafo traz uma medida de abrangência; os mapas recusam-se a ajustar sobre grafos abaixo de 0,99
- **Agrupamento a qualquer largura** — k-means esférico e agrupamento hierárquico residentes em GPU, com pontuações de qualidade corrigidas pela dimensão, comparáveis entre larguras
- **Deteção de novidade em fluxo** — avaliar as chegadas contra a estrutura de vizinhos mais próximos existente em alta dimensão, e colocá-las depois sobre um mapa UMAP vivo para que as populações anómalas e emergentes se tornem visíveis; a figura em fluxo mais abaixo é um breve script sobre a RPC de transformação de mapa
- **Fatorização e recomendação** — descodificar valores retidos diretamente a partir do índice; um método de vizinhança sem parâmetros, competitivo com referências treinadas num banco de testes público
- **Serviços de dados sintéticos** — bancos de hiperesferas uniformes e aumento k-NN de classes minoritárias para conjuntos desequilibrados
- **Visualização BloomMap** — renderização de pósteres com qualidade de publicação para agrupamentos hierárquicos
- **Operações sobre dados** — exportação para CSV, JSON e um formato binário; analítica de coleções; geração de embeddings de texto no servidor
- **Três formas de execução** — no seu próprio processo como pacote Python; como servidor MCP para um assistente; ou como servidor partilhado a que muitos clientes acedem por gRPC através de uma porta, disponível a pedido. As mesmas 204 RPC nos três casos.
- **Rastreabilidade de ponta a ponta** — parâmetros versionados, sementes, contabilidade de linhas e resultados exportáveis, de modo que toda a saída analítica possa ser examinada e repetida

## Obtê-lo

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

A base de dados executa-se dentro do seu processo. Não há nenhum servidor a arrancar nem porta a abrir. Uma GPU é utilizada quando existe (Metal em macOS, Vulkan em Linux). Sem GPU, o UltraDim carrega, indexa e pesquisa dados esparsos e densos, constrói grafos de vizinhança e linhagens de densidade, e mede a abrangência. Os ajustes UMAP, o agrupamento k-means e as linhagens k-means precisam de uma GPU e devolvem um erro sem ela. Medido em [`docs/GPU_SETTINGS.md`](../docs/GPU_SETTINGS.md).

Um servidor MCP, `mcp/ultradim_mcp_server_v0_4_0.py`, envolve o mesmo pacote sob a forma de 46 ferramentas, de modo que um assistente pode criar coleções, ingerir, indexar, pesquisar, agrupar e cartografar sem que o utilizador escreva Python. O seu guia é [`mcp/README.md`](../mcp/README.md).

Existe uma versão cliente-servidor. Um servidor UltraDim executa-se numa máquina anfitriã e é partilhado por muitos clientes através de uma porta. Os clientes escrevem e consultam por gRPC. O gRPC é um protocolo binário compacto, pelo que a ingestão de vetores largos é rápida na rede. É o mesmo motor que o pacote, com as mesmas 204 RPC. Contacte-nos para o obter. Isto inclui as organizações não comerciais que dele necessitem: podemos ajudá-lo a instalá-lo e a configurá-lo. jesung@gamakon.ai ou andrew@gamakon.ai.

## Executá-lo com um assistente de IA

O repositório inclui um servidor MCP, `mcp/ultradim_mcp_server_v0_4_0.py`, que expõe a base de dados como 46 ferramentas ao Claude Code, ao Codex ou a qualquer assistente que fale MCP. O assistente passa então a operar a base de dados em seu nome: cria a família, ingere os seus vetores, constrói o índice, pesquisa, agrupa e cartografa, e lê-lhe os resultados. O utilizador descreve o estudo; o assistente faz as chamadas.

Instale o pacote, clone este repositório e abra uma sessão de assistente no clone. Para o Claude Code, o ficheiro `.mcp.json` da raiz regista o servidor; para o Codex, acrescente a `~/.codex/config.toml`:

```toml
[mcp_servers.ultradim]
command = "python3.12"
args = ["/path/to/UltraDim/mcp/ultradim_mcp_server_v0_4_0.py", "--db", "/path/to/your/db"]
```

`command` tem de ser o Python em que o pacote está instalado. Depois peça, por palavras: «carrega os vetores deste ficheiro no UltraDim, torna-os pesquisáveis e mostra-me um mapa». A primeira chamada do assistente deve ser a ferramenta `whats_available`, que enumera cada ferramenta e o caminho nominal diretamente a partir do pacote. O guia completo é [`mcp/README.md`](../mcp/README.md) (em inglês).

## O que pode fazer com ele

**Pesquisar em dados ultralargos e confiar nas respostas.** O UltraDim trata os seus dados à sua largura nativa — impressões digitais moleculares, cestos de compras, genómica em codificação one-hot, embeddings de texto — sem hashing de características nem truncatura da sua parte. As pontuações que recebe são cossenos verdadeiros contra os seus vetores originais, e o índice mede a pedido a sua própria abrangência de candidatos contra as respostas exaustivas exatas, de modo que cada corpus vem com um certificado de qualidade e não com uma esperança.

**Construir mapas 2-D vivos de dados com 30 M de dimensões.** Os mapas UMAP são calculados de forma nativa no servidor, pelo que a construção de mapas funciona a larguras em que as ferramentas habituais nem sequer conseguem carregar os dados. Os mapas são objetos vivos: os novos pontos são colocados sobre um mapa existente em milissegundos, os lotes pequenos incorporam-se a aproximadamente 1,5 % do custo de uma reconstrução, e o histórico de versões do mapa serve ainda como detetor de deriva para o seu fluxo de dados.

<p align="center">
  <img src="../figures/umap_chembl_30m.png" width="410" alt="UMAP de 50 000 moléculas do ChEMBL a 30 M de dimensões, abrangência do grafo 0,9996">
  <img src="../figures/umap_mnist_70k.png" width="410" alt="UMAP dos 70 000 dígitos do MNIST">
</p>
<p align="center"><i>Esquerda: 50 000 moléculas do ChEMBL cartografadas a 30 000 000 de dimensões brutas; o grafo de vizinhança sob o mapa mediu uma abrangência de 0,9996 contra o oráculo exato. Direita: o mapa de controlo MNIST 70K, saído da mesma cadeia de processamento.</i></p>

<p align="center">
  <img src="../figures/forex_umap_2007_2026.gif" width="560" alt="O mercado cambial como mapa vivo, de 2007 a 2026, um ponto por dia de negociação">
</p>
<p align="center"><i>Trinta anos do mercado cambial num único mapa. Cada ponto é um dia de negociação, descrito pelos retornos padronizados de 1 992 pares cambiais nesse dia, e os dias que se moveram de forma semelhante ficam juntos. O mapa foi ajustado sobre os primeiros 3 000 dias e cada dia posterior foi nele colocado à medida que chegava, todas as sessões de janeiro de 1996 a abril de 2026, coloridas por ano. O que o mapa mostra é que a dinâmica do mercado muda de ano para ano, e muitas vezes de forma drástica. Uma estratégia de negociação construída sobre os dias de um ano tem pouco alcance para além dele antes de perder valor. Os primeiros dez anos construíram o mapa de base, pelo que a animação mostra de 2007 a 2026; a <a href="../figures/forex_market_full_1996_2026.mp4">série completa desde 1996</a> é um vídeo de oito minutos. Aprenda a fazer um destes diagramas a partir do nosso exemplo, <a href="../docs/examples/04_living_map_animation.py">docs/examples/04_living_map_animation.py</a>.</i></p>

**Agrupar e pontuar a qualquer largura.** O k-means esférico e o agrupamento hierárquico executam-se residentes em GPU a dimensionalidade extrema, com pontuações de qualidade corrigidas pela dimensão que continuam comparáveis entre larguras; assim, a pergunta «este agrupamento é real?» tem uma resposta estatística a 30 M de dimensões, e não apenas a 300.

**Realizar análises que aproveitam a largura em vez de a combater.** Pontuação de novidade das chegadas sobre um mapa ajustado; fatorização que descodifica valores retidos diretamente a partir do índice; geração de dados sintéticos e aumento de classes minoritárias; analítica de coleções; exportações para as ferramentas a jusante.

<p align="center">
  <img src="../figures/stream_anomaly_map.png" width="560" alt="Mapa de anomalias em fluxo: 987 442 artigos da DBpedia ajustados, com 2 904 chegadas coloridas segundo a sua novidade">
</p>
<p align="center"><i>Deteção de novidade em fluxo, mostrada sobre um mapa vivo: 987 442 artigos da DBpedia ajustados (a cinzento) e 2 904 pontos recém-chegados, circundados e coloridos segundo a sua novidade medida; chegadas familiares a verde, anomalias a vermelho.</i></p>

<p align="center">
  <img src="../figures/stream_dichotomy.png" width="410" alt="Dicotomia da pontuação de novidade entre chegadas familiares e novas">
  <img src="../figures/chembl_support_saturation.png" width="410" alt="Saturação do suporte de características do ChEMBL à medida que o corpus cresce">
</p>
<p align="center"><i>Esquerda: a pontuação de novidade separa com nitidez as chegadas familiares das novas. Direita: analítica de corpus a 30 M de dimensões; a saturação do suporte de características à medida que o corpus do ChEMBL cresce.</i></p>

## Desempenho medido

Todos os números provêm de experiências controladas contra oráculos exaustivos exatos, num único Apple M3 Max; qualidade e latência são reportadas em conjunto.

| Corpus | Largura | Linhas | Qualidade | Latência / débito |
|---|---|---|---|---|
| Moléculas do ChEMBL (esparso) | 30 000 000 | 500 000 | recall@10 = 0,9992 | 56 ms por consulta |
| Moléculas do ChEMBL (esparso, perfil rápido) | 30 000 000 | 500 000 | recall@10 = 0,9964 | 29 ms por consulta |
| Embeddings da DBpedia (denso) | 1 536 | 1 000 000 | precisão@10 = 0,9945 | 1 339 consultas/s a 2,99 ms no p50 |
| Cestos de compras (esparso) | 100 000 | 100 000 | recall@10 = 0,9851 | p50 17,5 ms |
| Dados estruturados sintéticos (esparso) | 1 800 000 | 50 000 | recall@10 = 1,000 | p50 15,7 ms |

A largura custa pouco: levar um corpus de 1 M para 10 M de dimensões acrescenta ~0,08 GiB de memória residente, porque o armazenamento esparso cresce com os seus valores não nulos, não com a largura declarada.

## Trabalhar com grupos de investigação

O UltraDim está a ser avaliado com grupos de investigação sobre cargas de trabalho científicas reais: representações moleculares, perfis genómicos e epigenómicos, e grandes matrizes observacionais. A utilização em investigação é gratuita ao abrigo da licença não comercial; descarregue o pacote e comece. Um bom projeto tem um corpus de alta dimensionalidade, grande, esparso ou lento de analisar com as ferramentas atuais; uma representação vetorial e uma métrica defensáveis; e uma pergunta de recuperação, de coorte, de agrupamento ou de visualização.

**[Trabalhar com grupos de investigação →](../EARLY_ACCESS.md)** — ou escreva para **andrew@gamakon.ai** para obter ajuda com o seu corpus, ou sobre a utilização comercial.

## Documentos

| Documento | Conteúdo |
|---|---|
| [Apresentação do UltraDim](../docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research*: motivação, perguntas de investigação, princípios de avaliação e programa de acesso antecipado (não confidencial, junho de 2026, em inglês) |
| [Testemunhos](../TESTIMONIALS.md) | O que dizem os grupos participantes |
| [Guia do utilizador](../docs/UltraDim_User_Guide.md) | Instalação, início rápido denso, exemplo esparso de ponta a ponta, abrangência, mapas, agrupamento, lista de RPC, autoajuste (em inglês) |
| [Guia de afinação](../docs/UltraDim_Tuning_Guide.md) | O que move a abrangência, o que não move, e o que fazer quando cai abaixo da tolerância (em inglês) |
| [Substituir e eliminar linhas](../docs/SPARSE_UPSERT_SEMANTICS.md) | Identificadores de linha, facetas, novas tentativas, durabilidade (em inglês) |
| [Com e sem GPU](../docs/GPU_SETTINGS.md) | O que precisa de uma GPU, medido; as duas configurações (em inglês) |
| [Guia do servidor MCP](../mcp/README.md) | Instalação, atualização, cada ferramenta, o caminho nominal, notas de versão (em inglês) |
| [Registo de alterações](../CHANGELOG.md) | Cada versão, da 0.1 à 0.4.0 (em inglês) |

## Sobre

O UltraDim é desenvolvido e licenciado pela **Gamakon Ltd**. A utilização não comercial é gratuita ao abrigo da licença PolyForm Noncommercial 1.0.0. Existe uma versão cliente-servidor disponível a pedido, também para as organizações não comerciais que dela necessitem; podemos ajudá-lo a instalá-la e a configurá-la. Escreva para [jesung@gamakon.ai](mailto:jesung@gamakon.ai) ou para [andrew@gamakon.ai](mailto:andrew@gamakon.ai).

### Origem

*Como surgiu*

Internamente, a base de dados UltraDim utiliza uma forma inteiramente nova de índice vetorial, desenvolvida por Andrew Morgan, autor de *Mastering Spark for Data Science*. Inventou este índice para construir e pôr à prova as suas ideias para resolver o desafio ARC-AGI; esse trabalho continua em curso.

Com trinta anos de engenharia em ciência de dados, Andrew implementou-o com uma longa lista de otimizações que, juntamente com o novo índice, permitem substituir um grande cluster Spark por um portátil Mac.

Andrew recorreu à IA para ajudar, mas explica que foi extremamente frustrante. «A IA detesta inovar. Como nunca tinha visto este desenho de índice, teve continuamente dificuldade em contribuir com algo útil, e muitas vezes revertia deliberadamente o código para ideias antigas.» Um ano de frustração persistente depois, o resultado é um sistema de que estamos genuinamente orgulhosos. Esperamos que o aprecie e que o use para construir algo notável.
