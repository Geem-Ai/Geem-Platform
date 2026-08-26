"""Remote MCP tool-source domain (Phase 13B-13C).

This package owns tenant MCP server inventory and explicit Expert grants.  It
does not own the egress implementation or the tool-execution loop; those are
separate security and runtime boundaries.
"""

from app.mcp.models import McpServerTool, McpToolGrant

__all__ = ["McpServerTool", "McpToolGrant"]
