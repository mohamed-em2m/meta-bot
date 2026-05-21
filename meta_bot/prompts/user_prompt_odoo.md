---
env: default
---
**Query**: "{{ query }}"
**Current Date/Time**: {{ time }}

## Processing Instructions

1. **Analyze** the natural language query
2. **Validate** table and column names against provided dictionaries
3. **Construct** a full SQL `SELECT` statement with appropriate `WHERE` conditions
4. **Execute** via `sql_read` tool call
5. **Format** results, including record counts
6. **Handle** errors and implement retry logic as needed
7 choose city from here if cities if the desire city not in our cities so filiter by it


**Rules**:

* Always include `stage_id = 1` for apartment listings unless overridden
* Use `IN` for string filters, not `LIKE`, unless partial match is needed
* Do not use date filters
* End every response with a tool call; never return raw data without a tool invocation
* you must only use the suitable queries come in main query

* use reveal_id to reterive apartments or booked
* think smart about using filds befor use it
you must call the tool odoo reader you can't return response
Call the tool now:
