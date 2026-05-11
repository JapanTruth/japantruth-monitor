import os, requests, json, time, re
from datetime import datetime

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

# 記事取得
res = requests.get(
    f"{SUPABASE_URL}/rest/v1/posts?select=slug,title,body,excerpt,source_url&order=date.desc&limit=200",
    headers=headers_sb
)
posts = res.json()
print(f"✅ 取得完了: {len(posts)}件をスキャン\n")

# PROPER_NOUN_FIXESを読み込む
try:
    _code = open("news_monitor.py").read()
    _start = _code.index("PROPER_NOUN_FIXES = {")
    _end = _code.index("\n}", _start) + 2
    exec(_code[_start:_end])
    print(f"✅ PROPER_NOUN_FIXES: {len(PROPER_NOUN_FIXES)}パターン読み込み完了\n")
except Exception as e:
    print(f"⚠️ PROPER_NOUN_FIXES読み込み失敗: {e}")
    PROPER_NOUN_FIXES = {}

FORBIDDEN = [
    "可能性がある", "かもしれない", "見守る", "注視する",
    "注目が集まる", "懸念される", "期待が高まる",
    "避けられない", "直結する", "国際社会", "国際秩序",
    "グローバル市場", "どこへ向かうのか", "どこに向かうのか",
    "とされる", "といわれる",
]

duplicates = []
forbidden_issues = []
cyrillic_issues = []
known_issues = []
translation_issues = []
source_mismatch_issues = []
new_proper_noun_suggestions = []
auto_fixed = []

# =============================
# 1. 重複記事チェック
# =============================
print("=" * 50)
print("📋 1. 重複記事チェック")
print("=" * 50)

url_seen = {}
title_seen = {}

for post in posts:
    slug = post.get("slug", "")
    title = post.get("title", "") or ""
    url = re.sub(r'[?#].*$', '', post.get("source_url", "") or "")

    if url and url in url_seen:
        duplicates.append({"type": "URL重複", "slug1": url_seen[url], "slug2": slug, "title": title})
        print(f"🔴 URL重複: {slug[:50]}")
    elif url:
        url_seen[url] = slug

    import re as _re2
    stop_ja = {"の","が","を","に","は","で","と","も","な","する","した","て","や","へ","から","まで","より","として","による","大統領","首相","氏","戦争","問題","発言","表明"}
    title_words = set(w for w in _re2.findall(r"[ァ-ヴー]{3,}|[一-龥]{2,}", title) if w not in stop_ja)
    for prev_title, prev_slug in list(title_seen.items()):
        prev_words = set(w for w in _re2.findall(r"[ァ-ヴー]{3,}|[一-龥]{2,}", prev_title) if w not in stop_ja)
        if len(title_words & prev_words) >= 2 and slug != prev_slug:
            duplicates.append({"type": "タイトル類似", "slug1": prev_slug, "slug2": slug, "title": title})
            print(f"🟡 タイトル類似: {title[:40]}")
            print(f"   残す: {prev_title[:40]}")
            break
    title_seen[title] = slug

if not duplicates:
    print("✅ 重複なし")

# =============================
# 2. 禁止ワードチェック + 自動修正
# =============================
print(f"\n{'=' * 50}")
print("🚫 2. 禁止ワードチェック（自動修正付き）")
print("=" * 50)

forbidden_fixes = {
    "避けられない状況だ": "深刻な局面だ",
    "避けられない": "避けがたい",
    "とされる。": "と報告されている。",
    "とされる、": "と報告されている、",
    "とされる ": "と報告されている ",
    "国際社会": "各国政府",
    "どこへ向かうのか": "どう動くべきか",
    "どこに向かうのか": "どう動くべきか",
    "グローバル市場": "世界市場",
    "直結する": "関連する",
}

for post in posts:
    slug = post.get("slug", "")
    title = post.get("title", "") or ""
    body = post.get("body", "") or ""
    found = [w for w in FORBIDDEN if w in body or w in title]
    if found:
        # 自動修正
        nt, nb, ne = title, body, post.get("excerpt", "") or ""
        for wrong, correct in forbidden_fixes.items():
            nt, nb, ne = nt.replace(wrong, correct), nb.replace(wrong, correct), ne.replace(wrong, correct)
        if nt != title or nb != body:
            res2 = requests.patch(
                f"{SUPABASE_URL}/rest/v1/posts?slug=eq.{slug}",
                headers=headers_sb,
                json={"title": nt, "body": nb, "excerpt": ne}
            )
            if res2.status_code == 204:
                auto_fixed.append(slug)
                print(f"🔧 自動修正: {title[:40]}")
                print(f"   修正語: {', '.join(found)}")
            else:
                forbidden_issues.append({"slug": slug, "title": title, "found": found})
                print(f"🚫 修正失敗: {title[:40]}")
        else:
            forbidden_issues.append({"slug": slug, "title": title, "found": found})
            print(f"🚫 {title[:40]} → {', '.join(found)}")

