import feedparser
import requests
import os
import json
import time
import subprocess
import re
import hashlib
from datetime import datetime, timezone, timedelta
JST = timezone(timedelta(hours=9))
from PIL import Image
from io import BytesIO

import os
GROQ_API_KEYS = [
    os.environ.get("GROQ_API_KEY_1", ""),
    os.environ.get("GROQ_API_KEY_2", ""),
    os.environ.get("GROQ_API_KEY_3", ""),
]
GROQ_API_KEY = GROQ_API_KEYS[0]
_key_index = 0

def get_next_key():
    global _key_index, GROQ_API_KEY
    _key_index = (_key_index + 1) % len(GROQ_API_KEYS)
    GROQ_API_KEY = GROQ_API_KEYS[_key_index]
    print(f"🔑 APIキー切り替え: key{_key_index + 1}")
    return GROQ_API_KEY
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
X_API_KEY = os.environ.get("X_API_KEY", "")
X_API_SECRET = os.environ.get("X_API_SECRET", "")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET", "")
GITHUB_REPO_PATH = os.environ.get("GITHUB_REPO_PATH", os.path.expanduser("~/japantruth-nextjs"))

if not os.path.exists(os.path.join(GITHUB_REPO_PATH, "src")):
    import subprocess as _sp
    _token = os.environ.get("GITHUB_TOKEN", "")
    _clone_url = f"https://JapanTruth:{_token}@github.com/JapanTruth/japantruth-nextjs.git"
    print(f"🔄 リポジトリをclone中: {GITHUB_REPO_PATH}")
    _sp.run(["git", "clone", "--depth=1", _clone_url, GITHUB_REPO_PATH], check=True)
    print(f"✅ リポジトリをclone完了: {GITHUB_REPO_PATH}")
else:
    print(f"✅ リポジトリ既存: {GITHUB_REPO_PATH}")
_seen_dir = GITHUB_REPO_PATH if os.path.exists(os.path.join(GITHUB_REPO_PATH, "src")) else os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(_seen_dir, "seen_articles.json")

