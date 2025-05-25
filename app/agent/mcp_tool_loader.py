"""MCP Tool Loader for managing MCP server connections and tool registration."""

from typing import Dict, List, Optional

from app.config import config
from app.logger import logger
from app.tool.mcp import MCPClients, MCPClientTool


class MCPToolLoader:
    """Handles MCP server connections and tool loading with proper separation of concerns."""
    
    def __init__(self, mcp_clients: Optional[MCPClients] = None):
        """Initialize the MCP tool loader.
        
        Args:
            mcp_clients: Optional MCPClients instance, creates new if not provided
        """
        self.mcp_clients = mcp_clients or MCPClients()
        self.connected_servers: Dict[str, str] = {}
        
    async def load_configured_servers(self) -> List[MCPClientTool]:
        """Load all MCP servers from configuration.
        
        Returns:
            List of MCPClientTool instances from all connected servers
        """
        all_tools = []
        
        for server_id, server_config in config.mcp_config.servers.items():
            try:
                tools = await self._load_single_server(server_id, server_config)
                all_tools.extend(tools)
            except Exception as e:
                logger.error(f"Failed to load MCP server {server_id}: {e}")
                
        return all_tools
    
    async def _load_single_server(self, server_id: str, server_config) -> List[MCPClientTool]:
        """Load tools from a single MCP server.
        
        Args:
            server_id: Unique identifier for the server
            server_config: Server configuration object
            
        Returns:
            List of tools from this server
        """
        if server_config.type == "sse":
            return await self._connect_sse_server(server_id, server_config)
        elif server_config.type == "stdio":
            return await self._connect_stdio_server(server_id, server_config)
        else:
            logger.warning(f"Unknown server type: {server_config.type}")
            return []
    
    async def _connect_sse_server(self, server_id: str, server_config) -> List[MCPClientTool]:
        """Connect to an SSE-based MCP server.
        
        Args:
            server_id: Server identifier
            server_config: Server configuration with URL
            
        Returns:
            List of tools from the connected server
        """
        if not server_config.url:
            logger.warning(f"SSE server {server_id} has no URL configured")
            return []
            
        await self.mcp_clients.connect_sse(server_config.url, server_id)
        self.connected_servers[server_id] = server_config.url
        logger.info(f"Connected to SSE MCP server {server_id} at {server_config.url}")
        
        return self._get_tools_for_server(server_id)
    
    async def _connect_stdio_server(self, server_id: str, server_config) -> List[MCPClientTool]:
        """Connect to a stdio-based MCP server.
        
        Args:
            server_id: Server identifier
            server_config: Server configuration with command and args
            
        Returns:
            List of tools from the connected server
        """
        if not server_config.command:
            logger.warning(f"STDIO server {server_id} has no command configured")
            return []
            
        await self.mcp_clients.connect_stdio(
            server_config.command,
            server_config.args or [],
            server_id
        )
        self.connected_servers[server_id] = server_config.command
        logger.info(f"Connected to STDIO MCP server {server_id} using command {server_config.command}")
        
        return self._get_tools_for_server(server_id)
    
    def _get_tools_for_server(self, server_id: str) -> List[MCPClientTool]:
        """Get all tools associated with a specific server.
        
        Args:
            server_id: Server identifier
            
        Returns:
            List of tools from the specified server
        """
        return [
            tool for tool in self.mcp_clients.tools 
            if tool.server_id == server_id
        ]
    
    async def connect_server(
        self,
        server_url: str,
        server_id: str = "",
        use_stdio: bool = False,
        stdio_args: Optional[List[str]] = None
    ) -> List[MCPClientTool]:
        """Connect to a single MCP server dynamically.
        
        Args:
            server_url: Server URL or command
            server_id: Optional server identifier
            use_stdio: Whether to use stdio connection
            stdio_args: Arguments for stdio connection
            
        Returns:
            List of tools from the newly connected server
        """
        if use_stdio:
            await self.mcp_clients.connect_stdio(
                server_url, 
                stdio_args or [], 
                server_id
            )
        else:
            await self.mcp_clients.connect_sse(server_url, server_id)
            
        self.connected_servers[server_id or server_url] = server_url
        return self._get_tools_for_server(server_id or server_url)
    
    async def disconnect_server(self, server_id: str = "") -> None:
        """Disconnect from an MCP server.
        
        Args:
            server_id: Server to disconnect from, or empty to disconnect all
        """
        await self.mcp_clients.disconnect(server_id)
        
        if server_id:
            self.connected_servers.pop(server_id, None)
        else:
            self.connected_servers.clear()
    
    async def cleanup(self) -> None:
        """Clean up all MCP connections."""
        await self.disconnect_server()  # Disconnect all