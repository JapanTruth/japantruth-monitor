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
    {"url": "https://feeds.businessinsider.com/custom/all", "category": "investment", "source": "Business Insider"},
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
        "1. Is this newsworthy? Answer yes if: war/conflict, diplomacy/summit, economic news, politics, business/corporate news, crime, social issues, sports, science/tech, environment. Answer no if: clearly trivial, opinion pieces, roundups/summaries of already-known events, 'what to watch' preview articles, political cartoons/satire compilations, weekly photo galleries, 'best of' collections, news quizzes, photo essays, 'in pictures' articles, investment fund filings, SEC filings, stock portfolio updates, ETF holdings changes, or vague titles like 'What in the World'.\n"
        "2. Is this topic already covered in the recently covered articles above? Answer yes ONLY if the EXACT SAME EVENT with the EXACT SAME MAIN SUBJECT is already reported. Answer no if: different angle, new development, different person, or no recent articles.\n"
        "   SAME=YES: Putin ceasefire + Putin announces ceasefire. DIFFERENT=NO: Trump tariffs EU + Trump Iran deal.\n"
        "3. Best 2-3 English words for Unsplash photo search. No abbreviations, acronyms, or proper nouns. Use common visual concepts only (e.g. parliament building, politician speech, protest crowd, military ship, stock market).\n\n"
        "Reply in exactly this format:\n"
        "NEWSWORTHY: yes\n"
        "ALREADY_COVERED: no\n"
        "IMAGE: parliament building"
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
        "ABSOLUTE RULES:\n"
        "- Output language: Japanese only, declarative style (da/de-aru form, NOT desu/masu). No exceptions. (except keyword field which must be English)\n"
        "- title field MUST be Japanese. Never output English in the title field.\n"
        "- Only use numbers, dates, and proper nouns explicitly present in the source article.\n"
        "- Never fabricate. Never speculate beyond source. If information is insufficient, use what IS in the source. Never speculate beyond source.\n"
        "- Never use numbered lists or bullet points anywhere in the body text.\n"
        "- All newline characters inside JSON values MUST be escaped as \\n, never actual line breaks.\n\n"
        "CRITICAL PROPER NOUN RULES:\n"
        "- ALL person names, place names, org names: transliterate from EXACT spelling in source. Do NOT guess.\n"
        "- If you are unsure of Japanese rendering: write the English name in katakana phonetically from spelling, do not invent.\n"
        "- ALL English words in body/title MUST be converted to katakana or Japanese. NO English words allowed in output except: AI, GDP, SNS, IMF, WHO, NATO, EV, IPO, CEO, CFO, KOSPI, LNG, RSF, UAE, BBC, CNN.\n"
        "- Band names, museum names, song titles, product names: ALL must be katakana.\n"
        "CRITICAL NUMBER/UNIT RULES:\n"
        "- trillion = 兆（1 trillion = 1兆、10 trillion = 10兆）\n"
        "- billion = 十億（1 billion = 10億、100 billion = 1000億）\n"
        "- million = 百万（1 million = 100万）\n"
        "- NEVER invent numbers. Copy exactly from source. No person has quadrillion-dollar assets.\n"
        "CRITICAL ROLE TRANSLATIONS: Senate=上院(NOT下院), House=下院(NOT上院), Secretary of State=国務長官, Attorney General=司法長官, Chief of Staff=首席補佐官, Treasury Secretary=財務長官\n\n"
        "- pleads guilty / guilty plea=有罪を認めた (NOT 起訴)\n"
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
        "- 〜とされる / 〜といわれる / 〜の見方もある / 〜に向けた動き / 〜を受けて\n"
        "- 〜とみられる / 〜が示唆される / 〜が指摘されている / 〜が懸念される\n"
        "- 〜が広がっている / 〜が高まっている / 〜が求められている / 〜が必要とされる\n"
        "- 〜が報じられた / 〜と報告された / 〜が明らかになった / 〜が確認された\n"
        "- 〜に注目が集まる / 〜への関心が高まる / 〜の動向が注目される\n"
        "*** VIOLATION of any above = automatic rewrite. These are ABSOLUTE bans. ***\n\n"
        "BACKGROUND: Only source facts + universally known facts (capitals, WWII). Never invent. If insufficient: omit.\n\n"
        "- If you cannot write background using only (A) and (B): omit the entire section. Do not guess.\n\n"
        "JAPANTRUTH PERSPECTIVE — EXACTLY 3 sentences:\n"
        "- S1: BEGIN with specific number/company/country from source. Cite Japan impact if natural (yen/energy/exports/supply chain), otherwise cite commodity/trade route/geopolitical angle.\n"
        "- S2: Choose the most natural angle from source: (A) Who benefits financially? (B) What past policy does this contradict? (C) Hidden context not in headline? (D) Japan impact (yen/energy/exports/security)? (E) For culture/sports/entertainment: what does this reveal about society, industry structure, or human behavior? Always cite one specific fact from source.\n"
        "- S3: One sharp conclusion grounded in S1+S2. MUST have specific subject (company/country/person name), not この/その/同社/同国. End with ONE of: (A)[具体的主語]の判断は妥当だ (B)[具体的事実]が本質的な問題だ (C)[具体的手法]には無理がある (D)[具体的事実]を示している. NEVER end with: 試される/備えられているか/予想される/局面だ/深刻な局面/この判断\n"
        "- BANNED in ALL sentences: 〜はどこへ向かうのか/避けられない/直結する/〜とされる/同社/同国/この/その\n\n"
        "CATEGORY-SPECIFIC RULES:\n"
        "- politics: elections, government policy, diplomacy, military, security — NOT financial markets\n"
        "- economy: GDP, employment, trade volume, corporate earnings, inflation, industry — NOT stock prices\n"
        "- international: cross-border armed conflict, war, UN/international organizations, terrorism\n"
        "- investment: stock prices, bonds, crypto, forex, central bank interest rates, financial markets\n"
        "- culture: sports, entertainment, science, technology, society, environment, health\n\n"
        "\n"
        "OUTPUT FORMAT: Respond ONLY with a valid JSON object. No markdown, no extra text.\n"
        "Example:\n"
        "{\"title\": \"日本語タイトル\", \"excerpt\": \"日本語1文\", \"keyword\": \"english\", \"category\": \"politics\", \"body\": \"## 何が起きているのか\\n本文...\"}\n"
    )



    prompt = (
        f"Convert the following English article into a Japanese article and return as JSON.\n"
        f"CRITICAL: Do NOT add any proper nouns, numbers, or dates not in the source. If source lacks detail, write fewer sentences.\n\n"
        "/no_think\n"
        f"Title: {title}\nContent: {content[:3500]}\n\n"
        "JSON fields:\n"
        "- title: MUST be Japanese. Assertive title with at least one concrete proper noun, number, or country name from source. Avoid: 発表, 明らかに, 判明, 示す, めぐり. NEVER include dates (年/月/日) in the title.\n"
        "- excerpt: The single most surprising or counterintuitive fact. MUST contain specific number, name, or paradox.\n"
        "  GOOD: '停戦宣言から2時間で1000件超の違反が報告された' / '元CIA長官が自社株を売却した翌日に捜査開始'\n"
        "  BAD: 〜が発表された / 〜が明らかになった / 〜が行われた / 〜が報じられた\n"
        "  MUST start with a number, name, or surprising verb. NEVER copy first sentence of 何が起きているのか.\n"
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
        "  (MINIMUM 3 sentences. who/what/when/where/why/how. Source facts only. Never fewer than 3 sentences.)\n\n"
        "  ## 背景\\n\n"
        "  (2-4 sentences. ONLY facts explicitly in source + universally known facts like WWII dates, country capitals.\n"
        "   NEVER write 省略. If limited info: use what is available from source.)\n\n"
        "   NEVER invent statistics, percentages, or context not in source.)\\n\\n"
        "  ## JapanTruthの視点\\n\n"
        "  (Exactly 3 sentences. No lists. No bullet points.\n"
        "   Sentence 1: BEGIN with a SPECIFIC NUMBER or NAMED ENTITY from source (e.g. '米国の関税率145%が', 'ブラックストーンの20億ドルが', 'キューバの電力網崩壊で'). Never vague. Never: 同社/同国/同氏/この/その/この動き/この問題.\n"
        "   Sentence 2: Hidden context — policy inconsistency, historical contradiction, or corporate incentive. Must be specific.\n"
        "   Sentence 3: ONE of these ONLY (rotate, never repeat same ending twice):\n"
        "     〜が予想される / 〜と見られる / 〜は避けられない状況だ / 〜という判断は妥当だ\n"
        "     〜はこのリスクに備えられているか / 〜という問いに答えが出ていない / 〜が試される局面だ\n"
        "   NEVER: 〜はどこへ向かうのか / 〜方向性はどこへ / 〜はどこに向かうのか)\n"
    )



    data = {
        "model": "qwen/qwen3-32b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1500,
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
            _score, _reasons = score_article(_article)
            # verify_and_fix_proper_nouns は逆修正のリスクがあるため無効化
            # _processed = verify_and_fix_proper_nouns(title, _processed)
            _processed = post_process_article(_article)
            print(f"📊 記事品質スコア: {_score}/10" + (f" | {chr(39).join(_reasons)}" if _reasons else " | 問題なし"))
            if _score < 6:
                print(f"⏭️ 低品質記事をスキップ（スコア{_score}）")
                return None
            # AIによる追加品質評価
            try:
                _title_short = (_processed.get('title','') or '')[:80]
                _ai_prompt = (
                    f"Rate this Japanese news article quality from 1-10. Reply with ONLY a single integer.\n"
                    f"Title: {_title_short}\n"
                    f"Criteria: has specific facts/numbers, logical, no vague language, newsworthy\n"
                    f"Reply format: just the number, e.g. 8"
                )
                _gkey = GROQ_API_KEYS[0]
                _gh = {"Authorization": f"Bearer {_gkey}", "Content-Type": "application/json"}
                _gd = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": _ai_prompt}], "max_tokens": 100, "temperature": 0.1}
                _gr = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=_gh, json=_gd, timeout=15)
                _graw = _gr.json()["choices"][0]["message"]["content"]
                _graw = re.sub(r"<think>.*?</think>", "", _graw, flags=re.DOTALL).strip()
                _graw = re.sub(r"```json|```", "", _graw).strip()
                _ai_score = int(''.join(filter(str.isdigit, _graw.strip()[:3])) or '7')
                print(f"🤖 AI品質スコア: {_ai_score}/10")
                if _ai_score < 6:
                    print(f"⏭️ AI判定で低品質記事をスキップ（スコア{_ai_score}）")
                    return None
            except Exception as _ge:
                print(f"⚠️ AI品質評価失敗: {_ge}")

            return _processed
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
        except Exception as _te:
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
    "ハンタービルス": "ハンタウイルス",
    "ハンタービルス感染": "ハンタウイルス感染",
    "ハンタナウス": "ハンタウイルス",
    "ハンタウイルス症候群": "ハンタウイルス肺症候群",
    "ハンタナウス症候群": "ハンタウイルス肺症候群",

    "ハンターウイルス": "ハンタウイルス",
    # 政治家
    "ネラージュ・モディ": "ナレンドラ・モディ",
    "エロン・マスク": "イーロン・マスク",
    "エлон・マスク": "イーロン・マスク",
    "エлон": "イーロン",
    "パブロ・エスコバール": "パブロ・エスコバル",
    "オデュセイ": "オデュッセイ",
    "ドン・キホーテ": "ドンキホーテ",
    "エリック・カンタナ": "エリック・カントナ",
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
    "ナジェル・ファーガー": "ナイジェル・ファラージュ",
    "アントロピック": "アンソロピック",
    "ナイジェル・ファーガー": "ナイジェル・ファラージュ",
    "ネルジー・ファラージュ": "ナイジェル・ファラージュ",
    "ネルジー・ファーガー": "ナイジェル・ファラージュ",
    "キエフ": "キーウ",
    "ニューカッテルアンダーライム": "ニューキャッスル・アンダー・ライム",
    "ファーガー": "ファラージュ",
    "ルービオ": "ルビオ",
    "マーコ・ルビオ": "マルコ・ルビオ",
    "スタイマー": "スターマー",
    "ヘグゼス": "ヘグセス",
    "ヒューシン": "フセイン",
    "スピアス": "スピアーズ",
    "トレウアメニ": "チュアメニ",
    "ブルド・ラフェンスパーガー": "ブラッド・ラフェンスパーガー",
    "ミュスク": "マスク",
    "スターク氏": "スターマー氏",
    "バファタ": "バフタ",
    "ペルシングスクエア": "パーシング・スクエア",
    "Schumer": "シューマー",
    "Vodafone": "ボーダフォン",
    "Spanish Broadcasting": "スパニッシュ・ブロードキャスティング",
    "White Circle": "ホワイト・サークル",
    "Look Mum No Computer": "ルック・マム・ノー・コンピューター",
    "Furby": "ファービー",
    "JPモーガン": "JPモルガン",
    "Datadog": "データドッグ",
    "Cerebras": "セレブラス",
    "Ananym": "アナニム",
    "Uniper": "ユニパー",
    "Innio": "インニオ",
    "Equinox Gold": "エクイノックス・ゴールド",
    "Yesteryear": "イエスタイヤー",
    "Ovo Energy": "オボ・エナジー",
    "AirAsia": "エアアジア",
    "RedNote": "レッドノート",
    "WeChat": "ウィーチャット",
    "Uber": "ウーバー",
    "DeepSeek": "ディープシーク",
    "Sandisk": "サンディスク",
    "Anduril": "アンデュリル",
    "Coinbase": "コインベース",
    "Anthropic": "アンソロピック",
    "ShinyHunters": "シャイニーハンターズ",
    "Fannie Mae": "ファニーメイ",
    "Freddie Mac": "フレディマック",
    "Safepoint": "セーフポイント",
    "高stakesな": "重要な",
    "EcoCeres": "エコセレス",
    "バティゲ": "ブティジェッジ",
    "バーチャー・ハサウェイ": "バークシャー・ハサウェイ",
    "エルゾグ": "ヘルツォーク",
    "ヴェンバヤマ": "ウェンバンヤマ",
    "ダシルバ": "ダ・シルバ",
    "マムダーニ": "マムダニ",
    "スークイ": "スーキ",
    "ウェンバーマン": "ウェンバンヤマ",
    "ラガーデ": "ラガルド",
    "ジョンヒュン": "ジョンヒョン",
    "フィーネス": "ファインズ",
    "チェビロン": "シェブロン",
    "スカボロ": "スカーバラ",
    "ヴェルカー": "ウェルカー",
    "エルビル": "アルビル",
    "白宮": "ホワイトハウス",
    "マーチング・シン": "マー・シン",
    "英字NVIDIA": "NVIDIA",
    "ゴールブ": "ゴラブ",
    "アメイ・ポーラー": "エイミー・ポーラー",
    "アッカサ清真寺": "アル＝アクサ・モスク",
    "ブルームフィールド": "ブルックフィールド",
    "バングター": "バンガー",
    "サシャン・コリンズ": "スーザン・コリンズ",
    "トラフィカーラ": "トラフィギュラ",
    "アブダブ": "アブダビ",
    "Lumentum": "ルメンタム",
    "スワッチ": "スウォッチ",
    "Lumentum Holdings": "ルメンタム・ホールディングス",
    "ビームイッシュ": "ビーミッシュ",
    "ヘルツェゴボイナ": "ヘルツェゴビナ",
    "マンドーソン": "マンデルソン",
    "ウェス・スタリング": "ウェス・ストリーティング",
    "キャリア・スターマー": "キア・スターマー",
    "モーガン・スタンレー": "モルガン・スタンレー",
    "フィナンシャル・タイムズ": "ファイナンシャル・タイムズ",
    "フェルヴォ": "フェルボ",
    "ピュリツァー": "ピューリッツァー",
    "メランリア": "メラニア",
    "アヌアール": "アンワル",
    "アヌアル": "アンワル",
    "Grab": "グラブ",
    "Pulitzer": "ピューリッツァー",
    "ByteDance": "バイトダンス",
    "Kalshi": "カルシ",
    "Centerspace": "センタースペース",
    "GeneDx": "ジーンDx",
    "高stakes": "重要",
    "Datadog": "データドッグ",
    "Cerebras": "セレブラス",
    "Ananym": "アナニム",
    "Uniper": "ユニパー",
    "Innio": "インニオ",
    "Equinox Gold": "エクイノックス・ゴールド",
    "Yesteryear": "イエスタイヤー",
    "Ovo Energy": "オボ・エナジー",
    "AirAsia": "エアアジア",
    "RedNote": "レッドノート",
    "WeChat": "ウィーチャット",
    "Uber": "ウーバー",
    "DeepSeek": "ディープシーク",
    "Sandisk": "サンディスク",
    "Anduril": "アンデュリル",
    "Coinbase": "コインベース",
    "Anthropic": "アンソロピック",
    "ShinyHunters": "シャイニーハンターズ",
    "Fannie Mae": "ファニーメイ",
    "Freddie Mac": "フレディマック",
    "Safepoint": "セーフポイント",
    "高stakesな": "重要な",
    "EcoCeres": "エコセレス",
    "バティゲ": "ブティジェッジ",
    "バーチャー・ハサウェイ": "バークシャー・ハサウェイ",
    "エルゾグ": "ヘルツォーク",
    "ヴェンバヤマ": "ウェンバンヤマ",
    "ダシルバ": "ダ・シルバ",
    "マムダーニ": "マムダニ",
    "スークイ": "スーキ",
    "ウェンバーマン": "ウェンバンヤマ",
    "ラガーデ": "ラガルド",
    "ジョンヒュン": "ジョンヒョン",
    "フィーネス": "ファインズ",
    "チェビロン": "シェブロン",
    "スカボロ": "スカーバラ",
    "ヴェルカー": "ウェルカー",
    "エルビル": "アルビル",
    "白宮": "ホワイトハウス",
    "マーチング・シン": "マー・シン",
    "英字NVIDIA": "NVIDIA",
    "ゴールブ": "ゴラブ",
    "アメイ・ポーラー": "エイミー・ポーラー",
    "アッカサ清真寺": "アル＝アクサ・モスク",
    "ブルームフィールド": "ブルックフィールド",
    "バングター": "バンガー",
    "サシャン・コリンズ": "スーザン・コリンズ",
    "トラフィカーラ": "トラフィギュラ",
    "アブダブ": "アブダビ",
    "ビームイッシュ": "ビーミッシュ",
    "ヘルツェゴボイナ": "ヘルツェゴビナ",
    "マンドーソン": "マンデルソン",
    "ウェス・スタリング": "ウェス・ストリーティング",
    "キャリア・スターマー": "キア・スターマー",
    "モーガン・スタンレー": "モルガン・スタンレー",
    "フィナンシャル・タイムズ": "ファイナンシャル・タイムズ",
    "フェルヴォ": "フェルボ",
    "ピュリツァー": "ピューリッツァー",
    "メランリア": "メラニア",
    "アヌアール": "アンワル",
    "アヌアル": "アンワル",
    "Grab": "グラブ",
    "Pulitzer": "ピューリッツァー",
    "ByteDance": "バイトダンス",
    "Kalshi": "カルシ",
    "Centerspace": "センタースペース",
    "GeneDx": "ジーンDx",
    "高stakes": "重要",
    "Megadrone": "メガドローン",
    "Zibra": "ザイブラ",
    "Sam Battle": "サム・バトル",
    "ホワイト・アックマン": "ビル・アックマン",
    "ジョリー・ビー": "ジョリビー",
    "キャレル・グループ": "カーライル・グループ",
    "ブレイトリング": "ブライトリング",
    "バーファ賞": "バフタ賞",
    "アーニー": "アーノルド",
    "キャメロン・スターク": "キア・スターマー",
    "テタミナー": "ターミネーター",
    "リテラション": "リティゲーション",
    "バーイ": "バーリー",
    "Tai Po": "大埔",
    "Wang Fuk Court": "宏福苑",
    "Amos Yee": "アモス・イー",
    "チアハナ": "ティファナ",
    "マダウィ": "マフダウィ",
    "ユースフ": "ユーサフ",
    "アラーグチ": "アラグチ",
    "ホンコン": "香港",
    "ペーター・マギャル": "ペーテル・マジャル",
    "マギャル": "マジャル",
    "ミズーホ": "みずほ",
    "近期内に": "近い将来",
    "近期内": "近い将来",
    "カブリヨ": "クラビヨ",
    "コス피": "KOSPI",
    "코스피": "KOSPI",
    "アフメド・アル・シャラア": "アフマド・アル・シャラア",
    "ダブois": "デュボア",
    "デュボis": "デュボア",
    "西 bank": "ヨルダン川西岸",
    "西bank": "ヨルダン川西岸",
    "西 Bank": "ヨルダン川西岸",
    "第14代レオ教皇": "レオ14世",
    "レオ教皇": "レオ14世教皇",
    "マーコ・ルービオ": "マルコ・ルビオ",
    "カシュ・パテル": "カッシュ・パテル",
    "リフォーム党": "リフォームUK",
    "わいせつな接近": "危険な接近",
    "ケア・スターマー": "キア・スターマー",
    "米イラン": "米国とイラン",
    "米イスラエル": "米国とイスラエル",
    "パレスチナ系米国人": "パレスチナ系アメリカ人",
    "ロドニー・バレト": "ロドニー・バレル",
    "ロドニー・バレイト": "ロドニー・バレル",
    "ラウ・フークォー": "ラウ・フックォー",
    "オーシャン・コイ": "オーシャン・コー",
    "イランの国家メディア": "イランの国営メディア",
    "ルーラ大統領": "ルラ大統領",
    "ルーラ": "ルラ",
    "クリス・マッソン": "クリス・メイソン",
    "米イスラエル連合": "米国・イスラエル連合",
    "アメリカ中央司令部": "米中央軍司令部",
    "米上院議員12人": "米上院議員12人",
    "ユーロ・メド人権監視団": "ユーロ・メド人権モニター",
    "レーニングレード広場": "レニングラード広場",
    "火炎瓶攻撃を実行した男が6月1日に起訴される": "火炎瓶攻撃で有罪認定",
    "6月1日に起訴される": "有罪を認める",
    "起こっている": "起きている",
    "南中国新聞（SCMP）": "サウスチャイナ・モーニング・ポスト（SCMP）",
    "南中国新聞": "サウスチャイナ・モーニング・ポスト",
    "タイポ火災": "大埔（タイポ）火災",
    "見込みを立てた油田は見つからず": "商業的に採算の取れる油田は発見されず",
    "空の井戸以外にも有害廃棄物を残した": "掘削済みの廃坑以外にも有害物質を残した",
    "空白チェック企業": "ブランクチェック会社",
    "イーロン戦争": "イラン戦争",
    "リスクは避けられない状況だ": "リスクが表面化しつつある",
    "に直結する": "に関連する",
    "避けられない状況だ": "深刻な局面だ",
    "避けられない": "避けがたい",
    "とされる。": "と報告されている。",
    "国際社会": "各国政府",
    "どこへ向かうのか": "今後の動向が注目される",
    "どこに向かうのか": "今後の動向が注目される",
    "マイケル・バリー": "マイケル・バーリ",
    "[Labour Party]": "労働党",
    "[Chris Mason]": "クリス・メイソン",
    "[Lady Gaga]": "レディー・ガガ",
    "[Elton John]": "エルトン・ジョン",
    "[Angine de Poitrine]": "アンジン・ド・ポワトリーヌ",
    # 新規追加（translation_checker 2026-05-09結果）
    "ゲーマーストップ": "ゲームストップ",
    "テドロス・アダノム・ゲブレイエスス": "テドロス・アダノム",
    "ハンタウイルス症候群": "ハンタウイルス肺症候群",
    "AnthropicのMythos": "アンソロピックのMythos",
    "スレイマン・アル・ハッジ": "スレイマン・アル・ハジ",
    "トゥーンスフィア": "トゥーンスフィア",
    "国家データ局": "国家情報局",
    "プーチン氏、": "プーチン大統領、",
    "プーチン氏が": "プーチン大統領が",
    "プーチン氏は": "プーチン大統領は",
    "カシュ・パテル": "カッシュ・パテル",
}

