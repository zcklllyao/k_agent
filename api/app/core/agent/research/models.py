"""深度研究的中间数据模型（阶段间用明确结构传递，不靠隐式约定）。"""
from dataclasses import dataclass, field

# 来源类型
SOURCE_WEB = "web"  # 联网搜索 + 抓正文
SOURCE_KB = "kb"  # 用户知识库
SOURCE_MCP = "mcp"  # MCP 工具产出


@dataclass
class PlanSection:
    """报告提纲中的一个章节。"""

    heading: str  # 章节标题
    points: str = ""  # 该章节要写的要点/角度（指导写作，不直接展示）
    sub_questions: list[str] = field(default_factory=list)  # 多视角子问题（v2）


@dataclass
class ResearchPlan:
    """规划阶段产出：报告标题 + 章节提纲 + 多角度子查询。"""

    title: str
    sections: list[PlanSection] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)  # 扁平化的检索子查询（供检索复用）


@dataclass
class Learning:
    """逐源提炼出的一条「要点」（v2 核心）：干净事实 + 绑定来源号。

    引用对齐提前到提炼阶段——写作时直接用带号要点，[来源N] 天然正确。
    """

    text: str  # 提炼后的干净要点（事实/数据/观点）
    source_index: int  # 绑定的来源号（对应 Source.index）
    date_hint: str = ""  # 提炼时识别到的时效（如 "2026-03"），无则空
    relevance: float = 0.5  # 与研究主题相关度 0~1，低于阈值丢弃


@dataclass
class CuratedSection:
    """大纲整理阶段产出：一个章节 + 核心论点 + 分配给它的要点编号。"""

    heading: str
    thesis: str = ""  # 本节核心论点（一句话，指导写作）
    learning_ids: list[int] = field(default_factory=list)  # 分配的 Learning 全局编号（1 起）


@dataclass
class Source:
    """一条带引用号的资料来源。"""

    index: int  # 引用号（从 1 起，全文统一）
    type: str  # SOURCE_WEB / SOURCE_KB / SOURCE_MCP
    title: str
    content: str  # 抓到的正文/检索片段/工具结果（已截断）
    url: str | None = None  # web 源有 url；kb/mcp 可空

    def cite_label(self) -> str:
        """参考来源区的一行展示文本。"""
        if self.url:
            return f"[{self.title or self.url}]({self.url})"
        prefix = {SOURCE_KB: "知识库", SOURCE_MCP: "工具"}.get(self.type, "")
        name = self.title or "未命名来源"
        return f"{name}（{prefix}）" if prefix else name


@dataclass
class WrittenSection:
    """写作阶段产出：一个已写好的章节。"""

    heading: str
    content: str


@dataclass
class ResearchResult:
    """整篇研究最终产物（落库用）。"""

    title: str
    markdown: str
    sources: list[dict]  # 序列化后的来源列表
