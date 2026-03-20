"""
RPGツクールMZ セリフ入力アシスト（JSON直接編集版）

MapXXX.json / CommonEvents.json を直接編集して「文章の表示」コマンドを追加する。
GUI操作不要、ツクールを閉じた状態で実行すること。

使い方:
  python serif_json.py <テキストファイル> <Map.json> [イベントID] [ページ番号]
  python serif_json.py <テキストファイル> <CommonEvents.json> [コモンイベントID]

テキストフォーマット:
  【名前/顔ファイル:顔番号】
  セリフ1行目
  セリフ2行目
  （空行で区切り＝次の文章コマンド）

  例:
  【リード/Actor1:0】
  こんにちは！
  今日はいい天気ですね。

  【エリナ/Actor1:1】
  そうですね！

  背景タイプ: {bg=0} ウィンドウ(デフォルト), {bg=1} 暗くする, {bg=2} 透明
  ウィンドウ位置: {pos=0} 上, {pos=1} 中, {pos=2} 下(デフォルト)
  書き込みモード: {mode=append} 末尾追加(デフォルト), {mode=replace} 既存を置換
"""

import json
import sys
import re
import os
import shutil
import io
import glob
import datetime

# Windows コンソール出力の文字化け対策（GUI版ではstdoutがNoneになる）
if sys.stdout and sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


MAX_LINES_PER_MESSAGE = 4


def read_text_file(filepath):
    """テキストファイルを読み込む（エンコーディング自動判定）"""
    # 優先順: UTF-8 BOM → UTF-8 → Shift-JIS → CP932
    encodings = ['utf-8-sig', 'utf-8', 'shift_jis', 'cp932']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                content = f.read()
            return content
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"テキストファイルのエンコーディングを判定できません: {filepath}")


def parse_header(line):
    """【名前/顔ファイル:インデックス】をパース"""
    m = re.match(r'【(.*?)】', line)
    if not m:
        return None

    content = m.group(1)
    name = ""
    face_file = ""
    face_index = 0

    if '/' in content:
        name, face_part = content.split('/', 1)
        if ':' in face_part:
            face_file, idx = face_part.rsplit(':', 1)
            face_index = int(idx)
        else:
            face_file = face_part
    else:
        name = content

    return {
        'name': name.strip(),
        'face_file': face_file.strip(),
        'face_index': face_index,
    }


def parse_text_file(filepath):
    """テキストファイルをパースしてメッセージコマンドのリストを返す"""
    content = read_text_file(filepath)
    return parse_text_string(content)


def parse_text_string(text):
    """テキスト文字列をパースしてメッセージコマンドのリストを返す"""
    lines = text.split('\n')

    messages = []
    current_header = {'name': '', 'face_file': '', 'face_index': 0}
    current_lines = []
    bg_type = 0   # ウィンドウ
    pos_type = 2  # 下

    def flush():
        nonlocal current_lines
        if not current_lines:
            return
        for i in range(0, len(current_lines), MAX_LINES_PER_MESSAGE):
            chunk = current_lines[i:i + MAX_LINES_PER_MESSAGE]
            messages.append({
                **current_header,
                'lines': chunk,
                'bg_type': bg_type,
                'pos_type': pos_type,
            })
        current_lines = []

    for line in lines:
        line = line.rstrip('\n').rstrip('\r')

        if line.startswith('#'):
            continue

        # 設定行
        bg_match = re.search(r'\{bg=(\d)\}', line)
        if bg_match:
            bg_type = int(bg_match.group(1))
            continue
        pos_match = re.search(r'\{pos=(\d)\}', line)
        if pos_match:
            pos_type = int(pos_match.group(1))
            continue

        # mode指定はパーサーでは無視（呼び出し側で処理）
        if re.match(r'\{mode=\w+\}', line):
            continue

        header = parse_header(line)
        if header is not None:
            flush()
            current_header = header
            continue

        if line.strip() == '':
            flush()
            continue

        current_lines.append(line)

    flush()
    return messages


def parse_mode_from_text(text):
    """テキストから書き込みモードを取得（append or replace）"""
    m = re.search(r'\{mode=(\w+)\}', text)
    if m:
        return m.group(1)
    return 'append'


