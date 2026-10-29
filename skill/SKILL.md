---
name: tsubame-lumerical
description: TSUBAME 4.0 で Ansys Lumerical(FDTD・varFDTD・MODE・RCWA・lumapi・Lumerical スクリプト)を回す作業。.fsp を GPU / CPU / MPI で解く、lumapi の Python や .lsf をジョブで動かす、研究室の Lumerical ライセンスの残りを見る、Lumerical のジョブが止まったときに直す。接続・hpcjob・資源と課金は tsubame スキルと一緒に使う。
---

# TSUBAME で Lumerical を回す

{{DATE}} に tsubame-lumerical-setup が {{USER}} さんのために書いたスキル。TSUBAME への接続・hpcjob の使い方・資源の種類と課金・守る規則は **`tsubame` スキル**にある。ここには Lumerical に固有のことだけを書く。この PC の持ち主のものなので、使い方に合わせて自由に直してよい。

## 入れたもの

| 項目 | 値 |
|---|---|
| Lumerical | {{VERSION}}(`{{LUM_ROOT}}`。入れた人: {{OWNER}}) |
| 環境の設定 | `{{LUMENV}}`(どのジョブも最初に `source` する) |
| ライセンス | `{{LICFILE}}`(研究室のライセンスサーバ。TSUBAME のライセンスではないので、ポイントとは別。研究室の人と共有) |
| ライセンスの本数(入れたとき) | {{FEATURES}} |
| 確かめた回し方 | {{VERIFIED}}(小さな模型を Lumerical スクリプトで作り、解き、lumapi で結果を読むまで) |
| ジョブの雛形 | このスキルのフォルダの [`lum_job.sh`](lum_job.sh) |

## 回し方

1. **プロジェクトを用意する**: `tsubame` スキルの「計算を回す」のとおり、hpcjob のプロジェクト(`hpcjob.toml`・`src/`・`jobs/`・`results/`)を作る。このスキルの `lum_job.sh` を `jobs/` に写す。
   **`hpcjob.toml` の `[local]` に次の 2 行を足す**。hpcjob は既定では `.py`・`.sh` などしか送らず、`.fsp`・`.lsf` を送らないため(足さないと、ジョブが「ファイルが無い」で止まる):
   ```toml
   sync_extensions = [".py", ".sh", ".json", ".toml", ".yaml", ".csv", ".mat", ".npz", ".fsp", ".lsf", ".lms", ".ldev"]
   text_extensions = [".py", ".sh", ".json", ".toml", ".yaml", ".csv", ".md", ".txt", ".lsf"]
   ```
2. **ファイルを置く**: 解く `.fsp`、lumapi の `.py`、Lumerical スクリプトの `.lsf` を `src/` に置く。`src/` の中身は投げるたびに全部送り直すので、大きな `.fsp`(数百 MB)は解き終えたら `src/` から外す。
3. **投げる**(プロジェクトのフォルダで):

| やりたいこと | コマンドの例 |
|---|---|
| 大きな 3D の FDTD を GPU で | `hpcjob submit lum_job.sh -r gpu_1=1 -t 0:30:00 -- model.fsp gpu` |
| CPU 80 コアの MPI で | `hpcjob submit lum_job.sh -r cpu_80=1 -t 2:00:00 -- model.fsp mpi` |
| 小さな計算をスレッドで | `hpcjob submit lum_job.sh -r cpu_16=1 -t 0:30:00 -- model.fsp cpu` |
| lumapi の Python(模型を作る・掃引する・結果を読む) | `hpcjob submit lum_job.sh -r cpu_8=1 -t 1:00:00 -- sweep.py py <引数>` |
| Lumerical スクリプト | `hpcjob submit lum_job.sh -r cpu_8=1 -t 0:30:00 -- make.lsf lsf` |

4. **結果を取る**: `.fsp` は `out/` に写してから解くので、`hpcjob pull out/model.fsp`。エンジンのログは `out/model_p0.log`(必要なメモリ「Estimate of memory required」と、終わったか「Simulation completed successfully」が出る)。Python や .lsf が書いたファイルは、書いた場所から `pull` する。

h_rt(`-t`)は、最初は短い試しで実行時間を見てから決める(長く取るだけでポイントがかかる。`tsubame` スキルの reference.md)。

