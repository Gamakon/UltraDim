# UltraDim

**一个面向极高维度数据集的快速分析型向量存储。**<br>
**已在三千万维上得到验证，目标是十亿维。**

*本文档是[英文版 README](../README.md) 的简体中文译本。文中的路径和链接均指向仓库中的文件。*

*初次接触？[写给非技术读者：什么是高维稀疏数据？](zh_WHAT_IS_HIGH_DIMENSIONAL_SPARSE_DATA.md)*

UltraDim 存储、搜索、映射、分类和聚类向量，其维度远远超出传统向量数据库的限制：稠密数据可达约 256,000 维，稀疏数据可达数千万维，并已在真实化学语料上以 **30,000,000 维**的生产运行得到验证，并已演示至 1 亿维。它以 Rust 编写，通过 macOS 上的 Metal 和 Linux 上的 Vulkan 实现 GPU 加速，并由 Python 驱动。

UltraDim 以编译好的 Python wheel（预编译安装包）形式发布，支持 Apple silicon 上的 macOS、Linux x86_64 和 Linux arm64，适用于 Python 3.12。当前版本为 0.4.0，见 [Releases](../../../releases) 页面。非商业用途在 PolyForm Noncommercial License 1.0.0 下免费。商业用途需要向 Gamakon Ltd 取得许可。许可证文本见 [`LICENSE`](../LICENSE)；说明两种许可途径的声明见 [`LICENSES/LICENSE.md`](../LICENSES/LICENSE.md)。

<p align="center">
  <img src="../figures/chembl_50k_30m_bloommap.svg" width="820" alt="50,000 个 ChEMBL 分子在 30,000,000 维下聚类的 BloomMap">
</p>
<p align="center"><i>以 BloomMap 呈现的化学空间：50,000 个 ChEMBL 分子，在其原生的 30,000,000 维下进行层次聚类。</i></p>

---

## 功能特性

- **超高维数据加载** — 摄入大型稠密向量，已测试至约 256,000 维；或大型稀疏向量，已测试至 3000 万维，并已演示 1 亿维。内存与磁盘需求随非零元素数量增长，而非随原始向量的大小增长
- **精确的最近邻排序** — 两阶段搜索先找出候选点，再以真余弦计算对其进行精确排序。
- **内置的召回率与索引延迟审计函数** — 并附带一个用于扫描参数设置的自动调优函数。
- **高吞吐稠密搜索** — 在 DBpedia-1M 上每秒 1,339 次查询，p50 延迟 2.99 ms，precision@10 = 0.9945
- **原生 UMAP 映射** — 面向超高维数据集的确定性的、带缓存的、快速的 UMAP 实现；新的未见点在毫秒级内完成评分；包含增量重拟合，其代价约为重建的 1.5%；可输出二维至 256 维之间的结果，支持可视化与降维
- **带质量阈值的 k-NN 图构建** — 每张图都附带一个实测的召回率数值；对召回率低于 0.99 的图，映射会拒绝拟合
- **面向超高维数据的聚类，即使是 3000 万维** — 常驻 GPU 的快速球面 k-means 与层次聚类，可直接对极高维的原始数据进行聚类
- **流式高维异常检测** — 将新到达的数据点对照现有的高维最近邻结构进行评分，然后将其放置到一张活的 UMAP 图上，使异常和新兴群体变得可见；下方的流式图示是一段基于映射变换 RPC 的简短脚本
- **因子分解与推荐** — 直接从索引解码留出值；一种无参数的邻域方法，在公开基准上可与经过训练的基线相媲美
- **在超球面上生成合成数据** — 代码提供基于 wgpu 的 Muller-Marsaglia 均匀点生成，点位于我们的数据索引所在的超球面上。这是一种实验性方法的一部分：将真实点的少数类标签赋予其 k 个最近的合成邻点，以重新平衡数据集。
- **BloomMap 可视化** — 层次聚类的出版级海报渲染
- **数据操作** — 导出为 CSV、JSON 和一种二进制格式；集合分析；服务器内文本嵌入
- **MCP 服务器** — 使任何智能体或 AI 都能帮助您使用本系统并研究您的数据。
- **三种运行方式** — 作为 Python wheel 在您自己的进程中运行；作为 MCP 服务器供助手使用；或作为共享服务器，由多个客户端通过端口以 gRPC 访问（按需提供）。三种方式提供相同的 204 个 RPC。
- **全程可溯源** — 版本化的参数、随机种子、行计数记录和可导出的结果，使每一项分析输出都可以被检验和复现

