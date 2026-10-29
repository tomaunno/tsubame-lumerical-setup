# TSUBAME で Lumerical を使えるようにする手順(Claude Code・Codex 向け)

この手順は、あなた(Claude Code か Codex)が本人のパソコンで進める。終わったとき本人は、あなたに「この .fsp を TSUBAME の GPU で解いて」と頼むだけで、研究室の Lumerical のライセンスを使って TSUBAME 4.0 で Lumerical を回せるようになっている。準備に使ったファイルは最後に片付け、残さない。

この台本は、tsubame-claude-setup(このパソコンから本人のアカウントで TSUBAME に入れるようにし、`tsubame` スキルと hpcjob を入れる一式)が書いたスキルから、接続名・グループ・置き場所を読む。それがまだなら、手順 2 で同じ会話のまま先に済ませる。本人が送るお願いは 1 通でよい。

## 進め方の決まり

- **本人はプログラムを知らない前提で進める**。コマンドは全部あなたが打つ。本人にしてもらうのは、選択肢を選ぶ、「許可」を押す、インストーラをダウンロードする、ライセンスサーバの場所を調べる、の 4 つだけ。
- 質問は 1 つずつ、選択肢とおすすめを付けて聞く(AskUserQuestion が使えればそれで)。専門用語には言い換えを添える:
  - インストーラ =「Lumerical を入れるための元のファイル」
  - ライセンスサーバ =「研究室の Lumerical の使用権を貸し出しているパソコン」
  - ジョブ =「TSUBAME に頼む計算の 1 件」
  - 計算ノード =「TSUBAME の中で実際に計算するコンピュータ」
- エラーの文字はそのまま見せない。何が起きたかと次に何をするかを、普通の言葉で伝える。
- パスワードは本人だけが打つ。あなたは聞かない、見ない、打たない(この手順にパスワードを打つ場面はない)。
- 手順はどこからやり直しても壊れない。済んでいる所は台本が飛ばす。

最初に本人へこう伝える:

> これから、研究室の Lumerical のライセンスを使って、TSUBAME で Lumerical を回せるように準備します。研究室の TSUBAME グループに、誰かが入れた Lumerical がもうあれば、それを使うので 10〜20 分で終わります(大半は TSUBAME の順番待ちです)。無ければ新しく入れるので 30 分〜1 時間かかり、Lumerical の Linux 版のインストーラと、研究室のライセンスサーバの場所を用意してもらいます。どちらになるかは、このあと調べてお伝えします。
>
> 途中で何度か「実行してよいか」と聞かれるので「はい(Yes)」を押してください。TSUBAME のポイントは、全部で 0.05 ポイント未満です。

## 台本の呼び方

台本は `setup/lumsetup.py`。tsubame-claude-setup で入れた uv が、Python ごと用意して動かす。コマンドはこのフォルダ(手順 1 で置く `~/tsubame-lumerical-setup`)で打つ。この文書の `<LS>` は次の意味:

- Git Bash / Mac のターミナル: `~/.local/bin/uv run --managed-python --python 3.12 setup/lumsetup.py`
- PowerShell: `& "$HOME\.local\bin\uv.exe" run --managed-python --python 3.12 setup\lumsetup.py`

(`uv` が PATH にあれば `uv run --managed-python --python 3.12 setup/lumsetup.py` でもよい。uv が無ければ、tsubame-claude-setup がまだなので手順 2 の `no_base_setup` と同じに扱う。)

どのサブコマンドも、最後の 1 行に `RESULT {json}` を出す。`status` を見て、下の各手順の分かれ道に進む。この文書に書いていない `status` や `reason` が出たら、`detail` と `hint` を読んで原因を考える。分かった値は `setup/state.json` に残り、次の手順に引き継がれる。

TSUBAME のジョブを待つサブコマンド(`upload --wait`・`install`・`verify`)は、最長 7 分待って返る。どれもタイムアウト 600000 ミリ秒で動かす。

## Codex(ChatGPT)で進めるとき

この手順書は Claude Code を前提に書いてあるが、OpenAI の Codex でも同じように進められる。あなたが Codex なら、次のように読み替える:

- 台本は、tsubame-claude-setup が書いた `tsubame` スキルを、Claude Code の置き場所(`~/.claude/skills/`)と Codex の置き場所(`~/.agents/skills/`)の両方から探す。この手順で書くスキルも、見つけた方の隣に書く。台本に何かを付ける必要はない。
- 文中の「Claude」「Claude Code」は「Codex」と読む。本人への言葉でもそう言う。
- 質問は、選択肢とおすすめを付けた普通の文で 1 つずつ聞く。
- 「タイムアウト 600000 ミリ秒で動かす」は、そのコマンドの制限時間を 10 分にして動かす、という意味。
- Codex は、ネットワークを使うコマンド(ssh・scp・ダウンロード)や、このフォルダの外(`~/.agents`)に書くコマンドの前に、本人に許可を求めることがある。最初に本人へ「Codex が『実行してよいか』『ネットワークを使ってよいか』と聞いてきたら、許可してください」と伝えておく。
- Codex の既定の設定では、コマンドはネットワークを使えない。TSUBAME に触れるコマンド(`<LS>` の `check`・`upload`・`install`・`use`・`verify`・`cleanup`、ssh・scp・git clone)は、最初からネットワークを使える許可を求めて動かす。`ssh_failed` が返り、`detail` に `Permission denied` が無ければ、鍵の問題ではなくネットワークが止められている。鍵を直しに行かず、ネットワークの許可を求めてやり直す。
- `upload --file` は裏でコピーを続けるプロセスを起こして、すぐ返る。Codex の実行の仕組みがコマンドの終わりにそれを止めてしまうとき(`upload --wait` が `upload_failed` を返し、`got_bytes` が途中で止まっている)は、`upload --file <ファイル> --foreground` で送り直す。こちらは送り終わるまで返らないので、制限時間を長め(30 分など)にして動かす。

## 1. この台本を手元に置く

`~/tsubame-lumerical-setup` が無ければ置く。git があれば `git clone https://github.com/tomaunno/tsubame-lumerical-setup ~/tsubame-lumerical-setup`。無ければ zip で置く:

- PowerShell: `Invoke-WebRequest https://github.com/tomaunno/tsubame-lumerical-setup/archive/refs/heads/main.zip -OutFile $HOME\tls.zip; Expand-Archive $HOME\tls.zip $HOME -Force; Rename-Item $HOME\tsubame-lumerical-setup-main tsubame-lumerical-setup; Remove-Item $HOME\tls.zip`
- Mac: `curl -L -o ~/tls.zip https://github.com/tomaunno/tsubame-lumerical-setup/archive/refs/heads/main.zip && unzip -q ~/tls.zip -d ~ && mv ~/tsubame-lumerical-setup-main ~/tsubame-lumerical-setup && rm ~/tls.zip`

完了: `~/tsubame-lumerical-setup/setup/lumsetup.py` がある。

## 2. 今の状態を見る

`<LS> check`。

- `no_base_setup`(uv が無くて `check` を動かせないときも同じ): このパソコンから TSUBAME を使う準備がまだ。**同じ会話のまま、先にそれを済ませてから、ここに戻る**:
  1. 本人にこう伝える:「先に、このパソコンからあなたのアカウントで TSUBAME に入れるようにします(10〜20 分)。終わったら、そのまま Lumerical の準備に進みます。」
  2. tsubame-claude-setup を `~/tsubame-claude-setup` に置き(git があれば `git clone https://github.com/tomaunno/tsubame-claude-setup ~/tsubame-claude-setup`。無ければ、その手順書の手順 1 の zip の方法)、その `SETUP.md` を読んで、手順 1〜11 をそのとおりに進める。あなたが Codex なら、その手順書の「Codex(ChatGPT)で進めるとき」にも従う。ログイン名などは、その手順書が本人に聞く。
  3. その手順 12(終わりを伝える)は、ここでは言わない。この手順書に戻って `<LS> check` をもう一度動かし、続きを進める。TSUBAME の準備ができたことは、この手順書の最後(手順 9)でまとめて伝える。
  - TSUBAME の準備の途中で止まったとき(研究室の TSUBAME グループにまだ入っていない `no_group` など)は、その手順書の指示どおりに本人に伝えて止める。次に同じお願いをされたら、この手順書の最初からやり直せばよい。済んだ所は台本が飛ばす。