# 禁止表現は意味変化リスクが低いものだけ最小限に絞る
FORBIDDEN_REPLACEMENTS = {
    "可能性がある": "と見られる",
    "グローバル市場": "世界市場",
}

def _safe_replace(text, wrong, correct):
    """禁止表現の安全な置換"""
    return text.replace(wrong, correct)

def _safe_proper_noun(text, wrong, correct):
    """固有名詞の安全な置換"""
    return text.replace(wrong, correct)

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
    processed = {k: _process_value(v) for k, v in result.items()}

    # JapanTruthの視点の締め方が連続して同じ場合に修正
    body = processed.get("body", "") or ""
    endings = [
        "が問われる局面だ",
        "が試される局面だ",
        "が注目される",
        "注目される",
    ]
    replacements = {
        "が問われる局面だ": "はこのリスクに備えられているか",
        "が試される局面だ": "という判断は妥当だ",
        "が注目される": "という問いに答えが出ていない",
        "注目される": "という問いに答えが出ていない",
    }
    import re as _re
    # 視点セクションを抽出
    view_match = _re.search(r'(## JapanTruth' + 'の視点' + r'\n)(.*?)($|\n##)', body, _re.DOTALL)
    if view_match:
        view_text = view_match.group(2)
        found_endings = [e for e in endings if view_text.count(e) >= 2]
        for e in found_endings:
            # 2回目以降の出現を別の表現に置換
            first = view_text.find(e)
            second = view_text.find(e, first + 1)
            if second >= 0:
                new_ending = replacements.get(e, "という判断は妥当だ")
                view_text = view_text[:second] + view_text[second:].replace(e, new_ending, 1)
        body = body[:view_match.start(2)] + view_text + body[view_match.end(2):]
        processed["body"] = body

    # 禁止ワード自動修正
    body = processed.get("body", "") or ""
    title = processed.get("title", "") or ""
    excerpt = processed.get("excerpt", "") or ""
    
    forbidden_fixes = {
        "とされる": "と報告されている",
        "といわれる": "と報告されている",
        "とみられる": "と報告されている",
        "示唆している": "示している",
        "示唆する": "示す",
        "示唆される": "示されている",
        "指摘されている": "と報告されている",
        "懸念される": "懸念がある",
        "懸念が広がり": "懸念が増し",
        "懸念されている": "懸念がある",
        "注目されている": "焦点となっている",
        "指摘されている": "示されている",
        "と示されている": "と判明している",
        "と示された": "と判明した",
        "注目される": "注目を浴びる",
        "注目されている": "焦点となっている",
        "指摘されている": "示されている",
        "注目を集めている": "注目を浴びている",
        "が問われている": "が試される",
        "が問われる": "が試される",
        "必要とされる": "必要だ",
        "求められている": "必要だ",
        "求められる": "必要だ",
        "可能性がある": "見通しだ",
        "かもしれない": "という見方がある",
        "と見られる": "と報告されている",
        "と分析されると": "と報告されると",
        "と分析されている": "と報告されている",
        "とされている": "と報告されている",
        "と見られている": "と報告されている",
        "国際社会": "各国政府",
        "国際秩序": "世界秩序",
        "直結する": "関連する",
        "避けられない": "深刻だ",
        "深刻な局面だ": "深刻な状況だ",
        "試される局面だ": "本質的な問題だ",
        "再び高まっている": "増している",
        "と判明している": "と示されている",
        "妥当だと考えられる": "妥当だ",
        "が高まっている": "が増している",
        "が広がっている": "が拡大している",
        "と伝えられている": "と報告されている",
        "と伝えられた": "と報告された",
        "と伝えている": "と報告している",
        "と発表されている": "と報告されている",
        "と報じている": "と報告している",
        "浮き彫りにしている": "示している",
        "浮き彫りにした": "示した",
        "可能性が高い": "見通しだ",
        "どこへ向かうのか": "今後の動向が焦点となっている",
        "可能性は高い": "見通しだ",
        "予想される": "見込まれる",
        "可能性が増している": "深刻な状況だ",
        "予想させる": "示している",
        "主張した": "述べた",
        "主張している": "述べている",
        "如実に現れている": "示している",
        "と分析している": "と述べている",
        "浮き彫りになる": "示される",
        "浮き彫りになっている": "示されている",
        "繰り返しと": "繰り返されると",
        "と報告されている。": "と判明している。",
        "となると報告されている": "となる",
        "示唆されている": "示されている",
        "と報じられている": "と報告されている",
        "主張されている": "と報告されている",
    }
    for wrong, correct in forbidden_fixes.items():
        body = body.replace(wrong, correct)
        title = title.replace(wrong, correct)
        excerpt = excerpt.replace(wrong, correct)
    processed["body"] = body
    processed["title"] = title
    processed["excerpt"] = excerpt

    return processed

