#!/bin/bash
#$ -cwd
#$ -j y
# Lumerical のジョブ(tsubame-lumerical-setup が {{USER}} さん用に書いた雛形)。資源と時間は投げるときに渡す:
#   hpcjob submit lum_job.sh -r <資源>=1 -t <時:分:秒> -- <ファイル> <回し方> [数]
#   (hpcjob を使わないなら、ファイルのあるフォルダで) qsub -g <グループ> -l <資源>=1 -l h_rt=<時:分:秒> lum_job.sh <ファイル> <回し方> [数]
#
#   <x.fsp> gpu           GPU で解く(gpu_1 など)
#   <x.fsp> cpu [N]       1 プロセス N スレッドで解く(既定は割り当てのコア数)
#   <x.fsp> mpi [N]       Open MPI の N プロセスで解く(既定は割り当てのコア数。複数ノードも可)
#   <x.lsf> lsf           Lumerical スクリプトを画面なしで動かす(画面用ライセンスを 1 本使う)
#   <x.py>  py [引数...]   lumapi を使う Python を、Lumerical に付いている Python で動かす(同上)
#
# .fsp は out/ に写してから解く(src/ から送った元のファイルは書き換えない)。
# 解いた結果は out/<名前>.fsp、エンジンのログは out/<名前>_p0.log。
. /etc/profile.d/modules.sh 2>/dev/null
source {{LUMENV}}
set -eu
IN=$1; MODE=$2; N=${3:-}
echo "[lum] host=$(hostname) mode=$MODE slots=${NSLOTS:-?} start=$(date '+%F %T')"
case $MODE in
  gpu|cpu|mpi)
    mkdir -p out
    cp "$IN" out/
    cd out
    F=$(basename "$IN")
    case $MODE in
      gpu) nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
           fdtd-engine -gpu "$F" ;;
      cpu) fdtd-engine -t "${N:-${NSLOTS:-4}}" "$F" ;;
      mpi) module load openmpi
           mpirun -np "${N:-${NSLOTS:-4}}" --bind-to core -x LD_LIBRARY_PATH -x HOSTALIASES \
             -x ANSYSLMD_LICENSE_FILE -x LUMERICAL_LD_LIBRARY_PATH fdtd-engine-ompi-lcl -t 1 "$F" ;;
    esac
    grep -h -E "Estimate of memory|Simulation completed" "${F%.fsp}_p0.log" 2>/dev/null || true ;;
  lsf) fdtd-solutions-batch "$IN" ;;
  py)  shift 2; "$LUM_PY" "$IN" "$@" ;;
  *)   echo "回し方は gpu / cpu / mpi / lsf / py のどれか: $MODE"; exit 2 ;;
esac
echo "[lum] done $(date '+%F %T')"
