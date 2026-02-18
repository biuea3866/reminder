import os
import json
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# ─── 설정 ──────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_PARENT_PAGE_ID = os.environ["NOTION_PARENT_PAGE_ID"]  # 허브 페이지 ID

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
TODAY_DISPLAY = datetime.now(KST).strftime("%Y년 %m월 %d일")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

ANALYSIS_PROMPT = """아래는 개발자의 학습 기록 데이터입니다.
오늘 날짜: {today}

{raw_data}

---

위 데이터를 분석해서 아래 작업을 수행해주세요:

## 작업 지시

1. 위 데이터(커밋 메시지, README, 블로그 글)에서 **흥미롭고 학습 가치가 높은 토픽 3개**를 선택하세요.
   - 최근에 작업한 기술, 개념, 프로젝트 중에서 고르세요.
   - 서로 다른 분야의 토픽을 골라주세요 (예: 프론트엔드 1개, 백엔드 1개, 인프라 1개).

2. 각 토픽에 대해 **자세한 학습 노트**를 작성하세요. 데이터에서 확인할 수 있는 내용만으로 부족하다면, 웹 검색을 활용해 추가 정보를 보충하세요.

3. 각 토픽은 아래 형식으로 작성하세요:

## 토픽 1: [토픽 제목]

### 개요
- 이 토픽이 무엇인지, 왜 중요한지 2~3문장으로 설명

### 핵심 개념 정리
- 관련 핵심 개념들을 불릿 포인트로 정리
- 각 개념에 대해 1~2문장씩 설명 추가

### 실무 활용 예시
- 실제 코드나 설정 예시
- 또는 어떤 상황에서 사용하는지 구체적으로

### 더 알아볼 것
- 이 토픽과 관련해서 추가로 공부하면 좋을 내용
- 관련 공식 문서나 참고 자료 링크

(토픽 2, 토픽 3도 동일한 형식)

---

마지막으로 아래 섹션을 추가해주세요:

## 오늘의 한줄 요약
- 오늘 학습 데이터에서 느낀 전체적인 인사이트 한 문장

## 최근 활동 타임라인
- 커밋과 블로그 글을 시간순으로 정리

---

**중요:**
- 한국어로 작성하세요.
- 데이터에 나온 내용만으로 충분한 설명이 안 되면 웹 검색으로 보충하세요.
- 개발자가 아침에 읽으며 학습 동기를 얻을 수 있도록 격려하는 톤으로 작성하세요.
- 마크다운 형식으로 작성하되, 코드 블록(```)은 사용하지 마세요 (노션 변환 호환성).
"""


# ─── 1. 데이터 수집 ────────────────────────────────────

def fetch_github_repo(owner: str, repo: str) -> str:
    """GitHub API로 최근 커밋 & README 가져오기"""
    result = []

    # 최근 커밋 10개
    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=10"
    resp = requests.get(url, timeout=10)
    if resp.status_code == 200:
        commits = resp.json()
        result.append(f"### [{owner}/{repo}] 최근 커밋")
        for c in commits:
            msg = c["commit"]["message"].split("\n")[0]
            date = c["commit"]["author"]["date"][:10]
            result.append(f"- {date}: {msg}")

    # README
    url_readme = f"https://api.github.com/repos/{owner}/{repo}/readme"
    resp_readme = requests.get(url_readme, timeout=10)
    if resp_readme.status_code == 200:
        import base64
        content = base64.b64decode(resp_readme.json()["content"]).decode("utf-8", errors="ignore")
        result.append(f"\n### [{owner}/{repo}] README (요약용)")
        result.append(content[:3000])  # 앞 3000자만

    return "\n".join(result)


def fetch_tistory_blog(blog_url: str) -> str:
    """티스토리 블로그 RSS로 최근 글 가져오기"""
    rss_url = blog_url.rstrip("/") + "/rss"
    resp = requests.get(rss_url, timeout=10)
    if resp.status_code != 200:
        return "블로그 RSS 수집 실패"

    soup = BeautifulSoup(resp.text, "xml")
    items = soup.find_all("item")[:10]

    result = ["### 블로그 최근 글 (biuea.tistory.com)"]
    for item in items:
        title = item.find("title").text if item.find("title") else "제목 없음"
        pub_date = item.find("pubDate").text[:16] if item.find("pubDate") else ""
        description = item.find("description")
        desc_text = ""
        if description:
            desc_soup = BeautifulSoup(description.text, "html.parser")
            desc_text = desc_soup.get_text()[:300]
        result.append(f"\n**{title}** ({pub_date})\n{desc_text}")

    return "\n".join(result)


# ─── 2. AI 심화 분석 (Gemini 우선, Claude 폴백) ───────

def analyze_with_gemini(raw_data: str) -> str:
    """Gemini API + Google Search 그라운딩으로 3개 토픽 심화 분석"""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = ANALYSIS_PROMPT.format(today=TODAY_DISPLAY, raw_data=raw_data)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            max_output_tokens=8000,
        ),
    )

    return response.text