def score_article(result):
    """記事品質スコアリング（0-10点）低品質記事を弾く"""
    score = 10
    reasons = []
    title = result.get("title", "") or ""
    body = result.get("body", "") or ""
    excerpt = result.get("excerpt", "") or ""

    # タイトルチェック
    if len(title) < 10:
        score -= 3
        reasons.append("タイトルが短すぎる")
    if not any(c.isdigit() or '一' <= c <= '鿿' or '゠' <= c <= 'ヿ' for c in title):
        score -= 2
        reasons.append("タイトルに固有情報なし")

    # 背景の質チェック
    bg_match = body.find("## 背景")
    if bg_match >= 0:
        bg_text = body[bg_match:bg_match+200]
        if "省略" in bg_text:
            score -= 2
            reasons.append("背景省略")
        elif len(bg_text) < 80:
            score -= 1
            reasons.append("背景が極端に短い")

    # JapanTruthの視点の質チェック
    vp_match = body.find("## JapanTruthの視点")
    if vp_match >= 0:
        vp_text = body[vp_match:vp_match+300]
        vague = ["この動き", "この問題", "この状況", "どう動くべきか", "どこへ向かう"]
        found_vague = [w for w in vague if w in vp_text]
        if found_vague:
            score -= len(found_vague)
            reasons.append(f"視点が曖昧: {', '.join(found_vague[:2])}")

    # 禁止ワードチェック
    forbidden = ["可能性がある", "かもしれない", "どこへ向かうのか", "国際社会", "避けられない", "とされる", "とみられる", "示唆している", "が問われる", "注目されている", "必要とされる", "が高まっている", "が広がっている", "と伝えられている", "懸念される", "指摘されている", "と分析されている", "浮き彫りにしている", "求められる", "直結する"]
    found = [w for w in forbidden if w in body]
    if found:
        score -= len(found)
        reasons.append(f"禁止ワード: {', '.join(found[:3])}")

    # bodyの長さチェック
    if len(body) < 200:
        score -= 3
        reasons.append("本文短すぎ")
    elif len(body) < 400:
        score -= 1
        reasons.append("本文やや短い")

    # JapanTruthの視点チェック
    if "JapanTruthの視点" not in body:
        score -= 2
        reasons.append("JapanTruthの視点なし")

    # 省略チェック
    if "省略" in body or "省略" in excerpt:
        score -= 2
        reasons.append("省略あり")

    # 背景セクションチェック
    if "## 背景" not in body:
        score -= 1
        reasons.append("背景なし")

    # 何が起きているのかセクションチェック
    if "## 何が起きているのか" not in body:
        score -= 2
        reasons.append("何が起きているのかなし")

    # excerptチェック
    if len(excerpt) < 20:
        score -= 1
        reasons.append("excerpt短い")
    elif len(excerpt) < 50:
        score -= 1
        reasons.append("excerptやや短い")
    bad_excerpts = ["が発表された", "が明らかになった", "が行われた", "が報じられた", "が確認された"]
    if any(w in excerpt for w in bad_excerpts):
        score -= 1
        reasons.append("excerpt平凡")

    # 禁止ワード追加ペナルティ（多いほど重い）
    if len(found) >= 3:
        score -= 2
        reasons.append("禁止ワード多数")

    score = max(0, score)
    return score, reasons

