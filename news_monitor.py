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
    {"url": "https://feeds.businessinsider.com/custom/all", "category": "culture", "source": "Business Insider"},
    {"url": "https://www.fool.com/feeds/index.aspx", "category": "investment", "source": "Motley Fool"},
    # 政治
    {"url": "https://feeds.bbci.co.uk/news/politics/rss.xml", "category": "politics", "source": "BBC Politics"},
    {"url": "https://abcnews.go.com/abcnews/topstories", "category": "politics", "source": "ABC News"},
    {"url": "https://www.independent.co.uk/news/world/rss", "category": "international", "source": "The Independent"},
    {"url": "https://feeds.npr.org/1004/rss.xml", "category": "politics", "source": "NPR World"},
    # 文化
    {"url": "https://www.theguardian.com/culture/rss", "category": "culture", "source": "The Guardian"},
    {"url": "https://www.theatlantic.com/feed/all/", "category": "culture", "source": "The Atlantic"},
    {"url": "https://www.channelnewsasia.com/rssfeeds/8395884", "category": "international", "source": "Channel News Asia"},
    {"url": "https://foreignpolicy.com/feed", "category": "politics", "source": "Foreign Policy"},
    {"url": "https://www.middleeasteye.net/rss", "category": "international", "source": "Middle East Eye"},
]

def load_seen():
    """Supabaseから過去7日間の掲載済みURLを取得してseenセットを構築"""
    seen = set()
    seen_images = set()
    try:
        import requests as _rq
        from datetime import datetime, timezone, timedelta
        _sb_url = "https://xhvvxfvxkqcadqhdqtmn.supabase.co"
        _sb_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        _h = {"apikey": _sb_key, "Authorization": f"Bearer {_sb_key}"}
        _cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _res = _rq.get(
            f"{_sb_url}/rest/v1/posts?select=source_url,slug&created_at=gte.{_cutoff}&limit=1000",
            headers=_h, timeout=10
        )
        for p in _res.json():
            if p.get("source_url"):
                seen.add(p["source_url"])
            if p.get("slug"):
                seen.add(p["slug"])
        # skipped_urlsも読み込む
        _res2 = _rq.get(
            f"{_sb_url}/rest/v1/skipped_urls?select=url&created_at=gte.{_cutoff}&limit=1000",
            headers=_h, timeout=10
        )
        for p in _res2.json():
            if p.get("url"):
                seen.add(p["url"])
        print(f"✅ Supabaseから{len(seen)}件の既掲載記事を読み込み")
    except Exception as e:
        print(f"⚠️ Supabase読み込み失敗: {e}")
        # フォールバック: seen_articles.jsonから読み込み
        if os.path.exists(SEEN_FILE):
            with open(SEEN_FILE) as f:
                data = json.load(f)
                if isinstance(data, dict):
                    seen = set(data.get("articles", []))
                    seen_images = set(data.get("images", []))
    return seen, seen_images

def save_seen(seen, seen_images):
    """seen_imagesのみローカル保存（記事IDはSupabaseで管理）"""
    try:
        with open(SEEN_FILE, "w") as f:
            json.dump({"articles": [], "images": list(seen_images)[-200:]}, f)
    except Exception as e:
        print(f"⚠️ seen保存失敗: {e}")


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

