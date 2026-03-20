"""
serif_json.py のテスト
"""

import json
import os
import glob
import unittest
from serif_json import (
    parse_text_file, parse_text_string, parse_mode_from_text,
    messages_to_commands, inject_commands, inject_commands_common,
    parse_header, backup_file, read_text_file, is_common_events_file,
    make_empty_event, find_empty_position,
)


class TestParseHeader(unittest.TestCase):
    def test_name_and_face(self):
        h = parse_header('【リード/Actor1:0】')
        self.assertEqual(h['name'], 'リード')
        self.assertEqual(h['face_file'], 'Actor1')
        self.assertEqual(h['face_index'], 0)

    def test_name_and_face_index(self):
        h = parse_header('【エリナ/Actor2:7】')
        self.assertEqual(h['name'], 'エリナ')
        self.assertEqual(h['face_file'], 'Actor2')
        self.assertEqual(h['face_index'], 7)

    def test_name_only(self):
        h = parse_header('【村人】')
        self.assertEqual(h['name'], '村人')
        self.assertEqual(h['face_file'], '')
        self.assertEqual(h['face_index'], 0)

    def test_empty_narrator(self):
        h = parse_header('【】')
        self.assertEqual(h['name'], '')
        self.assertEqual(h['face_file'], '')

    def test_not_header(self):
        self.assertIsNone(parse_header('普通のテキスト'))
        self.assertIsNone(parse_header(''))


class TestParseTextString(unittest.TestCase):
    def test_basic(self):
        text = "【リード/Actor1:0】\nこんにちは\n今日はいい天気\n"
        msgs = parse_text_string(text)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]['name'], 'リード')
        self.assertEqual(msgs[0]['lines'], ['こんにちは', '今日はいい天気'])

    def test_multiple_messages(self):
        text = "【A】\nセリフ1\n\n【B】\nセリフ2\n"
        msgs = parse_text_string(text)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]['name'], 'A')
        self.assertEqual(msgs[1]['name'], 'B')

    def test_auto_split_4lines(self):
        text = "【A】\n1\n2\n3\n4\n5\n"
        msgs = parse_text_string(text)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]['lines'], ['1', '2', '3', '4'])
        self.assertEqual(msgs[1]['lines'], ['5'])

    def test_narrator(self):
        text = "【リード/Actor1:0】\nセリフ\n\n【】\nナレーション\n"
        msgs = parse_text_string(text)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[1]['name'], '')
        self.assertEqual(msgs[1]['face_file'], '')

    def test_bg_and_pos(self):
        text = "{bg=1}\n{pos=0}\n【A】\nテスト\n"
        msgs = parse_text_string(text)
        self.assertEqual(msgs[0]['bg_type'], 1)
        self.assertEqual(msgs[0]['pos_type'], 0)

    def test_comment_ignored(self):
        text = "# コメント\n【A】\nテスト\n# もう1つコメント\n"
        msgs = parse_text_string(text)
        self.assertEqual(len(msgs), 1)

    def test_mode_ignored_in_parse(self):
        text = "{mode=replace}\n【A】\nテスト\n"
        msgs = parse_text_string(text)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]['lines'], ['テスト'])

    def test_control_characters_passthrough(self):
        text = '【A】\n\\C[1]赤いテキスト\\C[0]\n\\V[1]番の変数\n\\N[1]の名前\n'
        msgs = parse_text_string(text)
        self.assertIn('\\C[1]', msgs[0]['lines'][0])
        self.assertIn('\\V[1]', msgs[0]['lines'][1])
        self.assertIn('\\N[1]', msgs[0]['lines'][2])

    def test_header_persists(self):
        text = "【A/Actor1:0】\nセリフ1\n\nセリフ2\n"
        msgs = parse_text_string(text)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]['name'], 'A')
        self.assertEqual(msgs[1]['name'], 'A')
        self.assertEqual(msgs[1]['face_file'], 'Actor1')

    def test_empty_text(self):
        msgs = parse_text_string("")
        self.assertEqual(len(msgs), 0)

    def test_only_comments(self):
        msgs = parse_text_string("# comment\n# another\n")
        self.assertEqual(len(msgs), 0)


