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
    print("✅ seen_articles.json保存完了")


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
                    print(f"⏳ レート制限エラー全文: {msg[:200]}")
                    remaining, reset_time = parse_rate_limit_msg(msg)
                    print(f"⏳ レート制限 | 残り: {remaining} | リセット: {reset_time}")
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
    return False, ""  # 全キー失敗時はスキップ扱い

def summarize_article(title, content, category):
    from translations import TRANSLATIONS as _TRANSLATIONS
    system_prompt = (
        "You are a senior journalist at JapanTruth, an independent Japanese-language news media.\n"
        "Mission: Cover stories that mainstream Japanese media would not prioritize or would underreport.\n"
        "Voice: Skeptical of governments and corporations. Treats readers as intelligent citizens.\n\n"
        "ABSOLUTE RULES:\n"
        "- Output language: Japanese only, declarative style (だ・である). No exceptions. (except keyword field which must be English)\n"
        "- title field MUST be Japanese. Never output English in the title field.\n"
        "- Only use numbers, dates, and proper nouns explicitly present in the source article.\n"
        "- Never fabricate. Never speculate beyond source. If information is insufficient, reduce output length rather than speculate.\n"
        "- Never use numbered lists or bullet points anywhere in the body text.\n"
        "- All newline characters inside JSON values MUST be escaped as \\n, never actual line breaks.\n\n"
        "CRITICAL PROPER NOUN RULES:\n"
        "- ALL person names, place names, org names: transliterate from EXACT spelling in source. Do NOT guess.\n"
        "- If you are unsure of Japanese rendering: write the English name in katakana phonetically from spelling, do not invent.\n"
        f"KNOWN CORRECT TRANSLATIONS:\n{_TRANSLATIONS}\n"
        "CRITICAL ROLE/INSTITUTION TRANSLATIONS:\n"
        "- Senate=上院、House of Representatives=下院（混同厳禁）\n"
        "- Speaker of the House=下院議長\n"
        "- House Minority Leader=下院少数党院内総務\n"
        "- House Majority Leader=下院多数党院内総務\n"
        "- Senate Majority/Minority Leader=上院多数党/少数党院内総務\n"
        "- Secretary of State=国務長官（外務大臣ではない）\n"
        "- Attorney General=司法長官（検事総長ではない）\n"
        "- Chief of Staff=首席補佐官\n"
        "- National Security Advisor=国家安全保障担当大統領補佐官\n"
        "- Treasury Secretary=財務長官\n\n"
        "CRITICAL LEGAL TERM TRANSLATIONS:\n"
        "- pleads guilty / guilty plea=有罪を認めた（起訴ではない）\n"
        "- indicted=起訴された\n"
        "- charged with=〜の罪で訴追された\n"
        "- convicted=有罪判決を受けた\n"
        "- sentenced=判決を受けた / 〜の刑を言い渡された\n"
        "- acquitted=無罪判決を受けた\n"
        "- arrested=逮捕された\n"
        "- detained=拘束された / 身柄を拘束された\n\n"
        "STRICTLY FORBIDDEN PHRASES — automatic failure if any appear:\n"
        "- 可能性がある / かもしれない / 見守る / 注視する / 検討する\n"
        "- 注目が集まる / 求められる / 懸念される / 期待が高まる / 重要性を示す\n"
        "- 避けられない / 直結する / 公算が大きい / 注目される / 重要な意味を持つ\n"
        "- 〜と言えよう / 〜ではないだろうか / グローバル市場 / 国際社会 / 国際秩序\n"
        "- 〜とされる / 〜といわれる / 〜の見方もある / 〜に向けた動き / 〜を受けて\n\n"
        "BACKGROUND SECTION — ALLOWED SOURCES ONLY:\n"
        "- (A) Facts explicitly written in the source article\n"
        "- (B) ONLY these universally known facts: country capitals/borders, major wars with confirmed dates (WWII/Korean War etc.), UN member states\n"
        "- NOTHING ELSE. No statistics, no percentages, no names, no dates not in source.\n"
        "- If you cannot write background using only (A) and (B): omit the entire section. Do not guess.\n\n"
        "JAPANTRUTH PERSPECTIVE — MANDATORY STRUCTURE (exactly 3 sentences, no lists, no bullet points):\n"
        "Sentence 1 — DIRECT IMPACT:\n"
        "  Must BEGIN with a specific number, company name, or country name from the source. Never begin with 同社/同国/同氏/同組織/この/その.\n"
        "  If Japan link naturally exists: cite yen rate, energy cost, export volume, or named Japanese company.\n"
        "  If Japan is NOT in the source: cite specific commodity price, trade route, or named institution. Do NOT force Japan.\n"
        "Sentence 2 — HIDDEN CONTEXT:\n"
        "  Must be one of: policy inconsistency, historical precedent contradiction, corporate incentive, or geopolitical subtext.\n"
        "  Must cite a specific fact. Never vague.\n"
        "Sentence 3 — SHARP CONCLUSION (vary across articles, do not always use same ending):\n"
        "  If facts support conclusion: 〜が予想される / 〜と見られる / 〜は避けられない状況だ / 〜という判断は妥当だ\n"
        "  If facts do not support conclusion: question ending 〜はどう動くべきか / 〜はこのリスクに備えられているか / 〜はどこへ向かうのか / 〜という問いに答えが出ていない\n"
        "  NEVER use the same ending as the previous article. Never end with abstract philosophical statement. Never repeat sentence 1 or 2.\n\n"
        "CATEGORY-SPECIFIC RULES:\n"
        "- politics: elections, government policy, diplomacy, military, security — NOT financial markets\n"
        "- economy: GDP, employment, trade volume, corporate earnings, inflation, industry — NOT stock prices\n"
        "- international: cross-border armed conflict, war, UN/international organizations, terrorism\n"
        "- investment: stock prices, bonds, crypto, forex, central bank interest rates, financial markets\n"
        "- culture: sports, entertainment, science, technology, society, environment, health\n\n"
        "FAILURE MODE PREVENTION:\n"
        "- If data is missing: shorten, do not speculate\n"
        "- If causal link cannot be proven from source: do not state it\n"
        "- If Japan relevance is unclear: omit Japan entirely\n"
        "- Never start two consecutive sentences with the same subject\n\n"
        "OUTPUT FORMAT: Respond ONLY with a valid JSON object. No markdown, no extra text.\n"
        "Example:\n"
        "{\"title\": \"日本語タイトル\", \"excerpt\": \"日本語1文\", \"keyword\": \"english\", \"category\": \"politics\", \"body\": \"## 何が起きているのか\\n本文...\"}\n"
    )



    prompt = (
        f"Convert the following English article into a Japanese article and return as JSON.\n"
        f"CRITICAL: Do NOT add any proper nouns, numbers, or dates not in the source. If source lacks detail, write fewer sentences.\n\n"
        "/no_think\n"
        f"Title: {title}\nContent: {content[:2500]}\n\n"
        "JSON fields:\n"
        "- title: MUST be Japanese. Assertive title with at least one concrete proper noun, number, or country name from source. Avoid: 発表, 明らかに, 判明, 示す, めぐり.\n"
        "- excerpt: The single most surprising or counterintuitive fact from this story. NOT a plain summary.\n"
        "  GOOD: 具体的な数字・人名・逆説的事実を含む1文。読者が思わず記事を開きたくなる文。\n"
        "  BAD: 〜が行われた / 〜が発表された / 〜が明らかになった などの平凡な要約。\n"
        "  MUST differ from the first sentence of 何が起きているのか. Never copy it.\n"
        "- keyword: 1-3 English words for Unsplash image search. Must be a concrete visual subject.\n"
        "  GOOD: country names, city names, physical objects (oil rig, cargo ship, fighter jet, stock exchange, courtroom).\n"
        "  BAD: abstract words (talks, concerns, tensions, signals, warns, plans, deals, growth, crisis).\n"
        "- category: Choose exactly one: politics / economy / international / investment / culture\n"
        "  politics: elections, government policy, diplomacy, military, security — NOT stock prices\n"
        "  economy: GDP, employment, trade volume, corporate earnings, inflation — NOT stock prices\n"
        "  international: cross-border armed conflict, war, UN/international organizations, terrorism\n"
        "  investment: stock prices, bonds, crypto, forex, central bank rate decisions, financial markets\n"
        "  culture: sports, entertainment, science, technology, society, environment, health\n"
        "- body: Use EXACTLY this format:\n"
        "  ## 何が起きているのか\\n\n"
        "  (2-5 sentences. who/what/when/where/why/how. Source facts only. Check legal terms: pleads guilty=有罪を認めた, indicted=起訴, convicted=有罪判決.)\\n\\n"
        "  ## 背景\\n\n"
        "  (2-4 sentences. ONLY facts from source + universally known facts. NEVER add statistics or names not in source. If thin: omit entirely.)\\n\\n"
        "  ## JapanTruthの視点\\n\n"
        "  (Exactly 3 sentences. No lists. No bullet points.\n"
        "   Sentence 1: BEGIN with specific number/company/country from source. Never: 同社/同国/同氏/この/その.\n"
        "   Sentence 2: Hidden context — policy inconsistency, historical contradiction, or corporate incentive. Must be specific.\n"
        "   Sentence 3: ONE of: 〜が予想される / 〜と見られる / sharp reader question ending 〜はどう動くべきか / 〜はこのリスクに備えられているか / 〜はどこへ向かうのか)\n"
    )



    data = {
        "model": "qwen/qwen3-32b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 3000,
        "temperature": 0.3,
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
                    print(f"⏳ レート制限エラー全文: {msg[:200]}")
                    remaining, reset_time = parse_rate_limit_msg(msg)
                    print(f"⏳ レート制限 | 残り: {remaining} | リセット: {reset_time}")
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
            _article = {
                "title": parsed.get("title", "").strip(),
                "excerpt": parsed.get("excerpt", "").strip(),
                "keyword": parsed.get("keyword", "news"),
                "category": cat,
                "body": parsed.get("body", "").strip(),
                "tokens": result.get("usage", {}).get("total_tokens", 0),
                "tokens_input": result.get("usage", {}).get("prompt_tokens", 0),
                "tokens_output": result.get("usage", {}).get("completion_tokens", 0),
            }
            return post_process_article(_article)
        except Exception as e:
            import traceback
            print(f"⚠️ 試行{attempt+1}失敗: {type(e).__name__}: {e}")
            traceback.print_exc()
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


import re as _re

# 後処理：最小限のセーフティネット（固有名詞の誤字のみ）
# ⚠️ 後処理はプロンプトで防げなかった明確な誤字のみ対象
# 意味が変わる可能性のある禁止表現の置換はしない（プロンプトに任せる）

PROPER_NOUN_FIXES = {
    # ウイルス
    "ハンターバイラス": "ハンタウイルス",
    "ハンターウイルス": "ハンタウイルス",
    # 政治家
    "ネラージュ・モディ": "ナレンドラ・モディ",
    "エロン・マスク": "イーロン・マスク",
    "マーカス・ハミル": "マーク・ハミル",
    "ヘイキム・ジェフリー": "ハキーム・ジェフリーズ",
    "モーセン・マダウィ": "モフセン・マダウィ",
    "ペゼーシキアン": "ペゼシュキアン",
    # 企業
    "ベルクシャー": "バークシャー",
    # 役職
    "上院民主党議長": "下院民主党院内総務",
    "政治委員長": "政治委員",
    # 艦艇・レース
    "最上級護衛艦": "もがみ型護衛艦",
    "ノースウェスト200マイルスーパー・バイクレース": "ノースウェスト200スーパーバイクレース",
}

# 禁止表現は意味変化リスクが低いものだけ最小限に絞る
FORBIDDEN_REPLACEMENTS = {
    "可能性がある": "と見られる",
    "グローバル市場": "世界市場",
}

def _safe_replace(text, wrong, correct):
    """日本語対応の安全な置換（前後の文字を確認）"""
    return _re.sub(
        rf'(?<![ァ-ンぁ-ん一-龥ー]){_re.escape(wrong)}(?![ァ-ンぁ-ん一-龥ー])',
        correct,
        text
    )

def _safe_proper_noun(text, wrong, correct):
    """固有名詞の安全な置換（完全一致のみ）"""
    return _re.sub(
        rf'(?<![ァ-ンぁ-ん一-龥ー]){_re.escape(wrong)}(?![ァ-ンぁ-ん一-龥ー])',
        correct,
        text
    )

def _process_value(value):
    """再帰的に文字列を処理（str/list/dict対応）"""
    if isinstance(value, str):
        for wrong, correct in PROPER_NOUN_FIXES.items():
            value = _safe_proper_noun(value, wrong, correct)
        for wrong, correct in FORBIDDEN_REPLACEMENTS.items():
            value = _safe_replace(value, wrong, correct)
        return value
    elif isinstance(value, list):
        return [_process_value(v) for v in value]
    elif isinstance(value, dict):
        return {k: _process_value(v) for k, v in value.items()}
    return value

def post_process_article(result):
    """生成された記事の後処理（最小限のセーフティネット）"""
    return {k: _process_value(v) for k, v in result.items()}



def save_to_supabase(slug, title, date_str, time_str, category, excerpt, image_path, source_url, body, source_name, tags):
    """記事をSupabaseに保存"""
    try:
        import requests as _req
        SUPABASE_URL = "https://xhvvxfvxkqcadqhdqtmn.supabase.co"
        SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not SUPABASE_KEY:
            print("⚠️ SUPABASE_SERVICE_KEY未設定")
            return False
        
        post_data = {
            "slug": slug,
            "title": title,
            "date": f"{date_str} {time_str}",
            "category": category,
            "excerpt": excerpt,
            "premium": False,
            "image": image_path,
            "source": source_name,
            "tags": tags,
            "source_url": source_url,
            "body": body,
        }
        
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        
        res = _req.post(
            f"{SUPABASE_URL}/rest/v1/posts",
            headers=headers,
            json=post_data
        )
        if res.status_code in [200, 201]:
            print(f"✅ Supabase保存完了: {slug}")
            return True
        else:
            print(f"⚠️ Supabase保存失敗: {res.status_code} {res.text[:100]}")
            return False
    except Exception as e:
        print(f"⚠️ Supabase保存エラー: {e}")
        return False


def upload_to_cloudinary(local_path, slug):
    """画像をCloudinaryにアップロードしてURLを返す"""
    try:
        import cloudinary
        import cloudinary.uploader
        
        cloudinary.config(
            cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
            api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
            api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
        )
        
        result = cloudinary.uploader.upload(
            local_path,
            public_id=slug,
            overwrite=True,
            resource_type="image"
        )
        # バージョン番号なしのURLに変換
        raw_url = result.get("secure_url", "")
        public_id = result.get("public_id", "")
        url = f"https://res.cloudinary.com/dnqswecpg/image/upload/f_webp,q_auto/{public_id}" if public_id else raw_url
        print(f"☁️ Cloudinaryアップロード完了: {url}")
        return url
    except Exception as e:
        print(f"⚠️ Cloudinaryアップロード失敗: {e}")
        return None

# 以下2関数はSupabase移行後は未使用（削除候補）
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
    github_token = os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN", ""))
    if github_token:
        remote_url = f"https://JapanTruth:{github_token}@github.com/JapanTruth/japantruth-nextjs.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], capture_output=True)
    subprocess.run(["git", "config", "user.email", "thisisjapan@proton.me"], check=False)
    subprocess.run(["git", "config", "user.name", "JapanTruth Bot"], check=False)
    print(f"🔄 git pull...")
    subprocess.run(["git", "fetch", "origin"], capture_output=True)
    subprocess.run(["git", "reset", "--hard", "origin/main"], capture_output=True)
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
                rss2json_key = os.environ.get("RSS2JSON_API_KEY", "")
                if rss2json_key:
                    api_url = f"https://api.rss2json.com/v1/api.json?rss_url={requests.utils.quote(feed_info['url'])}&api_key={rss2json_key}&count=10"
                    rss_res = requests.get(api_url, timeout=10)
                    rss_data = rss_res.json()
                    if rss_data.get("status") == "ok":
                        feed = type("Feed", (), {"entries": [
                            type("Entry", (), {
                                "link": item.get("link", ""),
                                "title": item.get("title", ""),
                                "summary": item.get("description", item.get("title", "")),
                            })() for item in rss_data.get("items", [])
                        ]})()
                    else:
                        raise Exception(f"rss2json error: {rss_data.get('message')}")
                else:
                    rss_res = requests.get(feed_info["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
                    feed = feedparser.parse(rss_res.text)
            except Exception as e:
                print(f"⚠️ タイムアウト: {feed_info['source']} → スキップ ({e})")
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
        time.sleep(1)
    return new_articles

def main():
    print("🚀 JapanTruth自動投稿システム起動")
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
            # summarize_articleはrate_limit時もNoneを返す（rate_limit文字列は返さない）
            if not result:
                print("⚠️ 要約失敗（レート制限以外の原因）、スキップ")
                continue
            # titleが空または英語の場合はスキップ
            if not result.get("title"):
                print("⚠️ タイトル生成失敗 → スキップ")
                continue
            # タイトルが英語のみの場合もスキップ（日本語文字が含まれていない）
            import unicodedata as _ud
            if not any(_ud.name(c, '').startswith(('CJK', 'HIRAGANA', 'KATAKANA')) for c in result["title"]):
                print(f"⚠️ タイトルが日本語でない: {result['title'][:50]} → スキップ")
                continue
            date_str = datetime.now(JST).strftime("%Y-%m-%d")
            time_str = datetime.now(JST).strftime("%H:%M")
            # Unicodeクォートを正規化
            article["title"] = article["title"].replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", "\"").replace("\u201d", "\"")
            # slug = 日付+時刻+タイトル先頭30文字（重複防止）
            _slug_base = re.sub(r'[^a-z0-9]+', '-', article["title"].lower())[:30].strip('-')
            slug = f"{date_str}-{datetime.now(JST).strftime('%H%M%S')}-{_slug_base}"
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
            # Cloudinaryにアップロード
            if image_path and image_path != "/japantruth.png":
                local_img = os.path.join(GITHUB_REPO_PATH, "public", image_path.lstrip("/"))
                if os.path.exists(local_img):
                    cloud_url = upload_to_cloudinary(local_img, slug)
                    if cloud_url:
                        image_path = cloud_url
            print(f"🏷️ タグ生成中 [8b]...")
            tags = generate_tags(result.get("title", article["title"]), cat)
            if image_path != "/japantruth.png":
                seen_images.add(image_path)
            save_to_supabase(
                slug, result.get("title", article["title"]),
                date_str, time_str, cat,
                result.get("excerpt", ""), image_path,
                article["url"], result.get("body", ""),
                article["source"], tags
            )
            article_url = f"https://www.japan-truth.com/posts/{slug}"
            # post_to_x(result.get("title", article["title"]), article_url, image_path)  # 手動シェア
            daily_count += 1
            cycle_count += 1
            print(f"📊 本日の投稿数: {daily_count}/100 | スキップ: {skip_count}件")
            time.sleep(20)

        print("💤 15分待機中...")
        time.sleep(1800)



main()
