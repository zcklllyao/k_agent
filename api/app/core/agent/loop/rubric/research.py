"""研究报告 Rubric:6 维加权,直接对齐 V0.0.5 ① 离线评测的指标定义。

| 维度        | 权重 | 对应 ① 离线指标         | 单维硬门槛(0~5) |
|-----------|----|------------------|------------|
| 覆盖度       | 0.20 | Recall@k           | < 3       |
| 引用对齐      | 0.25 | RAGAS faithfulness | < 3       |
| 论证深度(新增)  | 0.15 | —                  | < 2       |
| 时效性       | 0.15 | —(深度研究 v2 新增)     | < 3       |
| 相关性       | 0.15 | RAGAS answer relevancy | < 3   |
| 结构与可读     | 0.10 | 启发式               | < 2       |

通过判定:加权总分 ≥ 0.7 且 所有单维 ≥ 硬门槛。
"""
from app.core.agent.loop.models import RubricDef, RubricDim

# 单维原始分量纲:0~5(verifier prompt 也按这个量纲打分)
_RAW_MAX = 5.0

RESEARCH_RUBRIC = RubricDef(
    name="research",
    raw_max=_RAW_MAX,
    # 研究审核用于交付前质检，不是学术论文答辩；允许可用报告带着改进项交付。
    pass_threshold=0.55,
    dims=[
        RubricDim(
            key="coverage",
            label="覆盖度",
            weight=0.20,
            threshold=1.5,
            desc=(
                "0~5,大纲所有子问题/章节是否被实质回答。"
                "5=全部覆盖且深入;3=主体覆盖但有小遗漏;1=只回答了部分子问题。"
            ),
        ),
        RubricDim(
            key="faithfulness",
            label="引用对齐",
            weight=0.25,
            threshold=1.5,
            desc=(
                "0~5,正文 [来源 N] 角标是否真出自该源,关键论点是否有引用支撑。"
                "5=每个论点都有源;3=多数有源但偶有漏引;1=明显与引用不符或缺引。"
            ),
        ),
        RubricDim(
            key="depth",
            label="论证深度",
            weight=0.15,
            threshold=1.5,
            desc=(
                "0~5,是否仅罗列事实,有无对比/取舍/因果分析。"
                "5=多层论证 + 真知灼见;3=有分析但偏浅;1=纯罗列、无分析。"
            ),
        ),
        RubricDim(
            key="timeliness",
            label="时效性",
            weight=0.15,
            threshold=1.5,
            desc=(
                "0~5,涉及时效话题时是否使用了当年/当月信息。"
                "如果主题不带时效性,本维默认满分(由 verifier 判断)。"
                "5=全部使用最新数据;3=部分新但有旧引用;1=明显用过期数据。"
            ),
        ),
        RubricDim(
            key="relevance",
            label="相关性",
            weight=0.15,
            threshold=1.5,
            desc=(
                "0~5,各章节是否紧扣主题、不离题、不堆砌无关内容。"
                "5=每段都紧扣;3=主体紧扣但个别章节散开;1=离题严重。"
            ),
        ),
        RubricDim(
            key="readability",
            label="结构与可读",
            weight=0.10,
            threshold=1.5,
            desc=(
                "0~5,有无 TL;DR、章节互斥、表格/列表运用恰当、行文流畅。"
                "5=清晰友好;3=可读但有冗余;1=结构混乱难读。"
            ),
        ),
    ],
)
