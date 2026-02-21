import asyncio
import logging
import aiohttp
import json
import traceback

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger("ParserTest")

OXY_USER = "Pika1_MhRPr"
OXY_PASS = "Pika=1234pika"

TEST_DORKS = [
    'inurl:php?id= "admin"',
    'filetype:sql "password"',
    'intitle:"index of" "backup"',
    'site:s3.amazonaws.com "config"',
    'inurl:admin/login.php',
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
        "limit": 50
    }
    logger.info("REQUEST for query: %s", query)
    logger.debug("Payload: %s", json.dumps(payload))

    try:
        async with session.post(
            url,
            auth=aiohttp.BasicAuth(OXY_USER, OXY_PASS),
            json=payload,
            timeout=aiohttp.ClientTimeout(total=90)
        ) as r:
            status = r.status
            body_text = await r.text()

            logger.info("RESPONSE status=%d for query: %s", status, query)

            if status != 200:
                logger.error(
                    "HTTP ERROR status=%d\nHeaders: %s\nBody (first 3000 chars):\n%.3000s",
                    status, dict(r.headers), body_text
                )
                return []

            try:
                data = json.loads(body_text)
            except json.JSONDecodeError as je:
                logger.error("JSON DECODE ERROR: %s\nRaw (first 2000 chars):\n%.2000s", je, body_text)
                return []

            urls = []
            results_list = data.get('results', [])
            logger.info("Got %d result pages", len(results_list))

            if not results_list:
                logger.warning(
                    "Empty 'results' array. Top-level keys: %s\nFull response (first 3000 chars):\n%.3000s",
                    list(data.keys()), json.dumps(data, indent=2)
                )

            for page_idx, page in enumerate(results_list):
                content = page.get('content', {})
                if not content:
                    logger.warning("Page %d: no 'content'. Keys: %s", page_idx, list(page.keys()))
                    continue

                results_obj = content.get('results', {})
                if not results_obj:
                    logger.warning("Page %d: content has no 'results'. Keys: %s", page_idx, list(content.keys()))
                    continue

                organic = results_obj.get('organic', [])
                if not organic:
                    logger.warning("Page %d: no 'organic'. Results keys: %s", page_idx, list(results_obj.keys()))
                    continue

                logger.info("Page %d: %d organic results", page_idx, len(organic))
                for res in organic:
                    u = res.get('url')
                    if u:
                        urls.append(u)

            logger.info("Extracted %d total URLs for query: %s", len(urls), query)
            return urls

    except asyncio.TimeoutError:
        logger.error("TIMEOUT (90s) for query: %s", query)
        return []
    except aiohttp.ClientError as e:
        logger.error("CLIENT ERROR: %s\n%s", e, traceback.format_exc())
        return []
    except Exception as e:
        logger.error("UNEXPECTED ERROR: %s\n%s", e, traceback.format_exc())
        return []


async def main():
    logger.info("=" * 60)
    logger.info("PARSER TEST START - testing %d dorks", len(TEST_DORKS))
    logger.info("=" * 60)

    all_urls = []
    async with aiohttp.ClientSession() as session:
        for i, dork in enumerate(TEST_DORKS):
            logger.info("-" * 40)
            logger.info("DORK %d/%d: %s", i + 1, len(TEST_DORKS), dork)
            logger.info("-" * 40)
            urls = await fetch_oxylabs_results(session, dork)
            all_urls.extend(urls)
            logger.info("Dork %d returned %d URLs", i + 1, len(urls))

    logger.info("=" * 60)
    logger.info("PARSER TEST COMPLETE")
    logger.info("Total unique URLs: %d", len(set(all_urls)))
    logger.info("=" * 60)

    if all_urls:
        logger.info("Sample URLs (first 10):")
        for u in list(set(all_urls))[:10]:
            logger.info("  %s", u)

if __name__ == "__main__":
    asyncio.run(main())
