"""Discover real tool schemas first; optionally call a tool with explicit JSON."""
import argparse
import json
from databricks.sdk import WorkspaceClient
from databricks_mcp import DatabricksMCPClient

parser = argparse.ArgumentParser()
parser.add_argument('--url', required=True)
parser.add_argument('--tool')
parser.add_argument('--args', default='{}')
args = parser.parse_args()
client = DatabricksMCPClient(server_url=args.url, workspace_client=WorkspaceClient())
tools = client.list_tools()
for tool in tools:
    print(tool.name, json.dumps(tool.inputSchema, indent=2))
if args.tool:
    if args.tool not in {t.name for t in tools}:
        raise ValueError('Tool not found; use a name printed above')
    result = client.call_tool(args.tool,json.loads(args.args))
    print(result)
    if getattr(result, 'isError', False):
        raise RuntimeError('MCP returned a tool error')
