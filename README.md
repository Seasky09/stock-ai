# stock-ai

한국 주식(코스피/코스닥) 데일리 리포트 자동화 시스템입니다.

## 기능 (V1.1)
- **실제 한국 금융 뉴스 수집**
  - 연합뉴스 RSS(경제/증권)
  - Google News Korea RSS
  - Naver Finance 메인 뉴스
- 제목/요약 추출 및 테마 키워드 분류
  - 예: semiconductors, EV, energy, defense, bio
- 가격 모멘텀/거래량/뉴스 감성 점수 기반 룰 스코어링
- 일일 리포트 생성 (Markdown)
- Telegram 또는 Email 전송 (선택)

## 분석 출력 포맷
리포트는 아래 구조로 생성됩니다.
1. Market Summary (실뉴스 기반)
2. Short-term Trading Candidates (뉴스+키워드+모멘텀)
3. Long-term Investment Candidates
4. Sector Leaders
5. Sell Watchlist
6. Key Notes (삼성전자, 한화솔루션, 현대차)
7. 참고 뉴스 Top 10

## 빠른 시작
```bash
python -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

`.env` 파일을 채운 뒤 실행:
```bash
set -a; source .env; set +a
python daily_korea_stock_report.py
```

생성 결과:
- `reports/korea_stock_report_YYYYMMDD.md`

## 설정(.env)
아래 항목만 먼저 설정하면 됩니다.
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ENABLE_EMAIL=true/false`

Telegram 전송 동작:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 둘 다 입력되어 있으면 리포트 생성 직후 Telegram 전송을 시도합니다.
- 둘 중 하나라도 비어 있으면 콘솔에 명확한 오류 메시지를 출력합니다.

추가 옵션:
- `DEMO_MODE=true` 로 두면 실뉴스 접근이 안 되는 환경에서도 샘플 뉴스(10건)로 리포트를 생성합니다.

## 외부 뉴스 접근 실패 시 동작
- 실뉴스 수집이 실패하면 자동으로 **샘플/데모 모드**로 전환해 리포트를 생성합니다.
- 리포트 Market Summary에 안내 문구가 함께 표시됩니다.
- 즉, 네트워크가 제한된 환경에서도 리포트 형태를 바로 확인할 수 있습니다.

## Windows 초보자용 실행 가이드
1. **Python 설치**
   - 브라우저에서 `python.org` 접속 → Windows용 Python 3 다운로드/설치.
   - 설치 시 **Add Python to PATH** 체크.
2. **프로젝트 폴더 열기**
   - 탐색기에서 프로젝트 폴더(`stock-ai`) 위치 확인.
3. **터미널 열기**
   - 폴더 빈 공간에서 Shift+마우스 우클릭 → “터미널 열기”(또는 PowerShell 열기).
4. **(선택) 가상환경 만들기**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
5. **환경 파일 만들기**
   ```powershell
   copy .env.example .env
   ```
   - 메모장으로 `.env`를 열어 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 입력.
6. **실행**
   ```powershell
   python daily_korea_stock_report.py
   ```
7. **결과 확인**
   - `reports\korea_stock_report_YYYYMMDD.md` 파일 열기.

## 자동 실행 (매일 아침 08:00 UTC 예시)
```bash
crontab -e
```
추가:
```cron
0 8 * * * cd /workspace/stock-ai && /usr/bin/bash -lc 'set -a; source .env; set +a; /usr/bin/python3 daily_korea_stock_report.py >> logs/daily.log 2>&1'
```

## 개선 아이디어 (다음 단계)
- 뉴스 본문 요약 강화 (기사 링크 본문 파싱)
- 테마-종목 매핑 고도화 (기업명 NER)
- 밸류에이션 지표(PER/PBR/FCF) 및 재무지표 추가
- 백테스트로 룰 가중치 튜닝
- HTML 리포트 + 차트 시각화
