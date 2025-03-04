import asyncio
import logging
import re
from asyncio import Semaphore
from typing import Dict, List
from urllib.parse import urljoin, urlparse

import aiohttp
import backoff
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pydantic import BaseModel

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GoogleSearchResult(BaseModel):
    title: str
    link: str
    snippet: str


class WebsiteContent(BaseModel):
    url: str
    content: str
    title: str
    success: bool = True
    message: str = ""
    links: List[str] = []
    depth: int = 0


class WholeWebsiteContent(BaseModel):
    root_url: str
    pages: Dict[str, WebsiteContent] = {}
    graph: Dict[str, List[str]] = {}  # Adjacency list representation
    depth_map: Dict[str, int] = {}  # Stores depth of each URL
    total_pages: int = 0
    max_depth_reached: int = 0

    class Config:
        arbitrary_types_allowed = True


async def crawl_website(
    start_url: str, max_depth: int = 2, max_pages: int = 100
) -> WholeWebsiteContent:
    """
    Recursively crawl website starting from given URL up to specified depth
    """
    visited = set()
    website_content = WholeWebsiteContent(root_url=start_url)

    async def should_crawl_url(url: str) -> bool:
        """Determine if URL should be crawled based on domain and other filters"""
        start_domain = urlparse(start_url).netloc
        url_domain = urlparse(url).netloc
        return (
            url not in visited
            and url_domain == start_domain
            and len(visited) < max_pages
        )

    async def dfs_crawl(url: str, depth: int = 0):
        """Depth-first search crawl implementation"""
        if depth > max_depth or not await should_crawl_url(url):
            return

        visited.add(url)
        website_content.depth_map[url] = depth
        website_content.max_depth_reached = max(
            website_content.max_depth_reached, depth
        )

        # Create session for this crawl
        async with aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0"}
        ) as session:
            semaphore = Semaphore(5)  # Limit concurrent requests

            # Process current URL
            page_content = await process_url(
                session,
                semaphore,
                GoogleSearchResult(title="", link=url, snippet=""),
                depth=depth,
            )

            if page_content and page_content.success:
                website_content.pages[url] = page_content
                website_content.graph[url] = page_content.links
                website_content.total_pages += 1

                # Recursively process all links
                tasks = []
                for link in page_content.links:
                    if await should_crawl_url(link):
                        tasks.append(dfs_crawl(link, depth + 1))

                if tasks:
                    await asyncio.gather(*tasks)

    # Start crawling from root URL
    await dfs_crawl(start_url)
    return website_content


async def process_url(
    session: aiohttp.ClientSession,
    semaphore: Semaphore,
    search_result: GoogleSearchResult,
    depth: int = 0,
) -> WebsiteContent:
    """Process a single URL with semaphore for rate limiting"""
    async with semaphore:
        url = search_result.link
        domain = urlparse(url).netloc
        logger.info(f"Fetching content from {domain} at depth {depth}")

        try:
            html = await fetch_with_retry(session, url)
            if html:
                content, title, links = sanitize_html(html, url)
                logger.info(
                    f"Successfully processed {domain}, title: {title}, links found: {len(links)}"
                )
                return WebsiteContent(
                    url=url,
                    content=content,
                    title=title or search_result.title,
                    links=links,
                    depth=depth,
                )

        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")

            return WebsiteContent(
                url=url,
                content=search_result.snippet,
                title=search_result.title,
                success=False,
                message=f"Failed to fetch content: {str(e)}",
                links=[],
                depth=depth,
            )


async def fetch_with_retry(session: aiohttp.ClientSession, url: str) -> tuple[str, str]:
    """Fetch URL content with retry logic"""

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, asyncio.TimeoutError),
        max_tries=3,
        max_time=30,
    )
    async def _fetch():
        timeout = ClientTimeout(total=10)
        async with session.get(url, timeout=timeout, allow_redirects=True) as response:
            response.raise_for_status()
            html = await response.text()
            return html

    try:
        return await _fetch()
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {str(e)}")
        return None


def sanitize_html(html: str, base_url: str) -> tuple[str, str, List[str]]:
    """Extract text content, title, and all links from HTML"""
    if not html:
        return "", "", []

    soup = BeautifulSoup(html, "html.parser")

    # Remove unwanted elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    # Get title
    title = soup.title.string if soup.title else ""

    # Get main content
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    # Extract all links and convert to absolute URLs
    links = []

    for link in soup.find_all("a", href=True):
        logger.info(f"Found link: {link['href']}")
        href = link["href"]
        try:
            # Convert relative URLs to absolute URLs
            absolute_url = urljoin(base_url, href)
            # Only include http(s) URLs
            if absolute_url.startswith(("http://", "https://")):
                links.append(absolute_url)
        except Exception as e:
            logger.error(f"Error processing link {href}: {str(e)}")

    return text, title, links


async def async_fetch_html_content(
    search_results: List[GoogleSearchResult],
) -> List[WebsiteContent]:
    """Async implementation of content fetching"""
    semaphore = Semaphore(5)  # Limit concurrent requests

    async with aiohttp.ClientSession(
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        }
    ) as session:
        tasks = [process_url(session, semaphore, result) for result in search_results]
        return await asyncio.gather(*tasks)


def fetch_html_content(
    search_results: List[GoogleSearchResult],
) -> List[WebsiteContent]:
    """Main function to fetch HTML content"""
    logger.info(f"Starting to fetch content for {len(search_results)} URLs")

    # Run async function in event loop
    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(async_fetch_html_content(search_results))

    logger.info("Completed fetching all content")
    return results


def google_search(query: str) -> List[GoogleSearchResult]:
    """
    Perform a Google search using service account credentials and return the first 10 results.

    Args:
        query (str): The search query

    Returns:
        List[Dict[str, str]]: List of dictionaries containing search results
        Each dictionary has 'title', 'link', and 'snippet' keys
    """

    SEARCH_ENGINE_ID = "21d74ec2048454109"  # You still need your Search Engine ID
    SCOPES = ["https://www.googleapis.com/auth/cse"]

    # Path to your service account JSON file
    SERVICE_ACCOUNT_FILE = "sentetik-945148a682b0.json"

    try:
        # Load credentials from the service account file
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )

        # Build the service using the credentials
        service = build("customsearch", "v1", credentials=credentials)

        # Perform the search
        result = service.cse().list(q=query, cx=SEARCH_ENGINE_ID, num=10).execute()

        # Extract and format the results
        search_results = []
        if "items" in result:
            for item in result["items"]:
                search_results.append(
                    GoogleSearchResult(
                        title=item["title"],
                        link=item["link"],
                        snippet=item["snippet"] if "snippet" in item else "",
                    )
                )

        return search_results

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return []


async def main():
    start_url = "https://www.robotistan.com/"
    website_graph = await crawl_website(start_url, max_depth=2, max_pages=100)

    # Print some statistics
    print(f"Total pages crawled: {website_graph.total_pages}")
    print(f"Max depth reached: {website_graph.max_depth_reached}")

    # Print the structure of the site
    for url, depth in website_graph.depth_map.items():
        print(f"{'  ' * depth}└─ {url}")

    # You can also analyze the graph structure
    for url, links in website_graph.graph.items():
        print(f"\nLinks from {url}:")
        for link in links:
            print(f"  → {link}")


if __name__ == "__main__":
    asyncio.run(main())
