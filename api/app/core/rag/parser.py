"""文档解析：把各类文件的二进制内容提取为纯文本。

支持 PDF / Word(docx) / Markdown / 纯文本 / HTML。
"""
import io

import chardet

from app.core.exceptions import BizError

SUPPORTED_EXTS = {".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm"}


def _decode_text(content: bytes) -> str:
    detected = chardet.detect(content)
    encoding = detected.get("encoding") or "utf-8"
    try:
        return content.decode(encoding, errors="ignore")
    except (LookupError, UnicodeDecodeError):
        return content.decode("utf-8", errors="ignore")


def decode_text(content: bytes) -> str:
    """对外暴露的文本解码：保留原始文本内容（不做 markdown→纯文本转换），用于预览。"""
    return _decode_text(content)


def _parse_pdf(content: bytes) -> str:
    import fitz  # pymupdf

    text_parts: list[str] = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts)


def _parse_docx(content: bytes) -> str:
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _parse_markdown(content: bytes) -> str:
    import markdown
    from bs4 import BeautifulSoup

    raw = _decode_text(content)
    html = markdown.markdown(raw)
    return BeautifulSoup(html, "html.parser").get_text("\n")


def _parse_html(content: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_decode_text(content), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n")


def parse_document(file_ext: str, content: bytes) -> str:
    """按扩展名解析文件二进制，返回纯文本。"""
    ext = file_ext.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    if ext == ".pdf":
        return _parse_pdf(content)
    if ext == ".docx":
        return _parse_docx(content)
    if ext in (".md", ".markdown"):
        return _parse_markdown(content)
    if ext in (".html", ".htm"):
        return _parse_html(content)
    if ext == ".txt":
        return _decode_text(content)
    raise BizError(f"不支持的文件类型: {ext}", code=3001)
