# Contributing

バグ報告・機能提案・プルリクエストを歓迎します。

## バグ報告・機能提案

[Issues](https://github.com/tonbiattack/link-watcher/issues) で受け付けています。<br>
バグ報告には以下を含めてください。

- 実行環境（OS、Python のバージョン）
- 実行したコマンドと環境変数（トークンは伏せてください）
- 期待した動作と実際の動作
- エラーメッセージ（`-v` または `-vv` 付きのログがあると助かります）

## プルリクエスト

1. リポジトリを fork してブランチを切る
2. 変更を実装する
3. `pytest` と `ruff check .`、`ruff format --check .` を通す
4. 変更内容と理由を書いて PR を作成

### 開発環境

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 守ってほしいこと

- **テストを追加する** — 挙動を変える変更にはテストを添えてください
- **通知の失敗を握りつぶさない** — 例外は `NotifyError` として送出し、CI を失敗させます
- **状態保存は通知の後** — 送信に失敗したときにリンクを取りこぼさないための不変条件です
- **依存は増やさない** — 標準ライブラリで足りる場合はそちらを優先してください
- **docstring と型ヒントを書く** — 公開関数には Google スタイルの docstring を付けます

### コミットメッセージ

[Conventional Commits](https://www.conventionalcommits.org/ja/) に近い形式を使っています。

```text
feat: グループIDへの送信に対応
fix: 空ページで誤って全リンク削除と判定される問題を修正
docs: README のセットアップ手順を更新
test: send_lines の分割境界のテストを追加
```

## リリース

`pyproject.toml` の `version` を更新し、タグを打ちます。

```bash
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0
```
