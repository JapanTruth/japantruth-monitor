import os, requests, json, time, re

SUPABASE_URL = "https://xhvvxfvxkqcadqhdqtmn.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
GROQ_API_KEYS = [
    os.environ.get("GROQ_API_KEY_1", ""),
    os.environ.get("GROQ_API_KEY_2", ""),
    os.environ.get("GROQ_API_KEY_3", ""),
]
key_index = 0

def get_key():
    global key_index
    k = GROQ_API_KEYS[key_index % 3]
    key_index += 1
    return k

headers_sb = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

res = requests.get(
    f"{SUPABASE_URL}/rest/v1/posts?select=slug,title,body,excerpt,source_url&order=date.desc&limit=100",
    headers=headers_sb
)
posts = res.json()
print(f"✅ 取得完了: {len(posts)}件をスキャン\n")

# =============================
# 1. 重複記事チェック
# =============================
print("=" * 50)
print("📋 重複記事チェック")
print("=" * 50)

url_seen = {}
title_seen = {}
duplicates = []

for post in posts:
    slug = post.get("slug", "")
    title = post.get("title", "") or ""
    url = post.get("source_url", "") or ""
    url_base = re.sub(r'[?#].*$', '', url)

    if url_base and url_base in url_seen:
        duplicates.append({
            "type": "URL重複",
            "slug1": url_seen[url_base],
            "slug2": slug,
            "title": title,
        })
        print(f"🔴 URL重複: {slug[:50]}")
        print(f"   重複元: {url_seen[url_base][:50]}")
    elif url_base:
        url_seen[url_base] = slug

    title_words = set(title.split())
    for prev_title, prev_slug in list(title_seen.items()):
        prev_words = set(prev_title.split())
        if len(title_words & prev_words) >= 4 and slug != prev_slug:
            duplicates.append({
                "type": "タイトル類似",
                "slug1": prev_slug,
                "slug2": slug,
                "title": title,
            })
            print(f"🟡 タイトル類似: {title[:40]}")
            print(f"   類似元: {prev_title[:40]}")
            break
    title_seen[title] = slug

if not duplicates:
    print("✅ 重複なし")

# =============================
# 2. 禁止ワードチェック
# =============================
print(f"\n{'=' * 50}")
print("🚫 禁止ワードチェック")
print("=" * 50)

FORBIDDEN = [
    "可能性がある", "かもしれない", "見守る", "注視する",
    "注目が集まる", "懸念される", "期待が高まる",
    "避けられない", "直結する", "国際社会", "国際秩序",
    "グローバル市場", "どこへ向かうのか", "どこに向かうのか",
    "とされる", "といわれる",
]

forbidden_issues = []
for post in posts:
    slug = post.get("slug", "")
    title = post.get("title", "") or ""
    body = post.get("body", "") or ""
    found = [w for w in FORBIDDEN if w in body or w in title]
    if found:
        forbidden_issues.append({
            "slug": slug,
            "title": title,
            "found": found,
            "url": f"https://www.japan-truth.com/posts/{slug}"
        })
        print(f"🚫 {title[:40]}")
        print(f"   検出: {', '.join(found)}")

if not forbidden_issues:
    print("✅ 禁止ワードなし")