def analyze_with_claude(raw_data: str) -> str:
    """Claude API + web_search 도구로 3개 토픽 심화 분석"""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = ANALYSIS_PROMPT.format(today=TODAY_DISPLAY, raw_data=raw_data)

    # web_search_20250305는 서버 사이드 도구 — API가 자동으로 검색 실행 후 결과 반환
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        messages=[{"role": "user", "content": prompt}],
    )

    # 텍스트 블록만 추출 (web_search_tool_result 블록 등은 제외)
    text_parts = []
    for block in response.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)

    return "\n".join(text_parts)


def analyze(raw_data: str) -> str:
    """Gemini 우선 시도, 실패 시 Claude 폴백"""
    # 1차: Gemini
    if GEMINI_API_KEY:
        try:
            print("  → Gemini로 분석 시도...")
            return analyze_with_gemini(raw_data)
        except Exception as e:
            print(f"  ⚠️ Gemini 실패: {e}")

    # 2차: Claude
    if ANTHROPIC_API_KEY:
        try:
            print("  → Claude로 분석 시도...")
            return analyze_with_claude(raw_data)
        except Exception as e:
            print(f"  ⚠️ Claude 실패: {e}")

    raise RuntimeError("Gemini와 Claude 모두 사용할 수 없습니다. API 키와 크레딧을 확인해주세요.")


# ─── 3. 노션 페이지 생성 ───────────────────────────────

def markdown_to_notion_blocks(text: str) -> list:
    """마크다운 텍스트를 노션 블록 배열로 변환"""
    blocks = []
    lines = text.split("\n")

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}})
            continue

        if line_stripped.startswith("## "):
            blocks.append({
                "object": "block", "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": line_stripped[3:]}}]}
            })
        elif line_stripped.startswith("### "):
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": line_stripped[4:]}}]}
            })
        elif line_stripped.startswith("- ") or line_stripped.startswith("* "):
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line_stripped[2:]}}]}
            })
        elif line_stripped.startswith("**") and line_stripped.endswith("**"):
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": line_stripped.strip("*")},
                                              "annotations": {"bold": True}}]}
            })
        else:
            content = line_stripped.replace("**", "")
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]}
            })

    return blocks


def append_blocks_to_page(page_id: str, blocks: list):
    """Notion 페이지에 블록을 100개씩 나눠서 추가"""
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i + 100]
        resp = requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            data=json.dumps({"children": chunk}),
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"❌ 블록 추가 실패 (chunk {i}): {resp.status_code} {resp.text}")
            resp.raise_for_status()


def create_notion_page(summary_text: str):
    """노션에 오늘 날짜 페이지 생성"""
    all_blocks = markdown_to_notion_blocks(summary_text)

    # 상단 메타 블록 추가
    header_blocks = [
        {
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": f"📅 {TODAY_DISPLAY} 자동 생성된 학습 리마인더입니다."}}],
                "icon": {"emoji": "🤖"},
                "color": "blue_background",
            }
        },
        {"object": "block", "type": "divider", "divider": {}},
    ]

    # 페이지 생성 시 첫 98개 블록 포함 (header 2개 + content 96개)
    first_batch = all_blocks[:96]
    remaining = all_blocks[96:]

    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "icon": {"emoji": "📖"},
        "properties": {
            "title": {"title": [{"text": {"content": f"📖 {TODAY} 학습 리마인더"}}]}
        },
        "children": header_blocks + first_batch,
    }

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        data=json.dumps(payload),
        timeout=30,
    )

    if resp.status_code == 200:
        page_id = resp.json()["id"]
        page_url = resp.json().get("url", "")
        print(f"✅ 노션 페이지 생성 완료: {page_url}")

        # 남은 블록이 있으면 추가
        if remaining:
            print(f"📎 추가 블록 {len(remaining)}개 삽입 중...")
            append_blocks_to_page(page_id, remaining)
            print("✅ 추가 블록 삽입 완료")
    else:
        print(f"❌ 노션 페이지 생성 실패: {resp.status_code} {resp.text}")
        resp.raise_for_status()


# ─── 메인 ──────────────────────────────────────────────

def main():
    print(f"🚀 Daily Reminder 시작 - {TODAY_DISPLAY}")

    # 1. 데이터 수집
    print("📡 데이터 수집 중...")
    til_data = fetch_github_repo("biuea3866", "TIL")
    poc_data = fetch_github_repo("biuea3866", "poc-project")
    blog_data = fetch_tistory_blog("https://biuea.tistory.com")

    raw_combined = f"{til_data}\n\n{poc_data}\n\n{blog_data}"
    print(f"📦 수집된 데이터: {len(raw_combined)}자")

    # 2. AI 심화 분석 (Gemini 우선, Claude 폴백)
    print("🤖 AI 심화 분석 중 (웹 검색 포함)...")
    summary = analyze(raw_combined)
    print(f"📝 분석 결과: {len(summary)}자")

    # 3. 노션 페이지 생성
    print("📝 노션 페이지 생성 중...")
    create_notion_page(summary)

    print("✅ 완료!")


if __name__ == "__main__":
    main()