## 获取

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install ./UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl      # numpy 随之一并安装
```

```python
import ultradim
db = ultradim.UltraDim("./db")
print(len(db.capabilities()))          # 204
db.call_json("RpcName", '{...}')       # 其中任意一个
```

数据库在您的进程内运行。无需启动服务器，也无需开放端口。存在 GPU 时会自动使用（macOS 上为 Metal，Linux 上为 Vulkan）。没有 GPU 时，UltraDim 仍可加载、索引和搜索稀疏与稠密数据，构建邻域图和密度谱系，并测量召回率。UMAP 拟合、k-means 聚类和 k-means 谱系需要 GPU，没有 GPU 时会返回错误。相关测量见 [`docs/GPU_SETTINGS.md`](../docs/GPU_SETTINGS.md)。

MCP 服务器 `mcp/ultradim_mcp_server_v0_4_0.py` 将同一个 wheel 封装为 46 个工具，使助手无需您编写 Python 即可创建集合、摄入、索引、搜索、聚类和映射。其指南见 [`mcp/README.md`](../mcp/README.md)。

另有客户端-服务器版本可供使用。一台 UltraDim 服务器在主机上运行，由多个客户端通过端口共享。客户端通过 gRPC 写入和查询。gRPC 是一种紧凑的二进制协议，因此宽向量的摄入在网络传输上很快。它与 wheel 是同一个引擎，提供相同的 204 个 RPC。请与我们联系以获取该版本。这也包括有此需要的非商业机构：我们可以帮助您安装和配置。联系方式：jesung@gamakon.ai 或 andrew@gamakon.ai。

## 通过 AI 助手运行

本仓库附带一个 MCP 服务器 `mcp/ultradim_mcp_server_v0_4_0.py`，它将数据库以 46 个工具的形式暴露给 Claude Code、Codex 或任何支持 MCP 的助手。随后助手代您操作数据库：创建集合族、摄入您的向量、构建索引、搜索、聚类和映射，并将结果读给您。您描述研究任务；它负责发起调用。

安装 wheel，克隆本仓库，并在克隆目录中打开一个助手会话。对于 Claude Code，仓库根目录下的 `.mcp.json` 会注册该服务器；对于 Codex，请在 `~/.codex/config.toml` 中添加：

```toml
[mcp_servers.ultradim]
command = "python3.12"
args = ["/path/to/UltraDim/mcp/ultradim_mcp_server_v0_4_0.py", "--db", "/path/to/your/db"]
```

`command` 必须是安装了该 wheel 的 Python。然后用自然语言提出请求："把这个文件里的向量加载到 UltraDim，让它们可以被搜索，并给我看一张图。"助手的第一次调用应当是 `whats_available` 工具，它会直接从 wheel 实时列出每一个工具和标准流程。完整指南见 [`mcp/README.md`](../mcp/README.md)（英文）。

## 它能做什么

**搜索超宽数据，并信任其结果。** UltraDim 以数据的原生维度处理您的数据——分子指纹、零售购物篮、one-hot 编码的基因组数据、文本嵌入——您无需做特征哈希或截断。您收到的分数是针对原始向量计算的真余弦值，且索引可按需将自身的候选召回率与精确暴力搜索的答案进行对照测量，因此每个语料库都附带一份质量证书，而不是一份期望。

**为 3000 万维数据构建活的二维地图。** UMAP 图在服务器上原生计算，因此地图构建可用于长度极大的大向量——在这样的长度下，其他工具连加载数据都很困难。地图是活的对象：新点在毫秒级内放置到现有地图上，小批量数据以约为重建 1.5% 的代价并入，而地图的版本历史同时可作为您数据流的漂移检测器。

<p align="center">
  <img src="../figures/umap_chembl_30m.png" width="410" alt="50,000 个 ChEMBL 分子在 3000 万维下的 UMAP，图召回率 0.9996">
  <img src="../figures/umap_mnist_70k.png" width="410" alt="MNIST 70,000 个手写数字的 UMAP">
</p>
<p align="center"><i>左：50,000 个 ChEMBL 分子在 30,000,000 个原始维度下的映射——地图之下的邻域图对照精确判定基准测得召回率 0.9996。右：由同一流水线生成的 MNIST 70K 校验图。</i></p>

<p align="center">
  <img src="../figures/forex_umap_2007_2026.gif" width="560" alt="作为活地图的外汇市场，2007 年至 2026 年，每个交易日一个点">
</p>
<p align="center"><i>三十年外汇市场，尽在一张地图。每个点是一个交易日，由当日 1,992 个货币对的标准化收益率描述，走势相近的日子彼此靠近。地图在最初 3,000 天上拟合，此后每一天在到达时被置入其中，涵盖从 1996 年 1 月到 2026 年 4 月的每一个交易日，按年份着色。地图显示，市场的动态逐年变化，且常常剧烈。基于某一年的交易日构建的交易策略，在该年之外适用范围有限，很快便失去价值。最初十年构建了基础地图，因此动画展示的是 2007 年至 2026 年；<a href="../figures/forex_market_full_1996_2026.mp4">自 1996 年起的完整序列</a>是一段八分钟的视频。如何自行绘制此类图表，请参照我们的示例 <a href="../examples/04_living_map_animation.py">examples/04_living_map_animation.py</a>。</i></p>

**对任意长度的向量进行聚类并评分。** 球面 k-means 和层次聚类在极高维度下常驻 GPU 运行，并附带经维度校正、可跨维度比较的质量分数——因此"这个聚类是真实的吗？"这一问题在 3000 万维下有统计学上的答案，而不仅限于 300 维。

在已拟合的地图上对新到达数据进行新颖性评分；直接从索引解码留出值的因子分解；合成数据生成与少数类增强；集合分析；面向下游工具的导出。

<p align="center">
  <img src="../figures/stream_anomaly_map.png" width="560" alt="流式异常地图：987,442 篇已拟合的 DBpedia 文章，以及 2,904 个按新颖性着色的新到达点">
</p>
<p align="center"><i>在活地图上展示的流式新颖性检测：987,442 篇已拟合的 DBpedia 文章（灰色）与 2,904 个新到达的点，后者以圆环标出并按实测新颖性着色——熟悉的到达点为绿色，异常点为红色。</i></p>

<p align="center">
  <img src="../figures/stream_dichotomy.png" width="410" alt="熟悉到达点与新到达点之间的新颖性分数二分">
  <img src="../figures/chembl_support_saturation.png" width="410" alt="ChEMBL 特征支持度随语料库增长的饱和情况">
</p>
<p align="center"><i>左：新颖性分数清晰地将熟悉的到达点与新到达点区分开来。右：3000 万维下的语料库分析——随着 ChEMBL 语料库增长，特征支持度趋于饱和。</i></p>

## 实测性能

所有数字均来自对照精确暴力搜索判定基准的受控实验运行，在单台 Apple M3 Max 上完成，质量与延迟一并报告。

| 语料库 | 维度 | 行数 | 质量 | 延迟 / 吞吐量 |
|---|---|---|---|---|
| ChEMBL 分子（稀疏） | 30,000,000 | 500,000 | recall@10 = 0.9992 | 每次查询 56 ms |
| ChEMBL 分子（稀疏，快速配置） | 30,000,000 | 500,000 | recall@10 = 0.9964 | 每次查询 29 ms |
| DBpedia 嵌入（稠密） | 1,536 | 1,000,000 | precision@10 = 0.9945 | 每秒 1,339 次查询，p50 2.99 ms |
| 零售购物篮（稀疏） | 100,000 | 100,000 | recall@10 = 0.9851 | p50 17.5 ms |
| 合成结构化数据（稀疏） | 1,800,000 | 50,000 | recall@10 = 1.000 | p50 15.7 ms |

凭借我们先进的工程技术，在高维度下工作是高效的。将一个语料库从 100 万维扩展到 1000 万维仅增加约 0.08 GiB 常驻内存，因为稀疏存储随非零元素数量增长，而非随声明的维度增长。

## 与研究团队合作

UltraDim 被研究团队用于真实的科学工作负载——分子表示、基因组与表观基因组谱、以及大型观测矩阵。研究用途在非商业许可下免费；下载 wheel 即可开始。一个好的项目应具备：一个高维、大规模、稀疏或用现有工具分析缓慢的语料库；一种站得住脚的向量表示和度量；以及一个检索、队列、聚类或可视化方面的问题。

**[与研究团队合作 →](../RESEARCH_GROUPS.md)** — 或写信至 **andrew@gamakon.ai**，就您的语料库寻求帮助，或咨询商业用途。

## 文档

| 文档 | 内容 |
|---|---|
| [UltraDim 概览](../docs/UltraDim_Overview.pdf) | *Analytical Vector Stores for Scientific Research*——动机、研究问题、评估原则（非保密，2026 年 6 月，英文） |
| [用户评价](../TESTIMONIALS.md) | 参与团队的评价 |
| [用户指南](../docs/UltraDim_User_Guide.md) | 安装、稠密数据快速入门、稀疏数据完整示例、召回率、地图、聚类、RPC 列表、自动调优器（英文） |
| [调优指南](../docs/UltraDim_Tuning_Guide.md) | 什么会影响召回率，什么不会，以及召回率低于容差时该怎么做（英文） |
| [替换与删除行](../docs/SPARSE_UPSERT_SEMANTICS.md) | 行 id、分面、重试、持久性（英文） |
| [有无 GPU 的运行](../docs/GPU_SETTINGS.md) | 哪些功能需要 GPU，附实测；两种设置（英文） |
| [MCP 服务器指南](../mcp/README.md) | 安装、升级、每个工具、标准流程、发行说明（英文） |
| [变更日志](../CHANGELOG.md) | 每个版本，从 0.1 到 0.4.0（英文） |

## 关于

UltraDim 由 **Gamakon Ltd** 开发并授权。非商业用途在 PolyForm Noncommercial License 1.0.0 下免费。客户端-服务器版本可按需提供，包括提供给有此需要的非商业机构；我们可以帮助您安装和配置。请写信至 [jesung@gamakon.ai](mailto:jesung@gamakon.ai) 或 [andrew@gamakon.ai](mailto:andrew@gamakon.ai)。

### 缘起

*它是如何诞生的*

在内部，UltraDim 数据库使用一种全新形式的向量索引，由 Andrew Morgan 开发——他是 *Mastering Spark for Data Science* 一书的作者。他发明这种索引是为了构建并检验他解决 ARC-AGI 挑战的想法；这项工作仍在进行中。

凭借三十年的数据科学工程经验，Andrew 在实现中采用了一长串优化措施，这些优化与新索引一起，使您能够用一台 Mac 笔记本电脑取代一个大型 Spark 集群。

Andrew 借助了 AI，但他表示这一过程令人极为沮丧。"AI 讨厌创新。由于它从未见过这种索引设计，它始终难以做出任何有用的贡献，还常常固执地把代码改回旧的思路。"经过一年持续的挫折之后，最终的成果是一个我们真正引以为豪的系统。希望您喜欢它，并用它构建出非凡的东西。
