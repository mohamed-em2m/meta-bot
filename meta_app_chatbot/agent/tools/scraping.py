import asyncio

import logging
import os
import re
import ssl
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union
import pytz

import aiohttp
import requests
import tiktoken
import httpx
import openai
from bs4 import BeautifulSoup, Comment, NavigableString
from googleapiclient.errors import HttpError
from playwright.async_api import async_playwright
from langchain_core.tools import tool
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from meta_app_chatbot.agent.tools.tool_prompts import system_template_summarize
from meta_app_chatbot.agent.utils import log_print, get_token_length
from meta_app_chatbot.cache.cache import cache_register


# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(loop_id)s] %(message)s"
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


SECTION_TAGS = {
    "section",
    "article",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


async def fetch_content_static(session, url, ssl_flag=False, retries=2):
    HEADERS = {"User-Agent": "Mozilla/5.0"}
    ssl_context = None
    if ssl_flag:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    for attempt in range(retries):
        try:
            async with session.get(url, headers=HEADERS, ssl=ssl_context) as response:
                if response.status == 200:
                    return await response.text()
                raise Exception(
                    f"[Error] Failed to fetch {url}, Status: {response.status}"
                )
        except Exception as e:
            print(f"[Retry {attempt + 1}/{retries}] Error fetching {url}: {e}")
    return None


async def async_fetch_dynamic(
    browser,
    url: str,
    semaphore: asyncio.Semaphore,
    remove_tags: tuple = ("script", "style"),
    remove_comments: bool = False,
    remove_lines: bool = False,
    remove_spaces: bool = True,
    timeout: int = 50,
    async_sleep: float = 2,
    max_retries: int = 2,
) -> tuple[str, str | None]:
    page = None
    timeout_ms = int(timeout * 1000)

    async with semaphore:
        try:
            page = await browser.new_page()
            logger.info(f"Navigating to {url}...")
            try:
                await page.goto(url, wait_until="load", timeout=timeout_ms)
            except Exception as e:
                logger.warning(f"Failed to fully load {url}: {e}")

            try:
                await page.wait_for_selector("body", timeout=timeout_ms)
                logger.info(f"'body' tag found on {url}")
            except Exception as e:
                logger.warning(f"No 'body' tag found on {url}: {e}")

            await asyncio.sleep(async_sleep)

            html_content = ""
            for attempt in range(1, max_retries + 1):
                html_content = await page.content()
                if html_content.strip():
                    break
                logger.warning(
                    f"Empty HTML on attempt {attempt} for {url}, retrying..."
                )
                await asyncio.sleep(async_sleep)

            if not html_content.strip():
                logger.error(
                    f"Failed to retrieve content after {max_retries} retries for {url}"
                )
                return url, None

            scrapped = get_html_content(
                html_content, remove_tags, remove_comments, remove_lines, remove_spaces
            )

            logger.info(f"Successfully fetched and cleaned content for {url}.")
            return url, scrapped

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return url, None

        finally:
            if page:
                await page.close()


def get_html_content(
    html_text: str,
    remove_tags=("script", "style"),
    remove_comments: bool = False,
    remove_spaces: bool = True,
    indent_val: int = 2,
) -> str:
    if not html_text:
        return None

    try:
        soup = BeautifulSoup(html_text, "html.parser")
        for t in remove_tags:
            for tag in soup.find_all(t):
                tag.decompose()

        body = soup.body or soup

        if remove_comments:
            for c in body.find_all(string=lambda t: isinstance(t, Comment)):
                c.extract()

        def recurse(node):
            pieces = []
            for child in node.children:
                if isinstance(child, NavigableString):
                    txt = child.strip()
                    if txt:
                        if remove_spaces:
                            txt = re.sub(r"\s+", " ", txt)
                        pieces.append(txt)
                else:
                    name = child.name.lower()

                    # section boundary
                    if name in SECTION_TAGS:
                        inner = recurse(child).strip()
                        # put blank lines around
                        pieces.append("\n\n" + inner + "\n\n")
                    elif name == "li":
                        inner = recurse(child).strip()
                        pieces.append("- " + inner + " ")
                    else:
                        pieces.append(recurse(child))
            return "".join(pieces)

        out = recurse(body).strip()
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out

    except Exception as e:
        logger.error(f"Error in get_structured_text: {e}")
        return None


def _sync_scrape_link(
    url,
    remove_tags=("script", "style"),
    remove_comments=False,
    remove_lines=True,
    remove_spaces=True,
    timeout=12,
):
    try:
        response = requests.get(
            url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout
        )
        if response.status_code != 200:
            raise ValueError(
                f"Failed to fetch {url}, Status code: {response.status_code}"
            )

        html_content = response.text

        return get_html_content(
            html_content,
            remove_tags,
            remove_comments,
            remove_lines,
            remove_spaces,
        )
    except Exception as e:
        print(f"[Error]: Failed to fetch {url}: {str(e)}")
        return None


async def _scrape_task_static(
    url: str,
    session: aiohttp.ClientSession,
    remove_tags: Sequence[str] = ("script", "style"),
    remove_comments: Optional[bool] = False,
    remove_lines: Optional[bool] = True,
    remove_spaces: Optional[bool] = True,
    ssl_flag: Optional[bool] = True,
    retries: Optional[int] = 2,
    user_query: str = "",
    index: int = 0,
):
    html_content = await fetch_content_static(session, url, ssl_flag, retries=retries)
    if html_content is None:
        return url, None

    scrapped = get_html_content(
        html_content, remove_tags, remove_comments, remove_lines, remove_spaces
    )
    if any(
        keyword in scrapped
        for keyword in ["<?php", "{%", "data.qryEvento", "<%=", "{{get_"]
    ):
        print("[Error]: Dynamic placeholders or server-side code detected in content.")
        return url, None
    return url, await summarize_agent.summarize(scrapped, user_query, index)


async def async_scrape_transform_links_static(
    urls: Sequence[str],
    remove_tags=("script", "style", "header", "footer"),
    remove_comments=False,
    remove_lines=True,
    remove_spaces=True,
    ssl_flag=True,
    timeout=7,
    retries=3,
    user_query: str = "",
):
    timeout_obj = aiohttp.ClientTimeout(total=timeout)

    async with aiohttp.ClientSession(timeout=timeout_obj) as session:

        async def wrapper(url, index):
            try:
                return await asyncio.wait_for(
                    _scrape_task_static(
                        url,
                        session,
                        remove_tags,
                        remove_comments,
                        remove_lines,
                        remove_spaces,
                        ssl_flag,
                        retries=retries,
                        user_query=user_query,
                        index=index,
                    ),
                    timeout=timeout,
                )
            except Exception:
                return ("", "")

        scraping_tasks = [
            asyncio.create_task(wrapper(url, index)) for index, url in enumerate(urls)
        ]
        return await asyncio.gather(*scraping_tasks)


async def async_scrape_transform_links_dynamic(
    urls: Sequence[str],
    remove_tags=("script", "style", "header", "footer"),
    remove_comments=False,
    remove_lines=True,
    remove_spaces=True,
    timeout=50,
    max_num_urls=3,
):
    async with async_playwright() as p:
        semaphore = asyncio.Semaphore(max_num_urls)
        browser = await p.chromium.launch(headless=True)
        tasks = [
            asyncio.create_task(
                async_fetch_dynamic(
                    browser,
                    url,
                    semaphore,
                    remove_tags,
                    remove_comments,
                    remove_lines,
                    remove_spaces,
                    timeout=timeout,
                )
            )
            for url in urls
        ]
        contents = await asyncio.gather(*tasks)

        await browser.close()
    return contents


def scrape_links(
    urls: Union[str, Sequence[str]],
    remove_tags=(
        "script",
        "style",
        "header",
        "footer",
        "nav",
        "noscript",
        "iframe",
        "form",
        "input",
        "button",
        "aside",
        "svg",
        "canvas",
        "object",
        "embed",
        "picture",
        "figure",
        "figcaption",
        "video",
        "audio",
        "meta",
        "navbar",
        "menu",
        "sidebar",
        "ads",
        "ad",
        "cookie",
        "popup",
        "modal",
        "banner",
        "subscribe",
        "newsletter",
        "tracking",
        "sponsor",
        "share",
        "comment",
        "breadcrumb",
        "template",
        "datalist",
        "dialog",
        "source",
    ),
    remove_comments=False,
    remove_lines=True,
    remove_spaces=True,
    ssl_flag=True,
    retries=2,
    timeout=7,
    is_async=True,
    static_scrape=True,
    user_query: str = "",
):
    if isinstance(urls, str):
        urls = [urls]
    if is_async:
        if static_scrape:
            return asyncio.run(
                async_scrape_transform_links_static(
                    urls,
                    remove_tags,
                    remove_comments,
                    remove_lines,
                    remove_spaces,
                    ssl_flag,
                    timeout=timeout,
                    retries=retries,
                    user_query=user_query,
                )
            )
        else:
            return asyncio.run(
                async_scrape_transform_links_dynamic(
                    urls,
                    remove_tags,
                    remove_comments,
                    remove_lines,
                    remove_spaces,
                    timeout=timeout,
                )
            )
    contents = []
    for url in urls:
        contents.append(
            (
                url,
                _sync_scrape_link(
                    url,
                    remove_tags,
                    remove_comments,
                    remove_lines,
                    remove_spaces,
                    timeout=timeout,
                ),
            )
        )
    return contents


def parse_iso_datetime(s: str) -> Optional[datetime]:
    """
    Parse ISO-style date/time strings and return it only if it's not in the future.

    Args:
        s: String containing a date/time

    Returns:
        Parsed datetime object or None if parsing fails
    """
    if not s:
        return None

    now = datetime.now(timezone.utc).astimezone()
    # now as a timezone-aware local datetime

    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",  # with offset
        "%Y-%m-%dT%H:%M:%S",  # no offset
        "%Y-%m-%d",
    ):  # date only
        try:
            dt = datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue

        # Make dt timezone-aware if it isn't already,
        # assuming local time for the no-offset cases:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now.tzinfo)

        # Return it regardless of whether it's in the future
        # (commented out future date check as it may filter out upcoming events)
        if dt >= now:
            return dt

    return None


