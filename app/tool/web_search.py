import asyncio
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import config
from app.logger import logger
from app.tool.base import BaseTool, ToolResult
from app.tool.search import (
    BaiduSearchEngine,
    BingSearchEngine,
    DuckDuckGoSearchEngine,
    GoogleSearchEngine,
    WebSearchEngine,
)
from app.tool.search.base import SearchItem
from app.tool.search.circuit_breaker import CircuitOpenError, SearchEngineCircuitBreaker


class SearchResult(BaseModel):
    """Represents a single search result returned by a search engine."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    position: int = Field(description="Position in search results")
    url: str = Field(description="URL of the search result")
    title: str = Field(default="", description="Title of the search result")
    description: str = Field(
        default="", description="Description or snippet of the search result"
    )
    source: str = Field(description="The search engine that provided this result")
    raw_content: Optional[str] = Field(
        default=None, description="Raw content from the search result page if available"
    )

    def __str__(self) -> str:
        """String representation of a search result."""
        return f"{self.title} ({self.url})"


class SearchMetadata(BaseModel):
    """Metadata about the search operation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    total_results: int = Field(description="Total number of results found")
    language: str = Field(description="Language code used for the search")
    country: str = Field(description="Country code used for the search")


class SearchResponse(ToolResult):
    """Structured response from the web search tool, inheriting ToolResult."""

    query: str = Field(description="The search query that was executed")
    results: List[SearchResult] = Field(
        default_factory=list, description="List of search results"
    )
    metadata: Optional[SearchMetadata] = Field(
        default=None, description="Metadata about the search"
    )

    @model_validator(mode="after")
    def populate_output(self) -> "SearchResponse":
        """Populate output or error fields based on search results."""
        if self.error:
            return self

        result_text = [f"Search results for '{self.query}':"]

        for i, result in enumerate(self.results, 1):
            # Add title with position number
            title = result.title.strip() or "No title"
            result_text.append(f"\n{i}. {title}")

            # Add URL with proper indentation
            result_text.append(f"   URL: {result.url}")

            # Add description if available
            if result.description.strip():
                result_text.append(f"   Description: {result.description}")

            # Add content preview if available
            if result.raw_content:
                content_preview = result.raw_content[:1000].replace("\n", " ").strip()
                if len(result.raw_content) > 1000:
                    content_preview += "..."
                result_text.append(f"   Content: {content_preview}")

        # Add metadata at the bottom if available
        if self.metadata:
            result_text.extend(
                [
                    f"\nMetadata:",
                    f"- Total results: {self.metadata.total_results}",
                    f"- Language: {self.metadata.language}",
                    f"- Country: {self.metadata.country}",
                ]
            )

        self.output = "\n".join(result_text)
        return self


class WebContentFetcher:
    """Utility class for fetching web content."""

    @staticmethod
    async def fetch_content(url: str, timeout: int = 10) -> Optional[str]:
        """
        Fetch and extract the main content from a webpage.

        Args:
            url: The URL to fetch content from
            timeout: Request timeout in seconds

        Returns:
            Extracted text content or None if fetching fails
        """
        headers = {
            "WebSearch": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        try:
            # Use asyncio to run requests in a thread pool
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url, headers=headers, timeout=timeout)
            )

            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch content from {url}: HTTP {response.status_code}"
                )
                return None

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "header", "footer", "nav"]):
                script.extract()

            # Get text content
            text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace and limit size (100KB max)
            text = " ".join(text.split())
            return text[:10000] if text else None

        except Exception as e:
            logger.warning(f"Error fetching content from {url}: {e}")
            return None