def screen_article(title, summary="", recent_titles=None):
    """ブレイキングニュースか判定＋既報チェック＋画像キーワード生成（8bモデル）"""
    snippet = summary[:100] if summary else ""
    recent_block = ""
    if recent_titles:
        recent_block = "Recently covered articles (last 3 hours):\n"
        for t in recent_titles[:15]:
            recent_block += f"- {t}\n"
        recent_block += "\n"
    prompt = (
        f"{recent_block}"
        f"New article title: {title}\nSnippet: {snippet}\n\n"
        "1. Is this newsworthy? Answer YES only if: affects many people (war/conflict/policy/crime/disaster/science), involves public figures in official capacity, or reveals important information about institutions/corporations/governments.\n"
        "   Answer NO if: personal lifestyle story (individual moving/career/life choices), investment filings or stock analysis, reading lists or gift guides, celebrity personal life, building renovation plans, or any story where the main interest is one person's private experience.\n"
        "2. Is this topic already covered in the recently covered articles above? Answer yes ONLY if the EXACT SAME EVENT with the EXACT SAME MAIN SUBJECT is already reported. Answer no if: different angle, new development, different person, or no recent articles.\n"
        "   SAME=YES: Putin ceasefire + Putin announces ceasefire. DIFFERENT=NO: Trump tariffs EU + Trump Iran deal.\n"
        "3. Best 2-3 English words for Unsplash photo search. No abbreviations, acronyms, or proper nouns. Use common visual concepts only (e.g. parliament building, politician speech, protest crowd, military ship, stock market).\n\n"
        "Reply in exactly this format:\n"
        "NEWSWORTHY: yes\n"
        "ALREADY_COVERED: no\n"
        "IMAGE: parliament building"
    )
    data = {
        "model": "llama-3.3-70b-versatile",
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
                get_next_key()
                continue
            if "choices" not in result:
                print(f"⚠️ APIエラー: {result.get('error', {}).get('message', str(result))[:200]}")
                get_next_key()
                continue
            text = result["choices"][0]["message"]["content"]
            is_breaking = "newsworthy: yes" in text.lower()
            already_covered = "already_covered: yes" in text.lower()
            if already_covered:
                print(f"⏭️ 既報と判定（8b）: {title[:50]}")
                return False, ""
            image_kw = ""
            for line in text.split("\n"):
                if line.startswith("image:"):
                    image_kw = line.replace("image:", "").strip()
                    break
            return is_breaking, image_kw
        except Exception as _se:
            print(f"⚠️ screen_article例外: {_se}")
            return False, ""
    return False, ""  # 全キー失敗時はスキップ扱い

def summarize_article(title, content, category):
    system_prompt = (
        "You are a senior journalist at JapanTruth, an independent Japanese-language news media.\n"
        "Mission: Cover stories that mainstream Japanese media would not prioritize or would underreport.\n"
        "Voice: Skeptical of governments and corporations. Treats readers as intelligent citizens.\n\n"
        "OUTPUT: Japanese only, da/de-aru form. JSON format only. No markdown.\n\n"
        "ABSOLUTE RULES:\n"
        "- Use ONLY numbers/dates/names explicitly in source. Never fabricate. Never speculate.\n"
        "- NEVER add Japan connections unless source explicitly mentions Japan/yen/Japanese companies.\n"
        "- No numbered lists or bullet points in body text.\n"
        "- All English words to katakana except: AI, GDP, SNS, IMF, WHO, NATO, EV, IPO, CEO, CFO, LNG, UAE, BBC, CNN.\n\n"
        "NUMBERS: trillion=兆 / billion=十億 / million=百万\n"
        "ROLES: Senate=上院 / House=下院 / Secretary of State=国務長官 / Attorney General=司法長官\n"
        "LEGAL: pleads guilty=有罪を認めた / indicted=起訴された / acquitted=無罪 / arrested=逮捕\n\n"
        "FORBIDDEN:\n"
        "- Speculation: とみられる/とされる/示唆している/かもしれない/と見られる\n"
        "- Bias: [leader]の判断は妥当だ/避けられない/[country]の行動は正しい\n"
        "- Vague: 試される局面だ/深刻な局面だ/どこへ向かうのか\n\n"
        "NEUTRALITY: Never endorse/condemn any government, military, or political group.\n\n"
        "CATEGORIES: politics(elections/policy/diplomacy/military) / economy(GDP/trade/earnings/inflation) / international(war/terrorism/UN) / investment(stocks/bonds/forex/rates) / culture(sports/tech/society/health)\n"
    )



    prompt = (
        f"Convert this English article to Japanese JSON. Source facts only.\n"
        f"/no_think\n"
        f"Title: {title}\nContent: {content[:3500]}\n\n"
        "JSON fields:\n"
        "title: Japanese, active voice, concrete noun/number/country. No: 発表/明らかに/について. No dates.\n"
        "excerpt: 2 sentences, 80+ chars. Surprising fact with number/name. Start with number or name. Never repeat title.\n"
        "keyword: 1-3 English words for photo. Concrete visual only.\n"
        "category: politics/economy/international/investment/culture\n"
        "body:\n"
        "## 何が起きているのか\n3 sentences. WHO+WHAT+WHEN or number. Different subject from title.\n"
        "## 背景\n2-4 sentences. Source facts only. Never repeat 何が起きているのか.\n"
        "## JapanTruthの視点\nEXACTLY 3 sentences:\n"
        "S1: Specific number or named entity. Never: この/その/同社/同国.\n"
        "S2: New angle not in above sections — who benefits, policy contradiction, hidden context.\n"
        "S3: ONE sentence ONLY. End: [事実]が本質的な問題だ OR [手法]には無理がある OR [X]が[Y]という矛盾を示している. Never: 試される/妥当だ/局面だ/見通しだ/深刻/この/その/と見られる/避けられない\n"
    )