class TestParseMode(unittest.TestCase):
    def test_default(self):
        self.assertEqual(parse_mode_from_text("hello"), 'append')

    def test_replace(self):
        self.assertEqual(parse_mode_from_text("{mode=replace}\n【A】\ntest"), 'replace')

    def test_append(self):
        self.assertEqual(parse_mode_from_text("{mode=append}"), 'append')


class TestMessagesToCommands(unittest.TestCase):
    def test_basic(self):
        msgs = [{'name': 'A', 'face_file': 'Actor1', 'face_index': 0,
                 'bg_type': 0, 'pos_type': 2, 'lines': ['こんにちは', '元気？']}]
        cmds = messages_to_commands(msgs)
        self.assertEqual(len(cmds), 3)  # 1x101 + 2x401
        self.assertEqual(cmds[0]['code'], 101)
        self.assertEqual(cmds[0]['parameters'], ['Actor1', 0, 0, 2, 'A'])
        self.assertEqual(cmds[1]['code'], 401)
        self.assertEqual(cmds[1]['parameters'], ['こんにちは'])
        self.assertEqual(cmds[2]['code'], 401)
        self.assertEqual(cmds[2]['parameters'], ['元気？'])


class TestEncoding(unittest.TestCase):
    def setUp(self):
        self.files = []

    def tearDown(self):
        for f in self.files:
            if os.path.exists(f):
                os.remove(f)

    def _write(self, name, encoding, content):
        path = f'_test_{name}.txt'
        self.files.append(path)
        with open(path, 'w', encoding=encoding) as f:
            f.write(content)
        return path

    def test_utf8(self):
        p = self._write('utf8', 'utf-8', '【リード】\nこんにちは\n')
        msgs = parse_text_file(p)
        self.assertEqual(msgs[0]['name'], 'リード')

    def test_shift_jis(self):
        p = self._write('sjis', 'shift_jis', '【リード】\nこんにちは\n')
        msgs = parse_text_file(p)
        self.assertEqual(msgs[0]['name'], 'リード')

    def test_utf8_bom(self):
        p = self._write('bom', 'utf-8-sig', '【リード】\nこんにちは\n')
        msgs = parse_text_file(p)
        self.assertEqual(msgs[0]['name'], 'リード')


class TestEventAutoCreate(unittest.TestCase):
    def test_create_new_event(self):
        map_data = {'width': 17, 'height': 13, 'data': [], 'events': [None]}
        cmds = messages_to_commands(parse_text_string('【A】\nテスト\n'))
        success, created = inject_commands(map_data, 3, 0, cmds)
        self.assertTrue(success)
        self.assertTrue(created)
        self.assertIsNotNone(map_data['events'][3])
        self.assertEqual(map_data['events'][3]['id'], 3)
        # 中身にコマンドが入っている
        page_cmds = map_data['events'][3]['pages'][0]['list']
        self.assertTrue(any(c['code'] == 101 for c in page_cmds))

    def test_existing_event_not_recreated(self):
        map_data = {'width': 17, 'height': 13, 'data': [],
                    'events': [None, make_empty_event(1, 5, 5)]}
        cmds = messages_to_commands(parse_text_string('【A】\nテスト\n'))
        success, created = inject_commands(map_data, 1, 0, cmds)
        self.assertTrue(success)
        self.assertFalse(created)

    def test_events_array_padded(self):
        map_data = {'width': 17, 'height': 13, 'data': [], 'events': [None]}
        cmds = messages_to_commands(parse_text_string('【A】\nテスト\n'))
        inject_commands(map_data, 5, 0, cmds)
        self.assertEqual(len(map_data['events']), 6)  # [None, None, None, None, None, EV5]
        self.assertIsNone(map_data['events'][1])
        self.assertIsNotNone(map_data['events'][5])

    def test_position_avoids_collision(self):
        map_data = {'width': 17, 'height': 13, 'data': [],
                    'events': [None, make_empty_event(1, 8, 6)]}
        x, y = find_empty_position(map_data)
        self.assertNotEqual((x, y), (8, 6))


