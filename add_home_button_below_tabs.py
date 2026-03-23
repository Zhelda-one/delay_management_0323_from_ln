# Home 버튼 자동 추가 스크립트 (탭 아래 오른쪽)
# 사용법: python add_home_button_below_tabs.py

import re

# Home 버튼 CSS - 탭 아래 오른쪽
home_button_css = """
    /* Home 버튼 스타일 */
    .home-button {
      position: fixed;
      top: 55px;
      right: 20px;
      z-index: 1000;
      background: #3b82f6;
      color: white;
      padding: 10px 20px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 14px;
      font-weight: 600;
      box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
      transition: all 0.3s ease;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .home-button:hover {
      background: #2563eb;
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
    }
    .home-button::after {
      content: "🏠";
      font-size: 16px;
    }
"""

# Home 버튼 HTML
home_button_html = """  <!-- Home 버튼 -->
  <a href="/" class="home-button">Home</a>

"""

# 처리할 파일 목록
files = [
    'templates/index.html',
    'templates/index_ul.html',
    'templates/index_iq.html'
]

for filepath in files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 기존 Home 버튼 제거 (있으면)
        if 'home-button' in content:
            # 기존 CSS 제거
            content = re.sub(r'/\* Home 버튼.*?\*/.*?\.home-button\s*\{[^}]+\}.*?\.home-button:hover\s*\{[^}]+\}.*?\.home-button::(before|after)\s*\{[^}]+\}', '', content, flags=re.DOTALL)
            # 기존 HTML 제거
            content = re.sub(r'<!--\s*Home 버튼\s*-->.*?<a[^>]*class="home-button"[^>]*>.*?</a>', '', content, flags=re.DOTALL)
            print(f"🔄 {filepath} - 기존 Home 버튼 제거")

        # CSS 추가 (</style> 앞에)
        content = content.replace('</style>', home_button_css + '  </style>')

        # HTML 추가 (<body> 다음에)
        content = re.sub(r'(<body[^>]*>)', r'\1\n' + home_button_html, content)

        # 백업 생성
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            with open(filepath + '.backup', 'w', encoding='utf-8') as f:
                f.write(backup_content)
        except:
            pass

        # 수정된 내용 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✅ {filepath} - Home 버튼 추가 완료 (탭 아래 오른쪽)")

    except FileNotFoundError:
        print(f"❌ {filepath} - 파일을 찾을 수 없음")
    except Exception as e:
        print(f"❌ {filepath} - 에러: {e}")

print("\n완료! 각 페이지 탭 아래 오른쪽에 Home 버튼이 추가되었습니다.")
print("탭과 겹치지 않습니다!")
print("백업 파일: *.backup")