## どの回し方を選ぶか

- **3D の大きな FDTD は GPU(gpu_1、H100 80 GB)がたいてい速くて安い**。例(3D・メッシュ 5 nm・メモリ 9 GiB・31 000 ステップ、2026-10 の実測): gpu_1 で 3 分、cpu_80 の 80 プロセスで 27 分、cpu_8 の 8 プロセスで 2 時間 40 分。結果はどれも研究室の Windows 機で解いたものと一致した(透過率の差 10⁻⁷ 以下)。
- GPU のメモリ(80 GB)に入らない、または GPU に対応しない設定(エンジンが GPU では動かないと言って止まる)なら、CPU の `mpi` に切り替える。cpu_80 は約 320 GB、cpu_160 は約 640 GB。
- 小さな計算(数分以内)は cpu_8〜cpu_16 の `cpu` で十分。
- 何本も回す掃引は、Python で `.fsp` を先に全部作り、エンジン(`gpu` / `cpu` / `mpi`)だけのジョブを並べる。hpcjob のアレイジョブ(`tsubame` スキルの reference.md)も使える。
- **RCWA・MODE(FDE・EME)・varFDTD は CPU**。Lumerical の RCWA には GPU 版がない(2026 R1 の `rcwa-engine` に GPU の部分がない)。これらは lumapi の `run()` や `findmodes()` で、`py` か `lsf` の回し方で動かす。

## ライセンスの使い方(研究室の人と共有している)

- ライセンスには、計算用(`lum_fdtd_solve` など)と画面用(`lum_fdtd_gui` など)がある。**`py` と `lsf` の回し方は、Lumerical の画面の部分を開くので画面用を 1 本使う**。画面用は本数が少ないことが多いので、何本も回すときは模型を先に作り、エンジンだけで解く。
- 1 本のジョブが使う計算用の本数は、使うコアや GPU が大きいほど増える。例(2026-10、ある研究室のライセンス): 32 コアまで 1 本、80 プロセス 3 本、H100 1 枚で 9 本。契約によって違うので、初めての大きさで回したら下の方法で確かめる。
- 同時にたくさん投げると、研究室で Windows の Lumerical を使う人の分が足りなくなる。大きな GPU ジョブを何本も並べる前に残りを見る。
- 残りの見方: {{LICENSE_COUNT}}

## つまずく点

- **ライセンスが取れない**(ログに `license` や `-15`・`-96`):
  - 研究室のライセンスサーバが止まっている、または全部使われている。上の lmstat で見る。
  - サーバの名前の読み替え(`{{DEST}}/hostaliases`。中身は「TSUBAME で引けない名前 → 引ける名前」)が古くなった。サーバの PC の名前や住所が変わったら、Lumerical を入れた人({{OWNER}})が tsubame-lumerical-setup を `install --server <新しい場所> --dest {{DEST}}` で動かす(その手順書の 2b)。入れ直さず、ライセンスの確認と `lumenv.sh` の書き直しだけをする。
- **複数ノードの MPI**: `mpirun` に `-x LD_LIBRARY_PATH -x HOSTALIASES -x ANSYSLMD_LICENSE_FILE -x LUMERICAL_LD_LIBRARY_PATH` を付ける(雛形は付けてある)。付けないと、ほかのノードの分がライセンスやライブラリを見つけられない。
- **MPI 版のエンジン**(`fdtd-engine-ompi-lcl`)は MPI を内蔵していない。`module load openmpi` を忘れると `libmpi.so.40` が無いと言って止まる。Intel MPI 版(`fdtd-engine-impi-lcl`)なら `module load intel-mpi`。
- **版の違い**: ここで保存した `.fsp` は、研究室の PC の Lumerical が古いと開けないことがある。行き来させるなら、研究室の PC と同じ版にそろえるか、模型は研究室の PC で作って TSUBAME では解くだけにする。
- **画面は出ない**: `QT_QPA_PLATFORM=offscreen` で動かしている。lumapi は `lumapi.FDTD(hide=True)` で開く。
- ログインノードでエンジンや lumapi を動かさない(`tsubame` スキルの規則)。数秒の lmstat は可。
- 消すとき: {{REMOVE_NOTE}}
