#!/usr/bin/env python3
"""Daily Korean stock market analysis automation (news-connected V1.1)."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import smtplib
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import certifi
from dataclasses import dataclass
from email.mime.text import MIMEText
from html import unescape
from pathlib import Path
from statistics import mean
from typing import Dict, List, Tuple

GOOGLE_NEWS_RSS = [
    "https://news.google.com/rss/search?q=한국+증시+코스피+코스닥&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=반도체+전기차+에너지+방산+한국증시&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=미국+금리+달러+유가+중국+경기+한국증시&hl=ko&gl=KR&ceid=KR:ko",
]

KOREAN_FINANCE_RSS = [
    "https://www.yna.co.kr/rss/economy.xml",  # 연합뉴스 경제
    "https://www.yna.co.kr/rss/marketplus.xml",  # 연합뉴스 증권
]

NAVER_FINANCE_NEWS_URL = "https://finance.naver.com/news/mainnews.naver"

STOCK_UNIVERSE = {
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "005380.KS": "현대차",
    "373220.KS": "LG에너지솔루션",
    "207940.KS": "삼성바이오로직스",
    "035420.KS": "NAVER",
    "035720.KS": "카카오",
    "051910.KS": "LG화학",
    "006400.KS": "삼성SDI",
    "009540.KS": "HD한국조선해양",
    "012450.KS": "한화에어로스페이스",
    "009830.KS": "한화솔루션",
    "068270.KS": "셀트리온",
    "105560.KS": "KB금융",
    "055550.KS": "신한지주",
}

TOPIC_STOCK_MAP = {
    "semiconductors": ["005930.KS", "000660.KS"],
    "ev": ["005380.KS", "373220.KS", "006400.KS", "051910.KS"],
    "energy": ["009830.KS", "051910.KS", "373220.KS"],
    "defense": ["012450.KS", "009830.KS"],
    "bio": ["207940.KS", "068270.KS"],
    "platform": ["035420.KS", "035720.KS"],
    "bank": ["105560.KS", "055550.KS"],
    "shipbuilding": ["009540.KS"],
}

KEYWORD_THEMES = {
    "semiconductors": ["반도체", "메모리", "HBM", "파운드리", "AI칩", "chip", "semiconductor"],
    "ev": ["전기차", "EV", "배터리", "2차전지", "충전", "IRA"],
    "energy": ["에너지", "태양광", "풍력", "전력", "원전", "LNG", "유가"],
    "defense": ["방산", "수출", "무기", "미사일", "군수"],
    "bio": ["바이오", "신약", "임상", "FDA", "바이오시밀러"],
    "platform": ["플랫폼", "광고", "커머스", "콘텐츠", "클라우드"],
    "bank": ["은행", "금융", "순이자", "대출", "예대마진"],
    "shipbuilding": ["조선", "선박", "수주", "해운"],
}

POSITIVE_KEYWORDS = ["급등", "상승", "호실적", "수주", "돌파", "성장", "확대", "신고가", "회복", "흑자"]
NEGATIVE_KEYWORDS = ["급락", "하락", "적자", "우려", "악화", "소송", "규제", "둔화", "리스크"]
MACRO_KEYWORDS = ["금리", "인플레이션", "달러", "환율", "유가", "중국", "미국", "관세"]

SPECIAL_TRACKING = {"005930.KS": "삼성전자", "009830.KS": "한화솔루션", "005380.KS": "현대차"}


@dataclass
class NewsItem:
    source: str
    title: str
    summary: str
    link: str
    published: str


@dataclass
class PriceSeries:
    closes: List[float]
    volumes: List[float]


@dataclass
class StockSignal:
    ticker: str
    name: str
    score_short: float
    score_long: float
    momentum_20d: float
    volume_ratio: float
    sentiment: float
    risk: str
    reasons: List[str]


@dataclass
class RuntimeConfig:
    telegram_bot_token: str
    telegram_chat_id: str
    enable_email: bool
    force_demo_mode: bool


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_dotenv(dotenv_path: str = ".env") -> None:
    """Minimal .env loader (no third-party dependency)."""
    path = Path(dotenv_path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        os.environ.setdefault(key, value)


def load_config() -> RuntimeConfig:
    load_dotenv()
    return RuntimeConfig(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        enable_email=parse_bool(os.getenv("ENABLE_EMAIL"), default=False),
        force_demo_mode=parse_bool(os.getenv("DEMO_MODE"), default=False),
    )


def http_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        return resp.read()


def decode_best_effort(data: bytes) -> str:
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def fetch_rss_news(urls: List[str], source: str, max_items_per_feed: int = 30) -> List[NewsItem]:
    items: List[NewsItem] = []
    for url in urls:
        try:
            xml_bytes = http_get(url)
            root = ET.fromstring(xml_bytes)
            for item in root.findall(".//item")[:max_items_per_feed]:
                title = strip_html(item.findtext("title") or "")
                summary = strip_html(item.findtext("description") or item.findtext("content:encoded") or "")
                link = (item.findtext("link") or "").strip()
                published = (item.findtext("pubDate") or "").strip()
                if title:
                    items.append(NewsItem(source=source, title=title, summary=summary, link=link, published=published))
        except Exception:
            continue
    return items


def fetch_naver_finance_news(max_items: int = 30) -> List[NewsItem]:
    """Parse Naver Finance main news list (title + summary)."""
    try:
        html = decode_best_effort(http_get(NAVER_FINANCE_NEWS_URL))
    except Exception:
        return []

    results: List[NewsItem] = []
    # Naver list rows usually include articleSubject/articleSummary blocks.
    pattern = re.compile(
        r"<dd class=\"articleSubject\">\s*<a href=\"(?P<link>[^\"]+)\"[^>]*>(?P<title>.*?)</a>.*?"
        r"<dd class=\"articleSummary\">(?P<summary>.*?)"
        r"(?:<span class=\"wdate\">(?P<date>.*?)</span>)?",
        re.S,
    )

    for m in pattern.finditer(html):
        raw_title = strip_html(m.group("title"))
        raw_summary = strip_html(m.group("summary"))
        raw_date = strip_html(m.group("date") or "")
        raw_link = m.group("link")

        if not raw_title:
            continue

        if raw_link.startswith("/"):
            raw_link = "https://finance.naver.com" + raw_link

        results.append(
            NewsItem(
                source="Naver Finance",
                title=raw_title,
                summary=raw_summary,
                link=raw_link,
                published=raw_date,
            )
        )
        if len(results) >= max_items:
            break

    return results


def fetch_news(min_items: int = 10) -> List[NewsItem]:
    """Collect real Korean financial news from multiple sources."""
    news: List[NewsItem] = []
    news.extend(fetch_rss_news(KOREAN_FINANCE_RSS, source="Korean Finance RSS", max_items_per_feed=40))
    news.extend(fetch_rss_news(GOOGLE_NEWS_RSS, source="Google News KR", max_items_per_feed=40))
    news.extend(fetch_naver_finance_news(max_items=40))

    # dedupe by title (normalized)
    deduped, seen = [], set()
    for n in news:
        key = re.sub(r"\s+", " ", n.title.strip().lower())
        if key and key not in seen:
            deduped.append(n)
            seen.add(key)

    # prioritize recent-ish and non-empty summary/title items
    deduped = [n for n in deduped if n.title]

    # hard floor requirement: return at least 10 when possible from fetched corpus
    if len(deduped) >= min_items:
        return deduped[: max(30, min_items)]
    return deduped


def sample_news_items() -> List[NewsItem]:
    """Demo sample used when live news access is unavailable."""
    base_date = dt.datetime.now().strftime("%Y-%m-%d")
    samples = [
        ("Google News KR", "반도체 업황 회복 기대감…메모리 가격 반등 신호", "반도체", "https://example.com/news1"),
        ("Korean Finance RSS", "전기차 배터리 공급망 재편, 국내 소재주 관심", "전기차 배터리", "https://example.com/news2"),
        ("Naver Finance", "국제유가 변동성 확대…에너지 관련주 등락", "에너지 유가", "https://example.com/news3"),
        ("Google News KR", "미국 금리 동결 가능성 부각, 외국인 수급 주목", "금리 달러 환율", "https://example.com/news4"),
        ("Korean Finance RSS", "방산 수출 기대감에 관련 대형주 강세", "방산 수출", "https://example.com/news5"),
        ("Naver Finance", "국내 조선업 수주잔고 증가, 실적 개선 기대", "조선 수주", "https://example.com/news6"),
        ("Google News KR", "바이오 업종 임상 결과 발표 앞두고 변동성 확대", "바이오 임상", "https://example.com/news7"),
        ("Korean Finance RSS", "플랫폼 기업 광고 회복 기대감 확산", "플랫폼 광고", "https://example.com/news8"),
        ("Naver Finance", "은행주 배당 매력 부각…금융주 재평가", "은행 금융", "https://example.com/news9"),
        ("Google News KR", "자동차 수출 호조세 지속, 환율 영향 점검", "자동차 전기차", "https://example.com/news10"),
    ]
    return [
        NewsItem(source=s, title=t, summary=summary, link=link, published=base_date)
        for s, t, summary, link in samples
    ]


def extract_theme_hits(text: str) -> List[str]:
    hits = []
    low = text.lower()
    for theme, kws in KEYWORD_THEMES.items():
        if any((kw.lower() in low) for kw in kws):
            hits.append(theme)
    return hits


def build_theme_news_map(news: List[NewsItem]) -> Tuple[Dict[str, int], Dict[str, List[NewsItem]]]:
    count: Dict[str, int] = {k: 0 for k in KEYWORD_THEMES}
    mapped: Dict[str, List[NewsItem]] = {k: [] for k in KEYWORD_THEMES}
    for n in news:
        text = f"{n.title} {n.summary}"
        for theme in extract_theme_hits(text):
            count[theme] += 1
            mapped[theme].append(n)
    return count, mapped


def sentiment_score(text: str) -> float:
    pos = sum(1 for k in POSITIVE_KEYWORDS if k in text)
    neg = sum(1 for k in NEGATIVE_KEYWORDS if k in text)
    return float(pos - neg)


def fetch_price_series(ticker: str, range_days: int = 120) -> PriceSeries | None:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
        f"?range={range_days}d&interval=1d"
    )
    try:
        data = json.loads(http_get(url))
        result = data["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        closes = [float(x) for x in quote.get("close", []) if x is not None]
        volumes = [float(x) for x in quote.get("volume", []) if x is not None]
        if len(closes) < 25 or len(volumes) < 25:
            return None
        return PriceSeries(closes=closes, volumes=volumes)
    except Exception:
        return None


def score_stocks(news: List[NewsItem], prices: Dict[str, PriceSeries]) -> List[StockSignal]:
    theme_count, _ = build_theme_news_map(news)
    ticker_sentiment: Dict[str, float] = {t: 0.0 for t in STOCK_UNIVERSE}
    ticker_reasons: Dict[str, List[str]] = {t: [] for t in STOCK_UNIVERSE}

    for n in news:
        text = f"{n.title} {n.summary}"
        s = sentiment_score(text)
        themes = extract_theme_hits(text)
        for theme in themes:
            for t in TOPIC_STOCK_MAP.get(theme, []):
                ticker_sentiment[t] += s + 0.4
                ticker_reasons[t].append(f"{theme} 관련 뉴스")

    signals: List[StockSignal] = []
    for ticker, name in STOCK_UNIVERSE.items():
        series = prices.get(ticker)
        if not series:
            continue

        closes, volumes = series.closes, series.volumes
        momentum_20d = (closes[-1] / closes[-20] - 1) * 100
        avg20_vol = mean(volumes[-20:]) if volumes[-20:] else 1
        volume_ratio = volumes[-1] / max(avg20_vol, 1)
        sent = ticker_sentiment.get(ticker, 0.0)

        score_short = (momentum_20d * 0.35) + ((volume_ratio - 1) * 20 * 0.35) + (sent * 0.30)
        ma20 = mean(closes[-20:])
        ma60 = mean(closes[-60:]) if len(closes) >= 60 else mean(closes[:-1])
        trend = (ma20 / ma60 - 1) * 100 if ma60 else 0

        theme_boost = 0.0
        for theme, tickers in TOPIC_STOCK_MAP.items():
            if ticker in tickers:
                theme_boost += theme_count.get(theme, 0) * 0.1

        score_long = (trend * 0.6) + (momentum_20d * 0.2) + (sent * 0.15) + theme_boost

        risks = []
        if volume_ratio > 2.5:
            risks.append("단기 과열 가능성")
        if momentum_20d < -8:
            risks.append("추세 약화")
        if sent < -2:
            risks.append("부정 뉴스 노출")
        risk = ", ".join(risks) if risks else "중립"

        reasons = list(dict.fromkeys(ticker_reasons.get(ticker, [])))[:3]
        if momentum_20d > 5:
            reasons.append("20일 모멘텀 우위")
        if volume_ratio > 1.5:
            reasons.append("거래량 증가")

        signals.append(
            StockSignal(
                ticker=ticker,
                name=name,
                score_short=score_short,
                score_long=score_long,
                momentum_20d=momentum_20d,
                volume_ratio=volume_ratio,
                sentiment=sent,
                risk=risk,
                reasons=reasons[:3],
            )
        )

    return signals


def pick_sector_leaders(signals: List[StockSignal], theme_count: Dict[str, int]) -> List[Tuple[str, str, str]]:
    leaders = []
    for theme, tickers in TOPIC_STOCK_MAP.items():
        candidates = [s for s in signals if s.ticker in tickers]
        if not candidates:
            continue
        leader = sorted(candidates, key=lambda x: (x.score_short + x.score_long), reverse=True)[0]
        support = f"모멘텀 {leader.momentum_20d:.1f}%, 거래량배수 {leader.volume_ratio:.2f}, 뉴스빈도 {theme_count.get(theme, 0)}"
        leaders.append((theme_count.get(theme, 0), (theme, leader.name, support)))
    return [x[1] for x in sorted(leaders, key=lambda y: y[0], reverse=True)[:5]]


def macro_summary(news: List[NewsItem]) -> str:
    macro_news = [n.title for n in news if any(k in f"{n.title} {n.summary}" for k in MACRO_KEYWORDS)]
    if macro_news:
        return " / ".join(macro_news[:3])

    fallback = [n.title for n in news[:3]]
    if fallback:
        return " / ".join(fallback)
    return "주요 뉴스 데이터가 제한적입니다. 외부 네트워크/소스 상태를 점검하세요."


def format_report(
    news: List[NewsItem],
    signals: List[StockSignal],
    theme_count: Dict[str, int],
    fetch_status: str,
) -> str:
    today = dt.datetime.now().strftime("%Y-%m-%d")
    short_candidates = sorted(signals, key=lambda x: x.score_short, reverse=True)[:5]
    long_candidates = sorted(signals, key=lambda x: x.score_long, reverse=True)[:5]
    sell_watch = [
        s
        for s in signals
        if (s.momentum_20d < -5 and s.volume_ratio > 1.3)
        or (s.sentiment < -2)
        or (s.volume_ratio > 3 and s.momentum_20d > 15)
    ]
    sell_watch = sorted(sell_watch, key=lambda x: x.momentum_20d)[:5]

    sector_leaders = pick_sector_leaders(signals, theme_count)

    lines = [f"[{today}]", "", "1. Market Summary"]
    lines.append(f"- 실뉴스 기준 핵심 이슈: {macro_summary(news)}")
    if fetch_status == "fallback":
        lines.append("- 안내: 외부 뉴스 소스 접근에 실패해 데모 뉴스로 리포트를 생성했습니다. (네트워크/방화벽 설정 점검 권장)")
    elif fetch_status == "failed":
        lines.append("- 안내: 외부 뉴스 소스 접근이 실패해 뉴스 기반 분석이 제한되었습니다. 인터넷 연결/프록시 설정을 확인하세요.")
    lines.append(f"- 수집 뉴스 수: {len(news)}건 (Google News KR + Korean RSS + Naver Finance)")
    lines.append("- 전반 코멘트: 뉴스/키워드/수급 기반 참고 리포트이며 절대적 매수·매도 판단은 아닙니다.")

    lines.extend(["", "2. Short-term Trading Candidates"])
    for s in short_candidates:
        reason = "; ".join(s.reasons) if s.reasons else "뉴스/키워드 신호 중립"
        lines.append(f"- {s.name} / {reason} / 리스크: {s.risk}")

    lines.extend(["", "3. Long-term Investment Candidates"])
    for s in long_candidates:
        thesis = f"추세+테마뉴스 반영, 20일 수익률 {s.momentum_20d:.1f}%"
        lines.append(f"- {s.name} / {thesis} / 리스크: {s.risk}")

    lines.extend(["", "4. Sector Leaders"])
    for sector, leader, support in sector_leaders:
        lines.append(f"- {sector} / {leader} / 근거: {support}")

    lines.extend(["", "5. Sell Watchlist"])
    if sell_watch:
        for s in sell_watch:
            reasons = []
            if s.momentum_20d < -5 and s.volume_ratio > 1.3:
                reasons.append("거래량 동반 하락")
            if s.sentiment < -2:
                reasons.append("부정 뉴스")
            if s.volume_ratio > 3 and s.momentum_20d > 15:
                reasons.append("과열 구간")
            lines.append(f"- {s.name} / {', '.join(reasons)}")
    else:
        lines.append("- 해당 조건 충족 종목 제한적")

    lines.extend(["", "6. Key Notes (Samsung Electronics, Hanwha Solutions, Hyundai Motor)"])
    for t, name in SPECIAL_TRACKING.items():
        s = next((x for x in signals if x.ticker == t), None)
        if s:
            lines.append(f"- {name}: 20일 모멘텀 {s.momentum_20d:.1f}%, 거래량배수 {s.volume_ratio:.2f}, 리스크 {s.risk}")
        else:
            lines.append(f"- {name}: 데이터 수집 실패(재시도 필요)")

    lines.extend(["", "[참고 뉴스 Top 10]"])
    for n in news[:10]:
        summary = n.summary[:120] + ("..." if len(n.summary) > 120 else "")
        lines.append(f"- ({n.source}) {n.title} / {summary}")

    return "\n".join(lines)


def save_report(report_text: str, out_dir: str = "reports") -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    date_str = dt.datetime.now().strftime("%Y%m%d")
    out_file = Path(out_dir) / f"korea_stock_report_{date_str}.md"
    out_file.write_text(report_text, encoding="utf-8")
    return out_file


def send_telegram(report_text: str, cfg: RuntimeConfig) -> Tuple[bool, str]:
    token, chat_id = cfg.telegram_bot_token, cfg.telegram_chat_id
    if not token or not chat_id:
        return False, "Telegram 전송 실패: TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": report_text[:3800]}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(req, timeout=20, context=ssl_ctx) as resp:
            ok = 200 <= resp.status < 300
            return ok, ("Telegram 전송 성공" if ok else f"Telegram 전송 실패: HTTP {resp.status}")
    except Exception as exc:
        return False, f"Telegram 전송 실패: {exc}"


def send_email(subject: str, report_text: str, cfg: RuntimeConfig) -> bool:
    if not cfg.enable_email:
        return False
    sender = os.getenv("EMAIL_SENDER")
    recipient = os.getenv("EMAIL_RECIPIENT")
    password = os.getenv("EMAIL_APP_PASSWORD")
    smtp_server = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    if not sender or not recipient or not password:
        return False

    msg = MIMEText(report_text, _charset="utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, recipient
    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        return True
    except Exception:
        return False


def run_pipeline() -> Path:
    cfg = load_config()
    fetch_status = "live"
    news = [] if cfg.force_demo_mode else fetch_news(min_items=10)
    if cfg.force_demo_mode:
        fetch_status = "fallback"
        news = sample_news_items()
    elif len(news) == 0:
        # fallback for restricted environments
        fetch_status = "fallback"
        news = sample_news_items()

    theme_count, _ = build_theme_news_map(news)
    prices = {t: p for t in STOCK_UNIVERSE if (p := fetch_price_series(t)) is not None}
    signals = score_stocks(news, prices)

    report = format_report(news, signals, theme_count, fetch_status=fetch_status)
    out = save_report(report)

    subject = f"[KR Stock AI] Daily Report {dt.datetime.now().strftime('%Y-%m-%d')}"
    tg_ok, tg_msg = send_telegram(report, cfg)
    em_ok = send_email(subject, report, cfg)

    print(f"Report saved: {out}")
    print(f"News collected: {len(news)}")
    print(f"News mode: {fetch_status}")
    print(f"Signals generated: {len(signals)}")
    print(f"Theme hits: {theme_count}")
    print(f"Telegram sent: {tg_ok} ({tg_msg})")
    print(f"Email sent: {em_ok}")
    return out


if __name__ == "__main__":
    run_pipeline()
