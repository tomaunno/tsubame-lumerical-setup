# TSUBAME で Lumerical を使えるようにする

研究室で持っている **Ansys Lumerical** のライセンスで、東京科学大のスパコン **TSUBAME 4.0** の上で Lumerical(FDTD・varFDTD・MODE・RCWA・lumapi)を動かすための準備一式です。あなたのパソコンの **Claude Code**(か ChatGPT の **Codex**)が、あなたの TSUBAME のアカウントで Lumerical を使えるようにし、試しに解くところまで進めます。研究室の TSUBAME グループに、誰かがこの一式で入れた Lumerical がもうあれば、それを共有して使います(グループに 1 つあれば全員で使えます)。

準備が済めば、Claude に「この .fsp を TSUBAME の GPU で解いて」と頼むだけで、計算を送る・終わるのを待つ・結果を取ってくる、までを Claude がやります。大きな 3D の FDTD は、TSUBAME の GPU(H100)1 枚で、研究室の Windows 機の 8 コアより数十倍速く解けることがあります(下の「速さの例」)。

プログラムの知識は要りません。コマンドは全部 Claude が打ちます。

## 用意するもの

- **TSUBAME のアカウント**(`ux12345` のようなログイン名)と、**研究室の TSUBAME グループへの参加**。
- **Claude Code** か、ChatGPT の **Codex**(下の「ChatGPT(Codex)を使っている人へ」)。

