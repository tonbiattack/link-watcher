# link-watcher

[![CI](https://github.com/tonbiattack/link-watcher/actions/workflows/ci.yml/badge.svg)](https://github.com/tonbiattack/link-watcher/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Web ページのリンクを定期的に取得し、**新しく増えたリンクだけ**を LINE に通知する小さなツールです。<br>
GitHub Actions での定期実行を想定していますが、CLI としても使えます。

> 以前のバージョンは LINE Notify を使っていましたが、同サービスは 2025 年 3 月 31 日に終了しました。<br>
> このバージョンは **LINE Messaging API** に移行済みです。

## 特徴

- **差分だけ通知** — 前回のスナップショットを JSON に保存し、増えたリンクのみ送信
- **通知成功後に保存** — 送信に失敗したら状態を更新しないので、次回リトライで取りこぼさない
- **通知失敗は失敗として扱う** — エラーを握りつぶさず CI が赤くなる
- **設定は環境変数 or CLI** — GitHub Actions でもローカルでも同じコード
- **テスト済み** — 40 件のユニットテストと ruff による lint / format チェック
- **依存は 2 つだけ** — BeautifulSoup と requests

## クイックスタート

```bash
pip install git+https://github.com/tonbiattack/link-watcher.git
```

```bash
export LINE_CHANNEL_ACCESS_TOKEN="your-channel-access-token"
export LINE_TO="Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # 省略すると友だち全員に broadcast

link-watcher https://example.com/news --selector "h2 a" -v
```

初回はリンクを記録するだけで通知しません。2 回目以降に新しいリンクが現れると通知されます。

## セットアップ

### 1. LINE 側の準備

1. [LINE Developers](https://developers.line.biz/ja/) でプロバイダーと **Messaging API** チャンネルを作成
2. チャンネルの「Messaging API 設定」から **チャンネルアクセストークン（長期）** を発行
3. 送信先を決める
   - **1:1 で受け取りたい**: 自分のユーザーID（`U` で始まる）。公式アカウントを友だち追加したうえで取得
   - **グループに送りたい**: グループID（`C` で始まる）。Bot をグループに招待し、Webhook の `groupId` から取得
   - **とりあえず動かしたい**: `LINE_TO` を未設定にすると broadcast（友だち全員宛て）

### 2. 監視対象のリンクを決める

`--selector` に CSS セレクタを指定します。既定値は `a[href]`（ページ内の全リンク）です。<br>
記事一覧だけを対象にしたい場合は、その一覧の見出しリンクに絞るとノイズが減ります。

```bash
link-watcher https://example.com/blog --selector "article h2 a" --dry-run -v
```

`--dry-run` は「何を通知するか」をログに出すだけで、送信も保存もしません。<br>
セレクタの調整はこれで行うのがおすすめです。

## 設定一覧

環境変数と CLI 引数の両方を受け付けます。CLI 引数が優先されます。

| 環境変数 | CLI | 既定値 | 説明 |
| --- | --- | --- | --- |
| `WATCH_URL` | 位置引数 `URL` | — | 監視するページ（必須） |
| `WATCH_SELECTOR` | `--selector` | `a[href]` | 追跡するリンクの CSS セレクタ |
| `WATCH_STATE_PATH` | `--state` | `.linkwatch/state.json` | 前回スナップショットの保存先 |
| `WATCH_TIMEOUT` | `--timeout` | `30` | HTTP タイムアウト（秒） |
| `WATCH_IGNORE` | `--ignore` | （なし） | 除外する URL の正規表現（改行区切り／複数指定可） |
| `WATCH_DRY_RUN` | `--dry-run` | 無効 | 送信も保存もせず結果だけ表示 |
| `WATCH_NO_SEED` | `--no-seed` | 無効 | 初回でも既存リンクを通知する |
| `LINE_CHANNEL_ACCESS_TOKEN` | — | — | Messaging API のチャンネルアクセストークン |
| `LINE_TO` | — | broadcast | 送信先のユーザーID／グループID／ルームID |

## GitHub Actions で使う

リポジトリに `.github/workflows/watch.yml` が含まれています。

1. **Settings → Secrets and variables → Actions** を開く
2. Secrets に登録
   - `LINE_CHANNEL_ACCESS_TOKEN`（必須）
   - `LINE_TO`（任意）
3. Variables に登録（Secrets ではなく Variables で問題ありません）
   - `WATCH_URL`（必須）
   - `WATCH_SELECTOR`（任意）
   - `WATCH_IGNORE`（任意、改行区切り）
4. `Watch` ワークフローを手動実行（`workflow_dispatch`）して動作確認

以降は 30 分ごとに実行され、前回のスナップショットは **Actions のキャッシュ**（`.linkwatch`）に保存されます。<br>
リポジトリに状態をコミットしないので、履歴が `chore: update watch state` で埋まりません。手動実行時は `dry_run` / `no_seed` を切り替えられます。

`WATCH_URL` が未設定のあいだは、スケジュール実行はエラーではなく「設定待ちでスキップ」します（実行ログに notice が出ます）。

> キャッシュは 7 日間アクセスがないと削除されます。その場合の次回実行は初回扱い（シード）になり、通知は飛びません。<br>
> 状態を Git で管理したい場合は、`WATCH_STATE_PATH` をリポジトリ内のパス（例: `state/links.json`）にして、ワークフローに状態のコミット手順を追加してください。

## CLI リファレンス

```text
link-watcher [-h] [--selector SELECTOR] [--state STATE] [--timeout TIMEOUT]
             [--ignore REGEX] [--dry-run] [--no-seed] [-v] [--version] [url]

  url                 監視するページ（省略時は $WATCH_URL）
  --selector          追跡するリンクの CSS セレクタ
  --state             状態ファイルのパス
  --timeout           HTTP タイムアウト（秒）
  --ignore REGEX      除外する URL の正規表現（繰り返し指定可）
  --dry-run           送信も保存もせず結果だけ表示
  --no-seed           初回でも既存リンクを通知
  -v, --verbose       -v で INFO、-vv で DEBUG
```

終了コードは `0`（成功、変化なしを含む）と `1`（取得・保存・通知の失敗）です。

## 動作の仕組み

```text
fetch_html()  →  extract_links()  →  filter_links()  →  diff()
                                                          │
                                    ┌─────────────────────┴─────────────────────┐
                             変化あり → LINE に送信 → 状態を保存          変化なし → 何もしない
```

- リンクは絶対 URL に正規化し、`#fragment` を除去して重複を排除します
- `javascript:` / `mailto:` / `tel:` / `data:` などの遷移しないスキームは除外します
- リンクが 1 件も取れなかった場合は「セレクタが壊れた」とみなして失敗させます（空ページでの誤検知防止）
- 状態ファイルは一時ファイル経由で書き込むため、途中で落ちても壊れません

## 開発

```bash
git clone https://github.com/tonbiattack/link-watcher.git
cd link-watcher
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest
ruff check .
ruff format --check .
```

コントリビュート方法は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## 注意事項

- 対象サイトの利用規約と `robots.txt` を確認し、常識的な間隔でアクセスしてください
- チャンネルアクセストークンは Secrets で管理し、リポジトリにコミットしないでください
- GitHub Actions のスケジュール実行は、混雑時に数分〜数十分遅延することがあります

## ライセンス

[MIT](LICENSE)
