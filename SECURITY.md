# Security Policy

## サポート対象

最新のリリースのみを対象に修正します。

| Version | Supported |
| --- | --- |
| 1.x | ✅ |

## 脆弱性の報告

**公開の Issue には書かないでください。**<br>
GitHub の [Private vulnerability reporting](https://github.com/tonbiattack/link-watcher/security/advisories/new) から報告してください。

以下を含めていただけると助かります。

- 影響範囲（どの機能で、何ができてしまうか）
- 再現手順
- 想定される修正方針（あれば）

## 取り扱いに注意すべき情報

このツールは LINE の **チャンネルアクセストークン** を扱います。

- トークンは環境変数または GitHub Secrets で管理し、コードや状態ファイルに保存しないでください
- ログにトークンやメッセージ本文を出さない設計にしていますが、独自改修時は注意してください
- トークンが漏洩した可能性がある場合は、LINE Developers コンソールで **Reissue** して再発行してください
