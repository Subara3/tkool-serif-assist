"""
RPGツクールMZ セリフ入力アシスト GUI版
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json
import os
import re
import sys
import io

# stdout文字化け対策
if sys.stdout and sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from serif_json import (
    parse_text_file, parse_text_string, parse_mode_from_text,
    messages_to_commands, inject_commands, inject_commands_common,
    parse_header, backup_file, read_text_file, is_common_events_file,
    MAX_LINES_PER_MESSAGE,
)


class SerifChecker:
    """テキストの検証"""

    def __init__(self, text, face_files=None):
        self.text = text
        self.face_files = face_files or []
        self.errors = []
        self.warnings = []

    def check(self):
        self.errors = []
        self.warnings = []
        lines = self.text.split('\n')

        current_header = None
        current_lines = []
        msg_count = 0
        line_num = 0

        for i, line in enumerate(lines, 1):
            line = line.rstrip('\r')

            if line.startswith('#'):
                continue

            if re.match(r'\{(bg|pos|mode)=\w+\}', line):
                continue

            header = parse_header(line)
            if header is not None:
                if current_lines:
                    msg_count += 1
                    self._check_lines(current_lines, line_num, msg_count)
                current_header = header
                current_lines = []
                self._check_header(header, i)
                continue

            if line.strip() == '':
                if current_lines:
                    msg_count += 1
                    self._check_lines(current_lines, line_num, msg_count)
                    current_lines = []
                continue

            if not current_lines:
                line_num = i
            current_lines.append((i, line))

        if current_lines:
            msg_count += 1
            self._check_lines(current_lines, line_num, msg_count)

        if msg_count == 0:
            self.errors.append((0, "メッセージが1つもありません"))

        return len(self.errors) == 0

    def _check_header(self, header, line_num):
        if header['face_file'] and self.face_files:
            if header['face_file'] not in self.face_files:
                self.warnings.append(
                    (line_num, f"顔ファイル '{header['face_file']}' がプロジェクトに見つかりません")
                )
        if header['face_index'] < 0 or header['face_index'] > 7:
            self.errors.append(
                (line_num, f"顔番号 {header['face_index']} は範囲外です（0〜7）")
            )

    def _check_lines(self, lines, start_line, msg_num):
        if len(lines) > MAX_LINES_PER_MESSAGE:
            self.warnings.append(
                (start_line, f"メッセージ{msg_num}: {len(lines)}行あります（4行ごとに自動分割されます）")
            )
        for line_num, text in lines:
            if len(text) > 50:
                self.warnings.append(
                    (line_num, f"1行が{len(text)}文字あります（ウィンドウからはみ出す可能性）")
                )


class SerifApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RPGツクールMZ セリフ入力アシスト")
        self.root.geometry("1000x850")
        self.root.configure(bg='#f0f0f0')

        self.map_file = tk.StringVar()
        self.event_id = tk.IntVar(value=1)
        self.page_num = tk.IntVar(value=0)
        self.write_mode = tk.StringVar(value='append')
        self.face_files = []

        self._build_ui()

    def _build_ui(self):
        # --- 上部: ファイル選択 ---
        top = ttk.LabelFrame(self.root, text="設定", padding=10)
        top.pack(fill=tk.X, padx=10, pady=(10, 5))

        # マップファイル
        row1 = ttk.Frame(top)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="対象ファイル:").pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.map_file, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(row1, text="Map...", command=self._browse_map).pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="Common...", command=self._browse_common).pack(side=tk.LEFT, padx=2)

        # イベントID・ページ・モード
        row2 = ttk.Frame(top)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="イベントID:").pack(side=tk.LEFT)
        ttk.Spinbox(row2, from_=1, to=999, textvariable=self.event_id, width=5).pack(side=tk.LEFT, padx=5)
        ttk.Label(row2, text="ページ:").pack(side=tk.LEFT, padx=(15, 0))
        ttk.Spinbox(row2, from_=0, to=99, textvariable=self.page_num, width=5).pack(side=tk.LEFT, padx=5)
        ttk.Label(row2, text="モード:").pack(side=tk.LEFT, padx=(15, 0))
        ttk.Radiobutton(row2, text="追加", variable=self.write_mode, value='append').pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(row2, text="置換", variable=self.write_mode, value='replace').pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="テキストファイルを読込", command=self._load_text).pack(side=tk.RIGHT)

        # --- 中央: エディタ + プレビュー ---
        mid = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左: テキストエディタ
        left_frame = ttk.LabelFrame(mid, text="セリフテキスト", padding=5)
        mid.add(left_frame, weight=1)

        self.editor = scrolledtext.ScrolledText(
            left_frame, wrap=tk.WORD, font=("Yu Gothic UI", 11),
            undo=True, bg='#1e1e1e', fg='#d4d4d4',
            insertbackground='white', selectbackground='#264f78',
            padx=8, pady=8
        )
        self.editor.pack(fill=tk.BOTH, expand=True)
        self.editor.bind('<<Modified>>', self._on_text_change)

        # シンタックスハイライト用タグ
        self.editor.tag_configure('header', foreground='#569cd6', font=("Yu Gothic UI", 11, "bold"))
        self.editor.tag_configure('comment', foreground='#6a9955')
        self.editor.tag_configure('setting', foreground='#ce9178')
        self.editor.tag_configure('narrator', foreground='#c586c0')
        self.editor.tag_configure('error_line', background='#5c1a1a')

        # 右: プレビュー + チェック結果
        right_frame = ttk.Frame(mid)
        mid.add(right_frame, weight=1)

        # プレビュー
        preview_frame = ttk.LabelFrame(right_frame, text="プレビュー", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        self.preview = scrolledtext.ScrolledText(
            preview_frame, wrap=tk.WORD, font=("Yu Gothic UI", 10),
            state=tk.DISABLED, bg='#252526', fg='#cccccc',
            padx=8, pady=8
        )
        self.preview.pack(fill=tk.BOTH, expand=True)

        self.preview.tag_configure('cmd_header', foreground='#569cd6')
        self.preview.tag_configure('cmd_text', foreground='#d4d4d4')
        self.preview.tag_configure('cmd_narrator', foreground='#c586c0')
        self.preview.tag_configure('info', foreground='#808080')

        # チェック結果
        check_frame = ttk.LabelFrame(right_frame, text="チェック結果", padding=5)
        check_frame.pack(fill=tk.X, pady=(5, 0))

        self.check_text = scrolledtext.ScrolledText(
            check_frame, wrap=tk.WORD, font=("Yu Gothic UI", 9),
            height=5, state=tk.DISABLED, bg='#1e1e1e', fg='#cccccc',
            padx=8, pady=4
        )
        self.check_text.pack(fill=tk.X)
        self.check_text.tag_configure('error', foreground='#f44747')
        self.check_text.tag_configure('warning', foreground='#cca700')
        self.check_text.tag_configure('ok', foreground='#4ec9b0')

        # --- 下部: 実行ボタン ---
        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill=tk.X)

        self.status_label = ttk.Label(bottom, text="テキストを入力するか、ファイルを読み込んでください")
        self.status_label.pack(side=tk.LEFT)

        ttk.Button(bottom, text="書き込み実行", command=self._execute).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom, text="チェック", command=self._check).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom, text="テキスト保存", command=self._save_text).pack(side=tk.RIGHT, padx=5)

        # サンプルテキストを初期表示
        self._insert_sample()

    def _insert_sample(self):
        sample = """# セリフを入力してください
