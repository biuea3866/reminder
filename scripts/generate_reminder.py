import os
import json
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import anthropic

# ─── 설정 ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
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


# ─── 2. Claude로 요약 ──────────────────────────────────

def summarize_with_claude(raw_data: str) -> dict:
    """Claude API로 학습 리마인더 요약 생성"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""
아래는 개발자의 학습 기록 데이터입니다.
오늘 날짜: {TODAY_DISPLAY}

{raw_data}

---

위 데이터를 바탕으로 **학습 리마인더 요약**을 작성해주세요.
다음 항목을 포함해 마크다운 형식으로 작성하세요:

1. **📌 오늘의 학습 하이라이트** - 가장 최근에 배운/작업한 주요 내용 3~5가지
2. **🔄 복습 포인트** - 다시 한번 짚고 넘어갈 개념이나 코드
3. **💡 인사이트** - 공부한 내용에서 얻을 수 있는 핵심 교훈 또는 패턴
4. **📅 최근 활동 요약** - 커밋 & 블로그 글 타임라인
5. **🚀 다음에 볼 것들** - 연관된 심화 학습 추천

한국어로 작성해주세요. 개발자가 아침에 읽으며 학습 동기를 얻을 수 있도록 격려하는 톤으로 작성해주세요.
"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text

    # 섹션 파싱
    sections = {
        "highlight": "",
        "review": "",
        "insight": "",
        "timeline": "",
        "next": "",
        "full": text,
    }
    return sections


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
            # bold 인라인 처리 (간단 버전)
            content = line_stripped.replace("**", "")
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]}
            })

    return blocks[:95]  # Notion API 한 번에 100블록 제한


def create_notion_page(summary_text: str):
    """노션에 오늘 날짜 페이지 생성"""
    blocks = markdown_to_notion_blocks(summary_text)

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

    payload = {
        "parent": {"page_id": NOTION_PARENT_PAGE_ID},
        "icon": {"emoji": "📖"},
        "properties": {
            "title": {"title": [{"text": {"content": f"📖 {TODAY} 학습 리마인더"}}]}
        },
        "children": header_blocks + blocks,
    }

    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        data=json.dumps(payload),
        timeout=30,
    )

    if resp.status_code == 200:
        page_url = resp.json().get("url", "")
        print(f"✅ 노션 페이지 생성 완료: {page_url}")
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

    # 2. Claude 요약
    print("🤖 Claude로 요약 중...")
    result = summarize_with_claude(raw_combined)

    # 3. 노션 페이지 생성
    print("📝 노션 페이지 생성 중...")
    create_notion_page(result["full"])

    print("✅ 완료!")


if __name__ == "__main__":
    main()
