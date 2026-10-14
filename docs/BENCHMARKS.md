# Manual Genie / MCP acceptance questions

| Question | Expected result |
|---|---|
| How many mature expected welcome communications? | 10,000 |
| How many were delivered on time? | 9,500 |
| What is the SLA breach rate? | 5% |
| Separate late from unconfirmed | 200 late, 300 unconfirmed |
| How many are still pending? | 20, use investigation; not in mature metric view |
| How many customers breached the SLA? | 500 in this dataset |
| What happened to C09701? | Validation failure, MISSING_PHONE, R09701_1, no message attempt |
| What happened to C09881? | Provider rejected M09881_1, no confirmed delivery |
| What happened to C09971? | Accepted attempt, no receipt, UNKNOWN cause |
| What happened to C00001? | Initial failure R00001_0, recovered R00001_1, delivered ON_TIME |
| Is C09500 late? | No; delivered exactly at 15 minutes |
| Why were the 200 late messages late? | UNKNOWN; no causal evidence injected |
| Does 280 graph failure paths mean 280 missed messages? | No; 100 recovered failures are included |

For full integration acceptance, the combined metrics-plus-evidence question must produce calls to both
Genie and graph MCP servers. Capture the generated SQL, statement/evidence IDs and final response.
Do not provide the test truth table to Genie; benchmarks must be answered from source-derived data.
