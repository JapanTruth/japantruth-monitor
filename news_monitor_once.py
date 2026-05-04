import os, sys

with open(os.path.join(os.path.dirname(__file__), 'news_monitor.py')) as f:
    lines = f.readlines()

new_lines = []
skip_next = False
for i, line in enumerate(lines):
    # Flaskスレッド起動とmain()を置換
    if line.strip() == 'Thread(target=run_server, daemon=True).start()':
        continue
    # while Trueをif Trueに
    if '    while True:' in line:
        new_lines.append(line.replace('    while True:', '    if True:'))
        continue
    # 15分待機とtime.sleepをスキップ
    if 'time.sleep(1800)' in line:
        new_lines.append(line.replace('time.sleep(1800)', 'sys.exit(0)'))
        continue
    new_lines.append(line)

code = ''.join(new_lines)
exec(compile(code, 'news_monitor.py', 'exec'))
