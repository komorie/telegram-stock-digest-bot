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

### 5. 명령어 모음

모든 명령은 PowerShell에서 `C:\Projects\Telegram` 폴더에서 실행.

| 명령                     | 동작                                                 |
| ------------------------ | ---------------------------------------------------- |
| `.\catch-up.cmd`         | 마지막 발송 이후 누락분을 정리해서 텔레그램으로 발송 |
| `.\catch-up-dry-run.cmd` | 위와 같지만 화면에만 출력 (발송 안 함)               |
| `.\run-dry-run.cmd`      | 최근 24시간 기준 수집+요약, 화면 출력 (테스트용)     |
| `.\collect.cmd`          | 메시지 수집만. 첫 로그인이나 문제 진단용             |
| `.\test.cmd`             | 테스트 실행                                          |

### 6. catch-up 동작 방식

**catch-up은 작업 스케줄러용 명령**. 매일 11:00에 자동 실행되도록 등록하면 됨.

**핵심 원리**: 마지막 발송 시각을 DB에 기록 → 다음 실행 때 그 시점부터 이어서 처리. 사용자가 시간 계산할 필요 없음.

**기준**: `daily_digest_hour = 11` (11:00이 하루 경계)

#### 4가지 규칙

1. 새 11:00 경계가 안 지났으면 → **발송 안 함**
2. 11:00 놓쳤지만 하루 늦은 정도면 → **현재까지 한 번에 발송**
3. 이틀 이상 밀렸으면 → **오래된 구간부터 여러 번 나눠 발송**
4. 첫 실행이라 기록 없으면 → **최신 완료 구간 1개만**

#### 상황별 예시

| 상황                       | 결과              |
| -------------------------- | ----------------- |
| 방금 발송 후 5분 뒤 재실행 | 발송 없음         |
| 11:00 전 실행              | 발송 없음         |
| 11:00 지나 당일 실행       | 1개 발송          |
| 며칠 끄고 켠 후 실행       | 여러 개 나눠 발송 |
| 첫 실행                    | 최신 1개          |

#### 실제 타임라인 예시

```text
[5/26 23:20] 첫 실행
  → 5/25 11:00 ~ 5/26 23:20 발송

[5/27 10:59] 실행
  → 아직 11:00 전, 발송 없음

[5/27 14:00] 실행
  → 5/26 23:20 ~ 5/27 14:00 발송

[5/26 23:20 이후 PC 끄고 5/28 14:00 실행]
  → 5/26 23:20 ~ 5/27 10:59 발송
  → 5/27 11:00 ~ 5/28 14:00 발송
```

### 7. LLM 설정

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

LLM이 켜져 있으면 주요 뉴스, 새로운 투자 아이디어, 포트폴리오 섹션을 LLM이 함께 요약합니다.

#### 주요 뉴스 선정 기준

현재 주요 뉴스는 별도 점수 계산 코드가 아니라 LLM 프롬프트 기준으로 고릅니다.

- 시장 전체, 특정 섹터, 대형 기업, 정책/규제, 지정학, 실적/가이던스에 의미 있는 변화
- 후속 파급이 예상되거나 여러 종목/산업에 영향을 줄 수 있는 뉴스
- 단순 주가 등락, 반복 링크, 맥락 없는 영상/광고, 약한 관련성은 제외

`💡 새로운 투자 아이디어` 섹션은 주요 뉴스까지는 아니지만 새롭게 관찰할 만한 기업/산업/테마 후보를 2~3개 뽑습니다. 매수/매도 추천이 아니라 원문에 근거한 관찰 후보 정리입니다.

운영 정책:

- `llm.enabled = true`이면 LLM 요약이 필수입니다.
- LLM 요청이 실패하면 다이제스트를 발송하지 않고, 해당 기간도 처리 완료로 기록하지 않습니다.
- 따라서 다음 `catch-up` 실행 때 같은 기간을 다시 시도합니다.
- `llm.enabled = false`일 때만 규칙 기반 기본 요약을 사용합니다.

