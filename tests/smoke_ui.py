from pathlib import Path
import re
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8877/"


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    )
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL, wait_until="domcontentloaded")
    page.locator("#focusChart .cmp-fund-line").wait_for(timeout=60000)
    assert page.locator("#focusChart .cmp-index-line").count() == 1
    if page.locator("#metricLeaderLabel").inner_text() == "已统计基金最高":
        assert page.locator("#metricLeaderLabel").inner_text() == "已统计基金最高"
        assert re.search(r"已统计 \d+/\d+", page.locator("#metricLeaderName").inner_text())
    aligned = page.evaluate("""() => comparableSeries(
      [{d:'2026-01-02',cum:1},{d:'2026-01-05',cum:1.1},{d:'2026-01-06',cum:1.2}],
      [{d:'2026-01-02',v:100},{d:'2026-01-05',v:105}]
    )""")
    assert [round(point["fund"]) for point in aligned] == [0, 10]
    assert [round(point["index"]) for point in aligned] == [0, 5]
    page.screenshot(path=str(ROOT / "mockups" / "implemented-desktop.png"))

    page.locator("#watchList .watch-row").nth(1).click()
    page.wait_for_function("document.querySelector('#focusName').textContent.includes('浦银全球智能科技')")
    page.locator("#focusChart .cmp-index-line").wait_for(timeout=60000)
    page.get_by_role("button", name="近三月").first.click()
    assert page.locator("#focusRanges .focus-range.on").inner_text() == "近三月"
    page.locator("#focusRanges .focus-range").last.click()
    assert page.locator("#focusRanges .focus-range.on").inner_text() == "全部"
    assert page.locator("#focusChart .cmp-index-line").count() == 1

    page.locator('.card[data-code="100055"] .f-head').click()
    page.locator('.card[data-code="100055"] .cmp-index-line').wait_for(timeout=60000)
    assert page.locator('.card[data-code="100055"] .cmp-fund-line').count() == 1
    page.locator('.card[data-code="100055"] .holdings-panel').wait_for()
    side_by_side = page.evaluate("""() => {
      const card = document.querySelector('.card[data-code="100055"]');
      const left = card.querySelector('.detail-analysis').getBoundingClientRect();
      const right = card.querySelector('.holdings-panel').getBoundingClientRect();
      return left.right < right.left && Math.abs(left.y - right.y) < 50;
    }""")
    assert side_by_side
    assert page.locator('.card[data-code="100055"] .holdings-scroll .hold tr').count() > 1
    page.locator('.card[data-code="100055"]').evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 90)")
    page.screenshot(path=str(ROOT / "mockups" / "implemented-fund-detail-desktop.png"))
    page.locator('.card[data-code="100055"] .hm-tab').last.click()
    assert page.locator('.card[data-code="100055"] .hm-tab.on').inner_text() == "全部"
    assert page.locator('.card[data-code="100055"] .cmp-index-line').count() == 1
    page.locator('button[data-v="etf"]').click()
    page.locator('#view-etf .etf-row').first.wait_for(timeout=60000)
    page.locator('button[data-v="home"]').click()
    page.locator('#focusChart .cmp-index-line').wait_for(timeout=60000)
    search = page.locator('#kw')
    search.fill('100055')
    assert page.locator('#list > .card').count() == 1
    assert page.locator('#list > .card').first.get_attribute('data-code') == '100055'
    search.fill('013403')
    page.locator('#results .r-row').first.wait_for(timeout=30000)
    added_code = page.locator('#results .r-row').first.locator('.r-sub').inner_text().split(' · ')[0]
    page.locator('#results .r-row').first.click()
    assert search.input_value() == ''
    assert page.locator('#results').is_hidden()
    assert page.locator(f'#list > .card[data-code="{added_code}"]').count() == 1
    page.wait_for_timeout(1000)
    assert page.locator('#results').is_hidden()
    assert not errors, errors

    mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    mobile_page = mobile.new_page()
    mobile_page.goto(URL, wait_until="domcontentloaded")
    mobile_page.locator("#focusChart .cmp-index-line").wait_for(timeout=60000)
    assert mobile_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    mobile_page.screenshot(path=str(ROOT / "mockups" / "implemented-mobile.png"))
    mobile_page.locator('.card[data-code="100055"] .f-head').click()
    mobile_page.locator('.card[data-code="100055"] .cmp-index-line').wait_for(timeout=60000)
    mobile_page.locator('.card[data-code="100055"] .holdings-panel').wait_for()
    stacked = mobile_page.evaluate("""() => {
      const card = document.querySelector('.card[data-code="100055"]');
      const chart = card.querySelector('.hm-chart-block').getBoundingClientRect();
      const holdings = card.querySelector('.holdings-panel').getBoundingClientRect();
      const secondary = card.querySelector('.hm-secondary').getBoundingClientRect();
      return holdings.y >= chart.bottom && secondary.y >= holdings.bottom;
    }""")
    assert stacked
    visible_rows = mobile_page.locator('.card[data-code="100055"] .holdings-scroll tr:visible')
    assert visible_rows.count() == 6
    mobile_page.locator('.card[data-code="100055"]').evaluate("el => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 8)")
    mobile_page.screenshot(path=str(ROOT / "mockups" / "implemented-fund-detail-mobile.png"))
    mobile_page.locator('.card[data-code="100055"] .holdings-toggle').click()
    assert visible_rows.count() > 6
    assert mobile_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    print("desktop and mobile: passed")
    browser.close()
