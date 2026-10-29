# tsubame-lumerical-setup

研究室の Lumerical ライセンスで、TSUBAME 4.0 の計算ノードから Lumerical を使えるようにする準備一式。tsubame-claude-setup の続き。Claude Code でも Codex(ChatGPT)でも進められる。

- セットアップを頼まれたら: `SETUP.md` の手順に、上から順に従う。Codex で進めるときは、その中の「Codex(ChatGPT)で進めるとき」の読み替えに従う。
- この台本やスキルの雛形を直すときは: `README.md` の「開発する人向け」。`skill/` の `{{…}}` は `setup/lumsetup.py skill` が埋める値なので、増やすときは `cmd_skill` の `values` にも足す。
