import pathlib
p = pathlib.Path("C:/Users/Hasbullish/janiela-actions/.github/workflows/scrape-payments.yml")
t = p.read_text(encoding="utf-8")
old = "      - run: playwright install chromium --with-deps"
new = "      - run: playwright install chromium"
assert old in t, "pattern not found"
t = t.replace(old, new)
p.write_text(t, encoding="utf-8")
print("fixed")
print(t)