RSS_FEEDS = [
    # 国際
    {"url": "https://www.aljazeera.com/xml/rss/all.xml", "category": "international", "source": "Al Jazeera"},
    {"url": "https://www.scmp.com/rss/91/feed", "category": "international", "source": "South China Morning Post"},
    {"url": "http://feeds.bbci.co.uk/news/world/rss.xml", "category": "international", "source": "BBC"},
    # 経済
    {"url": "https://www.cnbc.com/id/10000664/device/rss/rss.html", "category": "economy", "source": "CNBC"},
    {"url": "https://asia.nikkei.com/rss/feed/nar", "category": "economy", "source": "Nikkei Asia"},
    {"url": "https://rss.dw.com/rdf/rss-en-all", "category": "economy", "source": "DW News"},
    # 投資
    {"url": "https://fortune.com/feed/", "category": "investment", "source": "Fortune"},
    {"url": "https://feeds.bloomberg.com/markets/news.rss", "category": "investment", "source": "Bloomberg"},
    {"url": "https://www.fool.com/feeds/index.aspx", "category": "investment", "source": "Motley Fool"},
    # 政治
    {"url": "https://feeds.bbci.co.uk/news/politics/rss.xml", "category": "politics", "source": "BBC Politics"},
    {"url": "https://rss.politico.com/politics-news.xml", "category": "politics", "source": "Politico"},
    {"url": "https://feeds.npr.org/1004/rss.xml", "category": "politics", "source": "NPR World"},
    # 文化
    {"url": "https://www.theguardian.com/culture/rss", "category": "culture", "source": "The Guardian"},
    {"url": "https://www.theatlantic.com/feed/all/", "category": "culture", "source": "The Atlantic"},
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            data = json.load(f)
            if isinstance(data, dict):
                return set(data.get("articles", [])), set(data.get("images", []))
            return set(data), set()
    return set(), set()

def save_seen(seen, seen_images):
    with open(SEEN_FILE, "w") as f:
        json.dump({"articles": list(seen)[-500:], "images": list(seen_images)[-200:]}, f)


def parse_rate_limit_msg(msg):
    """レート制限メッセージからTPD残りとリセット時間を解析"""
    import re
    remaining = None
    reset_time = None
    limit_match = re.search(r'Limit (\d+), Used (\d+)', msg)
    if limit_match:
        limit = int(limit_match.group(1))
        used = int(limit_match.group(2))
        remaining = limit - used
    reset_match = re.search(r'try again in (.+?)\.', msg)
    if reset_match:
        reset_time = reset_match.group(1)
    return remaining, reset_time

def screen_article(title, summary=""):
    """ブレイキングニュースか判定＋画像キーワード生成（8bモデル）"""
    snippet = summary[:100] if summary else ""
    prompt = (
        f"Title: {title}\nSnippet: {snippet}\n\n"
        "1. Is this newsworthy? Answer yes if: war/conflict, diplomacy/summit, economic news, politics, business/corporate news, crime, social issues, sports, science/tech, environment, or any topic readers would find interesting. Answer no only for clearly trivial/irrelevant content.\n"
        "2. Best 2-3 English words for Unsplash photo search. No abbreviations, acronyms, or proper nouns. Use common visual concepts only (e.g. parliament building, politician speech, protest crowd, military ship, stock market).\n\n"
        "Reply in exactly this format:\n"
        "NEWSWORTHY: yes\n"
        "IMAGE: parliament building\n"
        "or\n"
        "NEWSWORTHY: no\n"
        "IMAGE: soccer match"
    )
    data = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 30,
        "temperature": 0
    }
    for attempt in range(len(GROQ_API_KEYS)):
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        try:
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
            result = res.json()
            if "error" in result:
                if "rate_limit" in str(result["error"]):
                    msg = result["error"].get("message", "")
                    remaining, reset_time = parse_rate_limit_msg(msg)
                    print(f"⏳ レート制限 | 残り: {remaining:,}トークン | リセット: {reset_time}")
                    get_next_key()
                    continue
                return False, ""
            text = result["choices"][0]["message"]["content"].strip().lower()
            is_breaking = "newsworthy: yes" in text
            image_kw = ""
            for line in text.split("\n"):
                if line.startswith("image:"):
                    image_kw = line.replace("image:", "").strip()
                    break
            return is_breaking, image_kw
        except:
            return False, ""
    return "rate_limit"