def verify_and_fix_proper_nouns(source_title, result):
    """8bモデルで固有名詞の誤訳をチェック・修正"""
    import requests as _req
    title_jp = result.get("title", "")
    body_jp = result.get("body", "")[:800]

    prompt = (
        f"Source English title: {source_title}\n"
        f"Japanese title: {title_jp}\n"
        f"Japanese body (first 800 chars): {body_jp}\n\n"
        f"Find ONLY clearly wrong transliterations of person names, organization names, or medical terms.\n"
        f"Common errors to check: Hantavirus(ハンタウイルス), Anthropic(アンソロピック), "
        f"Nigel Farage(ナイジェル・ファラージュ), names ending in wrong katakana.\n"
        f"If you find errors, respond ONLY in this format (one per line):\n"
        f"FIX: [wrong]|[correct]\n"
        f"If no errors, respond: OK"
    )

    for key in GROQ_API_KEYS:
        if not key:
            continue
        try:
            res = _req.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0
                },
                timeout=10
            )
            data = res.json()
            if "error" in data:
                continue
            response = data["choices"][0]["message"]["content"].strip()
            if response == "OK":
                return result
            fixes = {}
            for line in response.split("\n"):
                if line.startswith("FIX:") and "|" in line:
                    parts = line[4:].strip().split("|")
                    if len(parts) == 2:
                        wrong, correct = parts[0].strip(), parts[1].strip()
                        if wrong and correct and wrong != correct:
                            fixes[wrong] = correct
            if fixes:
                print(f"🔧 固有名詞修正: {fixes}")
                for k, v in result.items():
                    if isinstance(v, str):
                        for wrong, correct in fixes.items():
                            v = v.replace(wrong, correct)
                        result[k] = v
            return result
        except Exception as e:
            print(f"⚠️ 固有名詞チェックエラー: {e}")
            continue
    return result



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
        url = f"https://res.cloudinary.com/dnqswecpg/image/upload/f_webp,q_auto/{public_id}.webp" if public_id else raw_url
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
        return full_text[:3500]
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
            # 過去6時間の同一ドメイン記事数チェック（最大3件まで）
            import urllib.parse as _ulp
            _domain = _ulp.urlparse(feed_info["url"]).netloc
            _cutoff6h = (datetime.now(JST) - timedelta(hours=6)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _sb_url2 = "https://xhvvxfvxkqcadqhdqtmn.supabase.co"
            _sb_key2 = os.environ.get("SUPABASE_SERVICE_KEY", "")
            _h2 = {"apikey": _sb_key2, "Authorization": f"Bearer {_sb_key2}", "Prefer": "count=exact"}
            _count_res = requests.get(f"{_sb_url2}/rest/v1/posts?select=count&source_url=like.*{_domain}*&created_at=gte.{_cutoff6h}", headers=_h2, timeout=5)
            _domain_count = int(_count_res.headers.get("content-range", "0-0/0").split("/")[-1])
            if _domain_count >= 5:
                print(f"⏭️ {_domain}は過去6時間に{_domain_count}件済み → スキップ")
                continue
            for entry in feed.entries[:2]:
                url = entry.link
                article_id = hashlib.md5(url.encode()).hexdigest()
                if "/video/" in url or "/videos/" in url or "/opinion/" in url or "/opinions/" in url or "/commentary/" in url:
                    continue
                summary = getattr(entry, "summary", entry.title)
                if len(summary) < 100:
                    continue
                if article_id not in seen and url not in seen:
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
    used_topics = {}  # {title: datetime} 3時間以内の類似トピック管理
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
        import random as _random
        new_articles = collect_new_articles(seen)
        _random.shuffle(new_articles)
        print(f"📋 新着記事: {len(new_articles)}件")
        # 全件チェック（最大10件）

        cycle_count = 0
        _cycle_generated_titles = []  # 同一サイクル内の生成済みタイトル
        for article in new_articles:
            if cycle_count >= 2:
                break
            # 類似トピックチェック（Supabaseで過去3時間の記事と比較）
            _now = datetime.now(JST)
            # ストップワードを除外してコアキーワードで比較
            _stop = {"the","a","an","of","in","on","at","to","for","is","are","was","were",
                     "as","by","with","from","that","this","it","be","has","have","had",
                     "and","or","but","not","will","says","say","said","after","over",
                     "new","us","its","their","his","her","s","how","why","what","who"}
            _title_norm = article["title"].lower().replace("three-day","3-day").replace("three day","3 day")
            _title_words = set(w for w in _title_norm.split() if w not in _stop and len(w) > 2)
            _recent = {t: dt for t, dt in used_topics.items() if (_now - dt).total_seconds() < 10800}
            used_topics = _recent
            # 常にSupabaseから過去3時間の記事を取得
            import requests as _rq
            import urllib.parse as _up
            _sb_url = "https://xhvvxfvxkqcadqhdqtmn.supabase.co"
            _sb_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
            _h = {"apikey": _sb_key, "Authorization": f"Bearer {_sb_key}"}
            _cutoff = (_now - timedelta(hours=3)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _res = _rq.get(f"{_sb_url}/rest/v1/posts?select=title,source_url,created_at&created_at=gte.{_cutoff}&order=created_at.desc&limit=100", headers=_h, timeout=5)
            _recent_posts = _res.json() if isinstance(_res.json(), list) else []
            _recent_titles = [p.get("title","") for p in _recent_posts]
            # source_urlのスラグも英語比較用に追加
            _recent_slugs = [" ".join(p.get("source_url","").replace("-"," ").replace("_"," ").split("/")[-3:]) for p in _recent_posts]
            _recent_urls = [p.get("source_url","") or "" for p in _recent_posts]
            _article_url_base = _up.urlparse(article["url"])._replace(query="", fragment="").geturl()
            _recent_urls_base = [_up.urlparse(u)._replace(query="", fragment="").geturl() for u in _recent_urls]
            import re as _re
            _stop_ja = {"の","が","を","に","は","で","と","も","な","する","した","て","や","へ","から","まで","より","として","による","大統領","首相","氏","戦争","問題","発言","表明"}
            _jp_words = lambda t: set(w for w in _re.findall(r"[ァ-ヴー]{3,}|[一-龥]{2,}", t) if w not in _stop_ja)
            _is_similar = any(len(_title_words & set(w for w in t.lower().split() if w not in _stop and len(w) > 2)) >= 2 for t in _recent)
            _is_similar = _is_similar or (_article_url_base in _recent_urls_base) or any(
                len(_title_words & set(w for w in t.lower().split() if w not in _stop and len(w) > 2)) >= 2
                for t in _recent_titles
            ) or any(len(_jp_words(article["title"]) & _jp_words(t)) >= 2 for t in _recent_titles)
            # 英語スラグとの比較
            _is_similar = _is_similar or any(
                len(_title_words & set(w for w in s.lower().split() if w not in _stop and len(w) > 3)) >= 2
                for s in _recent_slugs
            )
            # 同一サイクル内の生成済みタイトルと比較
            import re as _re2
            _jp_words2 = lambda t: set(w for w in _re2.findall(r"[ァ-ヴー]{3,}|[一-龥]{2,}", t) if w not in _stop_ja)
            _is_similar = _is_similar or any(
                len(_jp_words2(article["title"]) & _jp_words2(t)) >= 2
                for t in _cycle_generated_titles
            ) or any(
                len(_title_words & set(w for w in t.lower().split() if w not in _stop and len(w) > 2)) >= 2
                for t in _cycle_generated_titles
            )

            # 同一ドメインからの類似記事チェック
            import urllib.parse as _up2
            _domain = _up2.urlparse(article["url"]).netloc
            _domain_recent = [p for p in _recent_posts if _domain in (p.get("source_url","") or "")]
            _domain_title_words = set(w for w in article["title"].lower().split() if w not in _stop and len(w) > 3)
            _domain_similar = any(
                len(_domain_title_words & set(w for w in (p.get("title","") or "").lower().split() if len(w) > 3)) >= 2
                for p in _domain_recent
            )
            if _domain_similar:
                _is_similar = True
                print(f"⏭️ 同一ドメイン類似: {_domain}")

            # ① トピッククラスタリング：固有名詞2語一致でスキップ（6時間以内）
            if not _is_similar:
                _cutoff6h = (_now - timedelta(hours=6)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                _res6h = _rq.get(f"{_sb_url}/rest/v1/posts?select=title,source_url&created_at=gte.{_cutoff6h}&order=created_at.desc&limit=200", headers=_h, timeout=5)
                _posts6h = _res6h.json() if isinstance(_res6h.json(), list) else []
                _proper_nouns = set(w for w in _title_words if w[0].isupper() or len(w) >= 5)
                for _p6h in _posts6h:
                    _pt = (_p6h.get("title","") or "").lower()
                    _pt_words = set(w for w in _pt.split() if w not in _stop and len(w) > 2)
                    _common_proper = _proper_nouns & _pt_words
                    if len(_common_proper) >= 2:
                        _is_similar = True
                        print(f"⏭️ トピック一致（6時間）: {list(_common_proper)[:3]}")
                        break

            # ③ 生成済み日本語タイトルでも比較（6時間以内）
            if not _is_similar:
                _jp_recent = [p.get("title","") or "" for p in _posts6h]
                _is_similar = any(
                    len(_title_words & set(w for w in t.lower().split() if w not in _stop and len(w) > 2)) >= 2
                    for t in _jp_recent
                )

            # ④ カテゴリ×キーワード組み合わせ（2時間以内）
            if not _is_similar:
                _cutoff2h = (_now - timedelta(hours=2)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                _res2h = _rq.get(f"{_sb_url}/rest/v1/posts?select=title,tags,categories&created_at=gte.{_cutoff2h}&categories=eq.{article['category']}&limit=50", headers=_h, timeout=5)
                _posts2h = _res2h.json() if isinstance(_res2h.json(), list) else []
                for _p2h in _posts2h:
                    _pt_words = set(w for w in (_p2h.get("title","") or "").lower().split() if w not in _stop and len(w) > 3)
                    if len(_title_words & _pt_words) >= 2:
                        _is_similar = True
                        print(f"⏭️ 同カテゴリ類似（2時間）: {article['category']}")
                        break
            if _is_similar:
                # 3時間以内は完全スキップ、3〜6時間は続報として掲載
                _age_hours = 0
                for _recent_post in _recent_posts:
                    _ru = _up.urlparse(_recent_post.get("source_url","") or "")._replace(query="", fragment="").geturl()
                    if _ru == _article_url_base:
                        _age_hours = 99  # 同一URL→完全スキップ
                        break
                    # created_atで経過時間を計算
                    _cat = _recent_post.get("created_at","")
                    if _cat:
                        try:
                            from dateutil import parser as _dp
                            _post_time = _dp.parse(_cat).replace(tzinfo=timezone.utc)
                            _hours = (_now.astimezone(timezone.utc) - _post_time).total_seconds() / 3600
                            if _hours < _age_hours or _age_hours == 0:
                                _age_hours = _hours
                        except:
                            pass
                if _age_hours >= 99 or _age_hours < 3:
                    seen.add(article["id"])
                    save_seen(seen, seen_images)
                    print(f"⏭️ 類似トピック（3時間以内）をスキップ: {article['title'][:50]}")
                    continue
                else:
                    article["is_followup"] = True
                    print(f"📰 続報として処理: {article['title'][:50]}")
            seen.add(article["id"])
            save_seen(seen, seen_images)
            print(f"🔎 判定中 [8b]: {article['title'][:60]}")
            is_breaking, image_kw = screen_article(article["title"], article.get("content", ""), recent_titles=_recent_titles)
            if not is_breaking:
                print("⏭️ ブレイキングニュースではないのでスキップ")
                continue
            article["image_kw"] = image_kw
            time.sleep(3)  # TPM制限対策
            print(f"🌐 記事本文スクレイピング中: {article['url'][:60]}")
            # 古い記事（2年以上前）をスキップ
            import re as _re_year
            _year_match = _re_year.search(r"/20(\\d{2})/", article["url"])
            if _year_match:
                _article_year = int("20" + _year_match.group(1))
                from datetime import datetime as _dt
                if _dt.now().year - _article_year >= 2:
                    print(f"⏭️ 古い記事をスキップ（{_article_year}年）: {article['title'][:50]}")
                    continue
            scraped = scrape_article(article["url"])
            if scraped:
                print(f"✅ スクレイピング成功: {len(scraped)}文字取得")
                article["content"] = scraped
            else:
                print(f"⚠️ スクレイピング失敗 → スキップ")
                continue
            print(f"📰 処理中 [Qwen3-32b]: {article['title'][:60]}")
            _processed = summarize_article(article["title"], article["content"], article["category"])
            result = _processed  # 互換性のため
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
            # 日本語タイトルで重複チェック（生成後）
            import re as _re_jp
            _stop_ja2 = {"の","が","を","に","は","で","と","も","な","する","した","て","や","へ","から","まで","より","として","による","大統領","首相","氏","問題","発言","表明","報告","発表"}
            _jp_title = result.get("title","") or ""
            _jp_title_words = set(w for w in _re_jp.findall(r"[ァ-ヴー]{3,}|[一-龥]{2,}", _jp_title) if w not in _stop_ja2)
            _jp_dup = False
            for _rt in _recent_titles + list(_cycle_generated_titles):
                _rt_words = set(w for w in _re_jp.findall(r"[ァ-ヴー]{3,}|[一-龥]{2,}", _rt) if w not in _stop_ja2)
                if len(_jp_title_words & _rt_words) >= 2:
                    _jp_dup = True
                    print(f"⏭️ 日本語タイトル類似でスキップ: {_jp_title[:40]}")
                    break
            if _jp_dup:
                seen.add(article["id"])
                save_seen(seen, seen_images)
                # skipped_urlsに保存
                try:
                    _rq.post(
                        f"{_sb_url}/rest/v1/skipped_urls",
                        headers={**_h, "Content-Type": "application/json"},
                        json={"url": article["id"], "reason": "jp_title_dup"},
                        timeout=5
                    )
                except:
                    pass
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
            tags = generate_tags(_processed.get("title", article["title"]), cat)
            if image_path != "/japantruth.png":
                seen_images.add(image_path)
            save_to_supabase(
                slug, _processed.get("title", article["title"]),
                date_str, time_str, cat,
                _processed.get("excerpt", ""), image_path,
                article["url"], _processed.get("body", ""),
                article["source"], tags
            )
            article_url = f"https://www.japan-truth.com/posts/{slug}"
            # post_to_x(result.get("title", article["title"]), article_url, image_path)  # 手動シェア
            daily_count += 1
            used_topics[article["title"]] = datetime.now(JST)
            if article.get("is_followup") and _processed and _processed.get("title"):
                if not _processed["title"].startswith("【続報】"):
                    _processed["title"] = "【続報】" + _processed["title"]
            if _processed and _processed.get("title"):
                used_topics[_processed["title"]] = datetime.now(JST)
                # 生成済み日本語タイトルをSupabaseの_recent_titlesに即座に追加
                _recent_titles.append(_processed["title"])
                _cycle_generated_titles.append(_processed["title"])
                _cycle_generated_titles.append(article["title"])  # 英語タイトルも追加
            cycle_count += 1
            print(f"📊 本日の投稿数: {daily_count}/100 | スキップ: {skip_count}件")
            time.sleep(20)

        print("💤 15分待機中...")
        time.sleep(1800)
        # translation_checkerを15分ごとに実行
        try:
            import subprocess
            print("🔍 translation_checker実行中...")
            subprocess.run(["python3", "translation_checker.py"], timeout=300, capture_output=False)
            print("✅ translation_checker完了")
        except Exception as _tce:
            print(f"⚠️ translation_checker失敗: {_tce}")



main()
