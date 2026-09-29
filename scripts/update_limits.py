"""Refresh confidently parsed fund purchase limits from public fund notices."""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app.js"
OUTPUT = ROOT / "limits.json"
TODAY = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
HEADERS = {"Referer": "https://fundf10.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
NOTICE_LIST = "https://api.fund.eastmoney.com/f10/JJGG"
NOTICE_CONTENT = "https://np-cnotice-fund.eastmoney.com/api/content/ann"
RELEVANT = re.compile(r"申购")
CHANGE = re.compile(r"限制|调整|暂停|恢复|开放|大额")
EXCLUDE = re.compile(r"休市|节假日|假期|费率|代销")
AMOUNT = re.compile(r"限制申购金额\s*[（(]单位\s*[:：]?\s*人民币元[）)]\s*([\d,.]+)")
GROUP = re.compile(r"下属分级基金的限制申购金额[^\r\n]*")
EFFECTIVE = re.compile(r"(?:暂停大额申购|限制大额申购|调整大额申购)起始日\s*(\d{4})年(\d{1,2})月(\d{1,2})日")
# Reviewed notices with tables that wrap the currency/unit label across lines.
# Match the exact announcement ID, so a later announcement is never overridden.
REVIEWED = {
    "AN202609241829834303": {"amount": 10000.0, "effectiveDate": "2026-09-28", "classes": ["100055", "022184", "026228"], "scope": "各份额分开计算"},
    "AN202609231829773864": {"amount": 5.0, "effectiveDate": "2026-09-24", "classes": ["040046", "014978"]},
}


def defaults() -> list[dict]:
    funds = []
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*\{ code:'(\d{6})'.*?limitClasses:\[(.*?)\]\s*\},?\s*$", line)
        if not match:
            continue
        classes = re.findall(r"code:'(\d{6})'", match[2])
        baseline = re.search(r"scopeDate:'(\d{4}-\d{2}-\d{2})'", line)
        funds.append({"code": match[1], "classes": classes or [match[1]], "baseline": baseline[1] if baseline else ""})
    if len(funds) < 100:
        raise RuntimeError(f"Only {len(funds)} funds parsed; refusing an incomplete snapshot")
    return funds


def parse_amount(content: str, class_count: int) -> tuple[float, str] | None:
    match = AMOUNT.search(content)
    if not match:
        return None
    amount = float(match[1].replace(",", ""))
    if not 0 < amount < 100_000_000:
        return None
    if class_count > 1:
        group = GROUP.search(content)
        if not group:
            return None
        tail = group[0].split("）")[-1].split(")")[-1]
        values = [float(value.replace(",", "")) for value in re.findall(r"\d[\d,]*(?:\.\d+)?", tail)]
        if len(values) < class_count or any(value != amount for value in values[:class_count]):
            return None
    effective = EFFECTIVE.search(content)
    date = ""
    if effective:
        date = f"{effective[1]}-{int(effective[2]):02d}-{int(effective[3]):02d}"
    return amount, date


def get_json(session: requests.Session, url: str, params: dict) -> dict:
    response = session.get(url, params=params, timeout=20, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected fund response")
    return data


def fetch_one(session: requests.Session, fund: dict) -> tuple[dict | None, dict | None]:
    payload = get_json(session, NOTICE_LIST, {"fundcode": fund["code"], "pageIndex": 1, "pageSize": 30, "type": 5})
    rows = payload.get("Data")
    if not isinstance(rows, list):
        raise ValueError("Notice list unavailable")
    hit = next((row for row in rows if RELEVANT.search(row.get("TITLE", "")) and CHANGE.search(row.get("TITLE", "")) and not EXCLUDE.search(row.get("TITLE", ""))), None)
    if not hit or hit.get("PUBLISHDATEDesc", "") < fund["baseline"]:
        return None, None
    result = get_json(session, NOTICE_CONTENT, {"client_source": "web_fund", "show_all": 1, "art_code": hit["ID"]})
    data = result.get("data") or {}
    parsed = parse_amount(data.get("notice_content", ""), len(fund["classes"]))
    reviewed = REVIEWED.get(hit["ID"])
    if reviewed and reviewed["classes"] == fund["classes"]:
        parsed = reviewed["amount"], reviewed["effectiveDate"]
    source_url = data.get("attach_url_web") or data.get("attach_url") or ""
    if not source_url.startswith("https://pdf.dfcfw.com/"):
        source_url = ""
    base = {"date": hit["PUBLISHDATEDesc"], "title": hit.get("TITLE", ""), "url": source_url}
    if not parsed:
        return None, base
    amount, effective_date = parsed
    if effective_date and effective_date > TODAY:
        return None, base
    entry = {**base, "amount": amount, "effectiveDate": effective_date, "classes": fund["classes"]}
    if reviewed and reviewed.get("scope"):
        entry["scope"] = reviewed["scope"]
    return entry, None


def main() -> int:
    funds = defaults()
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])))
    existing = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    limits, unverified = {}, {}
    errors = []
    for index, fund in enumerate(funds, 1):
        code = fund["code"]
        try:
            verified, uncertain = fetch_one(session, fund)
            if verified:
                limits[code] = verified
            elif uncertain:
                unverified[code] = uncertain
        except Exception as exc:
            errors.append(code)
            if code in existing.get("limits", {}):
                limits[code] = existing["limits"][code]
            elif code in existing.get("unverified", {}):
                unverified[code] = existing["unverified"][code]
            print(f"{code}: {exc}", file=sys.stderr)
        if index < len(funds):
            time.sleep(0.15)
    if len(errors) > len(funds) // 4:
        raise RuntimeError(f"{len(errors)} source requests failed; refusing to publish a partial snapshot")
    output = {"checkedAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"), "limits": limits, "unverified": unverified}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Checked {len(funds)} funds: {len(limits)} verified limits, {len(unverified)} needs review, {len(errors)} request errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