def summarize_article(title, content, category):
    system_prompt = (
        "You are a senior journalist at JapanTruth, an international news media for Japanese readers.\n"
        "あなたはJapanTruthのシニアジャーナリストです。政治・経済・国際情勢の専門家として英語記事を高品質な日本語記事に変換してください。\n\n"
        "ABSOLUTE RULES / 絶対ルール:\n"
        "- Output language: Japanese only（「だ・である」体、例外なし）\n"
        "- 固有名詞（人名・企業名・地名）は日本語で一般的に使われる表記を使用する。例：Sri Lanka→スリランカ、Powell→パウエル、Ukraine→ウクライナ、Berkshire→バークシャー、Warren Buffett→ウォーレン・バフェット、Donald Trump→ドナルド・トランプ、Federal Reserve→連邦準備制度、Iran→イラン、Israel→イスラエル、Gaza→ガザ、Elon Musk→イーロン・マスク、Tesla→テスラ、Apple→アップル、Microsoft→マイクロソフト、Google→グーグル、Amazon→アマゾン、Samsung→サムスン、TSMC→TSMC、NATO→NATO、OPEC→OPEC、IMF→IMF、WHO→WHO、EU→EU、UN→国連、CIA→CIA、FBI→FBI、Pentagon→ペンタゴン、Wall Street→ウォール街、Silicon Valley→シリコンバレー、White House→ホワイトハウス、Congress→議会、Senate→上院、Hamas→ハマス、Hezbollah→ヒズボラ、Putin→プーチン、Zelensky→ゼレンスキー、Modi→モディ、Macron→マクロン、Starmer→スターマー。日本語の慣用表記が存在する場合はそれを優先し、ない場合のみカタカナに音訳する\n"
        "- 数字・日付・固有名詞は必ず元記事に存在するものだけを使用する\n"
        "- 元記事にない情報・文脈・統計・人名を一切追加しない\n"
        "- Do NOT invent any proper nouns, dates, names, or statistics not present in the source\n"
        "- If the source article lacks detail, write fewer sentences rather than fabricating content\n\n"
        "FACT INTEGRITY / 事実の正確性:\n"
        "- Every name, number, and event must be directly traceable to the source text\n"
        "- 背景セクションでは、記事に明示された事実＋一般常識レベルの文脈のみ使用可。架空の詳細は禁止\n"
        "- 情報が不足している場合は文数を減らす。捏造して埋めない\n\n"
        "FORBIDDEN PHRASES / 禁止表現:\n"
        "- 〜の重要性を示す / 見守る / 注視する / 検討する / 可能性がある\n"
        "- Vague filler sentences that add no factual value\n"
        "- Any content not grounded in the source article\n\n"
        "JAPANTRUTH視点のルール:\n"
        "- 日本への具体的な影響がある場合：日本経済・外交・安全保障への影響を分析\n"
        "- 日本との関連が薄い場合：無理に日本に結びつけず、世界経済・地政学・国際秩序への影響に集中する\n"
        "- 推奨表現：〜が予想される / 〜の公算が大きい / 〜と見られる / 〜は避けられない\n"
        "- 3〜4文で具体的かつ断定的に書く\n\n"
        "OUTPUT FORMAT: Respond ONLY with a valid JSON object. No markdown, no extra text.\n"
        "Example:\n"
        '{"title": "日本語タイトル", "excerpt": "日本語1文", "keyword": "english", "category": "politics", "body": "## 何が起きているのか\\n本文..."}'
    )

    prompt = (
        f"以下の英語記事を日本語記事に変換し、JSON形式で返せ。\n"
        f"⚠️ 元記事に存在しない固有名詞・数字・日付を絶対に追加するな。情報が少なければ文数を減らせ。\n\n"
        f"タイトル: {title}\n本文: {content[:4000]}\n\n"
        "JSONのフィールド:\n"
        "- title: 断定的な日本語タイトル（元記事の数字か固有名詞を含む）\n"
        "- excerpt: 誰が・何を・なぜを含む日本語1文（元記事の事実のみ）\n"
        "- keyword: 1-3 English words for Unsplash photo search. MUST be a specific, visually searchable concept. GOOD: country names (Japan, Iran, Germany), city names (Tokyo, London), company logos (Tesla, Samsung), natural objects (oil rig, cargo ship, military jet). BAD: abstract words (talks, concerns, tensions, house, makers, profits, signals, outlines, targets, urges, slams, calls, vows, warns, seeks, pushes, plans, deals). If no clear visual concept exists, use the most relevant country name.\n"
        "- category: Choose exactly one:\n"
        "  politics: elections, government, diplomacy, policy, military, security, politicians\n"
        "  economy: corporate earnings, GDP, employment, trade, inflation, industry, business\n"
        "  international: conflict, war, international organizations, treaties, refugees, terrorism, geopolitics\n"
        "  investment: stocks, bonds, crypto, financial markets, central banks, interest rates, forex\n"
        "  culture: sports, entertainment, science, technology, society, environment, education, health\n"
        "- body: Write in the following format:\n"
        "  ## 何が起きているのか\\n"
        "  (3-5 sentences. Cover key facts: who, what, when, where, why, how. Use only numbers/names from source. If source lacks detail, write 3 sentences only.)\\n\\n"
        "  ## 背景\\n"
        "  (3-5 sentences. Historical and political context using ONLY facts stated in the article plus basic general knowledge. Do NOT invent names, dates, or statistics. If detail is lacking, write 3 sentences.)\\n\\n"
        "  ## JapanTruthの視点\\n"
        "  (3-4 sentences. If clear Japan impact exists: analyze effect on Japan economy/diplomacy/security. If Japan connection is weak: focus on global economic or geopolitical implications instead. Never force a Japan connection. Use: 〜が予想される/〜の公算が大きい/〜と見られる/〜は避けられない. FORBIDDEN: 可能性がある/見守る/注視する.)\\n"
    )

    data = {
        "model": "qwen/qwen3-32b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 3000,
        "temperature": 0.5,
        "response_format": {"type": "json_object"}
    }

    for attempt in range(len(GROQ_API_KEYS)):
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        try:
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
            result = res.json()
            # result already set
            if "error" in result:
                if "rate_limit" in str(result["error"]):
                    msg = result["error"].get("message", "")
                    remaining, reset_time = parse_rate_limit_msg(msg)
                    print(f"⏳ レート制限 | 残り: {remaining:,}トークン | リセット: {reset_time}")
                    get_next_key()
                    continue
            text = result["choices"][0]["message"]["content"]

            import json as _json
            raw = text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"```json|```", "", raw).strip()
            parsed = _json.loads(raw)
            cat_raw = parsed.get("category", "international").lower()
            cat = next((c for c in ["politics","economy","international","culture","investment"] if c in cat_raw), "international")
            return {
                "title": parsed.get("title", "").strip(),
                "excerpt": parsed.get("excerpt", "").strip(),
                "keyword": parsed.get("keyword", "news"),
                "category": cat,
                "body": parsed.get("body", "").strip(),
                "tokens": result.get("usage", {}).get("total_tokens", 0),
                "tokens_input": result.get("usage", {}).get("prompt_tokens", 0),
                "tokens_output": result.get("usage", {}).get("completion_tokens", 0),
            }
        except Exception as e:
            print(f"⚠️ 試行{attempt+1}失敗: {type(e).__name__}: {e}")
            time.sleep(10)
    return None

