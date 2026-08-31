from app.core.agent.query_routing import requests_knowledge_search


def test_general_questions_do_not_mount_knowledge_tool() -> None:
    assert not requests_knowledge_search("什么是机器学习？")
    assert not requests_knowledge_search("请解释一下全球经济为什么会波动")
    assert not requests_knowledge_search("如何提高英语口语？")


def test_explicit_document_questions_mount_knowledge_tool() -> None:
    assert requests_knowledge_search("总结我上传的论文")
    assert requests_knowledge_search("根据这篇文章提炼三个结论")
    assert requests_knowledge_search("知识库里有多少篇文章？")
    assert requests_knowledge_search("search my documents for the deployment steps")