class TestInjectCommands(unittest.TestCase):
    def _make_map(self):
        return {'width': 17, 'height': 13, 'data': [],
                'events': [None, make_empty_event(1, 5, 5)]}

    def test_append_mode(self):
        map_data = self._make_map()
        cmds1 = messages_to_commands(parse_text_string('【A】\n1行目\n'))
        cmds2 = messages_to_commands(parse_text_string('【B】\n2行目\n'))
        inject_commands(map_data, 1, 0, cmds1, 'append')
        inject_commands(map_data, 1, 0, cmds2, 'append')
        page_cmds = map_data['events'][1]['pages'][0]['list']
        # 両方入っている
        texts = [c['parameters'][0] for c in page_cmds if c['code'] == 401]
        self.assertIn('1行目', texts)
        self.assertIn('2行目', texts)

    def test_replace_mode(self):
        map_data = self._make_map()
        cmds1 = messages_to_commands(parse_text_string('【A】\n古いセリフ\n'))
        cmds2 = messages_to_commands(parse_text_string('【B】\n新しいセリフ\n'))
        inject_commands(map_data, 1, 0, cmds1, 'append')
        inject_commands(map_data, 1, 0, cmds2, 'replace')
        page_cmds = map_data['events'][1]['pages'][0]['list']
        texts = [c['parameters'][0] for c in page_cmds if c['code'] == 401]
        self.assertNotIn('古いセリフ', texts)
        self.assertIn('新しいセリフ', texts)

    def test_ends_with_code_0(self):
        map_data = self._make_map()
        cmds = messages_to_commands(parse_text_string('【A】\nテスト\n'))
        inject_commands(map_data, 1, 0, cmds)
        page_cmds = map_data['events'][1]['pages'][0]['list']
        self.assertEqual(page_cmds[-1]['code'], 0)


class TestCommonEvents(unittest.TestCase):
    def test_inject(self):
        common = [None, {'id': 1, 'name': 'CE001',
                         'list': [{'code': 0, 'indent': 0, 'parameters': []}]}]
        cmds = messages_to_commands(parse_text_string('【A】\nテスト\n'))
        success, _ = inject_commands_common(common, 1, cmds)
        self.assertTrue(success)
        self.assertTrue(any(c['code'] == 101 for c in common[1]['list']))

    def test_nonexistent_id(self):
        common = [None, {'id': 1, 'name': 'CE001',
                         'list': [{'code': 0, 'indent': 0, 'parameters': []}]}]
        cmds = messages_to_commands(parse_text_string('【A】\nテスト\n'))
        success, _ = inject_commands_common(common, 99, cmds)
        self.assertFalse(success)

    def test_is_common_events_file(self):
        self.assertTrue(is_common_events_file('CommonEvents.json'))
        self.assertTrue(is_common_events_file('/path/to/CommonEvents.json'))
        self.assertFalse(is_common_events_file('Map001.json'))


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.test_file = '_test_backup_target.json'
        with open(self.test_file, 'w') as f:
            f.write('{}')

    def tearDown(self):
        for f in glob.glob(f'{self.test_file}*'):
            os.remove(f)

    def test_creates_timestamped_backup(self):
        bak = backup_file(self.test_file)
        self.assertTrue(os.path.exists(bak))
        self.assertRegex(bak, r'\.\d{8}_\d{6}\.bak$')

    def test_multiple_backups(self):
        bak1 = backup_file(self.test_file)
        # 少し待ってもう一つ（同じ秒だと同名になる可能性あるが気にしない）
        bak2 = backup_file(self.test_file)
        self.assertTrue(os.path.exists(bak1))
        self.assertTrue(os.path.exists(bak2))


if __name__ == '__main__':
    unittest.main()