class WebSearch(BaseTool):
    """Search the web for information using various search engines."""

    name: str = "web_search"
    description: str = """Search the web for real-time information about any topic.
    This tool returns comprehensive search results with relevant information, URLs, titles, and descriptions.
    If the primary search engine fails, it automatically falls back to alternative engines."""
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "(required) The search query to submit to the search engine.",
            },
            "num_results": {
                "type": "integer",
                "description": "(optional) The number of search results to return. Default is 5.",
                "default": 5,
            },
            "lang": {
                "type": "string",
                "description": "(optional) Language code for search results (default: en).",
                "default": "en",
            },
            "country": {
                "type": "string",
                "description": "(optional) Country code for search results (default: us).",
                "default": "us",
            },
            "fetch_content": {
                "type": "boolean",
                "description": "(optional) Whether to fetch full content from result pages. Default is false.",
                "default": False,
            },
        },
        "required": ["query"],
    }
    search_engine: dict[str, WebSearchEngine] = {
        "google": GoogleSearchEngine(),
        "baidu": BaiduSearchEngine(),
        "duckduckgo": DuckDuckGoSearchEngine(),
        "bing": BingSearchEngine(),
    }
    content_fetcher: WebContentFetcher = WebContentFetcher()
    circuit_breaker: SearchEngineCircuitBreaker = Field(
        default_factory=lambda: SearchEngineCircuitBreaker(
            failure_threshold=3,
            success_threshold=2,
            timeout=60.0,
            half_open_timeout=30.0
        )
    )

    async def execute(
        self,
        query: str,
        num_results: int = 5,
        lang: Optional[str] = None,
        country: Optional[str] = None,
        fetch_content: bool = False,
    ) -> SearchResponse:
        """
        Execute a Web search and return detailed search results.

        Args:
            query: The search query to submit to the search engine
            num_results: The number of search results to return (default: 5)
            lang: Language code for search results (default from config)
            country: Country code for search results (default from config)
            fetch_content: Whether to fetch content from result pages (default: False)

        Returns:
            A structured response containing search results and metadata
        """
        # Circuit breaker now handles retries internally

        # Use config values for lang and country if not specified
        if lang is None:
            lang = (
                getattr(config.search_config, "lang", "en")
                if config.search_config
                else "en"
            )

        if country is None:
            country = (
                getattr(config.search_config, "country", "us")
                if config.search_config
                else "us"
            )

        search_params = {"lang": lang, "country": country}

        # Try searching with circuit breaker pattern
        results = await self._try_all_engines_with_circuit_breaker(
            query, num_results, search_params
        )
        
        if results:
            # Fetch content if requested
            if fetch_content:
                results = await self._fetch_content_for_results(results)

            # Return a successful structured response
            return SearchResponse(
                status="success",
                query=query,
                results=results,
                metadata=SearchMetadata(
                    total_results=len(results),
                    language=lang,
                    country=country,
                ),
            )
        
        # Return an error response with circuit breaker status
        circuit_status = self.circuit_breaker.get_all_status()
        error_details = "All search engines are unavailable. Circuit breaker status: " + str(circuit_status)
        
        return SearchResponse(
            query=query,
            error=error_details,
            results=[],
        )

    async def _try_all_engines_with_circuit_breaker(
        self, query: str, num_results: int, search_params: Dict[str, Any]
    ) -> List[SearchResult]:
        """Try all search engines with circuit breaker pattern."""
        engine_order = self._get_engine_order()
        failed_engines = []
        skipped_engines = []

        for engine_name in engine_order:
            # Check if circuit is open before attempting
            if not self.circuit_breaker.is_available(engine_name):
                status = self.circuit_breaker.get_status(engine_name)
                logger.info(
                    f"⚡ Skipping {engine_name} - circuit breaker is OPEN. "
                    f"Retry after {status.get('retry_after_seconds', 0):.1f}s"
                )
                skipped_engines.append(engine_name)
                continue
                
            engine = self.search_engine[engine_name]
            logger.info(f"🔎 Attempting search with {engine_name.capitalize()}...")
            
            try:
                # Use circuit breaker to execute search
                search_items = await self.circuit_breaker.call(
                    engine_name,
                    self._perform_search_with_engine,
                    engine, query, num_results, search_params
                )
                
                if search_items:
                    if failed_engines or skipped_engines:
                        logger.info(
                            f"Search successful with {engine_name.capitalize()} "
                            f"(failed: {failed_engines}, skipped: {skipped_engines})"
                        )
                    
                    # Transform search items into structured results
                    return [
                        SearchResult(
                            position=i + 1,
                            url=item.url,
                            title=item.title or f"Result {i+1}",
                            description=item.description or "",
                            source=engine_name,
                        )
                        for i, item in enumerate(search_items)
                    ]
                else:
                    failed_engines.append(engine_name)
                    
            except CircuitOpenError as e:
                logger.warning(f"Circuit breaker prevented call to {engine_name}: {e}")
                skipped_engines.append(engine_name)
            except Exception as e:
                logger.error(f"Search with {engine_name} failed: {e}")
                failed_engines.append(engine_name)

        if failed_engines or skipped_engines:
            logger.error(
                f"All search engines unavailable. Failed: {failed_engines}, "
                f"Circuit open: {skipped_engines}"
            )
        return []

    async def _fetch_content_for_results(
        self, results: List[SearchResult]
    ) -> List[SearchResult]:
        """Fetch and add web content to search results."""
        if not results:
            return []

        # Create tasks for each result
        tasks = [self._fetch_single_result_content(result) for result in results]

        # Type annotation to help type checker
        fetched_results = await asyncio.gather(*tasks)

        # Explicit validation of return type
        return [
            (
                result
                if isinstance(result, SearchResult)
                else SearchResult(**result.dict())
            )
            for result in fetched_results
        ]

    async def _fetch_single_result_content(self, result: SearchResult) -> SearchResult:
        """Fetch content for a single search result."""
        if result.url:
            content = await self.content_fetcher.fetch_content(result.url)
            if content:
                result.raw_content = content
        return result

    def _get_engine_order(self) -> List[str]:
        """Determines the order in which to try search engines."""
        preferred = (
            getattr(config.search_config, "engine", "google").lower()
            if config.search_config
            else "google"
        )
        fallbacks = (
            [engine.lower() for engine in config.search_config.fallback_engines]
            if config.search_config
            and hasattr(config.search_config, "fallback_engines")
            else []
        )

        # Start with preferred engine, then fallbacks, then remaining engines
        engine_order = [preferred] if preferred in self.search_engine else []
        engine_order.extend(
            [
                fb
                for fb in fallbacks
                if fb in self.search_engine and fb not in engine_order
            ]
        )
        engine_order.extend([e for e in self.search_engine if e not in engine_order])

        return engine_order

    async def _perform_search_with_engine(
        self,
        engine: WebSearchEngine,
        query: str,
        num_results: int,
        search_params: Dict[str, Any],
    ) -> List[SearchItem]:
        """Execute search with the given engine and parameters."""
        # Execute in thread pool without retry (circuit breaker handles retries)
        items = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: list(
                engine.perform_search(
                    query,
                    num_results=num_results,
                    lang=search_params.get("lang"),
                    country=search_params.get("country"),
                )
            ),
        )
        
        # Empty results should be treated as failure for circuit breaker
        if not items:
            raise Exception("No results returned from search engine")
            
        return items


if __name__ == "__main__":
    web_search = WebSearch()
    search_response = asyncio.run(
        web_search.execute(
            query="Python programming", fetch_content=True, num_results=1
        )
    )
    print(search_response.to_tool_result())
