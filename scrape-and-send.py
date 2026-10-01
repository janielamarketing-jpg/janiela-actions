import asyncio, os, tempfile
from playwright.async_api import async_playwright

URL = "https://janiela.vercel.app"
PIN = os.getenv("JANIELA_PIN", "102394")

async def capture_tight():
    tmp = tempfile.mktemp(suffix=".png")
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        pg = await b.new_page(viewport={"width":1280,"height":900})
        await pg.goto(URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        await pg.click('button[aria-label="Open Navigation Menu"]')
        await asyncio.sleep(1.2)
        await pg.locator("text=Partner Konnect").first.click()
        await asyncio.sleep(3)
        try:
            try: await pg.wait_for_selector('input[type="password"]', timeout=5000)
            except: pass
            pin = await pg.query_selector('input[type="password"]')
            if pin:
                locked = await pg.evaluate("() => document.body.innerText.includes('Enter PIN')")
                if locked:
                    await pin.fill(PIN)
                    btn = await pg.query_selector('button:has-text("Unlock")')
                    if btn: await btn.click()
                    else: await pg.keyboard.press("Enter")
                    try: await pg.wait_for_function("() => document.body.innerText.includes('SUMMARY BREAKDOWN')", timeout=8000)
                    except: await asyncio.sleep(3)
                # Refresh to avoid stale cached total, then wait for fresh data
                try:
                    btn = await pg.query_selector('button:has-text("Refresh Now")')
                    if btn:
                        await btn.click()
                        await asyncio.sleep(6)
                        try: await pg.wait_for_function("() => document.body.innerText.includes('SUMMARY BREAKDOWN')", timeout=8000)
                        except: await asyncio.sleep(2)
                except: pass
        except Exception as e:
            print(f"PIN step: {e}")
        try:
            total_txt = await pg.evaluate("() => document.body.innerText")
            import re as _re
            m = _re.search(r"TOTAL OPEN[^\d₱P]*[₱P]?\s*([\d,]+\.\d{2})", total_txt)
            total_amt = m.group(1) if m else ""
        except:
            total_amt = ""
        print(f"total={total_amt}")
        box = await pg.evaluate('''() => {
            const t='SUMMARY BREAKDOWN BY DATE';
            const all=[...document.querySelectorAll('*')];
            const c=all.filter(el=>el.innerText&&el.innerText.includes(t)&&el.offsetHeight>350&&el.offsetHeight<1100&&el.innerText.length>200&&el.innerText.length<3000);
            if(!c.length) return null;
            c.sort((a,b)=>a.innerText.length-b.innerText.length);
            const r=c[0].getBoundingClientRect();
            return {x:r.x,y:r.y,w:r.width,h:r.height,scrollY:window.scrollY};
        }''')
        print(f"box={box}")
        if box and box['w']>0:
            await pg.evaluate(f"window.scrollTo(0,{box['scrollY']+box['y']-100})")
            await asyncio.sleep(0.8)
            box2 = await pg.evaluate('''() => {
                const t='SUMMARY BREAKDOWN BY DATE';
                const all=[...document.querySelectorAll('*')];
                const c=all.filter(el=>el.innerText&&el.innerText.includes(t)&&el.offsetHeight>350&&el.offsetHeight<1100&&el.innerText.length>200&&el.innerText.length<3000);
                c.sort((a,b)=>a.innerText.length-b.innerText.length);
                const r=c[0].getBoundingClientRect();
                return {x:r.x,y:r.y,w:r.width,h:r.height};
            }''')
            await pg.screenshot(path=tmp, clip={"x":max(0,box2["x"]-6),"y":max(0,box2["y"]-6),"width":box2["w"]+12,"height":box2["h"]+12})
        else:
            await pg.screenshot(path=tmp, full_page=True)
        await b.close()
    return tmp, total_amt

# Retry schedule in seconds before each attempt. The first is 0 so a healthy
# run is not delayed. Generous because this job is unattended - a missed day is
# a day with no summary at all.
SEND_RETRY_DELAYS = (0, 15, 30, 60, 120)


async def send_photo_with_retry(bot, chat_id, data, cap):
    import io
    from datetime import datetime
    import pytz
    last = "not attempted"
    for i, delay in enumerate(SEND_RETRY_DELAYS, 1):
        if delay:
            stamp = datetime.now(pytz.timezone("Asia/Manila")).strftime("%H:%M:%S")
            print(f"[{stamp}] upload retry {i}/{len(SEND_RETRY_DELAYS)} in {delay}s (last: {last})")
            await asyncio.sleep(delay)
        try:
            bio = io.BytesIO(data)
            bio.name = "summary.png"
            await bot.send_photo(chat_id=chat_id, photo=bio, caption=cap)
            return True
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            print(f"upload attempt {i}/{len(SEND_RETRY_DELAYS)} failed: {last}")
    return False



# --- time guard -------------------------------------------------------------
# GitHub's cron is best-effort, not punctual. This repo's runs have landed hours
# off their schedule, so a run outside the intended Manila window must not send:
# a summary at 1 AM is worse than no summary. The window is generous because a
# legitimately-late run should still deliver.
#
# Exits 0 (green) when out of window - a skip is the correct outcome, not a
# failure, and a red run here would cry wolf on every drift.
import sys
from datetime import datetime, timedelta, timezone

MANILA = timezone(timedelta(hours=8))

# (slot name, intended minute-of-day, earliest allowed, latest allowed)
WINDOWS = [
    ("morning", 7 * 60 + 20, 6 * 60 + 50, 9 * 60),
    ("evening", 19 * 60 + 30, 19 * 60, 21 * 60 + 30),
]


def within_window(now_local):
    """Return the slot this run belongs to, or None if it is out of window."""
    minutes = now_local.hour * 60 + now_local.minute
    for name, intended, lo, hi in WINDOWS:
        if lo <= minutes <= hi:
            return name, intended
    return None


def guard_or_skip():
    now_local = datetime.now(MANILA)
    hit = within_window(now_local)
    stamp = now_local.strftime("%a %b %d, %I:%M:%S %p")
    if hit:
        name, intended = hit
        hh, mm = divmod(intended, 60)
        log(f"in-window: {name} slot (intended {hh:02d}:{mm:02d} Manila)")
        return True
    lo = min(w[2] for w in WINDOWS)
    hi = max(w[3] for w in WINDOWS)
    log(f"OUT OF WINDOW at {stamp} Manila - skipping, no message sent")
    log(f"valid windows are {lo // 60:02d}:{lo % 60:02d}-09:00 and 19:00-21:30 Manila")
    return False


def log(msg):
    print(f"[{datetime.now(MANILA):%H:%M:%S}] {msg}", flush=True)


async def send():
    # Refuse to message the user outside the intended Manila hours.
    if not guard_or_skip():
        raise SystemExit(0)
    path, total_amt = await capture_tight()
    if not total_amt:
        # A capture that produced no total is a failed run, not a run with an
        # empty field. Exiting non-zero makes the Actions run red so the
        # failure is visible instead of arriving as a bare screenshot.
        print("FATAL: no TOTAL OPEN found - the capture did not reach the summary card")
        if os.path.exists(path):
            os.remove(path)
        raise SystemExit(2)

    from telegram.request import HTTPXRequest
    from telegram import Bot
    token = os.environ["BOT_TOKEN"]
    chat_id = os.environ["CHAT_ID"]
    req = HTTPXRequest(connect_timeout=30.0, read_timeout=90.0, write_timeout=90.0)
    bot = Bot(token=token, request=req)
    with open(path, "rb") as f:
        data = f.read()
    stamp = __import__("datetime").datetime.now(
        __import__("pytz").timezone("Asia/Manila")
    ).strftime("%a %b %d, %I:%M %p")
    cap = f"📊 Total Open: ₱{total_amt}\n🕒 {stamp} PH • Janiela Partner Konnect"

    ok = await send_photo_with_retry(bot, int(chat_id), data, cap)
    if ok:
        print(f"SENT {len(data)} bytes total={total_amt}")
    else:
        print("FATAL: upload failed after every retry")
    os.remove(path)
    if not ok:
        raise SystemExit(3)

import asyncio
asyncio.run(send())
