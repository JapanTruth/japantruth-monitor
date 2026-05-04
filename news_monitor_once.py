# GitHub Actions用：1回だけ実行して終了
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

# news_monitor.pyから必要な関数をインポートして1回だけ実行
exec(open('news_monitor.py').read().replace(
    'while True:',
    'if True:'
).replace(
    "print('💤 15分待機中...')\n        time.sleep(1800)",
    "print('✅ 1サイクル完了')\n        break"
).replace(
    'Thread(target=run_server, daemon=True).start()\nmain()',
    'main()'
))
