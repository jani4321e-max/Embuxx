import asyncio
import aiohttp
import json
import time
import logging

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("ConcurrencyTest")

OXY_USER = "Pika1_MhRPr"
OXY_PASS = "Pika=1234pika"

TEST_QUERY = 'inurl:login.php?id='

async def single_request(session, req_id):
    url = "https://realtime.oxylabs.io/v1/queries"
    payload = {
        "source": "google_search",
        "query": TEST_QUERY,
        "user_agent_type": "desktop_chrome",
        "parse": True,
        "start_page": 1,
        "pages": 1,
        "limit": 5,
    }
    start = time.time()
    try:
        async with session.post(
            url, auth=aiohttp.BasicAuth(OXY_USER, OXY_PASS),
            json=payload, timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            elapsed = round(time.time() - start, 1)
            await r.text()
            return {"id": req_id, "status": r.status, "time": elapsed}
    except asyncio.TimeoutError:
        return {"id": req_id, "status": "TIMEOUT", "time": round(time.time() - start, 1)}
    except Exception as e:
        return {"id": req_id, "status": f"ERROR: {e}", "time": round(time.time() - start, 1)}

async def test_level(count):
    logger.info("=" * 40)
    logger.info("TESTING %d concurrent requests...", count)
    logger.info("=" * 40)

    start = time.time()
    async with aiohttp.ClientSession() as session:
        tasks = [single_request(session, i + 1) for i in range(count)]
        results = await asyncio.gather(*tasks)

    total_time = round(time.time() - start, 1)

    success = sum(1 for r in results if r["status"] == 200)
    failed = [r for r in results if r["status"] != 200]

    logger.info("RESULTS for %d concurrent:", count)
    logger.info("  OK: %d/%d", success, count)
    logger.info("  Total time: %ss", total_time)

    if failed:
        for f in failed[:5]:
            logger.info("  FAILED #%d: status=%s time=%ss", f["id"], f["status"], f["time"])

    return success, count, failed

async def main():
    logger.info("OXYLABS CONCURRENCY LIMIT TEST")
    logger.info("Testing: 5 → 10 → 15 → 20 → 30 → 50")
    logger.info("")

    levels = [5, 10, 15, 20, 30, 50]
    max_working = 0

    for level in levels:
        success, total, failed = await test_level(level)

        if success == total:
            max_working = level
            logger.info("✅ %d concurrent: ALL PASSED", level)
        else:
            logger.info("❌ %d concurrent: %d FAILED", level, len(failed))
            if failed:
                first_err = failed[0]["status"]
                logger.info("   Error type: %s", first_err)
            break

        await asyncio.sleep(2)

    logger.info("")
    logger.info("=" * 40)
    logger.info("FINAL RESULT: Max concurrent = %d", max_working)
    logger.info("=" * 40)

if __name__ == "__main__":
    asyncio.run(main())
