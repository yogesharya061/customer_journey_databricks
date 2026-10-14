"""Tool SQL binding and failure behavior checks, with mocked workspace I/O."""
import importlib.util
import unittest
from unittest.mock import patch

try:
    HAS_MCP = importlib.util.find_spec('mcp') is not None and importlib.util.find_spec('databricks.sdk') is not None
except ModuleNotFoundError:
    HAS_MCP = False

@unittest.skipUnless(HAS_MCP, 'Install mcp_server/requirements.txt for tool tests')
class ToolTests(unittest.TestCase):
    def test_parameter_binding_and_read_only_scope(self):
        from mcp_server import server
        with patch.object(server,'query',return_value={'rows':[]}) as query:
            server.get_customer_journey('C09701')
            statement, params = query.call_args.args
            self.assertNotIn('C09701',statement)
            self.assertEqual(params['customer'],'C09701')
            self.assertIn('LIMIT 201',statement)
            self.assertIn('snapshot_id=:snapshot',statement)
        with self.assertRaises(ValueError):
            server.get_customer_journey("C09701' OR 1=1 --")
        with self.assertRaises(ValueError):
            server.explain_communication('unrestricted')

    def test_query_failure_is_not_a_successful_answer(self):
        from mcp_server import server
        from types import SimpleNamespace as NS
        with patch.object(server,'WAREHOUSE','demo'), patch.object(server,'WorkspaceClient') as client:
            client.return_value.statement_execution.execute_statement.return_value = NS(
                status=NS(state=NS(value='FAILED')),statement_id='test-statement')
            with self.assertRaisesRegex(RuntimeError,'test-statement'):
                server.query('SELECT 1')