if not forbidden_issues and not auto_fixed:
    print("✅ 禁止ワードなし")

# =============================
# 2.5 キリル文字・ハングル混入チェック + 自動修正
# =============================
print(f"\n{'=' * 50}")
print("🔤 2.5 キリル文字・ハングル混入チェック（自動修正付き）")
print("=" * 50)

import re as _re
cyrillic_pattern = _re.compile(r'[А-Яа-яЁёІіЇїЄєҐґ]+')
hangul_pattern = _re.compile(r'[가-힣ㄱ-ㅎㅏ-ㅣ]+')

for post in posts:
    slug = post.get("slug", "")
    title = post.get("title", "") or ""
    body = post.get("body", "") or ""
    excerpt = post.get("excerpt", "") or ""
    full_text = title + body + excerpt

    c_matches = cyrillic_pattern.findall(full_text)
    h_matches = hangul_pattern.findall(full_text)

    if c_matches or h_matches:
        cyrillic_issues.append({
            "slug": slug, "title": title,
            "cyrillic": list(set(c_matches))[:3],
            "hangul": list(set(h_matches))[:3],
            "url": f"https://www.japan-truth.com/posts/{slug}"
        })
        if c_matches:
            print(f"🔴 キリル文字検出: {title[:40]}")
            print(f"   検出: {list(set(c_matches))[:3]}")
            # PROPER_NOUN_FIXESに未登録なら提案
            for m in set(c_matches):
                context_idx = full_text.find(m)
                context = full_text[max(0,context_idx-5):context_idx+10]
                if m not in str(PROPER_NOUN_FIXES):
                    new_proper_noun_suggestions.append(f"キリル混入: 「{context}」")
        if h_matches:
            print(f"🔴 ハングル検出: {title[:40]}")
            print(f"   検出: {list(set(h_matches))[:3]}")

if not cyrillic_issues:
    print("✅ キリル文字・ハングルなし")

# =============================
# 3. 既知誤訳チェック + 自動修正
# =============================
print(f"\n{'=' * 50}")
print("📖 3. 既知誤訳チェック（PROPER_NOUN_FIXES・自動修正付き）")
print("=" * 50)

for post in posts:
    slug = post.get("slug", "")
    title = post.get("title", "") or ""
    body = post.get("body", "") or ""
    excerpt = post.get("excerpt", "") or ""
    full_text = title + body + excerpt
    found = {wrong: correct for wrong, correct in PROPER_NOUN_FIXES.items() if wrong in full_text}
    if found:
        # 自動修正
        nt, nb, ne = title, body, excerpt
        for wrong, correct in found.items():
            nt, nb, ne = nt.replace(wrong, correct), nb.replace(wrong, correct), ne.replace(wrong, correct)
        res2 = requests.patch(
            f"{SUPABASE_URL}/rest/v1/posts?slug=eq.{slug}",
            headers=headers_sb,
            json={"title": nt, "body": nb, "excerpt": ne}
        )
        if res2.status_code == 204:
            auto_fixed.append(slug)
            print(f"🔧 自動修正: {title[:40]}")
            for w, c in found.items():
                print(f"   「{w}」→「{c}」")
        else:
            known_issues.append({"slug": slug, "title": title, "fixes": found})
            print(f"🔴 修正失敗: {title[:40]}")

if not known_issues:
    print("✅ 既知誤訳なし")

# =============================
# 4. ソース記事との事実照合
# =============================
print(f"\n{'=' * 50}")
print("🔎 4. ソース記事との事実照合")
print("=" * 50)

def scrape_source(url):
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        text = re.sub(r'<[^>]+>', ' ', r.text)
        text = re.sub(r'\s+', ' ', text)
        return text[:3000]
    except:
        return ""

# 直近10件のみソース照合（負荷軽減）
for post in posts[:10]:
    slug = post.get("slug", "")
    title = post.get("title", "") or ""
    body = post.get("body", "") or ""
    source_url = post.get("source_url", "") or ""

    if not source_url:
        continue

    source_text = scrape_source(source_url)
    if not source_text:
        print(f"⚠️ スクレイプ失敗: {slug[:40]}")
        continue

    # 数字を抽出して照合
    jp_numbers = set(re.findall(r'\d+(?:,\d+)*(?:\.\d+)?', body))
    src_numbers = set(re.findall(r'\d+(?:,\d+)*(?:\.\d+)?', source_text))

    # 日本語記事にあってソースにない数字（4桁以上の数字は年として除外）
    suspicious = {n for n in jp_numbers - src_numbers if len(n) != 4 and n.replace(',','').replace('.','').isdigit() and int(n.replace(',','').split('.')[0]) > 100}

    if suspicious:
        source_mismatch_issues.append({
            "slug": slug,
            "title": title,
            "suspicious_numbers": list(suspicious)[:5],
            "url": f"https://www.japan-truth.com/posts/{slug}"
        })
        print(f"⚠️ 数字不一致: {title[:40]}")
        print(f"   要確認数字: {list(suspicious)[:5]}")
    else:
        print(f"✅ OK: {title[:40]}")

    time.sleep(1)