- `error` で `reason` が `ssh_failed`: TSUBAME に入れない。`tsubame` スキルの reference.md の「`Permission denied (publickey)` で入れなくなったとき」に従って直してから、もう一度 `check`。
- `ok` のとき、次を見る:
  - **`group_installs` が空でない**: 研究室の TSUBAME グループに、この一式で入れた Lumerical がもうある(`lumenv` がその設定ファイル、`owner` が入れた人のログイン名、`version` が版)。**手順 2b へ**(新しく入れない)。2 つ以上あれば、版の新しい方をおすすめにして本人に選んでもらう。
  - `installed_root` が入っている: 前に一度、自分の置き場所に取り出してある。手順 3 を飛ばし、手順 4 から進める(ライセンスの確かめと設定ファイルの書き直しだけをする。取り出しはしない)。手順 5 では入れる場所を聞かず、`--dest` も付けない(`dest` のまま)。
  - `dest_not_empty_without_install` が true: 入れる予定の場所(`dest`)に、別のファイルがある。本人に別の場所でよいかを聞き、`<置き場所>/apps/lumerical-2` のような空いた名前を決める(手順 5 で `--dest` に渡す)。
  - `group_disk`: グループのディスクの使用量と上限。入れるのに約 4 GB とファイル約 1.5 万個、途中でインストーラの 1.1 GB が要る。`dest` のある方(`/gs/fs` か `/gs/bs`)の空きが 6 GB 未満か、ファイル数(`file(M)`)の残りが 0.05 M 未満なら、本人に伝えて、グループの管理者と相談してもらう。

## 2b. 研究室で共有している Lumerical を使う

Lumerical の本体は、グループに 1 つあれば全員で使える(動かしても中身は書き換わらず、各自の設定と記録はそれぞれのホームに書かれる)。ライセンスも、その Lumerical に設定してある研究室のものを使う。本人にこう伝える:

> 研究室の TSUBAME グループに、<owner> さんが入れた Lumerical <version> がありました。新しく入れずに、これを使います。インストーラもライセンスサーバの場所も要りません。

`<LS> use --lumenv <lumenv>`。

- `ok`: 手順 6(試しに解く)へ。手順 3〜5 は飛ばす。
- 本人がその Lumerical を入れた人(`owner` が本人のログイン名)で、「ライセンスサーバの場所が変わったので設定し直したい」と言っているときは、`use` ではなく手順 4 から進め、手順 5 で `--dest` にその `lumenv` のあるフォルダを渡す。取り出しは飛ばされ、ライセンスの確かめと `lumenv.sh` の書き直しだけをする。確かめに失敗したときは、元の設定がそのまま残る(グループの人は使い続けられる)。
- `error` で `reason` が `not_usable`: その設定ファイルが読めないか、この一式で入れたものではない。別の候補があればそちらで。無ければ、入れた人に、フォルダをグループで読めるようにしてもらう(`chmod -R g+rX <そのフォルダ>`)か、手順 3 から新しく入れる。

## 3. インストーラを TSUBAME に送る

`check` の `uploaded` に `.tar.gz` があれば、前に送ってある。`upload --file` にそのファイルを渡すと、同じ大きさのものは送り直さずに `ok` が返る。

`installers_on_this_pc`(このパソコンのダウンロード・デスクトップにあるそれらしいファイル)を見る:

