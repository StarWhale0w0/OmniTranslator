 ### 🚀 OmniTranslator Pro v1.0.0

  OmniTranslator Pro는 Google Gemini AI 기반의 장편 소설(Light Novel / Web Novel) 및 전자책 전문 고성능 배치 번역
  데스크톱 애플리케이션입니다.
  EPUB과 TXT 문서를 완벽 지원하며, 다중 API 키 로테이션과 지능형 용어집 시스템으로 빠르고 일관성 있는 고품질 번역을
  제공합니다.
  
  ──────
  ## 🌟 주요 핵심 기능 (Key Features)
  ### 1. 📚 전자책(EPUB) 및 텍스트(TXT) 포맷 맞춤형 번역
  • EPUB DOM 구조 100% 보존: HTML 태그(<p>, <span>, <ruby>, <img> 등), 삽화, CSS 스타일 및 목차(NCX/Nav) 구조를 손상
  없이 유지하며 본문 텍스트만 정밀 번역.
  • TXT 순수 텍스트 번역: 불필요한 HTML 가상 태그를 배제하고 자연스러운 문단 구조의 순수 텍스트(.txt)로 출력 및 저장.
  • 다중 인코딩 자동 판별: UTF-8, CP949, EUC-KR, UTF-16 등 다양한 인코딩의 텍스트 파일을 깨짐 없이 자동 로드.

  ### 2. 🌐 언어별 특화 번역 프로필 & 프롬프트 엔지니어링

  • 🇯🇵 일본어 (JA): 라이트노벨 특유의 어조, 1인칭 대명사(私/僕/俺), 감정선 및 구어체 뉘앙스 최적화.
  • 🇨🇳 중국어 (ZH): 웹소설/선협/무협 고유명사 한자 음독 반영, 서술형 과거 시제(~였다) 강제 적용 및 불필요한 사이트
  광고 문구 자동 제거.
  • 🇺🇸 영어 (EN): 복합 관계절 문장 재구성 및 자연스러운 한국어 문체 전환.
  ### 3. 🧠 맵-리듀스(Map-Reduce) 기반 AI 전수 용어집 추출

  • 소설 전체 전수 스캔: 수십만 자 분량의 장편 소설 전체를 18,000자 블록으로 분할 분석하여 인명, 지명, 몬스터, 스킬,
  단체명 등 고유명사를 빠짐없이 추출.
  • 빈도 기반 대표 번역어 선별: 블록별 등장 횟수를 누적 집계하여 가장 정확한 대표 번역어를 선별하고, 실시간 테이블
  편집 및 저장을 지원.
  • 동적 용어집 주입(Dynamic Injection): 번역 진행 시 현재 청크에 등장하는 용어만 선별 주입하여 전체 번역의 일관성
  유지.

  ### 4. ⚡ 다중 API 키 자동 순환 & 병렬 비동기 처리

  • Multi-API Key Rotation: 복수의 Gemini API 키를 등록하여 분당 요청 제한(RPM/TPM) 및 429 오류를 방지하며 자동
  순환(Round-Robin/Failover).
  • 고속 비동기 병렬 처리: qasync + asyncio 기반으로 최대 16개 워커 동시 번역 수행.
  • 스마트 세션 이어하기(Checkpoint): 작업 중단 시 진행된 번역 청크와 용어집을 자동 보존하여 언제든 이어서 번역 가능.

  ### 5. 🛡️ 환각(반복 오류) 자가 검증 & 실시간 후처리 엔진

  • 사고 과정(Thinking) 유출 방지: 모델의 내부 자가 검증 텍스트(*Final check*, <think> 등) 원천 차단 및 정제.
  • 반복 환각 자동 복구: 동일 문장이 3회 이상 연속 출력되는 현상 감지 시 온도(Temperature)를 0.1로 낮추어 자동
  재요청(Auto-Retry) 수행.

  ### 6. 🎨 현대적인 PySide6 다크 테마 대시보드

  • 헤더에 현재 선택된 번역 언어 뱃지 실시간 표시.
  • 원문과 번역문을 나란히 비교할 수 있는 실시간 듀얼 프리뷰 패널.
  • 작업 진행률, ETA, 번역 속도(Chunks/sec) 및 상세 로그 콘솔 제공.
  ──────
  ## 🛠️ 기술 스택 (Tech Stack)

  • GUI Framework: Python 3.12, PySide6 (Qt for Python), qasync
  • LLM Engine: Google GenAI SDK (gemini-2.5-flash, gemini-2.5-pro)
  • Document Processing: ebooklib, BeautifulSoup4
  • Packaging: PyInstaller (Standalone Windows Executable)
  ──────
  ## 📥 설치 및 실행 방법

  1. GitHub Releases에서 최신 버전의 OmniTranslatorPro.exe를 다운로드합니다.
  2. 프로그램을 실행한 뒤 우측 상단 **[설정]**에서 발급받은 Gemini API Key를 1개 이상 입력합니다.
  3. 원문 파일(.epub 또는 .txt)을 선택하고 [AI 용어집 추출] 또는 **[번역 시작]**을 클릭합니다.