def generate_tags(title, category):
    category_tags = {
        "politics": "#政治 #外交",
        "economy": "#経済 #ビジネス",
        "international": "#国際情勢 #国際ニュース",
        "investment": "#投資 #金融市場",
        "culture": "#文化 #社会",
    }
    base_tags = category_tags.get(category, "#国際ニュース")
    for attempt in range(len(GROQ_API_KEYS)):
        try:
            res = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": f"以下のニュース記事タイトルに関連する日本語ハッシュタグを2つだけ生成せよ。#をつけてスペース区切りで出力せよ。余計な説明は不要。\n\nタイトル: {title}"}],
                    "max_tokens": 30,
                    "temperature": 0.3
                })
            result = res.json()
            if "error" in result and "rate_limit" in str(result["error"]):
                get_next_key()
                continue
            dynamic_tags = result["choices"][0]["message"]["content"].strip()
            return f"{base_tags} {dynamic_tags} #JapanTruth"
        except:
            break
    return f"{base_tags} #JapanTruth"


def _download_image(photo, slug, seen_images):
    from datetime import datetime as _dt
    import hashlib
    try:
        image_url = photo["urls"]["regular"]
        img_res = requests.get(image_url, timeout=15)
        img = Image.open(BytesIO(img_res.content)).convert("RGB")
        target_w, target_h = 1200, 630
        img_w, img_h = img.size
        scale = max(target_w / img_w, target_h / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))
        filename = f"{slug}.jpg"
        img.save(os.path.join(GITHUB_REPO_PATH, "public", filename), "JPEG", quality=75)
        webp_filename = f"{slug}.webp"
        img.save(os.path.join(GITHUB_REPO_PATH, "public", webp_filename), "WEBP", quality=70)
        seen_images.add(photo["urls"]["regular"])
        return f"/{filename}"
    except:
        return "/japantruth.png"

