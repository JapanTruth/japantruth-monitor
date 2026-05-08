import os, requests, json, time

SUPABASE_URL = "https://xhvvxfvxkqcadqhdqtmn.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
GROQ_API_KEYS = [
    os.environ.get("GROQ_API_KEY_1", ""),
    os.environ.get("GROQ_API_KEY_2", ""),
    os.environ.get("GROQ_API_KEY_3", ""),
]

headers_sb = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

res = requests.get(
    f"{SUPABASE_URL}/rest/v1/posts?select=slug,title,body,excerpt&order=date.desc&limit=50",
    headers=headers_sb
)
posts = res.json()
print(f"✅ 取得完了: {len(posts)}件をスキャン")

issues = []

for i, post in enumerate(posts):
    slug = post.get("slug", "")
    title_jp = post.get("title", "")
    body = post.get("body", "")[:1000]
    source_title = slug.replace("-", " ").strip()

    prompt = (
        f"You are a Japanese translation quality checker.\n"
        f"Source (English slug): {source_title}\n"
        f"Japanese title: {title_jp}\n"
        f"Japanese body (first 1000 chars): {body}\n\n"
        f"Check for these specific issues:\n"
        f"1. Person names that appear to be mistransliterated (wrong katakana)\n"
        f"2. Role/title mistranslations (e.g. Senate vs House confusion)\n"
        f"3. Legal term errors (e.g. 'pleads guilty' mistranslated as 起訴)\n"
        f"4. Organization names that seem wrong\n"
        f"5. Any English words left untranslated\n\n"
        f"If you find issues, respond in this exact format:\n"
        f"ISSUE: [wrong text] -> [correct text] | reason\n"
        f"If no issues found, respond with: OK\n"
        f"Be strict but only flag clear errors, not style differences."
    )

    key = GROQ_API_KEYS[i % 3]
    try:
        res2 = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0
            },
            timeout=15
        )
        result = res2.json()
        if "error" in result:
            print(f"⚠️ APIエラー: {result['error']}")
            time.sleep(2)
            continue

        response = result["choices"][0]["message"]["content"].strip()

        if response != "OK" and "ISSUE:" in response:
            issues.append({
                "slug": slug,
                "title": title_jp,
                "issues": response,
                "url": f"https://www.japan-truth.com/posts/{slug}"
            })
            print(f"🚨 問題検出: {slug[:40]}")
            print(f"   {response[:200]}")
        else:
            print(f"✅ OK: {slug[:40]}")

        time.sleep(1)

    except Exception as e:
        print(f"⚠️ エラー: {e}")
        time.sleep(2)

print(f"\n{'='*50}")
print(f"📊 スキャン完了: {len(posts)}件中 {len(issues)}件に問題の可能性")
print(f"{'='*50}")

if issues:
    print("\n🚨 要確認リスト:")
    for item in issues:
        print(f"\n📰 {item['title']}")
        print(f"   URL: {item['url']}")
        print(f"   {item['issues']}")

with open("translation_check_result.json", "w", encoding="utf-8") as f:
    json.dump({"checked": len(posts), "issues_count": len(issues), "issues": issues}, f, ensure_ascii=False, indent=2)

print("\n✅ 結果をtranslation_check_result.jsonに保存")