def messages_to_commands(messages):
    """メッセージリストをMZイベントコマンドのリストに変換"""
    commands = []
    for msg in messages:
        cmd_101 = {
            "code": 101,
            "indent": 0,
            "parameters": [
                msg['face_file'],
                msg['face_index'],
                msg['bg_type'],
                msg['pos_type'],
                msg['name'],
            ]
        }
        commands.append(cmd_101)

        for line in msg['lines']:
            cmd_401 = {
                "code": 401,
                "indent": 0,
                "parameters": [line]
            }
            commands.append(cmd_401)

    return commands


def make_empty_event(event_id, x=0, y=0):
    """空のイベントデータを生成"""
    return {
        'id': event_id,
        'name': f'EV{event_id:03d}',
        'note': '',
        'x': x,
        'y': y,
        'pages': [make_empty_page()]
    }


def make_empty_page():
    """空のイベントページを生成"""
    return {
        'conditions': {
            'actorId': 1, 'actorValid': False,
            'itemId': 1, 'itemValid': False,
            'selfSwitchCh': 'A', 'selfSwitchValid': False,
            'switch1Id': 1, 'switch1Valid': False,
            'switch2Id': 1, 'switch2Valid': False,
            'variableId': 1, 'variableValid': False, 'variableValue': 0,
        },
        'directionFix': False,
        'image': {
            'characterIndex': 0, 'characterName': '',
            'direction': 2, 'pattern': 1, 'tileId': 0,
        },
        'list': [{'code': 0, 'indent': 0, 'parameters': []}],
        'moveFrequency': 3,
        'moveRoute': {
            'list': [{'code': 0, 'parameters': []}],
            'repeat': True, 'skippable': False, 'wait': False,
        },
        'moveSpeed': 3, 'moveType': 0, 'priorityType': 0,
        'stepAnime': False, 'through': False, 'trigger': 0, 'walkAnime': True,
    }


def find_empty_position(map_data):
    """マップ上でイベントが存在しない位置を探す"""
    occupied = set()
    for ev in map_data.get('events', []):
        if ev:
            occupied.add((ev['x'], ev['y']))

    width = map_data.get('width', 17)
    height = map_data.get('height', 13)

    # 中央付近から探す
    cx, cy = width // 2, height // 2
    for r in range(max(width, height)):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                x, y = cx + dx, cy + dy
                if 0 <= x < width and 0 <= y < height and (x, y) not in occupied:
                    return x, y
    return 0, 0


def ensure_event_exists(map_data, event_id):
    """指定IDのイベントが存在しなければ自動作成する。作成したらTrue"""
    events = map_data.get('events', [])

    # events配列を必要な長さまで拡張
    while len(events) <= event_id:
        events.append(None)
    map_data['events'] = events

    if events[event_id] is not None:
        return False  # 既存

    # 空き位置を探してイベント作成
    x, y = find_empty_position(map_data)
    events[event_id] = make_empty_event(event_id, x, y)
    return True  # 新規作成


def ensure_page_exists(event, page_index):
    """指定ページが存在しなければ自動作成する。作成したらTrue"""
    while len(event['pages']) <= page_index:
        event['pages'].append(make_empty_page())
        created = True
    else:
        created = False
    return page_index >= len(event['pages']) - 1 and created


def inject_commands(map_data, event_id, page_index, new_commands, mode='append'):
    """
    マップデータの指定イベント・ページにコマンドを挿入する。

    mode:
      'append' - 既存コマンドの末尾（code=0の直前）に追加
      'replace' - 既存コマンドを全て置換
    """
    # イベントが存在しなければ自動作成
    created = ensure_event_exists(map_data, event_id)

    event = map_data['events'][event_id]

    # ページが存在しなければ自動作成
    while len(event['pages']) <= page_index:
        event['pages'].append(make_empty_page())

    page = event['pages'][page_index]
    cmd_list = page['list']

    if mode == 'replace':
        # 既存コマンドを全て置換
        page['list'] = new_commands + [{'code': 0, 'indent': 0, 'parameters': []}]
    else:
        # 末尾の code=0 の直前に挿入
        if cmd_list and cmd_list[-1]['code'] == 0:
            insert_pos = len(cmd_list) - 1
        else:
            insert_pos = len(cmd_list)

        for i, cmd in enumerate(new_commands):
            cmd_list.insert(insert_pos + i, cmd)

    return True, created


