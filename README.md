# OpenManus

## Features

- **Multiple Agent Types**: General-purpose, browser automation, data analysis, and software engineering agents
- **Flexible Tool System**: Extensible tools for various tasks including web browsing, code editing, and data visualization
- **MCP Integration**: Support for Model Context Protocol servers
- **Multi-Agent Workflows**: Orchestrate complex tasks with multiple agents
- **Sandboxed Execution**: Docker-based isolated environment for safe code execution
- **Multiple LLM Support**: Works with OpenAI, Anthropic, Azure, Ollama, Google, and AWS Bedrock

## Quick Start

### Prerequisites

- Python 3.12+
- Docker (optional, for sandbox mode)
- Playwright (for browser automation)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/OpenManus.git
cd OpenManus

# Install dependencies
pip install -r requirements.txt

# Install browser automation dependencies
playwright install

# Copy and configure settings
cp config/config.example.toml config/config.toml
# Edit config/config.toml with your API keys and preferences
```

### Usage

#### Single Agent Mode

```bash
python main.py
```

#### MCP Agent Mode

```bash
python run_mcp.py --prompt "Your task here"
```

#### Multi-Agent Flow Mode

```bash
python run_flow.py
```

## Configuration

The framework uses TOML configuration files. Key sections include:

- `llm`: LLM provider settings
- `browser`: Browser automation configuration
- `search`: Web search API settings
- `sandbox`: Docker sandbox configuration
- `mcp`: MCP server configurations

See `config/config.example.toml` for all available options.

## Agent Types

- **ManusAgent**: General-purpose agent with full tool access
- **MCPAgent**: Integrates with Model Context Protocol servers
- **BrowserAgent**: Specialized for browser automation
- **SWEAgent**: Software engineering tasks
- **DataAnalysis**: Data analysis and visualization
- **ReActAgent**: Implements ReAct (Reasoning + Acting) pattern

## Development

```bash
# Run tests
pytest tests/

# Run linting
pre-commit run --all-files
```