# =============================
# 2.5 キリル文字混入チェック
# =============================
print(f"
{'=' * 50}")
print('🔤 キリル文字混入チェック')
print('=' * 50)

import re as _re
cyrillic_pattern = _re.compile(r'[А-Яа-яЁёІіЇїЄєҐґ]+')
hangul_pattern = _re.compile(r'[가-힣ㄱ-ㅎㅏ-ㅣ]+')

cyrillic_issues = []
for post in posts:
    slug = post.get('slug', '')
    title = post.get('title', '') or ''
    body = post.get('body', '') or ''
    excerpt = post.get('excerpt', '') or ''
    full_text = title + body + excerpt
    c_matches = cyrillic_pattern.findall(full_text)
    h_matches = hangul_pattern.findall(full_text)
    if c_matches or h_matches:
        cyrillic_issues.append({
            'slug': slug,
            'title': title,
            'cyrillic': list(set(c_matches))[:3],
            'hangul': list(set(h_matches))[:3],
            'url': f'https://www.japan-truth.com/posts/{slug}'
        })
        if c_matches:
            print(f'🔴 キリル文字検出: {title[:40]}')
            print(f'   検出: {list(set(c_matches))[:3]}')
        if h_matches:
            print(f'🔴 ハングル検出: {title[:40]}')
            print(f'   検出: {list(set(h_matches))[:3]}')

if not cyrillic_issues:
    print('✅ キリル文字・ハングルなし')

# =============================
# 3. 既知誤訳パターンチェック
# =============================
print(f"\n{'=' * 50}")
print("📖 既知誤訳パターンチェック（PROPER_NOUN_FIXES）")
print("=" * 50)

try:
    _code = open("news_monitor.py").read()
    _start = _code.index("PROPER_NOUN_FIXES = {")
    _end = _code.index("\n}", _start) + 2
    exec(_code[_start:_end])
    print(f"✅ {len(PROPER_NOUN_FIXES)}パターン読み込み完了")
except Exception as e:
    print(f"⚠️ 読み込み失敗: {e}")
    PROPER_NOUN_FIXES = {}

known_issues = []
for post in posts:
    slug = post.get("slug", "")
    title = post.get("title", "") or ""
    body = post.get("body", "") or ""
    excerpt = post.get("excerpt", "") or ""
    full_text = title + body + excerpt
    found = {wrong: correct for wrong, correct in PROPER_NOUN_FIXES.items() if wrong in full_text}
    if found:
        known_issues.append({
            "slug": slug,
            "title": title,
            "fixes": found,
            "url": f"https://www.japan-truth.com/posts/{slug}"
        })
        print(f"🔴 {title[:40]}")
        for w, c in found.items():
            print(f"   「{w}」→「{c}」")

if not known_issues:
    print("✅ 既知誤訳なし")

# =============================
# 4. AI誤訳チェック（補助）
# =============================
print(f"\n{'=' * 50}")
print("🔍 AI誤訳チェック（補助）")
print("=" * 50)

translation_issues = []

for i, post in enumerate(posts):
    slug = post.get("slug", "")
    title_jp = post.get("title", "") or ""
    body = post.get("body", "")[:600]
    source_title = re.sub(r'^\d{4}-\d{2}-\d{2}-\d{6}-', '', slug).replace("-", " ")

    prompt = (
        f"Japanese translation quality check.\n"
        f"English source: {source_title}\n"
        f"Japanese title: {title_jp}\n"
        f"Japanese body: {body}\n\n"
        f"Flag ONLY clear errors:\n"
        f"1. Person names with clearly wrong katakana\n"
        f"2. Senate/House confusion\n"
        f"3. pleads guilty mistranslated as 起訴\n"
        f"4. English in brackets like [Name] still remaining\n\n"
        f"Format: FIX: [wrong] -> [correct] | reason\n"
        f"If nothing wrong: OK\n"
        f"Max 2 issues."
    )

    key = get_key()
    for attempt in range(3):
        try:
            res2 = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                    "temperature": 0
                },
                timeout=15
            )
            result = res2.json()
            if "error" in result:
                if "rate_limit" in str(result["error"]):
                    key = GROQ_API_KEYS[(key_index) % 3]
                    key_index += 1
                    print(f"⏳ レート制限 → キー切り替え")
                    time.sleep(5)
                    continue
                break

            response = result["choices"][0]["message"]["content"].strip()
            if response != "OK" and "FIX:" in response:
                translation_issues.append({
                    "slug": slug,
                    "title": title_jp,
                    "issues": response,
                    "url": f"https://www.japan-truth.com/posts/{slug}"
                })
                print(f"🚨 {slug[:40]}")
                print(f"   {response[:120]}")
            else:
                print(f"✅ OK: {slug[:40]}")
            break

        except Exception as e:
            print(f"⚠️ エラー: {e}")
            break

    time.sleep(2)

# =============================
# サマリー
# =============================
print(f"\n{'=' * 50}")
print(f"📊 スキャン完了: {len(posts)}件")
print(f"  🔴 重複記事:    {len(duplicates)}件")
print(f"  🚫 禁止ワード:  {len(forbidden_issues)}件")
print(f"  📖 既知誤訳:    {len(known_issues)}件")
print(f"  🚨 AI誤訳疑い: {len(translation_issues)}件")
print("=" * 50)

with open("translation_check_result.json", "w", encoding="utf-8") as f:
    json.dump({
        "checked": len(posts),
        "duplicates": duplicates,
        "forbidden_issues": forbidden_issues,
        "cyrillic_issues": cyrillic_issues,
        "known_issues": known_issues,
        "translation_issues": translation_issues,
    }, f, ensure_ascii=False, indent=2)

print("\n✅ 結果をtranslation_check_result.jsonに保存")
