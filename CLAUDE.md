# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenManus is an open-source framework for building general AI agents, created by the MetaGPT team. It provides multiple agent types and tools for various tasks including browser automation, data analysis, and software engineering.

## Development Commands

```bash
# Install dependencies (Python 3.12+ required)
pip install -r requirements.txt
# or with uv (recommended)
uv pip install -r requirements.txt

# Browser setup (required for browser automation features)
playwright install

# Run single agent mode
python main.py

# Run MCP agent mode
python run_mcp.py
# MCP command options:
# --connection stdio/sse (default: stdio)
# --interactive (interactive mode)
# --prompt "Your prompt here"

# Run multi-agent flow mode
python run_flow.py

# Run tests
pytest tests/

# Run specific test
pytest tests/sandbox/test_client.py::test_function_name

# Run linting and formatting (pre-commit hooks)
pre-commit run --all-files
```

## High-Level Architecture

The codebase follows a modular architecture with clear separation of concerns:

1. **Agent System** (`app/agent/`): All agents inherit from `BaseAgent` and implement the `step()` method. Key agents:

   - `ManusAgent`: Main general-purpose agent with full tool access (PythonExecute, BrowserUseTool, StrReplaceEditor, AskHuman, Terminate, and dynamic MCP tools)
   - `MCPAgent`: Integrates with Model Context Protocol servers (tools loaded dynamically from MCP servers)
   - `BrowserAgent`: Specialized for browser automation tasks (BrowserUseTool, Terminate)
   - `SWEAgent`: Software engineering tasks with file operations (Bash, StrReplaceEditor, Terminate)
   - `DataAnalysis`: Data analysis and visualization (NormalPythonExecute, VisualizationPrepare, DataVisualization, Terminate)
   - `ReActAgent`: Implements ReAct (Reasoning + Acting) pattern
   - `ToolCallAgent`: Base class for tool-calling agents (implements `think()` method)

2. **Tool System** (`app/tool/`): Tools inherit from `BaseTool` and implement `execute()` method returning `ToolResult` objects. Tools are configured directly in agent classes using `available_tools` field with `ToolCollection`.

3. **Configuration** (`app/config.py`): Uses TOML files for configuration. Always check `config/config.example.toml` for available options. Configuration is loaded via Pydantic models.

4. **Flow System** (`app/flow/`): Orchestrates multi-agent workflows. Flows are defined in TOML and processed by `FlowFactory`. Currently supports `FlowType.PLANNING`.

5. **Sandbox** (`app/sandbox/`): Docker-based isolated execution environment for running untrusted code safely. Enable with `use_sandbox = true` in config.

6. **Memory System**: Agents maintain conversation history in `Memory` class with user/system/assistant/tool message types.

## Key Patterns

- **Agent-Tool Mapping**: Each agent has specific tools defined in its `available_tools` field. ManusAgent supports dynamic tool addition from MCP servers.
- **Async Operations**: Most agent and tool operations are async. Use `asyncio.run()` in entry points. Tests use `@pytest.mark.asyncio`.
- **Error Handling**: Custom exceptions in `app/exceptions.py`. Always wrap external operations. Tools have fallback mechanisms.
- **Prompts**: System prompts are in `app/prompt/`. Each agent has its own prompt module with dynamic modification support.
- **State Management**: Agents use `AgentState` enum (IDLE, RUNNING, SUCCESS, FAILED, TERMINATED, ERROR).
- **Working Directories**: 
  - Workspace: `PROJECT_ROOT/workspace/`
  - Logs: `PROJECT_ROOT/logs/`
  - MCP server module: `app.mcp.server`

## Configuration Setup

Before running, copy and modify the example config:

```bash
cp config/config.example.toml config/config.toml
```

Key configuration sections:

- `llm`: LLM provider settings (supports OpenAI, Anthropic, Azure, Ollama, Google, AWS Bedrock)
- `llm.vision`: Vision model configuration (optional)
- `browser`: Browser automation settings (headless mode, security, proxy, CDP/WebSocket)
- `search`: Web search API configurations (supports Google, Baidu, DuckDuckGo, Bing with fallback)
- `sandbox`: Docker sandbox settings (memory/CPU limits, network, timeout) - Docker required
- `mcp`: MCP server configurations (stdio/SSE connections)

## Testing Guidelines

- Tests are in `tests/` directory
- Use pytest with async support: `@pytest.mark.asyncio`
- Sandbox tests require Docker to be running
- Mock external services when possible
- Pre-commit hooks must pass before PR submission

## Adding New Features

1. **New Agent**: Inherit from `BaseAgent` or `ToolCallAgent`, implement `step()` method (or `think()` for ToolCallAgent), define `available_tools`, add system/next_step prompts
2. **New Tool**: Inherit from `BaseTool`, implement `execute()` method, return `ToolResult` object, register in agent's `available_tools`
3. **New LLM Provider**: Add to `app/llm.py` following existing patterns, update config schema if needed
4. **New Search Engine**: Inherit from `BaseSearchEngine` in `app/tool/search/`, add to search engine registry
