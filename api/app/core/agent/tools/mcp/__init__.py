"""MCP 工具接入：把外部 MCP server 的工具转成 LangChain 工具。

基于官方 langchain-mcp-adapters：
- connection：MCPServer 行 → 官方 connection dict（含解密认证、SSRF 校验）
- loader：build_mcp_tools（问答用）+ fetch_tools_meta（test/sync 用）
"""