def get_image(keyword, slug, category, seen_images=None):
    if seen_images is None:
        seen_images = set()
    try:
        kw_map = {
            "politics": "politics government democracy",
            "economy": "economy finance business",
            "international": "international diplomacy world",
            "investment": "stock market investment",
            "culture": "culture arts society",
        }
        kw = keyword if keyword and keyword != "news" else kw_map.get(category, "world news")
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        # 1. keyword検索（AIが生成、最優先）
        url = f"https://api.unsplash.com/search/photos?query={requests.utils.quote(kw)}&per_page=10&orientation=landscape"
        res = requests.get(url, headers=headers, timeout=10)
        results = res.json().get("results", [])
        kw_used = kw
        # 2. keyword失敗時は固有名詞検索
        STOP_WORDS = {"with","that","this","from","over","after","about","into","than","have","been","will","says","said","what","when","where","which","their","there","were","they","them","more","some","also","both","just","than","then","here","such","most","make","made","take","very","even","back","only","well","each","much","many","also","before","could","would","should","house","court","calls","urge","warn","seek","amid","amid","slams","amid","push","plan","deal","amid","amid","amid"}
        if not results:
            slug_clean = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", slug)
            proper_nouns = [w.capitalize() for w in slug_clean.replace("-", " ").split() if len(w) > 3 and not w.isdigit() and w.lower() not in STOP_WORDS]
            if proper_nouns:
                proper_kw = " ".join(proper_nouns[:2])
                url2 = f"https://api.unsplash.com/search/photos?query={requests.utils.quote(proper_kw)}&per_page=10&orientation=landscape"
                res2 = requests.get(url2, headers=headers, timeout=10)
                results = res2.json().get("results", [])
                kw_used = proper_kw
        # 3. カテゴリキーワードで再検索
        if not results:
            kw_map2 = {
                "politics": "government parliament president",
                "economy": "stock market wall street finance",
                "international": "world globe diplomacy",
                "investment": "stock exchange trading finance",
                "culture": "city people society",
            }
            cat_kw = kw_map2.get(category, "world news global")
            url3 = f"https://api.unsplash.com/search/photos?query={requests.utils.quote(cat_kw)}&per_page=10&orientation=landscape"
            res3 = requests.get(url3, headers=headers, timeout=10)
            results = res3.json().get("results", [])
            kw_used = cat_kw
        # 4. それも失敗時はデフォルト画像
        if not results:
            return "/japantruth.png"
        # 使用済み画像を除外
        unused = [p for p in results if p["urls"]["regular"] not in seen_images]
        if not unused:
            unused = results
        seed = int(hashlib.md5(slug.encode()).hexdigest(), 16)
        photo = unused[seed % len(unused)]
        print(f"🔑 実際の画像キーワード: {kw_used}")
        return _download_image(photo, slug, seen_images)
    except:
        return "/japantruth.png"

def post_to_x(title, url, image_path):
    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET
        )
        # 画像をアップロード
        auth = tweepy.OAuth1UserHandler(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET)
        api = tweepy.API(auth)
        media_id = None
        img_file = os.path.join(GITHUB_REPO_PATH, "public", image_path.lstrip("/"))
        if os.path.exists(img_file):
            media = api.media_upload(img_file)
            media_id = media.media_id
        tweet_text = f"{title}\n\n{url}"
        if media_id:
            client.create_tweet(text=tweet_text, media_ids=[media_id])
        else:
            client.create_tweet(text=tweet_text)
        print(f"🐦 X投稿完了")
    except Exception as e:
        print(f"⚠️ X投稿失敗: {e}")

def format_body(body):
    # 重複セクションを除去
    if body.count("## 何が起きているのか") > 1:
        body = body[:body.index("## 何が起きているのか", body.index("## 何が起きているのか") + 1)]
    lines = body.split('\n')
    result = []
    sentence_count = 0
    for line in lines:
        if line.startswith('▶'):
            continue
        if line.startswith('#'):
            sentence_count = 0
            result.append(line)
        elif line.strip():
            # 句点で文を分割
            sentences = [s.strip() for s in line.replace('。', '。|||').split('|||') if s.strip()]
            for s in sentences:
                result.append(s)
                sentence_count += 1
                if sentence_count % 2 == 0:
                    result.append('')
        else:
            if result and result[-1] != '':
                result.append('')
            sentence_count = 0
    return '\n'.join(result).strip()

def create_md(date_str, time_str, slug, title, excerpt, category, image_path, source_url, body, source_name="Unknown", tags=""):
    title = title.replace('"', '′')
    excerpt = excerpt.replace('"', '′')
    md_content = f"""---
title: "{title}"
date: "{time_str}"
categories: "{category}"
excerpt: "{excerpt}"
premium: false
image: "{image_path}"
source: "{source_name}"
tags: "{tags}"
source_url: "{source_url}"
---

{format_body(body)}
"""
    filename = f"{date_str}-{slug}.md"
    filepath = os.path.join(GITHUB_REPO_PATH, "src", "posts", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md_content)
    return filename