def inject_commands_common(common_events, event_id, new_commands, mode='append'):
    """
    コモンイベントにコマンドを挿入する。
    """
    event = None
    for ev in common_events:
        if ev and ev.get('id') == event_id:
            event = ev
            break

    if not event:
        return False, False

    cmd_list = event['list']

    if mode == 'replace':
        event['list'] = new_commands + [{'code': 0, 'indent': 0, 'parameters': []}]
    else:
        if cmd_list and cmd_list[-1]['code'] == 0:
            insert_pos = len(cmd_list) - 1
        else:
            insert_pos = len(cmd_list)

        for i, cmd in enumerate(new_commands):
            cmd_list.insert(insert_pos + i, cmd)

    return True, False


def backup_file(filepath):
    """世代管理付きバックアップを作成"""
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{filepath}.{timestamp}.bak"
    shutil.copy2(filepath, backup_path)

    # 古いバックアップを10世代まで保持
    bak_pattern = f"{filepath}.*.bak"
    baks = sorted(glob.glob(bak_pattern), reverse=True)
    for old_bak in baks[10:]:
        try:
            os.remove(old_bak)
        except OSError:
            pass

    return backup_path


def is_common_events_file(filepath):
    """CommonEvents.jsonかどうか判定"""
    return os.path.basename(filepath).lower() == 'commonevents.json'


def main():
    print("=" * 50)
    print("RPGツクールMZ セリフ入力（JSON直接編集版）")
    print("=" * 50)
    print()

    if len(sys.argv) < 3:
        print("使い方: python serif_json.py <テキストファイル> <Map.json> [イベントID] [ページ番号]")
        print("        python serif_json.py <テキストファイル> <CommonEvents.json> [コモンイベントID]")
        print()
        print("例: python serif_json.py script.txt Map001.json 1 0")
        return

    text_file = sys.argv[1]
    map_file = sys.argv[2]
    event_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    page_index = int(sys.argv[4]) if len(sys.argv) > 4 else 0

    # テキストパース
    messages = parse_text_file(text_file)
    if not messages:
        print("入力するメッセージがありません。")
        return

    # テキストからモードを取得
    content = read_text_file(text_file)
    mode = parse_mode_from_text(content)

    is_common = is_common_events_file(map_file)

    print(f"テキストファイル: {text_file}")
    print(f"{'コモンイベント' if is_common else 'マップ'}ファイル: {map_file}")
    print(f"イベントID: {event_id}" + (f", ページ: {page_index}" if not is_common else ""))
    print(f"メッセージ数: {len(messages)}")
    print(f"モード: {'置換' if mode == 'replace' else '追加'}")
    print()

    for i, msg in enumerate(messages):
        face = f" [{msg['face_file']}:{msg['face_index']}]" if msg['face_file'] else ""
        name = f" {msg['name']}" if msg['name'] else ""
        lines_preview = ' / '.join(msg['lines'])[:50]
        print(f"  {i+1}.{name}{face}: {lines_preview}...")
    print()

    # JSON読み込み
    with open(map_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # コマンド生成
    commands = messages_to_commands(messages)
    print(f"生成コマンド数: {len(commands)}")
    print()

    # バックアップ
    bak_path = backup_file(map_file)
    print(f"バックアップ: {bak_path}")

    # 挿入
    if is_common:
        success, _ = inject_commands_common(data, event_id, commands, mode)
    else:
        success, created = inject_commands(data, event_id, page_index, commands, mode)
        if created:
            ev = data['events'][event_id]
            print(f"イベントID {event_id} を新規作成しました（位置: {ev['x']},{ev['y']}）")

    if success:
        with open(map_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"書き込み完了: {map_file}")
        print()
        print("ツクールMZでプロジェクトを開き直すと反映されます。")
    else:
        print("書き込み失敗。イベントIDを確認してください。")


if __name__ == '__main__':
    main()