- 1 つなら、それでよいかを本人に確かめる。2 つ以上なら、名前・大きさ・日付を並べて選んでもらう。
- 無ければ、本人にこう頼む:
  > Lumerical の Linux 版のインストーラをダウンロードしてください。Ansys のダウンロードセンター(https://download.ansys.com/ )に、研究室のライセンスにつながっている Ansys のアカウントでログインし、Lumerical の Linux 用のファイルを選びます。名前は `LUMERICAL_2026R1.04_LINX64.tar.gz` のような、`LINX64` が入っていて `.tar.gz` で終わるもので、1 GB ほどあります。版は、研究室の Windows の PC の Lumerical と同じものをおすすめします(新しい版で保存したファイルは、古い版では開けないことがあるためです)。
  > ダウンロードの権限が無いと言われたら、研究室のライセンスの担当の人に、このファイルをもらってください。ダウンロードできたら教えてください。

  終わったと言われたら、もう一度 `<LS> check` を動かしてファイルを見つける。見つからなければ、置いた場所を本人に聞く。

`<LS> upload --file <ファイルのパス>`。

- `uploading`: 裏でコピーが始まった。本人に「TSUBAME にインストーラを送っています。大学の中なら 1〜2 分、家からだと 10 分以上かかることがあります」と伝えて、`<LS> upload --wait`。
  - `still_uploading`: 進み具合(`percent`)を伝えて、もう一度 `upload --wait`。
  - `ok`: 手順 4 へ。
  - `upload_failed` か `checksum_mismatch`: 途中で切れた。`upload --file` からやり直す(はじめから送り直す)。
- `ok`(`already` が true): もう送ってある。手順 4 へ。
- `not_tar_gz`: 違うファイル(Windows 版など)。正しいファイルを選び直してもらう。

## 4. ライセンスサーバの場所を聞く

形は `ポート番号@サーバ`(例: `1055@licserver.example.com` や `1055@192.0.2.10`)。ポート番号を言われなければ 1055 を使う。

- `check` の `license_hints` に何かあれば、このパソコンの Lumerical が借りている先なので、それを候補として見せ、同じでよいかを聞く(`SERVER=1055@xxx` の `1055@xxx` の部分)。
- 無ければ本人に聞く:
  > 研究室の Lumerical のライセンスサーバの場所を教えてください。`1055@サーバの名前` か `1055@サーバの IP アドレス` の形です。研究室の Windows の PC で Lumerical が使えているなら、その PC の `C:\Program Files\ANSYS Inc\Shared Files\Licensing\ansyslmd.ini` の `SERVER=` の行か、`%APPDATA%\Lumerical\License.ini` の `ansysserver\host=` の行に書いてあります。分からなければ、研究室のライセンスの担当の人に聞いてください。

  名前と IP の両方が分かるなら、名前より IP の方が TSUBAME から確実に届く。

本人に一度だけこう伝える:「研究室のライセンスを TSUBAME から使ってよいかは、研究室の決まりに従ってください。TSUBAME で計算している間は、研究室の人が使える本数がその分減ります。」

## 5. 入れる

先に、入れる場所を決める。`check` の `group_shared_dest` があれば(グループのフォルダに書き込める)、本人に聞く:

> Lumerical をどこに入れますか。
> - 研究室の共有の場所 `<group_shared_dest>`(おすすめ): グループの全員が、入れ直さずに使えます。次に同じ研究室の人がこの準備をすると、自動でこれを使います。
> - 自分の置き場所 `<dest>`: 自分だけが使う場合。

共有の場所なら `--dest <group_shared_dest>` を付ける(親のフォルダ `apps` が無ければ、台本がグループの全員で書き込めるように作る)。`group_shared_dest` が無ければ聞かずに `dest` に入れる。

`<LS> install --server <ライセンスサーバ>`(場所を変えるなら `--dest <場所>` も)。TSUBAME の計算ノード(cpu_8)で 1 本のジョブを動かす。このジョブはインストーラを開いて入れ、計算ノードからライセンスサーバに届くかを確かめ、毎回のジョブで読む設定ファイル `lumenv.sh` を書く。順番待ちを除いて 5〜10 分、約 0.01 ポイント。前に入れてあれば、入れる所は飛ばしてライセンスだけを確かめる(1〜2 分)。

本人に「TSUBAME で Lumerical を入れています。10 分ほど待ちます」と伝える。

- `still_running`: 順番待ちか、入れている途中。もう一度 `<LS> install --watch`。3 回続いたら、混んでいることを伝え、待ち続けてよいか聞く。
- `ok`: 入った。`license_check` で伝え方を変える:
  - `lmstat`: `features` から、計算用(`lum_fdtd_solve`)と画面用(`lum_fdtd_gui`)の本数を本人に伝える。
  - `lmdiag` か `unconfirmed`: TSUBAME からはライセンスの本数を数えられないサーバだった(サーバが自分を TSUBAME で通じない名前で名乗っていて、数える道具がその読み替えを使わないため)。Lumerical 自体は読み替えで借りられるはずで、実際に借りられるかは手順 6 で確かめる、と伝える。
  - `aliases` が空でなければ、通じる名前への読み替えを設定したことを、一言だけ伝える。

  手順 6 へ。
- `license_failed`: Lumerical は入ったが、ライセンスを借りられない。`reason` ごとに:
  - `host_unresolvable`: TSUBAME からその名前のパソコンが見つからない(大学の名簿に載っていない名前)。サーバの IP アドレスを本人に聞き、`install --server 1055@<IP>` でもう一度(入れ直しはしない)。
  - `port_closed`: TSUBAME からサーバのその番号に届かない。考えられるのは、サーバのパソコンが止まっている、番号が違う、サーバの防火壁が TSUBAME からの接続を止めている、のどれか。本人には、研究室のライセンスの担当の人に次のように頼むよう伝える:「TSUBAME の計算ノード(外から見ると 131.112.133.241 と 131.112.133.242)から、ライセンスサーバの <ポート番号> 番と、ベンダデーモン(ansyslmd)の番号への接続を許可してください」。許可されたら `install --server` をもう一度。番地の出どころは TSUBAME4.0 FAQ「計算ノード用ゲートウェイサーバのIPアドレスについて(TSUBAME外ライセンスサーバへの接続など)」(https://www.t4.cii.isct.ac.jp/docs/faq.ja/pdf/faq.ja.pdf 、2026-10-13 版の 16 ページ)。変わっていないかをそこで確かめてから伝える。
  - `no_dns_name` か `selfname_unresolvable`: サーバが自分を TSUBAME で通じない名前で名乗っていて、IP アドレスから正式な名前も引けない。読み替えに使う名前が無いので、ここでは直せない。担当の人に「ライセンスサーバのパソコンに、大学の DNS の名前を付けてください」と頼むよう伝える。
  - `no_lumerical_features`: そのサーバに Lumerical のライセンスが無い(Zemax や TSUBAME の Ansys のサーバなど、別のサーバ)。正しい場所を本人に聞き直す。
  - `license_down`: 複数のサーバを並べた指定で、どのサーバからも返事が無かった。`license_detail` を読み、サーバの場所を本人に確かめ直す。
- `error`:
  - `dest_not_empty`: 入れる場所に別のファイルがある。手順 2 と同じように別の場所を決めて、`--dest` を付けてもう一度。
  - `no_installer`: TSUBAME にインストーラが無い。手順 3 からやり直す。
  - `untar_failed`・`no_rpm_in_installer`・`no_lumerical_in_installer`: 送ったファイルが Lumerical の Linux 版ではない(壊れている、別の製品、Windows 版など)。手順 3 で選び直す。
  - `untar_failed`・`rpm_extract_failed` で `DISK` の行の使用率が 100% 近い: グループのディスクの容量(か、ファイル数の上限)が足りない。途中まで取り出した分は消してある。本人に伝えて、グループの管理者と相談してもらう。
  - `partial_install`: 前の取り出しが途中で止まった跡(`<dest>/opt`)が残っている。本人に、その場所を消してやり直してよいかを聞き、よければ `ssh <接続名> rm -rf <dest>/opt` で消してから、もう一度 `install`。
  - `job_error_state`・`submit_failed`・`job_incomplete`: `detail` を読む。`submit_failed` で「group」や「point」に関する文があれば、グループかポイントの残りの問題(`tsubame` スキル)。
- `missing_libs` が `none` 以外でも、手順 6 の試験で困らなければ構わない(使わない部品のことがある)。試験が止まったら、その名前を手がかりにする。

## 6. 試しに解く

本人に聞く:

> 入れた Lumerical で、小さな模型を試しに解きます。GPU(H100)でも試しますか。
> - 試す(おすすめ): CPU と GPU の両方で解けるかを見ます。GPU は TSUBAME で Lumerical を使ういちばんの利点です。GPU の試験は順番待ちを除いて数分、0.02 ポイントほどです。ただし GPU は研究室の計算用ライセンスを多めに使うので(例: 9 本)、研究室のライセンスが混んでいるときは、CPU だけにしてもかまいません。
> - CPU だけ: 0.01 ポイント未満。

`<LS> verify --gpu`(CPU だけなら `<LS> verify`)。CPU のジョブは、模型を Lumerical スクリプトで作り、スレッドと Open MPI の 2 通りで解き、lumapi(Python)で透過率を読む。GPU のジョブは同じ模型を GPU で解く。

- `still_running`: もう一度 `<LS> verify --watch`。
- `ok`: どの回し方でも、透過率 T が見込み(`expected_T`)と合った。本人に「CPU(と GPU)で解けて、結果も見込みどおりでした」と伝える。手順 7 へ。
- `failed`: `report` の回し方ごとに見る。
  - `cad` が `fail`: 模型を作る所(画面用ライセンスを 1 本使う)で止まった。`detail` を読む。ライセンスの文なら、画面用が全部使われているか、ライセンスサーバのベンダデーモン(ansyslmd)の番号に TSUBAME から届いていない。前者なら少し待って `verify` をやり直す。何度やっても同じなら後者なので、手順 5 の `port_closed` と同じ頼み方を担当の人にしてもらう。
  - `solves` のどれかが失敗: `detail` を読む。GPU だけが失敗したなら、CPU では使えるので、そのことを伝えて手順 7 に進んでよい(スキルには「GPU は失敗」と書かれる)。
  - 解けたのに T が見込みから外れた: 版の違いで少しずれることはあるが、0.01 を超えるのはおかしい。数字を本人に見せ、続けてよいかを聞く。

## 7. スキルを書く

`<LS> skill`。Claude のスキル `~/.claude/skills/tsubame-lumerical/`(TSUBAME での Lumerical の回し方・ライセンスの使い方・つまずく点と、この人の値)と、ジョブの雛形 `lum_job.sh` を書く。

- `ok`: 手順 8 へ。

## 8. 片付ける

準備のためだけに作った物を消す。入れた Lumerical(`dest`)と、スキルは残る。

1. `<LS> cleanup`。TSUBAME の準備用のフォルダ(`<置き場所>/lumerical-setup`。送ったインストーラ・試験の模型・ジョブの記録)を消す。`kept` に何か残ったら、理由を本人に伝える。
2. このフォルダの外に出てから、uv のダウンロードの残りと、このフォルダを消す。消す前に、それがこのセットアップのフォルダかどうかを中身で確かめる:
   - PowerShell: `Set-Location $HOME; & "$HOME\.local\bin\uv.exe" cache clean; if (Test-Path "$HOME\tsubame-lumerical-setup\setup\lumsetup.py") { Remove-Item -Recurse -Force "$HOME\tsubame-lumerical-setup" }`
   - Git Bash / Mac: `cd ~ && ~/.local/bin/uv cache clean && if [ -f ~/tsubame-lumerical-setup/setup/lumsetup.py ]; then rm -rf ~/tsubame-lumerical-setup; fi`

   フォルダが使用中で消せないと出たら(Claude Code をこのフォルダで開いている場合)、次に Claude Code を別の場所で開いたときに消すよう、本人に伝える。
3. このパソコンにダウンロードしたインストーラ(`cleanup` の `local_installer`)は、本人のファイルなので消さない。「TSUBAME にはもう要りません。研究室の PC に入れ直すときに使わなければ、消してかまいません」と伝える。

完了: `~/tsubame-lumerical-setup` が無い。

## 9. 終わりを伝える

本人にこう伝える(`<…>` は実際の値にする):

> 準備ができました。
> - (手順 2 で TSUBAME の準備もしたときだけ、この行を入れる)このパソコンから、<ログイン名> のアカウントで TSUBAME に入れるようにしました(グループ <グループ>、置き場所 <置き場所>)。
> - TSUBAME に Lumerical <版> を入れました(<dest>)。研究室のライセンス(<ライセンスサーバ>)を、TSUBAME の計算ノードから借りて動きます。ライセンスは研究室の人と分け合って使います(本数が分かっていれば、計算用 <N> 本・画面用 <M> 本)。
>   (手順 2b で共有の Lumerical を使ったときは、この行を「研究室のグループで共有している Lumerical <版>(<dest>、<owner> さんが入れたもの)を使えるようにしました。」にする。)
> - 試しに小さな模型を <CPU と GPU / CPU> で解いて、結果も見込みどおりでした。
> - 準備のために使ったファイルは片付けました。ダウンロードしたインストーラは残してあります。
> - これからは Claude に「この .fsp を TSUBAME の GPU で解いて」「この lumapi のスクリプトを TSUBAME で回して」のように頼むだけです。大きな 3D の FDTD は GPU(gpu_1)がたいてい速くて安いです。
> - Claude Code を一度閉じて開き直すと、次からは今日書いたスキルが使えます。