def extract_events(data):
    events = []
    for item in data:
        if "pagemap" in item and "Event" in item["pagemap"]:
            events.append("Name|Date|url")

            for event in item["pagemap"]["Event"]:
                events.append(
                    f"{event.get('name')}|{event.get('startDate')}|{event.get('url')}"
                )

    return "\n".join(events)


def extract_events_from_search(
    search_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Extract comprehensive event information from Google Custom Search Engine results.

    Args:
        search_results: A list of dictionaries from search results

    Returns:
        A list of dictionaries with extracted event details
    """
    extracted_events = []
    if not isinstance(search_results, list):
        return extracted_events

    # Track unique events
    seen_events = set()

    for result in search_results:
        pagemap = result.get("pagemap", {})
        if not pagemap:
            continue

        # Extract from 'sportsevent'
        sports_events = pagemap.get("sportsevent", [])
        for event_data in sports_events:
            name = event_data.get("name")
            start_date_str = event_data.get("startdate")

            event_identifier = (name, start_date_str)
            if event_identifier in seen_events:
                continue  # Skip duplicate

            event_info = {
                "source": "sportsevent",
                "name": name,
                "start_date_raw": start_date_str,
                "location": event_data.get("location"),
                "home_team": event_data.get("hometeam"),
                "away_team": event_data.get("awayteam"),
                "organization": event_data.get("organization"),
                "url": event_data.get("url"),
                "result_title": result.get("title"),
                "result_link": result.get("link"),
            }

            # Parse date
            try:
                if start_date_str:
                    dt_part = start_date_str.split("T")[0]
                    event_info["start_date_parsed"] = datetime.strptime(
                        dt_part, "%Y-%m-%d"
                    ).date()
            except (ValueError, TypeError):
                event_info["start_date_parsed"] = None

            # Add if it has essential info
            if name and start_date_str:
                extracted_events.append(event_info)
                seen_events.add(event_identifier)

        # Extract from 'hcalendar'
        hcalendar_events = pagemap.get("hcalendar", [])
        for event_data in hcalendar_events:
            summary = event_data.get("summary")
            start_date_str = event_data.get("dtstart")

            event_identifier = (summary, start_date_str)
            if event_identifier in seen_events:
                continue  # Skip duplicate

            event_info = {
                "source": "hcalendar",
                "name": summary,
                "start_date_raw": start_date_str,
                "location": event_data.get("location"),
                "description": event_data.get("description"),
                "home_team": None,
                "away_team": None,
                "organization": None,
                "url": event_data.get("url"),
                "result_title": result.get("title"),
                "result_link": result.get("link"),
            }

            # Parse date
            try:
                if start_date_str:
                    dt_part = start_date_str.split("T")[0]
                    event_info["start_date_parsed"] = datetime.strptime(
                        dt_part, "%Y-%m-%d"
                    ).date()
            except (ValueError, TypeError):
                event_info["start_date_parsed"] = None

            # Add if it has essential info
            if summary and start_date_str:
                extracted_events.append(event_info)
                seen_events.add(event_identifier)

        # Extract from 'event'
        generic_events = pagemap.get("event", [])
        for event_data in generic_events:
            summary = event_data.get("summary")
            start_date_str = event_data.get("dtstart")

            event_identifier = (summary, start_date_str)
            if event_identifier in seen_events:
                continue  # Skip duplicate

            event_info = {
                "source": "event",
                "name": summary,
                "start_date_raw": start_date_str,
                "location": event_data.get("location"),
                "description": None,
                "home_team": None,
                "away_team": None,
                "organization": None,
                "url": event_data.get("url"),
                "result_title": result.get("title"),
                "result_link": result.get("link"),
            }

            # Parse date
            try:
                if start_date_str:
                    dt_part = start_date_str.split("T")[0]
                    event_info["start_date_parsed"] = datetime.strptime(
                        dt_part, "%Y-%m-%d"
                    ).date()
            except (ValueError, TypeError):
                event_info["start_date_parsed"] = None

            # Add if it has essential info
            if summary and start_date_str:
                extracted_events.append(event_info)
                seen_events.add(event_identifier)

    # Sort events by date
    extracted_events.sort(
        key=lambda x: x.get("start_date_parsed") or datetime.min.date()
    )

    return extracted_events


def format_extracted_events(events: List[Dict[str, Any]]) -> str:
    """
    Format extracted events into a string.

    Args:
        events: List of event dictionaries

    Returns:
        Formatted string with event information
    """
    if not events:
        return "No events found"

    result = ["source|name|start_date|location|url|result_title|result_link"]
    now = datetime.now()
    for event in events:
        date_str = (
            str(event.get("start_date_parsed", "N/A"))
            if event.get("start_date_parsed")
            else event.get("start_date_raw", "N/A")
        )
        row = f"{event.get('source', 'N/A')}|{event.get('name', 'N/A')}|{date_str}|{event.get('location', 'N/A')}|{event.get('url', 'N/A')}|{event.get('result_title', 'N/A')}|{event.get('result_link', 'N/A')}"
        if datetime.strptime(date_str, "%Y-%m-%d") >= now:
            result.append(row)

    return "\n".join(result)


def extract_events_all(items: List[Dict[str, Any]]) -> str:
    """
    Extract events from webpage data.

    Args:
        items: List of search result items

    Returns:
        String with formatted event information
    """
    events = ["title|summary|description|dtstart|startdate|url"]
    datetime.now()

    for item in items:
        pm = item.get("pagemap", {})

        # Look for different possible event lists
        for key in ("event", "hcalendar", "sportsevent"):
            for ev in pm.get(key, []):
                summary = (
                    ev.get("summary") or ev.get("name") or ev.get("description", "")
                )
                dt_str = ev.get("dtstart") or ev.get("startdate")
                dt = parse_iso_datetime(dt_str) if dt_str else None
                url = ev.get("url") or item.get("link", "")

                if dt:
                    events.append(f"{item.get('title', 'N/A')}|{summary}|{dt}|{url}")

    return "\n".join(events)


encoding = tiktoken.get_encoding("cl100k_base")
embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    separators=["\n\n", ". ", "\n", " "],
    length_function=lambda x: len(encoding.encode(x)),
)


def fly_search(query: str, res: List[str], top_k: int = 4) -> str:
    """
    Implement RAG (Retrieval-Augmented Generation) to find the most similar content.

    Args:
        query: Search query
        res: List of content to search through
        top_k: Number of top results to return

    Returns:
        String with the most relevant content
    """
    try:
        # Create embeddings
        vector_store = InMemoryVectorStore(embeddings)

        # Handle token encoding

        # Create text splitter for chunking
        # Ensure each result is non-empty and a string
        valid_results = [str(item) for item in res if item]

        if not valid_results:
            return "No valid content found for similarity search"

        # Split the documents
        results_split = splitter.split_documents(
            [Document(page_content=item) for item in valid_results]
        )

        if not results_split:
            return "No content chunks created for similarity search"

        # Add documents to vector store
        vector_store.add_documents(documents=results_split)

        # Perform similarity search
        results = vector_store.similarity_search(
            query=query, k=min(top_k, len(results_split))
        )

        # Format results
        formatted_results = [
            f"--- Relevant Content {i + 1} ---\n{result.page_content}\n"
            for i, result in enumerate(results)
        ]

        return "\n".join(formatted_results)

    except Exception as e:
        logger.error(f"Error in fly_search: {str(e)}")
        return f"Error performing similarity search: {str(e)}"


class LoopIdFilter(logging.Filter):
    def filter(self, record):
        try:
            record.loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            record.loop_id = "no-loop"
        return True


logger = logging.getLogger()
logger.addFilter(LoopIdFilter())

# --- Configure API ---
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    openai.api_key = api_key
    openai.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    logging.info("Configured OpenAI-compatible Gemini API.")
else:
    logging.error("GOOGLE_API_KEY not set. API calls will fail.")


class AnalysisAgent:
    def __init__(self, model_name="gemini-1.5-flash-8b"):
        self.model_name = model_name
        log_print("INFO", f"Initialized AnalysisAgent with model: {model_name}")
        self.client = openai.AsyncOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("Gemini_API_KEY"),
        )  # modern v1.x client
        self.client_2 = openai.AsyncOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("Gemini_API_KEY_2"),
        )

    def call(self, search_qeury, top_results):
        log_print("INFO", f"Call invoked for: {search_qeury}")
        try:
            return asyncio.run(self.summarize_all(search_qeury, top_results))
        except RuntimeError as e:
            log_print("Error", f"Event loop already running. Fallback: {e}")
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self.summarize_all(search_qeury, top_results)
            )

    async def summarize(self, user_query, text_to_summarize, index):
        day, date = self.get_time("Rome")

        try:
            chat_dict = system_template_summarize.invoke(
                {
                    "date": f"{date, day}",
                    "user_query": user_query,
                    "scraped_data": text_to_summarize,
                }
            ).model_dump()

            messages = []
            for item in chat_dict["messages"]:
                role = "user" if item["type"] == "human" else item["type"]
                messages.append({"role": role, "content": item["content"]})
            client = self.client if index % 2 else self.client_2

            # Define the task you want to timeout
            async def get_completion():
                response = await client.chat.completions.create(
                    model=self.model_name, messages=messages, temperature=0.5
                )
                return response.choices[0].message.content.strip()

            # Apply 5-second timeout
            return await asyncio.wait_for(get_completion(), timeout=5)

        except asyncio.TimeoutError:
            log_print("Warning", "Summarization timed out after 5 seconds.")
            return ""  # Return empty string on timeout

        except Exception as e:
            log_print("Error", f"OpenAI API error: {e}")
            return f"Error summarizing: {e}"

    async def summarize_all(self, search_qeury, top_results):
        log_print("INFO", f"Summarizing {len(top_results)} items...")
        tasks = []
        for index, item in enumerate(top_results):
            content = (
                str(item.get("snippet", "")) if isinstance(item, dict) else str(item)
            )
            if content.strip() and item not in ["", " ", None]:
                tasks.append(self.summarize(search_qeury, content, index))
            else:
                tasks.append(asyncio.sleep(0, result="Skipped: Empty content"))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [str(r) if isinstance(r, Exception) else r for r in results]

    def get_time(self, location="Rome"):
        try:
            tz_match = [
                tz for tz in pytz.all_timezones if location.lower() in tz.lower()
            ]
            tz = pytz.timezone(tz_match[0] if tz_match else "Europe/Rome")
            now = datetime.now(tz)
            return now.strftime("%A"), now.strftime("%Y-%m-%d")
        except Exception as e:
            logging.warning(f"Timezone error: {e}")
            now = datetime.now(pytz.utc)
            return now.strftime("%A"), now.strftime("%Y-%m-%d")


async def google_search(query: str):
    url = "https://google-search74.p.rapidapi.com/"
    params = {"query": query, "limit": "4", "related_keywords": "false"}
    headers = {
        "x-rapidapi-key": "d2ad802aa7msh093161d9f5a9686p1b63fejsn8a8d836b2333",
        "x-rapidapi-host": "google-search74.p.rapidapi.com",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            res = await client.get(url, headers=headers, params=params)
            res.raise_for_status()
            return res.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"error": str(e)}


# Example use
summarize_agent = AnalysisAgent()


@tool
def google_web_search(
    search_qeury: str, country: str = "it", lang: str = "lang_it"
) -> str:
    """
    Performs a Google Custom Search for the given query and scrapes the resulting web pages .
    Args:
        search_qeury (str): search Qeury used to find related content. It should be in the same language as specified by the `lang` parameter.
        country (str, optional): The two-letter country code used to localize search results (default is "it" for Italy).
        lang (str, optional): The language code used for processing and summarizing content. For best results, it should match the language of the specified country. Format: "lang_{language_code}" (e.g., "lang_it" for Italy, "lang_fr" for France). Default is "lang_it".

    Returns:
        str: A concise summary of the most relevant information extracted from the top search results.
    """

    try:
        logger.info(
            f"Starting search for: {search_qeury}, country {country} , lang {lang}"
        )
        key = {"search_qeury": search_qeury, "country": country, "lang": lang}
        if cache_register.exists_auto(key):
            return cache_register.get_auto(key)

        log_print("INFO", "Starting Google search")
        """
        # Create search service
        service = build("customsearch", "v1", developerKey=os.environ["CSE_KEY"])

        # Execute the search
        res = service.cse().list(
            q=search_qeury,
            cx=os.environ["CSE_ID"],
            num=num,
            lr=lang
        ).execute()"""

        log_print("INFO", "Completed Google search")

        async def run_async():
            return await asyncio.create_task(google_search(search_qeury).get("results"))

        res = asyncio.run(google_search(search_qeury))
        # Get search results
        results = res.get("results", [])

        if not results:
            return "No search results found"

        # Extract URLs
        urls = []
        for result in results:
            try:
                urls.append(result["url"])
            except Exception as e:
                logger.error(f"Error extracting link from result: {str(e)}")

        # Extract events from search results
        log_print("INFO", "Extracting events from search results")
        try:
            events = extract_events(results)
        except Exception as e:
            logger.error(f"Error extracting events: {str(e)}")
            events = "Error extracting events"

        # Extract comprehensive event information
        try:
            all_events_data = extract_events_from_search(results)
            all_events = format_extracted_events(all_events_data)
        except Exception as e:
            logger.error(f"Error extracting comprehensive events: {str(e)}")
            all_events = "Error extracting comprehensive events"

        # Extract additional event information
        try:
            events_all = extract_events_all(results)
        except Exception as e:
            logger.error(f"Error in extract_events_all: {str(e)}")
            events_all = "Error extracting additional events"

        # Scrape website content
        log_print("INFO", "Starting  scraping and cleaning")
        contents_results = [
            f"Source: {item[0]} \n" + item[1]
            for item in scrape_links(urls, user_query=search_qeury)
            if item[1] not in [None, ""]
        ]
        events = ["\n".join([events, all_events, events_all])]
        if not (events[0] not in ["", None]):
            contents_results = [
                "\n".join([events, all_events, events_all])
            ] + contents_results

        final_outputs = "\n".join(contents_results)
        # Perform similarity search
        log_print("INFO", "Completed  scraping and cleaning")

        # Combine all results
        combined_results = [
            "=" * 50,
            "SEARCH RESULTS AND Scraped Data",
            "=" * 50,
            final_outputs,
        ]
        str_combined_results = "\n".join(combined_results)
        print(
            f"number of tokens after preprocessing {get_token_length(str_combined_results)} and created from {len(contents_results)}"
        )
        cache_register.set_auto(key, str_combined_results)
        return str_combined_results

    except HttpError as e:
        error_message = f"Google API error: {str(e)}"
        logger.error(error_message)
        return error_message

    except Exception as e:
        error_message = f"Critical error: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_message)
        return error_message
