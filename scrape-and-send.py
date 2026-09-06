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
        except Exception as e:
            print(f"PIN step: {e}")
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
    return tmp

async def send():
    path = await capture_tight()
    import io
    from datetime import datetime
    import pytz
    from telegram.request import HTTPXRequest
    from telegram import Bot
    token = os.environ["BOT_TOKEN"]
    chat_id = os.environ["CHAT_ID"]
    req = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    bot = Bot(token=token, request=req)
    with open(path,"rb") as f: data=f.read()
    bio = io.BytesIO(data); bio.name="summary.png"
    total_open = ""
    try:
        import json as _json, urllib.request as _url
        with _url.urlopen("https://janiela.vercel.app/partner-konnect.json", timeout=20) as _r:
            _j = _json.loads(_r.read().decode())
        amt = float(_j.get('totalOpen') or 0)
        total_open = "\nTotal Open: ₱" + f"{amt:,.2f}"
    except Exception as _e:
        print(f"total fetch: {_e}")
    cap = f"📊 Summary Breakdown — {datetime.now(pytz.timezone('Asia/Manila')).strftime('%a %b %d %I:%M %p')}{total_open}"
    await bot.send_photo(chat_id=int(chat_id), photo=bio, caption=cap)
    print(f"sent {len(data)} bytes")
    os.remove(path)

import asyncio
asyncio.run(send())