def git_push(filename):
    os.chdir(GITHUB_REPO_PATH)
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if github_token:
        remote_url = f"https://JapanTruth:{github_token}@github.com/JapanTruth/japantruth-nextjs.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], capture_output=True)
    subprocess.run(["git", "config", "user.email", "thisisjapan@proton.me"], check=False)
    subprocess.run(["git", "config", "user.name", "JapanTruth Bot"], check=False)
    print(f"🔄 git pull...")
    subprocess.run(["git", "pull", "origin", "main", "--rebase"], capture_output=True)
    print(f"➕ git add...")
    subprocess.run(["git", "add", "."], capture_output=True)
    print(f"💾 git commit...")
    subprocess.run(["git", "commit", "-m", f"auto: add {filename}"], capture_output=True)
    print(f"🚀 git push...")
    result = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ プッシュ完了: {filename}")
    else:
        print(f"⚠️ プッシュ失敗: {result.stderr}")

def scrape_article(url):
    """記事本文をスクレイピング。失敗時はNoneを返す"""
    PAYWALLED = ["ft.com", "bloomberg.com", "wsj.com", "nikkei.com", "seekingalpha.com"]
    if any(domain in url for domain in PAYWALLED):
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return None
        from html.parser import HTMLParser
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ["script", "style", "nav", "header", "footer", "aside"]:
                    self.skip = True
            def handle_endtag(self, tag):
                if tag in ["script", "style", "nav", "header", "footer", "aside"]:
                    self.skip = False
            def handle_data(self, data):
                if not self.skip and data.strip():
                    self.text.append(data.strip())
        parser = TextExtractor()
        parser.feed(res.text)
        full_text = " ".join(parser.text)
        # 短すぎる場合は失敗扱い
        if len(full_text) < 300:
            return None
        return full_text[:4000]
    except Exception as e:
        return None

