#!/usr/bin/env python3
"""
JapanTruth Premium Article Writer
使い方: python3 premium_writer.py "テーマ（例：イラン情勢と日本のエネルギー安全保障）"
"""

import sys
import os
import json
import time
import requests
import re
from datetime import datetime
import pytz

# ── 設定 ──────────────────────────────────────────────
GROQ_API_KEYS = [
    os.environ.get("GROQ_API_KEY_1", ""),
    os.environ.get("GROQ_API_KEY_2", ""),
    os.environ.get("GROQ_API_KEY_3", ""),
]
GROQ_KEY_INDEX = 0

SUPABASE_URL = "https://xhvvxfvxkqcadqhdqtmn.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

UNSPLASH_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "W_yPkVheue0jTekukRXjWWPtnExdTK7afLtvMZ8P2aA")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "AceuFK6SEmEkAbKMBtdW6miI2cl2hsNO9BNK4hghaMg6gzNT4eaEhY8B")
RSS2JSON_KEY = os.environ.get("RSS2JSON_API_KEY", "xwoqrorti5dmqi68ynhvmrpgat0wpkstby21fi2y")

JST = pytz.timezone("Asia/Tokyo")

CLOUDINARY_CLOUD = os.environ.get("CLOUDINARY_CLOUD_NAME", "dnqswecpg")
CLOUDINARY_KEY = os.environ.get("CLOUDINARY_API_KEY", "123954577221463")
CLOUDINARY_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

# ── Groq API ──────────────────────────────────────────
def call_groq(messages, model="qwen/qwen3-32b", temperature=0.5, max_tokens=6000):
    global GROQ_KEY_INDEX
    for _ in range(len(GROQ_API_KEYS)):
        key = GROQ_API_KEYS[GROQ_KEY_INDEX % len(GROQ_API_KEYS)]
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        data = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            }
        try:
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=120)
            result = res.json()
            if "error" in result:
                print(f"⚠️ Groqエラー: {result['error']}")
                if "rate_limit" in str(result["error"]) or "413" in str(result["error"]):
                    GROQ_KEY_INDEX += 1
                    time.sleep(5)
                    continue
                return None
            return result
        except Exception as e:
            print(f"⚠️ Groq接続エラー: {type(e).__name__}: {e}")
            return None
    print("⚠️ 全APIキー失敗")
    return None

# ── ニュース収集 ──────────────────────────────────────
RSS_SOURCES = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.bloomberg.com/markets/news.rss",
]

def fetch_rss(url):
    try:
        api = f"https://api.rss2json.com/v1/api.json?rss_url={url}&api_key={RSS2JSON_KEY}&count=10"
        res = requests.get(api, timeout=10)
        data = res.json()
        return data.get("items", [])
    except:
        return []

def search_related_articles(theme):
    """テーマに関連するニュースを収集"""
    print(f"🔍 関連記事を収集中: {theme}")
    all_articles = []
    for url in RSS_SOURCES:
        items = fetch_rss(url)
        all_articles.extend(items)
        time.sleep(0.5)

    # テーマに関連する記事をフィルタリング（日本語テーマを英語キーワードに変換）
    jp_to_en = {
        "円安": ["yen", "dollar", "currency", "forex"],
        "円高": ["yen", "currency", "forex"],
        "投資": ["invest", "market", "stock", "asset"],
        "資産": ["asset", "wealth", "portfolio"],
        "防衛": ["defense", "protect", "hedge"],
        "エネルギー": ["energy", "oil", "gas"],
        "イラン": ["iran"],
        "中国": ["china", "chinese"],
        "米国": ["us", "america", "trump"],
        "日本": ["japan", "japanese"],
        "株": ["stock", "equity", "market"],
        "金利": ["rate", "interest", "fed"],
        "インフレ": ["inflation", "cpi", "price"],
        "戦争": ["war", "conflict", "military"],
        "貿易": ["trade", "tariff", "export"],
    }
    keywords = []
    for jp, en_list in jp_to_en.items():
        if jp in theme:
            keywords.extend(en_list)
    # 英語のままのキーワードも追加
    keywords.extend([w.lower() for w in theme.split() if len(w) > 3 and w.isascii()])
    if not keywords:
        keywords = ["economy", "market", "japan", "finance"]

    related = []
    for article in all_articles:
        title = article.get("title", "").lower()
        desc = article.get("description", "").lower()
        if any(kw in title or kw in desc for kw in keywords):
            related.append(article)

    print(f"✅ 関連記事: {len(related)}件 / 全{len(all_articles)}件")
    return related[:4]  # 最大4件

def scrape_content(url):
    try:
        from bs4 import BeautifulSoup
        res = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return text[:3000]
    except:
        return ""