# 書き方の例:

【リード/Actor1:0】
こんにちは！
今日はいい天気ですね。

【エリナ/Actor1:1】
そうですね！
お出かけ日和です。

# ナレーション（顔なし・名前なし）
{bg=1}
【】
二人は冒険に出かけた。

# 通常に戻す
{bg=0}
【リード/Actor1:0】
さあ、行こう！
"""
        self.editor.insert('1.0', sample)
        self._update_highlight()
        self._update_preview()

    def _browse_map(self):
        f = filedialog.askopenfilename(
            title="マップファイルを選択",
            filetypes=[("MZ Map JSON", "Map*.json"), ("All JSON", "*.json"), ("All", "*.*")]
        )
        if f:
            self.map_file.set(f)
            self._load_faces(f)
            self._load_file_info()

    def _browse_common(self):
        f = filedialog.askopenfilename(
            title="コモンイベントファイルを選択",
            filetypes=[("CommonEvents", "CommonEvents.json"), ("All JSON", "*.json")]
        )
        if f:
            self.map_file.set(f)
            self._load_faces(f)
            self._load_file_info()

    def _load_faces(self, json_path):
        """facesフォルダからファイル一覧取得"""
        data_dir = os.path.dirname(json_path)
        faces_dir = os.path.join(os.path.dirname(data_dir), 'img', 'faces')
        if os.path.isdir(faces_dir):
            self.face_files = [
                os.path.splitext(fn)[0]
                for fn in os.listdir(faces_dir)
                if fn.endswith('.png')
            ]

    def _load_file_info(self):
        try:
            filepath = self.map_file.get()
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if is_common_events_file(filepath):
                events = [e for e in data if e and e.get('id')]
                info_parts = []
                for ev in events[:10]:
                    cmd_count = len([c for c in ev.get('list', []) if c['code'] != 0])
                    if cmd_count > 0:
                        info_parts.append(f"CE{ev['id']:03d}({cmd_count})")
                self.status_label.config(text=f"コモンイベント: {len(events)}個 {', '.join(info_parts)}")
            else:
                events = [e for e in data.get('events', []) if e]
                info_parts = []
                for ev in events:
                    cmd_count = len([c for c in ev['pages'][0]['list'] if c['code'] != 0])
                    info_parts.append(f"EV{ev['id']:03d}({cmd_count})")
                self.status_label.config(text=f"マップ: {', '.join(info_parts) or 'イベントなし（新規作成されます）'}")
        except Exception as e:
            self.status_label.config(text=f"読込エラー: {e}")

    def _load_text(self):
        f = filedialog.askopenfilename(
            title="テキストファイルを選択",
            filetypes=[("Text", "*.txt"), ("All", "*.*")]
        )
        if f:
            try:
                content = read_text_file(f)
            except ValueError as e:
                messagebox.showerror("エラー", str(e))
                return

            self.editor.delete('1.0', tk.END)
            self.editor.insert('1.0', content)

            # テキスト内の{mode=...}をUIに反映
            mode = parse_mode_from_text(content)
            self.write_mode.set(mode)

            self._update_highlight()
            self._update_preview()

    def _save_text(self):
        f = filedialog.asksaveasfilename(
            title="テキストファイルを保存",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")]
        )
        if f:
            with open(f, 'w', encoding='utf-8') as fh:
                fh.write(self.editor.get('1.0', tk.END))

    def _on_text_change(self, event=None):
        if self.editor.edit_modified():
            self.editor.edit_modified(False)
            self.root.after(300, self._update_highlight)
            self.root.after(300, self._update_preview)

    def _update_highlight(self):
        for tag in ['header', 'comment', 'setting', 'narrator', 'error_line']:
            self.editor.tag_remove(tag, '1.0', tk.END)

        text = self.editor.get('1.0', tk.END)
        for i, line in enumerate(text.split('\n'), 1):
            start = f"{i}.0"
            end = f"{i}.end"

            if line.startswith('#'):
                self.editor.tag_add('comment', start, end)
            elif re.match(r'【.*?】', line):
                self.editor.tag_add('header', start, end)
                if line.strip() == '【】':
                    self.editor.tag_add('narrator', start, end)
            elif re.match(r'\{(bg|pos|mode)=\w+\}', line):
                self.editor.tag_add('setting', start, end)

    def _update_preview(self):
        self.preview.config(state=tk.NORMAL)
        self.preview.delete('1.0', tk.END)

        text = self.editor.get('1.0', tk.END)
        try:
            messages = parse_text_string(text)
        except Exception as e:
            self.preview.insert(tk.END, f"パースエラー: {e}\n", 'error')
            self.preview.config(state=tk.DISABLED)
            return

        bg_names = ['ウィンドウ', '暗くする', '透明']
        pos_names = ['上', '中', '下']

        self.preview.insert(tk.END, f"メッセージ数: {len(messages)}\n\n", 'info')

        for i, msg in enumerate(messages):
            face = f"{msg['face_file']}({msg['face_index']})" if msg['face_file'] else "なし"
            name = msg['name'] or "(ナレーション)"
            bg = bg_names[msg['bg_type']]
            pos = pos_names[msg['pos_type']]

            tag = 'cmd_narrator' if not msg['name'] and not msg['face_file'] else 'cmd_header'
            self.preview.insert(tk.END, f"◆文章：{name}, 顔={face}, {bg}, {pos}\n", tag)

            for line in msg['lines']:
                self.preview.insert(tk.END, f"  ：{line}\n", 'cmd_text')
            self.preview.insert(tk.END, "\n")

        self.preview.config(state=tk.DISABLED)

    def _check(self):
        text = self.editor.get('1.0', tk.END)
        checker = SerifChecker(text, self.face_files)
        is_ok = checker.check()

        self.editor.tag_remove('error_line', '1.0', tk.END)

        self.check_text.config(state=tk.NORMAL)
        self.check_text.delete('1.0', tk.END)

        if is_ok and not checker.warnings:
            self.check_text.insert(tk.END, "OK: 問題ありません\n", 'ok')
            messages = parse_text_string(text)
            commands = messages_to_commands(messages)
            self.check_text.insert(tk.END,
                f"メッセージ: {len(messages)}個  コマンド: {len(commands)}個\n", 'ok')
        else:
            for line_num, msg in checker.errors:
                self.check_text.insert(tk.END, f"エラー 行{line_num}: {msg}\n", 'error')
                if line_num > 0:
                    self.editor.tag_add('error_line', f"{line_num}.0", f"{line_num}.end")

            for line_num, msg in checker.warnings:
                self.check_text.insert(tk.END, f"警告 行{line_num}: {msg}\n", 'warning')

        self.check_text.config(state=tk.DISABLED)

    def _execute(self):
        filepath = self.map_file.get()
        if not filepath or not os.path.exists(filepath):
            messagebox.showerror("エラー", "対象ファイルを選択してください")
            return

        text = self.editor.get('1.0', tk.END)
        checker = SerifChecker(text, self.face_files)
        if not checker.check():
            errs = '\n'.join(f"行{ln}: {msg}" for ln, msg in checker.errors)
            messagebox.showerror("エラー", f"テキストにエラーがあります:\n{errs}")
            return

        messages = parse_text_string(text)
        if not messages:
            messagebox.showwarning("警告", "メッセージがありません")
            return

        commands = messages_to_commands(messages)
        mode = self.write_mode.get()
        is_common = is_common_events_file(filepath)

        mode_text = '置換（既存コマンドを全て入れ替え）' if mode == 'replace' else '追加（既存の末尾に追加）'
        target = 'コモンイベント' if is_common else 'マップイベント'

        if not messagebox.askyesno("確認",
                f"対象: {os.path.basename(filepath)}\n"
                f"種類: {target}\n"
                f"イベントID: {self.event_id.get()}\n"
                + (f"ページ: {self.page_num.get()}\n" if not is_common else "")
                + f"モード: {mode_text}\n"
                f"メッセージ数: {len(messages)}\n"
                f"コマンド数: {len(commands)}\n\n"
                f"書き込みますか？"):
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            bak_path = backup_file(filepath)

            if is_common:
                success, _ = inject_commands_common(data, self.event_id.get(), commands, mode)
                created = False
            else:
                success, created = inject_commands(data, self.event_id.get(), self.page_num.get(), commands, mode)

            if success:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)

                extra = ""
                if created:
                    ev = data['events'][self.event_id.get()]
                    extra = f"\nイベントID {self.event_id.get()} を新規作成しました（位置: {ev['x']},{ev['y']}）\n"

                messagebox.showinfo("完了",
                    f"書き込み完了！\n"
                    f"{len(messages)}個のメッセージを{'置換' if mode == 'replace' else '追加'}しました。\n"
                    f"{extra}"
                    f"バックアップ: {os.path.basename(bak_path)}\n\n"
                    f"ツクールMZでプロジェクトを開き直すと反映されます。")
                self.status_label.config(text=f"書き込み完了: {len(messages)}メッセージ")
                self._load_file_info()
            else:
                messagebox.showerror("エラー", "書き込みに失敗しました。イベントIDを確認してください。")

        except Exception as e:
            messagebox.showerror("エラー", f"書き込みエラー: {e}")


def main():
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use('clam')
    app = SerifApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
