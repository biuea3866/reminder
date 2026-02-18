# 📚 Daily Study Reminder

매일 오전 9시(KST)에 GitHub + 티스토리 블로그를 읽어 Claude AI로 요약하고, Notion에 자동으로 페이지를 생성합니다.

---

## 🚀 세팅 방법 (5분)

### 1. 이 레포지토리를 Fork 또는 새 레포에 업로드

### 2. GitHub Secrets 설정
레포 → Settings → Secrets and variables → Actions → **New repository secret**

| Secret 이름 | 값 | 얻는 방법 |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `NOTION_TOKEN` | `secret_...` | [notion.so/my-integrations](https://www.notion.so/my-integrations) → New integration |
| `NOTION_PARENT_PAGE_ID` | `30b165b9...` | 아래 참고 |

### 3. NOTION_PARENT_PAGE_ID 확인
생성된 허브 페이지 URL:
```
https://www.notion.so/30b165b99f5f81e9a17bef5cdee47eae
```
URL에서 마지막 32자리 = `30b165b99f5f81e9a17bef5cdee47eae`

### 4. Notion Integration 연결
1. [notion.so/my-integrations](https://www.notion.so/my-integrations) 에서 새 Integration 생성
2. **"📚 Daily Study Reminder"** 페이지 열기
3. 우측 상단 `•••` → **Connections** → 생성한 Integration 추가

### 5. 완료!
Actions 탭에서 `workflow_dispatch`로 한 번 수동 실행해서 테스트해보세요.

---

## ⏰ 스케줄
- 매일 **오전 9시 KST** (= UTC 00:00) 자동 실행
- Actions 탭에서 수동 실행도 가능

## 💰 비용
- GitHub Actions: **무료** (public repo 무제한, private도 월 2000분 무료)
- Claude API: 하루 1회 실행 시 약 **$0.01~0.03** (월 ~$0.5)
- Notion API: **무료**
