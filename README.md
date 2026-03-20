# RPGツクールMZ セリフ一括入力ツール

テキストファイルに書いたセリフを、RPGツクールMZの「文章の表示」イベントコマンドとして MapXXX.json / CommonEvents.json に一括で書き込むツールです。

ツクールMZを開かずに、何百行でも一発で流し込めます。

![GUI](doc/ss_05_gui.png)

## ダウンロード

**[最新版をダウンロード（v1.0.0）](https://github.com/Subara3/tkool-serif-assist/releases/download/v1.0.0/tkool-serif-assist-v1.0.0.zip)**

ZIPを展開して `serif_gui.exe` をダブルクリックするだけです。Python不要。

## 特徴

- **GUIエディタ** — シンタックスハイライト付きのダークテーマエディタ
- **リアルタイムプレビュー** — テキストを書くと右側に変換結果を即表示
- **チェッカー** — 顔番号の範囲外、存在しない顔ファイルなどを警告
- **イベント自動作成** — 存在しないイベントIDを指定すると空きタイルに自動配置
- **追加/置換モード** — 既存コマンドの末尾に追加 or 全て置換
- **コモンイベント対応** — CommonEvents.json にも書き込み可能
- **バックアップ世代管理** — タイムスタンプ付きで10世代保持
- **エンコーディング自動判定** — UTF-8 / BOM / Shift-JIS / CP932

## テキストフォーマット

```
# コメント

【リード/Actor1:0】
こんにちは！
今日はいい天気ですね。

【エリナ/Actor1:1】
そうですね！
お出かけ日和です。

# ナレーション
{bg=1}
【】
二人は冒険に出かけた。
```

| 書き方 | 意味 |
|--------|------|
| `【名前/顔ファイル:番号】` | 話者 + 顔グラ指定 |
| `【名前】` | 顔グラなし |
| `【】` | ナレーション（名前・顔リセット） |
| `{bg=0/1/2}` | 背景: ウィンドウ / 暗くする / 透明 |
| `{pos=0/1/2}` | 位置: 上 / 中 / 下 |
| `{mode=replace}` | 既存コマンドを置換（デフォルトは追加） |
| `#` | コメント |
| 空行 | メッセージの区切り |

4行を超えると自動分割。MZ制御文字（`\C[n]`, `\V[n]`, `\N[n]` 等）もそのまま使えます。

## ゲーム内での表示

| 顔グラ+名前 | ナレーション（暗くする） |
|---|---|
| ![セリフ](doc/ss_04_serif2.png) | ![ナレーション](doc/ss_04_serif4.png) |

## 使い方

1. `serif_gui.exe` をダブルクリック
2. 左のエディタにセリフを入力（またはテキストファイルを読込）
3. ツクールMZを閉じる
4. 「参照...」からプロジェクトの `data/MapXXX.json` を選択、イベントIDを指定
5. 「書き込み実行」
6. ツクールMZでプロジェクトを開くと反映

## 技術情報

MZの「文章の表示」のJSON構造：

```json
{"code": 101, "indent": 0, "parameters": ["Actor1", 0, 0, 2, "リード"]}
{"code": 401, "indent": 0, "parameters": ["こんにちは！"]}
{"code": 401, "indent": 0, "parameters": ["今日はいい天気ですね。"]}
```

`parameters`: `[顔ファイル名, 顔番号(0-7), 背景(0-2), 位置(0-2), 名前]`

公式リファレンス: [プラグイン講座](https://rpgmakerofficial.com/product/mz/plugin/) / [イベントコマンド一覧（PDF）](https://rpgmakerofficial.com/product/mz/plugin/javascript/script_reference/eventcode.pdf)

## 開発

```bash
# テスト
python -m pytest test_serif_json.py -v

# exe ビルド
pyinstaller --onefile --name serif_gui --windowed --hidden-import serif_json serif_gui.py
```

## ライセンス

MIT
