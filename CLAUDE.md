## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore the codebase.** The graph is faster, cheaper (fewer tokens), and gives you structural context (callers, dependents, test coverage) that file scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep/Glob
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with `callers_of` / `callees_of` / `imports_of` / `tests_for`
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key MCP Tools

| Tool                        | Use when                                               |
| --------------------------- | ------------------------------------------------------ |
| `semantic_search_nodes`     | Finding functions/classes by name or concept           |
| `query_graph`               | Tracing callers, callees, imports, tests, dependencies |
| `detect_changes`            | Reviewing code changes — gives risk-scored analysis    |
| `get_review_context`        | Need source snippets for review — token-efficient      |
| `get_impact_radius`         | Understanding blast radius of a change                 |
| `get_affected_flows`        | Finding which execution paths are impacted             |
| `get_architecture_overview` | Understanding high-level codebase structure            |
| `list_communities`          | Discovering logical module groupings                   |
| `refactor_tool`             | Planning renames, finding dead code                    |
| `get_flow_tool`             | Tracing a specific execution flow end-to-end           |

### CLI Commands (also wired as hooks)

| Command                                        | When it runs                | Purpose                                |
| ---------------------------------------------- | --------------------------- | -------------------------------------- |
| `uvx code-review-graph update --skip-flows`    | After every Edit/Write/Bash | Keeps graph in sync with latest code   |
| `uvx code-review-graph status`                 | Session start               | Confirms graph is healthy              |
| `uvx code-review-graph detect-changes --brief` | Pre-commit                  | Risk-scored summary of what's changing |

### Workflow

1. Graph auto-updates after every file edit (via `PostToolUse` hook).
2. Start exploration with `semantic_search_nodes` or `get_architecture_overview`.
3. Use `detect_changes` + `get_review_context` for all code reviews.
4. Use `get_impact_radius` before any refactor or deletion.
5. Use `query_graph` pattern="tests_for" to check test coverage before shipping.
