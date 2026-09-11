# k-agent — 个人 AI 知识库与记忆助手

> Personal AI Knowledge & Memory Assistant

k-agent 是一个多用户的个人 AI 知识库 + 记忆助手：把你的文档、图片、网页沉淀成可语义检索的知识库，从对话中自动萃取「记忆」构建你的专属知识图谱，并用 LLM Agent 自主编排「知识库 / 记忆 / 联网」三类工具来回答问题。

---

## 目录

- [核心功能](#核心功能)
- [技术栈](#技术栈)
- [系统架构](#系统架构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
  - [第 1 步：克隆代码](#第-1-步克隆代码)
  - [第 2 步：启动四个存储（Docker）](#第-2-步启动四个存储docker)
  - [第 3 步：配置并启动后端](#第-3-步配置并启动后端)
  - [第 4 步：启动 Celery worker / beat](#第-4-步启动-celery-worker--beat)
  - [第 5 步：启动前端](#第-5-步启动前端)
  - [第 6 步：注册账号并配置模型](#第-6-步注册账号并配置模型)
- [首次使用流程](#首次使用流程)
- [常见问题](#常见问题)
- [目录结构](#目录结构)
- [开发约定](#开发约定)

---

## 核心功能

- **知识库 RAG**：文档（PDF/Word/Markdown/TXT/HTML）、网页、图片入库；父子分块 + IK 中文分词；ES 向量 + BM25 混合检索（可选 Rerank）；带引用溯源。
- **图片多模态**：图片自动生成描述 / OCR / 物体 / 场景，并可语义检索。
- **AI 自动打标签**：入库内容自动分类，复用已有标签防膨胀。
- **记忆系统**：从「主动记住」或对话中异步萃取三元组，写入 Neo4j 四层溯源图谱（来源→片段→陈述→实体）；区分画像类实体与事件类（带时间，进时间线）；两层去重；社区聚类。
- **智能问答**：知识库 / 记忆 / 联网三个工具做成 LangChain Agent，LLM 自主编排（强模型走原生 function calling，弱模型走 ReAct 降级）；SSE 流式输出；带引用与工具调用标记；支持多模态看图问答。
- **搜索与导航**：全局搜索（文档 + 图片 + 记忆三排并列，语义相关度门控）、收藏夹、标签管理、每日回顾。
- **可视化**：知识图谱（AntV X6）、事件时间线、统计仪表盘（ECharts）。
- **情绪分析**：对话情绪分析（valence-arousal）、记忆深化分层与定时巩固。
- **角色与技能**：对话人格（角色卡，多组人设一键切换）、Skills 技能（提示词 + 工具白名单 + 绑库 + few-shot 打包，对话内即时挂载）。
- **多知识库**：分库管理 + 按库检索开关，ES kb_id 多库过滤。
- **记忆智能化**：反思引擎归纳「AI 眼中的你」洞察、对话每轮主动召回记忆、跨会话上下文、今日回顾的 AI 主动关心。
- **交互增强**：划词追问、快照式对话分享（无登录公开页）、语音输入（浏览器 + 云端 ASR 双路）。
- **深度研究与定时任务**：把「研究一个主题」拆成规划→多源检索→逐源提炼→反思补搜→大纲→分节写作的多阶段流水线,自动产出结构化带引用的报告;定时任务可自动运行并推送到已启用渠道（含飞书）,手动研究由用户决定是否推送;报告可自动归档到 GitCode。
- **真人对话模式**：全局开关,让对话切到真人微信聊天风格(口语 / 多气泡逐条连发 / 不甩 markdown 报告腔)。
- **Verifier Loop · Agent 自闭环质量保障**:每份研究报告 / 定时任务产出走独立 LLM-as-judge 按 6 维 Rubric 评分(覆盖度 / 引用对齐 / 论证深度 / 时效 / 相关性 / 可读),不合格自动选 Patch 或章节重写回炉,状态外置 DB 可中断恢复;深度研究和定时任务共用同一抽象框架。
- **全链路可观测 + 成本核算**:基于 OpenTelemetry GenAI 规范的 trace / span 模型覆盖 Agent 全部执行链路(工具调用 / LLM / 检索 / 写作 / 审稿);每次 LLM 调用按 model 单价精确核算 CNY 成本;前端 Gantt 时间线可下钻每一步的 prompt / 回复预览、tokens / cost、错误归因。
- **记忆审查与人类反馈闭环**:全景看 AI 关于你记住了什么(类型饼 / 置信度直方 / 30 天趋势)+ 审查低置信度实体(确认 / 修正 / 删除三按钮);用户操作沉淀到 `memory_corrections` 数据池,`human_verified` 状态回写图谱后直接提升主动召回权重。
- **离线评测体系**:自建中文 gold 集 + C-MTEB T2Retrieval 中文检索基线 + HotpotQA distractor 多跳问答基线;C-MTEB 混合检索 **nDCG@10 = 0.98** / MRR@10 = 1.0;HotpotQA 200 题 **EM = 62% / F1 = 74.49% / Recall@4 = 95.75%**;Verifier A/B 实验证明**跨家族审稿通过率 95% 显著高于同模型自评 0%**。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 + TypeScript + Ant Design 5 + Vite；状态 Zustand；图 AntV X6 + ECharts |
| 后端 | FastAPI（分层：controller → service → repository → model/db）；依赖用 **uv** 管理 |
| 业务库 | PostgreSQL 16 + SQLAlchemy 2.0（async）+ Alembic 迁移 |
| 向量/全文 | Elasticsearch 8.17（向量 + BM25 + IK 中文分词） |
| 记忆图谱 | Neo4j 5.26（实体-关系-事件三元组） |
| 异步/缓存 | Celery + Redis（多队列：parse / memory / beat / research） |
| LLM 编排 | LangChain（Agent 工具循环，方案B） |

---

## 系统架构

```
                         ┌─────────────┐
        浏览器  ───────▶ │  web (Vite) │  http://localhost:5173
                         └──────┬──────┘
                                │  /api 代理
                         ┌──────▼──────┐
                         │  api (FastAPI)  http://localhost:8000
                         └──┬───┬───┬───┬──┘
        ┌───────────────────┘   │   │   └────────────────────┐
        ▼                       ▼   ▼                        ▼
 ┌────────────┐        ┌──────────────┐  ┌──────────┐  ┌──────────┐
 │ PostgreSQL │        │Elasticsearch │  │  Neo4j   │  │  Redis   │
 │ 业务数据   │        │ 向量+全文检索│  │ 记忆图谱 │  │ 缓存+队列│
 └────────────┘        └──────────────┘  └──────────┘  └────┬─────┘
                                                            │ broker
                                       ┌────────────────────┴────────┐
                                       ▼                             ▼
                              ┌─────────────────┐         ┌─────────────────┐
                              │ celery worker   │         │ celery beat     │
                              │ 解析/萃取/聚类   │         │ 定时回顾/聚类    │
                              └─────────────────┘         └─────────────────┘
```

开发期：四个存储用 Docker 跑，应用（api / worker / beat / web）在本机手动起，方便热重载和调试。

---

## 环境要求

| 软件 | 版本 | 说明 |
|------|------|------|
| Docker Desktop | 最新 | 跑四个存储 |
| Python | 3.12+ | 后端 |
| uv | 0.5+ | Python 依赖管理（替代 pip）。安装见 https://docs.astral.sh/uv/ |
| Node.js | 18+ | 前端 |
| 一个 LLM API Key | — | 至少需要一个 **对话模型** + 一个 **Embedding 模型**。支持 OpenAI 兼容的 provider：OpenAI / 通义千问 / 豆包 / DeepSeek / 智谱。推荐：对话用 DeepSeek，Embedding 用智谱 `embedding-3` |

> 存储默认占用端口：PostgreSQL `5432`、Elasticsearch `9200`、Neo4j `7474/7687`、Redis `6379`。确保这些端口未被占用。

---

## 快速开始

下面以「存储用 Docker + 应用本地起」的开发模式为例，按顺序执行即可跑起来。命令在 Windows 下用 PowerShell / bash 均可，命令分隔符用 `;`。

### 第 1 步：克隆代码

```bash
git clone <你的仓库地址> k-agent
cd k-agent
```

### 第 2 步：启动四个存储（Docker）

根目录复制环境变量模板（用于 docker-compose 里的存储密码等）：

```bash
cp .env.example .env    # Windows: copy .env.example .env
```

只起四个存储容器（不起应用容器，应用本地跑）：

```bash
# docker-compose.yml 使用 external 数据卷；新电脑首次运行需先创建
docker volume create comet_pg_data
docker volume create comet_es_data
docker volume create comet_neo4j_data
docker volume create comet_redis_data

docker compose up -d postgres elasticsearch neo4j redis
```

> Elasticsearch 镜像是自定义构建的（内置 IK 中文分词插件，见 `docker/es/Dockerfile`），首次会自动 build，需要几分钟。
> 等容器健康后再继续。可用 `docker compose ps` 查看状态，ES 启动较慢（约 30~60 秒）。
> Git 仓库只保存代码，不包含 PostgreSQL/ES/Neo4j/Redis 数据卷和 `api/storage` 中的本地上传文件；换电脑后默认是全新实例。如需保留账号、模型配置、任务和知识库，请另行迁移数据卷/备份。

### 第 3 步：配置并启动后端

```bash
cd api
uv sync                       # 安装依赖（自动建 .venv）
cp .env.example .env          # Windows: copy .env.example .env
```

编辑 `api/.env`，**必须修改的两项密钥**：

```dotenv
# JWT 签名密钥，随便一段长随机字符串
JWT_SECRET=请改成一段随机长字符串

# API Key 加密密钥（Fernet），用下面命令生成一串填进来
FERNET_KEY=请填生成的-Fernet-Key
```

生成 `FERNET_KEY`：

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

其余存储地址默认指向 `localhost`，与第 2 步的容器端口一致，无需改动。

执行数据库迁移（建表）：

```bash
uv run alembic upgrade head
```

启动后端：

```bash
uv run python run.py
```

验证：浏览器或 curl 访问

- `http://localhost:8000/api/health` → 四个存储应全部 `ok`

> 后端启动时会自动初始化 ES 索引和 Neo4j 图谱约束/索引，无需手动操作。

### 第 4 步：启动 Celery worker / beat

文档解析、记忆萃取、社区聚类等耗时任务走异步队列，需要单独的进程。**新开一个终端**，在 `api` 目录下：

```bash
# Windows 必须用 --pool=solo（prefork 在 Windows 有权限问题）
# 主 worker：轻量任务与调度心跳
.\.venv\Scripts\python.exe -m celery -A app.celery_app.celery_app worker --loglevel=INFO -Q default,parse,memory,beat --pool=solo --hostname=core-worker@%h

# 研究 worker：单独承载深度研究，避免长任务堵住心跳
.\.venv\Scripts\python.exe -m celery -A app.celery_app.celery_app worker --loglevel=INFO -Q research --pool=solo --hostname=research-worker@%h
```

> Linux / macOS 可去掉 `--pool=solo`，并用 `--concurrency=N` 提高并发。
> 说明：Windows `--pool=solo` 是单进程串行，因此研究队列必须使用独立 worker；两个 worker 使用不同 hostname，便于监控和排障。

定时任务（每日回顾、定时全量聚类）需要 beat，**再开一个终端**（可选，不影响主流程）：

```bash
.\.venv\Scripts\python.exe -m celery -A app.celery_app.celery_app beat --loglevel=INFO
```

### 第 5 步：启动前端

**新开一个终端**：

```bash
cd web
npm install
npm run dev
```

打开 `http://localhost:5173`（开发环境 `/api` 默认代理到 8000；如果本地 API 使用其他端口，可通过 `VITE_API_PROXY_TARGET` 覆盖，无需额外配置跨域）。

### 第 6 步：注册账号并配置模型

1. 打开前端，点「注册」创建账号，登录。
2. 进入 **设置 → 模型配置**，至少添加两个模型：
   - **对话模型**（type=chat）：如 DeepSeek `deepseek-chat`，填 base_url、API Key。强模型建议勾上 `function_call` 能力，问答时走原生工具调用。
   - **Embedding 模型**（type=embedding）：如 智谱 `embedding-3`（维度固定 1024，与 `EMBEDDING_DIMS` 一致）。
   - 可选：多模态模型（看图问答）、Rerank 模型、联网搜索（type=websearch，provider 选千帆/tavily）。
3. 每个模型添加后点「测试连接」，通过后「设为默认」。

到这里就可以开始用了。

---

## 首次使用流程

1. **知识库**：上传一个 PDF 或导入一个网页 → 等状态变「完成」（解析+分块+向量化是异步的）→ 用语义检索能搜到内容。
2. **记忆**：进「记忆 → 我的画像」，在输入框写一段关于你自己的话（如「我在腾讯做后端，养了只叫多多的小狗，去年6月去上海看了周杰伦演唱会」）点「记住」→ worker 萃取后，画像出现实体、时间线出现事件、知识图谱出现节点。
3. **对话**：进「对话」，问知识库相关问题 / 记忆相关问题 / 开联网开关问实时信息，观察 AI 自动调用对应工具并给出带引用的流式回答。
4. **其它**：全局搜索（顶栏）、收藏夹、知识图谱、统计仪表盘、每日回顾。

---

## 常见问题

**Q：`/api/health` 某个存储显示连接失败？**
确认对应容器已起且健康（`docker compose ps`）。ES 启动慢，多等一会儿；端口被占用会连不上。

**Q：上传文档后一直「处理中」/ 记忆一直「萃取中」？**
说明 Celery worker 没起或队列不对。确认第 4 步的 worker 在跑，队列包含 `parse,memory`；Windows 必须加 `--pool=solo`。看 worker 终端日志排错。

**Q：对话报「未配置对话模型」/ 检索没结果？**
去模型配置确认已添加并「设为默认」对应类型的模型；Embedding 模型必须配置，否则无法向量化与检索。

**Q：中文检索效果差？**
确认用的是自定义构建的 ES 镜像（含 IK 分词）。如果误用了官方镜像，删掉 ES 容器和卷重新 `docker compose up -d --build elasticsearch`。

**Q：知识图谱 / 时间线是空的？**
图谱和事件来自记忆萃取。先用「主动记住」录入带信息（尤其带时间的经历）的文本并等萃取完成。事件萃取需要文本里有「一次性发生 + 有明确时间」的经历才会生成事件节点。

**Q：改了数据库模型怎么办？**
`uv run alembic revision --autogenerate -m "说明"` 生成迁移，检查脚本后 `uv run alembic upgrade head`。

---

## 目录结构

```
k-agent/
├── api/                      # 后端 FastAPI
│   ├── app/
│   │   ├── controllers/      # 路由层
│   │   ├── services/         # 业务逻辑
│   │   ├── repositories/     # 数据访问（含 neo4j/ 子目录）
│   │   ├── models/           # SQLAlchemy ORM 模型
│   │   ├── schemas/          # Pydantic 请求/响应
│   │   ├── core/             # 横切基础设施
│   │   │   ├── rag/          #   知识库检索（分块/解析/索引/混合检索）
│   │   │   ├── memory/       #   记忆（预处理/萃取/检索/聚类 + prompts）
│   │   │   ├── agent/        #   Agent 工具编排（方案B）
│   │   │   ├── llm/          #   LLM 客户端与工厂
│   │   │   └── storage/      #   文件存储（本地/OSS）
│   │   ├── tasks/            # Celery 异步任务
│   │   ├── db/               # 四存储连接（postgres/elastic/neo4j/redis）
│   │   ├── config.py         # 配置（pydantic-settings，读 .env）
│   │   ├── main.py           # FastAPI 入口
│   │   └── celery_app.py     # Celery 多队列配置
│   ├── migrations/           # Alembic 迁移
│   ├── run.py                # 本地启动入口
│   └── pyproject.toml        # 依赖（uv 管理）
├── web/                      # 前端 React + TS + AntD
│   └── src/
│       ├── api/              # 请求封装（client + 各模块）
│       ├── pages/            # 页面
│       ├── components/       # 通用组件
│       ├── layouts/          # 布局
│       └── stores/           # Zustand 状态
├── docker/es/                # 内置 IK 分词的 ES 镜像
├── docker-compose.yml        # 存储 + 应用容器编排
├── .env.example              # 根环境变量模板（docker-compose 用）
└── api/.env.example          # 后端环境变量模板（本地裸跑用）
```

---

## 开发约定

- 后端依赖用 **uv**（`uv add xxx` / `uv run xxx`），不要直接用 pip。
- 分层严格单向：controller → service → repository → model/db。
- 文件命名全称后缀：`xxx_model.py` / `xxx_repository.py` / `xxx_service.py` / `xxx_controller.py` / `xxx_schema.py`。
- 统一响应 `{ code, message, data }`；失败用中文提示。
- 改完代码自检：后端 `uv run ruff check .`，前端 `npx tsc --noEmit`。
- 业务表都带 `user_id` 做多租户隔离；API Key 等敏感信息用 Fernet 加密存储。