# ── 画像取得 ──────────────────────────────────────────
def get_image(keyword, slug):
    # Unsplash試行
    try:
        res = requests.get(
            f"https://api.unsplash.com/search/photos?query={keyword}&per_page=1",
            headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
            timeout=10
        )
        data = res.json()
        if data.get("results"):
            url = data["results"][0]["urls"]["regular"]
            img_data = requests.get(url, timeout=15).content
            local_path = f"/tmp/{slug}.jpg"
            with open(local_path, "wb") as f:
                f.write(img_data)
            print(f"🖼️ Unsplash画像取得完了: {local_path}")
            return local_path
    except Exception as e:
        print(f"⚠️ Unsplash失敗: {e}")
    # Pexels試行
    try:
        res = requests.get(
            f"https://api.pexels.com/v1/search?query={keyword}&per_page=1",
            headers={"Authorization": PEXELS_KEY},
            timeout=10
        )
        data = res.json()
        if data.get("photos"):
            url = data["photos"][0]["src"]["large"]
            img_data = requests.get(url, timeout=15).content
            local_path = f"/tmp/{slug}.jpg"
            with open(local_path, "wb") as f:
                f.write(img_data)
            print(f"🖼️ Pexels画像取得完了: {local_path}")
            return local_path
    except Exception as e:
        print(f"⚠️ Pexels失敗: {e}")
    return None

def upload_to_cloudinary(local_path, slug):
    try:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(cloud_name=CLOUDINARY_CLOUD, api_key=CLOUDINARY_KEY, api_secret=CLOUDINARY_SECRET)
        result = cloudinary.uploader.upload(local_path, public_id=slug, overwrite=True, resource_type="image")
        public_id = result.get("public_id", "")
        url = f"https://res.cloudinary.com/{CLOUDINARY_CLOUD}/image/upload/f_webp,q_auto/{public_id}"
        print(f"☁️ Cloudinaryアップロード完了: {url}")
        return url
    except Exception as e:
        print(f"⚠️ Cloudinaryアップロード失敗: {e}")
        return "/japantruth.png"

# ── プレミアム記事生成 ────────────────────────────────
def generate_premium_article(theme, articles):
    # 収集した記事の内容をまとめる
    sources_text = ""
    for i, article in enumerate(articles[:4], 1):
        title = article.get("title", "")
        desc = article.get("description", "")
        sources_text += f"- {title}\n"

    system_prompt = (
        "You are a senior analyst at JapanTruth, an independent Japanese-language media. "
        "Write premium deep-dive analysis articles in Japanese only (だ・である style). "
        "Focus on impact on Japanese investors, yen, energy, and assets. "
        "Include specific actionable advice. "
        "NEVER use: 可能性がある / かもしれない / グローバル市場 / 国際社会. "
        "Output ONLY valid JSON, no markdown, no code blocks, no thinking tags: "
        '{"title": "string", "excerpt": "string", "keyword": "english", "category": "investment", "body": "string"}'
    )

    prompt = (
        f"テーマ「{theme}」の深掘り投資分析記事を日本語で書け。\n"
        f"参考ニュース:{sources_text}\n"
        "bodyに以下5セクションを含めること(合計2000字以上):\n"
        "## 何が起きているのか ## 背景と構造的問題 ## 日本への具体的影響 ## JapanTruthの分析 ## 投資家が今すべき行動"
    )

    result = call_groq(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=4000
    )

    if not result:
        print(f"⚠️ Groq結果なし: {result}")
        return None

    try:
        raw = result["choices"][0]["message"]["content"]
        # <think>タグを除去
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        # JSON部分を抽出
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            raw = match.group(0)
        parsed = json.loads(raw)
        # 後処理
        for key in ["title", "excerpt", "body"]:
            if key in parsed:
                parsed[key] = parsed[key].replace("日本Truth", "JapanTruth")
                parsed[key] = parsed[key].replace("可能性がある", "見込まれる")
                parsed[key] = parsed[key].replace("かもしれない", "と判断される")
                parsed[key] = parsed[key].replace("国際社会", "各国政府")
                parsed[key] = parsed[key].replace("グローバル市場", "世界市場")
        return parsed
    except Exception as e:
        print(f"⚠️ JSONパース失敗: {e}")
        print(f"RAW FULL: {raw}")
        return None

# ── Supabase保存 ──────────────────────────────────────
def save_to_supabase(slug, title, date_str, time_str, category, excerpt, image_url, body):
    if not SUPABASE_KEY:
        print("⚠️ SUPABASE_SERVICE_KEY未設定")
        return False
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    post_data = {
        "slug": slug,
        "title": title,
        "date": f"{date_str} {time_str}",
        "category": category,
        "excerpt": excerpt,
        "premium": True,
        "image": image_url,
        "source": "JapanTruth Premium",
        "tags": "#プレミアム #投資 #資産防衛 #JapanTruth",
        "source_url": "https://www.japan-truth.com/premium",
        "body": body,
    }
    res = requests.post(f"{SUPABASE_URL}/rest/v1/posts", headers=headers, json=post_data)
    if res.status_code in [200, 201]:
        print(f"✅ Supabase保存完了: {slug}")
        return True
    else:
        print(f"⚠️ Supabase保存失敗: {res.status_code} {res.text[:100]}")
        return False

