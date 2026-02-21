import asyncio
import logging
import aiohttp
import json
import traceback

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("ParserTest")

OXY_USER = "Pika1_MhRPr"
OXY_PASS = "Pika=1234pika"

TEST_DORKS = [
    'inurl:php?id= "admin"',
    'filetype:sql "password"',
    'intitle:"index of" "backup"',
]

async def fetch_oxylabs_results(session, query):
    url = "https://realtime.oxylabs.io/v1/queries"
    payload = {
        "source": "google_search",
        "query": query,
        "user_agent_type": "desktop_chrome",
        "parse": True,
        "start_page": 1,
        "pages": 10,
        "limit": 50,
    }
    logger.info("REQUEST: %s", query)

    try:
        async with session.post(
            url,
            auth=aiohttp.BasicAuth(OXY_USER, OXY_PASS),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=90),
        ) as r:
            body_text = await r.text()
            logger.info("RESPONSE status=%d", r.status)

            if r.status != 200:
                logger.error("HTTP %d — %s", r.status, body_text[:500])
                return []

            data = json.loads(body_text)
            urls = []
            for page in data.get("results", []):
                organic = (
                    page.get("content", {})
                    .get("results", {})
                    .get("organic", [])
                )
                for item in organic:
                    u = item.get("url")
                    if u:
                        urls.append(u)

            logger.info("Extracted %d URLs", len(urls))
            return urls

    except Exception as e:
        logger.error("ERROR: %s\n%s", e, traceback.format_exc())
        return []


async def main():
    logger.info("=" * 50)
    logger.info("PARSER TEST — %d dorks", len(TEST_DORKS))
    logger.info("=" * 50)

    all_urls = []
    async with aiohttp.ClientSession() as session:
        for i, dork in enumerate(TEST_DORKS):
            logger.info("--- Dork %d/%d: %s ---", i + 1, len(TEST_DORKS), dork)
            urls = await fetch_oxylabs_results(session, dork)
            all_urls.extend(urls)
            logger.info("Dork %d → %d URLs", i + 1, len(urls))

    unique = list(set(all_urls))
    logger.info("=" * 50)
    logger.info("DONE — Total: %d | Unique: %d", len(all_urls), len(unique))
    logger.info("=" * 50)
    if unique:
        logger.info("Sample URLs:")
        for u in unique[:5]:
            logger.info("  %s", u)


if __name__ == "__main__":
    asyncio.run(main())
