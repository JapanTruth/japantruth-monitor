import os, sys, time, json, hashlib, re, requests, feedparser, subprocess
from datetime import datetime, timezone, timedelta
from PIL import Image
from io import BytesIO

# news_monitor.pyを読み込んで実行（Flaskなし、ループなし）
with open(os.path.join(os.path.dirname(__file__), 'news_monitor.py')) as f:
    code = f.read()

# Flaskサーバー部分を除去
code = code.replace('Thread(target=run_server, daemon=True).start()\nmain()', 'main()')

# whileループを1回だけに
code = code.replace('    while True:', '    if True:')
code = code.replace("        print('💤 15分待機中...')\n        time.sleep(1800)", "        print('✅ 1サイクル完了')\n        break")
code = code.replace('        print("💤 15分待機中...")\n        time.sleep(1800)', '        print("✅ 1サイクル完了")\n        break')

exec(compile(code, 'news_monitor.py', 'exec'))