# ── テーマ自動選択 ──────────────────────────────────────

def auto_select_theme():
    """最新ニュースから最も重要なテーマを自動選択"""
    print("🤖 テーマを自動選択中...")
    all_articles = []
    for url in RSS_SOURCES:
        items = fetch_rss(url)
        all_articles.extend(items)
        time.sleep(0.3)

    # タイトルリストを作成
    titles = [a.get("title", "") for a in all_articles[:30] if a.get("title")]
    titles_text = "\n".join(f"- {t}" for t in titles)

    # 過去のプレミアム記事テーマを取得して除外
    past_themes = []
    try:
        import requests as _rq
        _sb_url = "https://xhvvxfvxkqcadqhdqtmn.supabase.co"
        _sb_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        _h = {"apikey": _sb_key, "Authorization": f"Bearer {_sb_key}"}
        _res = _rq.get(f"{_sb_url}/rest/v1/posts?select=title&premium=eq.true&order=date.desc&limit=10", headers=_h, timeout=5)
        past_themes = [p.get("title","") for p in _res.json()]
        print(f"📋 過去のプレミアム記事: {len(past_themes)}件除外")
    except Exception as e:
        print(f"⚠️ 過去テーマ取得失敗: {e}")
    past_themes_text = "\n".join(f"- {t}" for t in past_themes)

    key = GROQ_API_KEYS[0]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "You are a Japanese financial analyst. Output only a JSON object."},
            {"role": "user", "content": f"以下のニュースから日本人投資家・資産防衛の観点で最も重要なテーマを1つ選び、日本語で具体的なテーマ名を返せ。\n\n【過去に書いたテーマ（重複禁止）】\n{past_themes_text}\n\nニュース一覧:\n{titles_text}\n\n出力形式: {{\"theme\": \"テーマ名\"}}"}
        ],
        "max_tokens": 100,
        "temperature": 0.3,
    }
    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=30)
    result = res.json()
    raw = result["choices"][0]["message"]["content"]
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    parsed = json.loads(raw)
    theme = parsed.get("theme", "円安と日本人投資家の資産防衛策")
    theme = theme[:30]  # 30字以内に制限
    print(f"✅ 自動選択テーマ: {theme}")
    return theme


# ── メイン ────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        theme = auto_select_theme()
    else:
        theme = sys.argv[1]
    print(f"\n🚀 プレミアム記事生成開始: {theme}\n")

    # 関連記事収集
    articles = search_related_articles(theme)
    if not articles:
        print("⚠️ 関連記事が見つかりませんでした。一般的な知識で生成します。")
        articles = []

    # 記事生成
    print("📝 記事生成中...")
    result = generate_premium_article(theme, articles)
    if not result:
        print("❌ 記事生成失敗")
        sys.exit(1)

    # スラッグ生成
    now = datetime.now(JST)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    # 日本語テーマから英語スラッグを生成
    slug_map = {
        "円安": "yen-depreciation", "円高": "yen-appreciation",
        "投資": "investment", "資産": "assets", "防衛": "defense",
        "エネルギー": "energy", "イラン": "iran", "中国": "china",
        "米国": "us", "日本": "japan", "株": "stocks",
        "金利": "interest-rate", "インフレ": "inflation",
        "戦争": "war", "貿易": "trade", "経済": "economy",
    }
    slug_base = theme
    for jp, en in slug_map.items():
        slug_base = slug_base.replace(jp, en)
    slug_base = re.sub(r'[^a-z0-9-]', '-', slug_base.lower())
    slug_base = re.sub(r'-+', '-', slug_base).strip('-')[:40]
    slug = f"{slug_base}-{now.strftime('%m%d%H%M')}"

    # 記事プレビュー
    print(f"\n{'='*50}")
    print(f"タイトル: {result.get('title', '')}")
    print(f"カテゴリ: {result.get('category', 'investment')}")
    print(f"本文文字数: {len(result.get('body', ''))}")
    print(f"{'='*50}\n")

    # 画像取得・アップロード
    print("🖼️ 画像取得中...")
    keyword = result.get("keyword", theme.split()[0])
    local_path = get_image(keyword, slug)
    if local_path and CLOUDINARY_SECRET:
        image_url = upload_to_cloudinary(local_path, slug)
    else:
        image_url = "/japantruth.png"

    # Supabase保存
    save_to_supabase(
        slug,
        result.get("title", theme),
        date_str,
        time_str,
        result.get("category", "investment"),
        result.get("excerpt", ""),
        image_url,
        result.get("body", "")
    )

    print(f"\n✅ プレミアム記事公開完了！")
    print(f"URL: https://www.japan-truth.com/posts/{slug}")

if __name__ == "__main__":
    main()