このパソコンから TSUBAME に入る準備([tsubame-claude-setup](https://github.com/tomaunno/tsubame-claude-setup))がまだなら、同じお願いの中で先にそれも済ませます(途中で 1 回、TSUBAME のポータルに大学の ID でログインしてもらいます)。

研究室の TSUBAME グループに、もう Lumerical が入っていれば(研究室で誰かが一度この一式を使っていれば)、用意するものはこれだけです。自動で見つけて、それを使います。

グループにまだ無いとき(研究室で最初の 1 人のとき)だけ、次の 2 つも要ります。

- **研究室の Lumerical のライセンスサーバの場所**(`1055@サーバの名前` のような 1 行)。研究室の Windows の PC で Lumerical が使えているなら、その PC の `C:\Program Files\ANSYS Inc\Shared Files\Licensing\ansyslmd.ini` か `%APPDATA%\Lumerical\License.ini` に書いてあります。分からなければ研究室のライセンスの担当の人に聞いてください。TSUBAME の計算ノードからそのサーバに届く必要があります(届かないときは、Claude が担当の人への頼み方を教えます)。
- **Lumerical の Linux 版のインストーラ**(`LUMERICAL_2026R1.04_LINX64.tar.gz` のような、1 GB ほどのファイル)。Ansys のダウンロードセンター(https://download.ansys.com/ )から、研究室のライセンスにつながった Ansys のアカウントでダウンロードします。権限が無ければ、ライセンスの担当の人からもらってください。版は、研究室の PC の Lumerical と同じものをおすすめします。最初の 1 人は、研究室の全員が使えるよう、グループの共有の場所(例: `/gs/fs/<グループ>/apps/lumerical`)に入れるのがおすすめです(Claude に「グループの共有の場所に入れて」と頼めば、そこに入れます)。

研究室のライセンスを TSUBAME から使ってよいかは、研究室の決まりに従ってください。TSUBAME で計算している間は、研究室の人が使える本数がその分減ります。

## ChatGPT(Codex)を使っている人へ

Claude Code の代わりに、ChatGPT のアカウントでそのまま使える **Codex**(パソコンで作業する版。アプリとターミナル版があります。入れ方: https://developers.openai.com/codex/quickstart )でも進められます。ブラウザやスマホの ChatGPT(会話だけの画面)では、あなたのパソコンでコマンドを動かせないのでできません。

- 下の「やり方」の Claude Code を Codex に置き換えて、同じ文を送ります。Codex は手順書の中の「Codex で進めるとき」を読んで、Codex が読む置き場所(`~/.agents/skills/tsubame-lumerical/`)にスキルを書きます。
- Codex が「実行してよいか」「ネットワークを使ってよいか」と聞いてきたら、許可してください(TSUBAME への接続とインストーラの送付に要ります)。
- Codex での通しの確認はまだしていません。うまくいかなかったら、どの手順で何が出たかを作った人に知らせてください。

## やり方

1. Claude Code を開きます。
2. 次の文をそのまま貼り付けて送ります。

   > https://github.com/tomaunno/tsubame-lumerical-setup をこのパソコンに持ってきて、中の SETUP.md の手順どおりに、私の TSUBAME のアカウントで TSUBAME と研究室の Lumerical を使えるようにセットアップしてください。

3. あとは AI の質問に答えるだけです。
   - 「実行してよいか」と聞かれたら「はい(Yes)」を押します。
   - TSUBAME の準備がまだなら、ログイン名を聞かれます。このパソコンに、前から TSUBAME で使っている鍵があれば、それをそのまま使います。無ければ新しい鍵を作り、TSUBAME のポータルに 1 回ログインしてもらいます(鍵にパスフレーズを付けると決めた場合は、新しく開く窓で自分で打ちます。AI には見えません)。
   - グループにまだ Lumerical が無いときだけ、インストーラのファイルと、ライセンスサーバの場所を聞かれます。

かかる時間は、グループの Lumerical を使うときは 10〜20 分、新しく入れるときは 30 分〜1 時間です。TSUBAME の準備もするなら、さらに 10〜20 分かかります。どちらも大半は TSUBAME の順番待ちと計算の待ち時間です。TSUBAME のポイントは、全部で 0.05 ポイント未満です(試しに解くジョブ 1〜2 本と、新しく入れるときはそのジョブ 1 本)。

## 終わったら

Claude に頼むだけです。

- 「この model.fsp を TSUBAME の GPU で解いて、結果を取ってきて」
- 「この lumapi のスクリプトで半径を 20 通り振って、TSUBAME で回して」
- 「研究室の Lumerical のライセンスはいま何本空いてる?」

途中で止まっても、もう一度同じ文を送れば続きから進みます。済んでいる所は自動で飛ばします。

## 入るもの

| 入るもの | 場所 | 役割 |
|---|---|---|
| Lumerical(グループにまだ無いときだけ) | TSUBAME のグループの共有の場所 `/gs/fs/<グループ>/apps/lumerical`(おすすめ)か、自分の `<置き場所>/apps/lumerical`。約 4 GB、ファイル約 1.5 万個 | 計算ノードで動く Lumerical 本体と、足りない部品(`libglut`)。毎回のジョブで読む設定ファイル `lumenv.sh`。グループの全員が読めるようにする |
| Claude のスキル | このパソコンの `~/.claude/skills/tsubame-lumerical/`(Codex なら `~/.agents/skills/tsubame-lumerical/`) | TSUBAME での Lumerical の回し方・ライセンスの使い方・つまずく点と、あなたの値。ジョブの雛形 `lum_job.sh` |

`<置き場所>` は、tsubame-claude-setup で決めた TSUBAME の作業用のフォルダです。準備のためだけに使った物(TSUBAME に送ったインストーラ、試験の模型、このセットアップのフォルダ)は、最後に Claude が片付けます。ダウンロードしたインストーラは、あなたのファイルなので残します。

やめるときは、このパソコンの `~/.claude/skills/tsubame-lumerical/` を消せば元どおりです。自分で入れた Lumerical を TSUBAME から消すときは、グループのほかの人が使っていないかを先に確かめてください。

## 速さの例

3D の FDTD(メッシュ 5 nm、必要メモリ 9 GiB、31 000 ステップ)の同じファイルを解いた時間です(2026-10、Lumerical 2026 R1.4)。

| どこで | 時間 | TSUBAME のポイント |
|---|---|---|
| 研究室の Windows 機(80 コアの共有機を 8 プロセスで。混んでいた日) | 4〜6 時間 | — |
| TSUBAME cpu_8(8 プロセス) | 2 時間 40 分 | 約 0.08 |
| TSUBAME cpu_80(80 プロセス) | 27 分 | 約 0.1〜0.2 |
| TSUBAME gpu_1(H100 1 枚) | 3 分 | 約 0.01〜0.05 |

結果は、どれも研究室の機で解いたものと一致しました(透過率の差 10⁻⁷ 以下)。ポイントの幅は、指定した時間の上限(h_rt)の取り方による違いです。どれだけ速くなるかは、模型の大きさと研究室の機の混み具合で変わります。

## わかっていること

- **Lumerical の RCWA は CPU だけ**です(GPU 版はありません)。GPU が効くのは FDTD です。
- GPU 1 枚は、研究室の計算用ライセンスを何本か使います(例: 9 本。契約によります)。大きな GPU ジョブをたくさん並べると、研究室の人の分が足りなくなります。Claude のスキルに、残りの見方を書いてあります。
- Windows で確かめました。Mac は手順の上では同じですが、まだ確かめていません。

---

## 開発する人向け

`SETUP.md` は Claude が読む手順書で、`setup/lumsetup.py` がその各手順の実体です(Python 3.11 以上、標準ライブラリだけ)。TSUBAME の上で動く部分は `setup/remote/`(入れるジョブ `install_job.sh`、試験のジョブ `verify_job.sh`、試験の模型 `make_cell.lsf`、結果を読む `read_t.py`)で、台本が改行を LF にして TSUBAME に送ります。

```
uv run --managed-python --python 3.12 setup/lumsetup.py check
```

自分の環境を壊さずに試すときは、`--claude-dir <仮のフォルダ>` を付けます。そのフォルダの `skills/tsubame/SKILL.md` に、tsubame-claude-setup が書くのと同じ形の表(接続名・ログイン名・グループ・置き場所・ssh / scp)を置いておけば、台本はそこから値を読みます。置き場所を試験用のフォルダにすれば、入れる先もそこになります。

手順 8 の片付けは、このフォルダごと消します。開発用の手元のコピーでは `cleanup` までにとどめ、フォルダを消すコマンドは打たないでください。

ライセンスサーバの名前の扱い: Lumerical はライセンスサーバに、ベンダデーモンの場所を問い合わせます。サーバはそれに、自分で名乗っている名前(研究室の PC の名前など)で答えます。TSUBAME がその名前を引けないとライセンスが借りられないので、`install_job.sh` が計算ノードで名乗りの名前を調べ、引けない 1 語の名前を `HOSTALIASES` で引ける名前に読み替えます。Ansys のライセンスのクライアントがサーバの名前を最初の 1 語に縮める分も、同じように読み替えます。

`skill/` の 2 つのファイルはスキルの雛形で、`{{…}}` は `skill` が埋めます。MIT ライセンス。
