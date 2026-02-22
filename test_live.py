import asyncio
import aiohttp
import sys
sys.path.insert(0, '/workspace')
from bot import check_sql

URLS = [
    "https://www.hpuniv.ac.in/university-detail/vc-message-detail.php?icdeol&messid=204",
    "https://www.zamalekrealestate.com/mobile/property/show.php?ID=1343",
    "http://www.elahi-grp.com/content.php?Id=62",
    "https://barodabusinessdirectory.com/individualprofile.php?Login_Id=433",
    "https://mindloops.org/mind-booster-content.php?id=110&type=qz",
]

async def main():
    print("=" * 60)
    print(f"TESTING {len(URLS)} URLs with bot's check_sql()")
    print("=" * 60)

    detected = 0
    async with aiohttp.ClientSession() as session:
        for url in URLS:
            print(f"\nTesting: {url}")
            result = await check_sql(session, url)
            if result:
                detected += 1
                print(f"  ✅ {result}")
            else:
                print(f"  ❌ NOT DETECTED")

    print(f"\n{'=' * 60}")
    print(f"RESULT: {detected}/{len(URLS)} detected")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