# =============================
# 5. AI誤訳チェック + 新規パターン提案
# =============================
print(f"\n{'=' * 50}")
print("🔍 5. AI誤訳チェック（新規パターン提案付き）")
print("=" * 50)

for i, post in enumerate(posts):
    slug = post.get("slug", "")
    title_jp = post.get("title", "") or ""
    body = post.get("body", "")[:3000]
    source_title = re.sub(r'^\d{4}-\d{2}-\d{2}-\d{6}-', '', slug).replace("-", " ")

    prompt = (
        f"Japanese translation quality check.\n"
        f"English source: {source_title}\n"
        f"Japanese title: {title_jp}\n"
        f"Japanese body: {body}\n\n"
        f"STRICT rules - only flag if you are 100%% certain:\n"
        f"1. English words left untranslated in brackets: [Name] or [Organization]\n"
        f"2. pleads guilty translated as 起訴 (must be 有罪を認めた)\n"
        f"3. Senate(上院) and House(下院) are confused\n"
        f"4. A number in the Japanese article that is clearly different from the source\n\n"
        f"DO NOT flag: style differences, minor wording choices, correct katakana names\n"
        f"DO NOT suggest alternative translations unless clearly wrong\n"
        f"If nothing clearly wrong: respond only with OK\n"
        f"Max 1 issue. Be conservative."
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
                    "max_tokens": 150,
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

            if "SUGGEST:" in response:
                for line in response.split("\n"):
                    if line.startswith("SUGGEST:"):
                        new_proper_noun_suggestions.append(f"{slug[:30]}: {line}")
                        print(f"💡 新パターン提案: {line[:80]}")

            if response != "OK" and "FIX:" in response:
                translation_issues.append({
                    "slug": slug,
                    "title": title_jp,
                    "issues": response,
                    "url": f"https://www.japan-truth.com/posts/{slug}"
                })
                print(f"🚨 {slug[:40]}")
                print(f"   {response[:120]}")
            elif "SUGGEST:" not in response:
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
print(f"  🔴 重複記事:        {len(duplicates)}件")
print(f"  🔧 自動修正済み:    {len(set(auto_fixed))}件")
print(f"  🚫 禁止ワード残:    {len(forbidden_issues)}件")
print(f"  🔤 文字混入:        {len(cyrillic_issues)}件")
print(f"  📖 既知誤訳残:      {len(known_issues)}件")
print(f"  🔎 数字不一致:      {len(source_mismatch_issues)}件")
print(f"  🚨 AI誤訳疑い:      {len(translation_issues)}件")
print(f"  💡 新パターン提案:  {len(new_proper_noun_suggestions)}件")
print("=" * 50)

if new_proper_noun_suggestions:
    print("\n💡 PROPER_NOUN_FIXESへの追加候補:")
    for s in new_proper_noun_suggestions:
        print(f"  {s}")

# PROPER_NOUN_FIXESに自動追加（FIX:形式のみ）
auto_added = []
try:
    nm_content = open("news_monitor.py").read()
    for suggestion in new_proper_noun_suggestions:
        # "FIX: [wrong] -> [correct] | reason" 形式を解析
        match = re.search(r'FIX:\s*([^->]+?)\s*->\s*([^|]+?)(?:\s*\|.*)?$', suggestion)
        if not match:
            continue
        wrong = match.group(1).strip()
        correct = match.group(2).strip()
        # 既に登録済みならスキップ
        if wrong in nm_content or len(wrong) < 3 or len(correct) < 3:
            continue
        # PROPER_NOUN_FIXESに追加
        insert_line = '    "カシュ・パテル": "カッシュ・パテル",'
        new_line = f'    "{wrong}": "{correct}",'
        nm_content = nm_content.replace(insert_line, insert_line + "\n" + new_line)
        auto_added.append(f"{wrong} → {correct}")
    
    if auto_added:
        open("news_monitor.py", "w").write(nm_content)
        import ast
        ast.parse(nm_content)
        print(f"\n✅ PROPER_NOUN_FIXESに{len(auto_added)}件自動追加:")
        for a in auto_added:
            print(f"  {a}")
        # Gitコミット
        import subprocess
        subprocess.run(["git", "add", "news_monitor.py"], cwd=".")
        subprocess.run(["git", "commit", "-m", f"fix: translation_checkerが{len(auto_added)}件の誤訳パターンを自動追加"], cwd=".")
        subprocess.run(["git", "push", "origin", "main"], cwd=".")
except Exception as e:
    print(f"⚠️ 自動追加失敗: {e}")


# =============================
# 2.7 カタカナ表記揺れチェック
# =============================
print(f"\n{'=' * 50}")
print("🔤 2.7 カタカナ表記揺れチェック")
print("=" * 50)

import re as _re
from collections import Counter as _Counter

# 全タイトルからカタカナ固有名詞を抽出
katakana_counter = _Counter()
slug_map = {}
for post in posts:
    title = post.get("title", "") or ""
    words = _re.findall(r"[ァ-ヴー]{3,}", title)
    for w in words:
        katakana_counter[w] += 1
        if w not in slug_map:
            slug_map[w] = (post.get("slug",""), title[:40])

# 既知の表記揺れペアをチェック
known_variants = [
    ("ヘグゼス", "ヘグセス"),
    ("アラーグチ", "アラグチ"),
    ("スピアス", "スピアーズ"),
    ("スピアーズ", "スピアーズ"),
    ("マダウィ", "マフダウィ"),
    ("チアハナ", "ティファナ"),
    ("ユースフ", "ユーサフ"),
    ("トレウアメニ", "チュアメニ"),
]

variant_issues = []
for wrong, correct in known_variants:
    if wrong in katakana_counter:
        variant_issues.append((wrong, correct, slug_map.get(wrong, ("",""))[1]))
        print(f"⚠️ 表記揺れ: 「{wrong}」→「{correct}」が正しい")

# 出現1回のみの珍しい固有名詞を報告
rare_words = [(w, c, slug_map.get(w,("",""))[1]) for w, c in katakana_counter.items() if c == 1 and len(w) >= 5]
if rare_words:
    print(f"\n💡 要確認の固有名詞（出現1回）: {len(rare_words)}件")
    for w, c, title in rare_words[:10]:
        print(f"  「{w}」: {title[:40]}")

if not variant_issues and not rare_words:
    print("✅ 表記揺れなし")

# =============================
# 5.5 excerpt品質チェック＋自動再生成
# =============================
print(f"\n{'=' * 50}")
print("📝 excerpt品質チェック")
print("=" * 50)

bad_excerpt_patterns = [
    "が発表された", "が明らかになった", "が行われた", "が報じられた",
    "が開催された", "が示された", "が確認された", "について述べた",
]
excerpt_issues = []
for post in posts:
    slug = post.get("slug", "")
    title = post.get("title", "") or ""
    excerpt = post.get("excerpt", "") or ""
    if len(excerpt) < 20:
        excerpt_issues.append({"slug": slug, "title": title, "reason": "短すぎる", "excerpt": excerpt})
        print(f"⚠️ 短いexcerpt: {title[:40]}")
    elif any(w in excerpt for w in bad_excerpt_patterns):
        found = [w for w in bad_excerpt_patterns if w in excerpt]
        excerpt_issues.append({"slug": slug, "title": title, "reason": f"平凡: {found[0]}", "excerpt": excerpt})
        print(f"⚠️ 平凡なexcerpt: {title[:40]} → {found[0]}")

if not excerpt_issues:
    print("✅ excerpt問題なし")

# =============================
# 6. 重複記事の自動削除
# =============================
if duplicates:
    print(f"\n{'=' * 50}")
    print("🗑️ 重複記事の自動削除")
    print("=" * 50)
    for dup in duplicates:
        slug = dup.get("slug2","")
        if not slug:
            continue
        res_del = requests.delete(
            f"{SUPABASE_URL}/rest/v1/posts?slug=eq.{slug}",
            headers=headers_sb
        )
        if res_del.status_code == 204:
            print(f"✅ 自動削除: {slug[:55]}")
        else:
            print(f"❌ 削除失敗: {slug[:55]}")

with open("translation_check_result.json", "w", encoding="utf-8") as f:
    json.dump({
        "checked": len(posts),
        "auto_fixed": len(set(auto_fixed)),
        "duplicates": duplicates,
        "forbidden_issues": forbidden_issues,
        "cyrillic_issues": cyrillic_issues,
        "known_issues": known_issues,
        "source_mismatch_issues": source_mismatch_issues,
        "translation_issues": translation_issues,
        "new_proper_noun_suggestions": new_proper_noun_suggestions,
    }, f, ensure_ascii=False, indent=2)

print("\n✅ 結果をtranslation_check_result.jsonに保存")
