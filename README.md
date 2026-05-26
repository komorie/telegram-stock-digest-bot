# 텔레그램 주식 소식 다이제스트 봇 v2

> 이 프로젝트는 Codex 바이브코딩 100%로 만든 v2 구현입니다.

로컬 Windows PC에서 텔레그램 채널/그룹 메시지를 수집하고, 주식/리서치 소식을 한국어 다이제스트로 정리해 텔레그램 봇으로 발송합니다.

## 사용법 요약

### 1. 준비물

- Python 3.11 이상
- Telegram API ID / API Hash: https://my.telegram.org 에서 발급
- BotFather 봇 토큰: 텔레그램 `@BotFather`에서 생성
- 결과를 받을 내 Telegram `chat_id`
- Gemini/OpenAI/Groq/OpenRouter 등 OpenAI 호환 LLM API 키, 선택 사항

### 2. 설치

PowerShell에서 프로젝트 폴더로 이동합니다.

```powershell
cd C:\Projects\Telegram
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

PowerShell 실행 정책 때문에 `Activate.ps1`이 막히는 경우가 있어서, 가상환경을 활성화하지 않고 `.venv` 안의 Python을 직접 실행하는 방식을 기본으로 씁니다.

### 3. 설정

예시 설정을 실제 설정으로 복사합니다.

```powershell
Copy-Item config.example.toml config.toml
notepad config.toml
```

주요 설정:

- `sources`: 수집할 텔레그램 채널/그룹 username 또는 링크
- `[telegram]`: Telethon 사용자 세션용 `api_id`, `api_hash`
- `[bot]`: 결과 발송용 BotFather 봇 `token`, 받을 `chat_id`
- `[llm]`: LLM 사용 여부와 모델 설정
- `[[portfolio.holdings]]`: 추적할 종목, 별칭, 관련 키워드
- `daily_digest_hour`: `catch-up` 명령이 하루를 끊는 기준 시각. 기본값 `11`
- `catch_up_max_days`: PC가 꺼져 있던 기간을 한 번에 따라잡을 최대 일수

`config.toml`, `.env`, `data/*.session`, `data/*.sqlite3`는 비밀/로컬 파일이라 git에 올리지 않습니다.

### 4. 첫 로그인 및 수집

처음 한 번은 텔레그램 계정 인증이 필요합니다.

```powershell
.\.venv\Scripts\python.exe -m tg_portfolio_bot collect --config config.toml
```

전화번호, 인증코드, 2FA 비밀번호를 물을 수 있습니다. 성공하면 `data/telegram.session`이 생기고 이후 재사용됩니다.

### 5. 실행

수집 + 요약을 화면에만 출력:

```powershell
.\.venv\Scripts\python.exe -m tg_portfolio_bot run --config config.toml --dry-run
```

수집 + 요약 + 텔레그램 발송:

```powershell
.\.venv\Scripts\python.exe -m tg_portfolio_bot run --config config.toml
```

수집만:

```powershell
.\.venv\Scripts\python.exe -m tg_portfolio_bot collect --config config.toml
```

이미 저장된 DB만 가지고 요약:

```powershell
.\.venv\Scripts\python.exe -m tg_portfolio_bot digest --config config.toml
```

특정 날짜 기준:

```powershell
.\.venv\Scripts\python.exe -m tg_portfolio_bot run --config config.toml --date 2026-05-03 --dry-run
```

마지막 발송 이후 누락된 daily digest를 처리:

```powershell
.\.venv\Scripts\python.exe -m tg_portfolio_bot catch-up --config config.toml
```

테스트 출력만 보고 발송하지 않기:

```powershell
.\.venv\Scripts\python.exe -m tg_portfolio_bot catch-up --config config.toml --dry-run
```

`catch-up`은 마지막으로 성공 발송한 daily 기간을 DB에 기록합니다. PC가 며칠 꺼져 있었다면 다음 실행 때 누락된 기간을 `전날 11:00 ~ 오늘 10:59` 단위로 나눠 순서대로 발송합니다. 기록이 전혀 없는 첫 실행에서는 최신 완료 구간 1개만 처리합니다.

`catch-up`의 기준 시각은 `daily_digest_hour = 11`입니다. 다만 실제 실행 시각이 11:00보다 늦어질 수 있으므로, v2는 고정된 날짜만 보지 않고 "마지막 발송 종료 시각 → 현재 실행 시각"을 기준으로 처리합니다.

동작 정책:

- 11:00 이전에 실행했고, 마지막 발송 이후 아직 새 11:00 경계가 지나지 않았다면 발송하지 않습니다.
- 11:00 정규 실행을 놓쳤지만 하루만 늦었다면, 마지막 발송 종료 시각부터 현재 실행 시각까지 한 덩어리로 보냅니다.
- PC를 모레 이후에 켜는 식으로 11:00 경계가 2개 이상 밀렸다면, 오래된 구간부터 나눠서 여러 개의 다이제스트를 보냅니다.
- 쌓인 구간이 2개로 계산되면 텔레그램 발송도 2번 일어납니다.

예시:

```text
5월 26일 23:20 첫 실행
→ 5월 25일 11:00 ~ 5월 26일 23:20

그다음 5월 27일 10:59 실행
→ 아직 11:00 경계 전이므로 발송 없음

그다음 5월 27일 14:00 실행
→ 5월 26일 23:20 ~ 5월 27일 14:00

5월 26일 23:20 이후 PC를 끄고 5월 28일 14:00에 실행
→ 5월 26일 23:20 ~ 5월 27일 10:59
→ 5월 27일 11:00 ~ 5월 28일 14:00
```

### 6. LLM 설정

Gemini OpenAI 호환 엔드포인트 예시:

```toml
[llm]
enabled = true
api_key = "YOUR_API_KEY"
base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
model = "gemini-2.5-flash"
temperature = 0.2
timeout_sec = 180
max_messages = 40
max_chars_per_message = 400
```

LLM이 켜져 있으면 주요 뉴스와 포트폴리오 섹션을 LLM이 함께 요약합니다. LLM이 꺼져 있거나 실패하면 규칙 기반 기본 요약으로 돌아갑니다.

### 7. Windows 작업 스케줄러 예시

작업 스케줄러에는 매일 11:00 실행으로 등록합니다. `설정` 탭에서 `예약된 시작 시간을 놓친 경우 가능한 한 빨리 작업 실행`을 켜면, 11:00에 PC가 꺼져 있었더라도 그날 처음 켰을 때 `catch-up`이 실행됩니다.

프로그램:

```text
C:\Projects\Telegram\.venv\Scripts\python.exe
```

인수:

```text
-m tg_portfolio_bot catch-up --config C:\Projects\Telegram\config.toml
```

시작 위치:

```text
C:\Projects\Telegram
```

### 8. 테스트

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

## 코드 요약

### 전체 흐름

```text
Telegram 채널/그룹
→ Telethon 사용자 세션 수집
→ SQLite 저장
→ LLM 요약 또는 규칙 기반 요약
→ 포트폴리오 관련 PDF 첨부 목록 보강
→ BotFather 봇으로 발송
```

### 주요 파일

- `src/tg_portfolio_bot/cli.py`
  - 명령줄 진입점입니다.
  - `collect`, `digest`, `run`, `catch-up`, `init-db` 명령을 처리합니다.

- `src/tg_portfolio_bot/collector.py`
  - Telethon으로 텔레그램 메시지를 수집합니다.
  - 사용자 계정 세션을 쓰므로 사용자가 볼 수 있는 공개/비공개 채널과 PDF 업로드를 읽을 수 있습니다.

- `src/tg_portfolio_bot/storage.py`
  - SQLite 저장소입니다.
  - 메시지를 중복 저장하지 않고, 이미 보낸 다이제스트와 daily 기간도 기록합니다.

- `src/tg_portfolio_bot/periods.py`
  - 로컬 시간대 기준 기간 계산을 담당합니다.
  - `catch-up`에서는 11:00 경계와 현재 실행 시각을 함께 고려해 기간을 만듭니다.

- `src/tg_portfolio_bot/classifier.py`
  - 메시지 텍스트와 PDF 파일명을 보유 종목 별칭/키워드에 매칭합니다.
  - PDF 본문을 읽지 않아도 파일명 기반으로 관련 종목에 붙일 수 있습니다.

- `src/tg_portfolio_bot/llm.py`
  - OpenAI 호환 Chat Completions API를 직접 호출합니다.
  - Gemini, OpenAI, Groq, OpenRouter 등 `base_url`만 맞으면 같은 방식으로 쓸 수 있습니다.

- `src/tg_portfolio_bot/digest.py`
  - 최종 다이제스트 문자열을 만듭니다.
  - LLM이 켜져 있으면 전체 요약을 LLM에 맡기고, PDF 단독 첨부 목록은 코드로 별도 보강합니다.

- `src/tg_portfolio_bot/sender.py`
  - BotFather 봇의 `sendMessage` API로 결과를 발송합니다.
  - 텔레그램 메시지 길이 제한에 맞춰 긴 다이제스트를 나눠 보냅니다.

- `src/tg_portfolio_bot/config.py`
  - `config.toml`과 `.env`를 읽어 앱 설정 객체로 변환합니다.
  - 보유 종목은 코드가 아니라 `[[portfolio.holdings]]` 설정에서 읽습니다.

### v2 정책

- PDF 본문은 다운로드하거나 파싱하지 않습니다.
- PDF 단독 업로드는 파일명과 원문 링크만 보존합니다.
- LLM 요약은 비용과 타임아웃을 줄이기 위해 `max_messages`, `max_chars_per_message`로 입력량을 제한합니다.
- LLM 실패 시에도 프로그램은 fallback 요약으로 계속 동작합니다.
- daily 자동 실행은 Windows 작업 스케줄러가 담당합니다.
- PC가 꺼져 있던 기간은 다음 `catch-up` 실행 때 마지막 발송 종료 시각부터 이어서 보강합니다.
- 하루 늦은 실행은 한 덩어리로 보내고, 모레 이상 밀린 경우에는 오래된 구간부터 나눠 보냅니다.