def collect_new_articles(seen):
    new_articles = []
    for feed_info in RSS_FEEDS:
        try:
            try:
                rss_res = requests.get(feed_info["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
                feed = feedparser.parse(rss_res.text)
            except Exception:
                print(f"⚠️ タイムアウト: {feed_info['source']} → スキップ")
                time.sleep(2)
                continue
            for entry in feed.entries[:2]:
                url = entry.link
                article_id = hashlib.md5(url.encode()).hexdigest()
                if "/video/" in url or "/videos/" in url or "/opinion/" in url or "/opinions/" in url or "/commentary/" in url:
                    continue
                summary = getattr(entry, "summary", entry.title)
                if len(summary) < 100:
                    continue
                if article_id not in seen:
                    new_articles.append({
                        "id": article_id,
                        "title": entry.title,
                        "content": getattr(entry, "summary", entry.title),
                        "url": url,
                        "category": feed_info["category"],
                        "source": feed_info["source"],
                    })
        except Exception as e:
            print(f"⚠️ フィード取得エラー: {e}")
        time.sleep(2)
    return new_articles

def main():
    print("🚀 JapanTruth自動投稿システム起動")
    feed_index = 0
    daily_count = 0
    skip_count = 0
    tpd_used = 0
    last_keyword = ""
    last_date = datetime.now(JST).strftime("%Y-%m-%d")
    seen, seen_images = load_seen()

    while True:
        # 日付が変わったらカウントリセット
        today = datetime.now(JST).strftime("%Y-%m-%d")
        if today != last_date:
            daily_count = 0
            tpd_used = 0
            skip_count = 0
            last_date = today

        print(f"\n🔍 全ソースをチェック中... ({datetime.now(JST).strftime('%H:%M')})")
        print(f"📡 RSSフィード取得中... (14ソース)")
        new_articles = collect_new_articles(seen)
        print(f"📋 新着記事: {len(new_articles)}件")
        # 全件チェック（最大10件）

        cycle_count = 0
        for article in new_articles:
            if cycle_count >= 2:
                break
            seen.add(article["id"])
            save_seen(seen, seen_images)
            print(f"🔎 判定中 [8b]: {article['title'][:60]}")
            is_breaking, image_kw = screen_article(article["title"], article.get("content", ""))
            if not is_breaking:
                print("⏭️ ブレイキングニュースではないのでスキップ")
                continue
            article["image_kw"] = image_kw
            time.sleep(3)  # TPM制限対策
            print(f"🌐 記事本文スクレイピング中: {article['url'][:60]}")
            scraped = scrape_article(article["url"])
            if scraped:
                print(f"✅ スクレイピング成功: {len(scraped)}文字取得")
                article["content"] = scraped
            else:
                print(f"⚠️ スクレイピング失敗 → RSSサマリーで代替")
            print(f"📰 処理中 [Qwen3-32b]: {article['title'][:60]}")
            result = summarize_article(article["title"], article["content"], article["category"])
            if result == "rate_limit":
                print("⏳ レート制限により生成不可 → failed_articles.jsonに保存")
                import json as _json
                skip_count += 1
                log_file = os.path.expanduser("~/failed_articles.json")
                failed = []
                if os.path.exists(log_file):
                    with open(log_file) as _f:
                        failed = _json.load(_f)
                failed.append({
                    "title": article["title"],
                    "url": article["url"],
                    "category": article["category"],
                    "source": article["source"],
                    "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M")
                })
                with open(log_file, "w") as _f:
                    _json.dump(failed, _f, ensure_ascii=False, indent=2)
                continue
            if not result:
                print("⚠️ 要約失敗（レート制限以外の原因）、スキップ")
                continue
            # titleが空の場合は処理続行
            if not result.get("title"):
                result["title"] = article["title"]
            date_str = datetime.now(JST).strftime("%Y-%m-%d")
            time_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
            # Unicodeクォートを正規化
            article["title"] = article["title"].replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", "\"").replace("\u201d", "\"")
            slug = re.sub(r'[^a-z0-9]+', '-', article["title"].lower())[:40].strip('-')
            cat = next((c for c in ["politics","economy","international","culture","investment"] if c in result.get("category", article["category"]).lower()), article["category"])
            image_kw = result.get("keyword") or article.get("image_kw") or "news"
            if image_kw == last_keyword:
                image_kw = image_kw + " building"
            last_keyword = result.get("keyword", "news")
            tokens_used = result.get("tokens", 0)
            tokens_input = result.get("tokens_input", 0)
            tokens_output = result.get("tokens_output", 0)
            tpd_used += tokens_used
            print(f"🔢 トークン消費: 入力{tokens_input:,} / 出力{tokens_output:,} / 合計{tokens_used:,} | 本日累計: {tpd_used:,}/500,000 (3アカウント合計1,500,000)")
            print(f"🖼️ 画像キーワード: {image_kw}")
            print(f"📥 Unsplash画像取得中...")
            image_path = get_image(image_kw, slug, cat, seen_images)
            print(f"🖼️ 画像保存完了: {image_path}")
            print(f"🏷️ タグ生成中 [8b]...")
            tags = generate_tags(result.get("title", article["title"]), cat)
            if image_path != "/japantruth.png":
                seen_images.add(image_path)
            print(f"📝 MDファイル作成中...")
            filename = create_md(
                date_str, time_str, slug,
                result.get("title", article["title"]),
                result.get("excerpt", ""),
                cat, image_path,
                article["url"],
                result.get("body", ""),
                article["source"],
                tags=tags,
            )
            print(f"📄 MDファイル作成完了: {filename}")
            git_push(filename)
            article_url = f"https://www.japan-truth.com/posts/{slug}"
            # post_to_x(result.get("title", article["title"]), article_url, image_path)  # 手動シェア
            daily_count += 1
            cycle_count += 1
            print(f"📊 本日の投稿数: {daily_count}/100 | スキップ: {skip_count}件")
            time.sleep(30)

        print("💤 15分待機中...")
        time.sleep(900)



# Render スリープ防止用Webサーバー
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def ping():
    return "OK", 200

def run_server():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    Thread(target=run_server, daemon=True).start()
    main()
