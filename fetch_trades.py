#!/usr/bin/env python3
"""압구정동 아파트 실거래가를 국토부 공공데이터 API에서 받아 data.json으로 저장.

사용법
  python fetch_trades.py              # 최근 4개월 갱신 (매일 자동 실행용)
  python fetch_trades.py --backfill   # 2006-01부터 전체 수집 (최초 1회)

환경변수 MOLIT_KEY 에 공공데이터포털 인증키(일반 인증키)를 넣어야 합니다.
"""
import os, sys, re, json, time, datetime as dt
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data.json"
CONF = ROOT / "zones.json"
KST = dt.timezone(dt.timedelta(hours=9))
URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
LAWD = "11680"  # 강남구


def get_key():
    k = os.environ.get("MOLIT_KEY", "").strip()
    if not k:
        sys.exit("환경변수 MOLIT_KEY 가 없습니다.")
    return urllib.parse.unquote(k)  # 인코딩된 키를 붙여넣어도 이중 인코딩되지 않게


def fetch_month(key, ym):
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({
            "serviceKey": key, "LAWD_CD": LAWD, "DEAL_YMD": ym,
            "numOfRows": 1000, "pageNo": page})
        root = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(URL + "?" + q, timeout=30) as r:
                    root = ET.fromstring(r.read())
                break
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(3)
        code = root.findtext(".//resultCode")
        if code in ("03", "003"):  # No Data: 거래 없는 달
            break
        if code not in ("00", "000"):
            sys.exit(f"API 오류 {ym}: {code} {root.findtext('.//resultMsg')}")
        for it in root.findall(".//item"):
            out.append({c.tag: (c.text or "").strip() for c in it})
        total = int(root.findtext(".//totalCount") or 0)
        if page * 1000 >= total:
            break
        page += 1
    return out


def norm(s):
    return re.sub(r"[\s·ㆍ∙]", "", s)


def classify(apt, conf):
    """단지명 -> (구역, 표시이름). 못 찾으면 (None, 원래이름)."""
    n = norm(apt)
    for raw, v in conf.get("overrides", {}).items():
        if norm(raw) == n:
            return v["zone"], v["label"]
    for k in conf.get("keywords", []):
        if k["kw"] in n:
            return k["zone"], k["label"]
    m = re.match(r"^(현대|한양|미성)\(?(\d+(?:[,.]\d+)*)", n)
    if m and m.group(1) in conf.get("families", {}):
        fam, nums = m.group(1), re.split(r"[,.]", m.group(2))
        zone = conf["families"][fam].get(nums[0])
        return zone, f"{fam} {'·'.join(nums)}차"
    return None, apt


def to_trade(it, conf):
    if "압구정" not in it.get("umdNm", ""):
        return None
    try:
        price = int(it["dealAmount"].replace(",", ""))
        area = float(it["excluUseAr"])
        date = dt.date(int(it["dealYear"]), int(it["dealMonth"]), int(it["dealDay"])).isoformat()
    except (KeyError, ValueError):
        return None
    zone, label = classify(it.get("aptNm", ""), conf)
    pm = conf.get("pyeong", {}).get(label, {}).get(str(round(area)))
    est = pm is None
    py = pm if pm else round(area / conf.get("supply_ratio", 0.75) / 3.3058)
    floor = int(it["floor"]) if it.get("floor", "").lstrip("-").isdigit() else None
    dong = it.get("aptDong", "").replace("동", "").strip() or None
    tid = f"{it['aptNm']}|{dong}|{area}|{floor}|{date}|{price}"
    return {
        "id": tid, "apt": it["aptNm"], "label": label, "zone": zone,
        "py": py, "py_est": est, "area": area, "floor": floor, "dong": dong,
        "price": price, "date": date, "first_seen": None, "high": False,
        "build": it.get("buildYear") or None,
        "buyer": it.get("buyerGbn") or None, "seller": it.get("slerGbn") or None,
        "dealing": it.get("dealingGbn") or None, "rgst": it.get("rgstDate") or None,
        "cancel": it.get("cdealType", "") == "O",
    }


def months(backfill):
    today = dt.datetime.now(KST).date()
    start = dt.date(2006, 1, 1) if backfill else (today.replace(day=1) - dt.timedelta(days=90)).replace(day=1)
    d = start
    while d <= today:
        yield d.strftime("%Y%m")
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def main():
    backfill = "--backfill" in sys.argv
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    key = get_key()
    old = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    had_data = bool(old.get("trades")) and not old.get("sample")
    trades = {t["id"]: t for t in old.get("trades", [])} if had_data else {}
    today = dt.datetime.now(KST).date().isoformat()

    for ym in months(backfill):
        for it in fetch_month(key, ym):
            t = to_trade(it, conf)
            if not t:
                continue
            cancel = t.pop("cancel")
            if cancel:
                trades.pop(t["id"], None)
                continue
            if t["id"] in trades:
                t["first_seen"] = trades[t["id"]].get("first_seen")
            elif had_data and not backfill:
                t["first_seen"] = today  # 이번에 처음 보인 거래 = 새로 뜬 거래
            trades[t["id"]] = t
        time.sleep(0.2)

    # 신고가: 같은 단지·평형에서 이전 계약 최고가를 넘으면 표시
    rows = sorted(trades.values(), key=lambda t: t["date"])
    best = {}
    for t in rows:
        g = (t["label"], t["py"])
        t["high"] = g in best and t["price"] > best[g]
        best[g] = max(best.get(g, 0), t["price"])

    rows.sort(key=lambda t: (t["date"], t["price"]), reverse=True)
    DATA.write_text(json.dumps({
        "updated": dt.datetime.now(KST).isoformat(timespec="minutes"),
        "count": len(rows), "trades": rows}, ensure_ascii=False), encoding="utf-8")

    miss = {}
    for t in rows:
        if t["zone"] is None:
            miss[t["apt"]] = miss.get(t["apt"], 0) + 1
    print(f"저장 {len(rows)}건")
    if miss:
        print("\n[구역 미지정 단지] zones.json 의 overrides 에 추가하세요:")
        for n, c in sorted(miss.items(), key=lambda x: -x[1]):
            print(f"  {n}  ({c}건)")


if __name__ == "__main__":
    main()