Gemini에서 `HTTP 429 Too Many Requests`가 나면 보통 Gemini API의 rate limit 또는 quota 문제입니다. Google Cloud의 월 지출 한도는 비용 예산이고, 429의 직접 원인인 RPM/TPM/RPD 제한과는 별개입니다.

Google 공식 문서 기준 Gemini API rate limit은 보통 다음 축으로 계산됩니다.

- `RPM`: 분당 요청 수
- `TPM`: 분당 입력 토큰 수
- `RPD`: 일일 요청 수

이 중 하나라도 넘으면 429가 날 수 있습니다. 이 봇은 텔레그램 메시지를 한 번에 많이 넣으므로, 요청 횟수가 적어도 `TPM` 또는 모델별 quota에 걸릴 수 있습니다. 실제 한도는 프로젝트/모델/사용 tier에 따라 달라지므로 Google AI Studio의 rate limit 화면에서 확인해야 합니다.

### 8. Windows 작업 스케줄러 예시

작업 스케줄러에는 매일 11:00 실행으로 등록합니다. `설정` 탭에서 `예약된 시작 시간을 놓친 경우 가능한 한 빨리 작업 실행`을 켜면, 11:00에 PC가 꺼져 있었더라도 그날 처음 켰을 때 `catch-up`이 실행됩니다.

짧은 실행 파일을 쓰는 방식:

프로그램:

```text
C:\Projects\Telegram\catch-up.cmd
```

인수:

```text
비워둠
```

시작 위치:

```text
C:\Projects\Telegram
```

원본 Python 명령을 직접 등록하는 방식:

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

### 9. 테스트

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
→ 주요 뉴스 / 투자 아이디어 / 포트폴리오 섹션 생성
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
  - 현재 출력에서는 PDF 단독 파일을 따로 리포트 목록으로 보여주지 않습니다.

- `src/tg_portfolio_bot/llm.py`
  - OpenAI 호환 Chat Completions API를 직접 호출합니다.
  - Gemini, OpenAI, Groq, OpenRouter 등 `base_url`만 맞으면 같은 방식으로 쓸 수 있습니다.

- `src/tg_portfolio_bot/digest.py`
  - 최종 다이제스트 문자열을 만듭니다.
  - LLM이 켜져 있으면 전체 요약을 LLM에 맡기고, PDF 단독 파일은 입력/출력에서 제외합니다.

- `src/tg_portfolio_bot/sender.py`
  - BotFather 봇의 `sendMessage` API로 결과를 발송합니다.
  - 텔레그램 메시지 길이 제한에 맞춰 긴 다이제스트를 나눠 보냅니다.

- `src/tg_portfolio_bot/config.py`
  - `config.toml`과 `.env`를 읽어 앱 설정 객체로 변환합니다.
  - 보유 종목은 코드가 아니라 `[[portfolio.holdings]]` 설정에서 읽습니다.

### v2 정책

- PDF 본문은 다운로드하거나 파싱하지 않습니다.
- PDF 단독 업로드는 현재 다이제스트 출력에서 제외합니다.
- 별도 리포트 수집용 채널은 정확도가 낮아 기본 수집 대상에서 제외했습니다.
- LLM 출력은 `주요 뉴스 다이제스트`, `💡 새로운 투자 아이디어`, `📊 내 포트폴리오` 세 덩어리로 구성합니다.
- LLM 요약은 비용과 타임아웃을 줄이기 위해 `max_messages`, `max_chars_per_message`로 입력량을 제한합니다.
- `llm.enabled = true` 상태에서 LLM이 실패하면 발송하지 않고, 해당 기간도 처리 완료로 기록하지 않습니다.
- `llm.enabled = false`일 때만 규칙 기반 fallback 요약을 사용합니다.
- daily 자동 실행은 Windows 작업 스케줄러가 담당합니다.
- PC가 꺼져 있던 기간은 다음 `catch-up` 실행 때 마지막 발송 종료 시각부터 이어서 보강합니다.
- 하루 늦은 실행은 한 덩어리로 보내고, 모레 이상 밀린 경우에는 오래된 구간부터 나눠 보냅니다.
