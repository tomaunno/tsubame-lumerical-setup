#!/bin/bash
#$ -cwd
#$ -j y
# tsubame-lumerical-setup: build a one-pillar test model with the CAD, solve it, and read the
# transmission back with lumapi. Submitted by `lumsetup.py verify` in its own folder:
#     qsub -g GROUP -l cpu_8=1 ... verify_job.sh LUMENV cpu      (threads, then Open MPI)
#     qsub -g GROUP -l gpu_1=1 ... verify_job.sh LUMENV gpu
# Every line the setup script reads starts with "LS ".
set -u
LUMENV=$1; MODE=$2
. /etc/profile.d/modules.sh 2>/dev/null
source "$LUMENV"
echo "LS START host=$(hostname) mode=$MODE slots=${NSLOTS:-?} $(date '+%F %T')"

rm -f cell.fsp
timeout 600 fdtd-solutions-batch make_cell.lsf > cad.log 2>&1
if [ -f cell.fsp ]; then
  echo "LS CAD=ok"
else
  echo "LS CAD=fail"
  grep -v '^\s*$' cad.log | tail -4 | sed 's/^/LS DETAIL /'
  echo "LS DONE"; exit 0
fi

solve() {                 # $1 name, the rest the engine command (the .fsp is appended)
  local name=$1; shift
  cp cell.fsp "$name.fsp"
  local t0; t0=$(date +%s)
  timeout 900 "$@" "$name.fsp" > "$name.out" 2>&1
  local rc=$? ok=fail
  grep -q "Simulation completed successfully" "$name.out" "${name}_p0.log" 2>/dev/null && ok=ok
  echo "LS SOLVE $name $ok rc=$rc wall=$(( $(date +%s) - t0 ))s"
  [ $ok = ok ] || grep -h -i -E "error|licens" "$name.out" "${name}_p0.log" 2>/dev/null | head -3 | sed 's/^/LS DETAIL /'
}
case $MODE in
  cpu)
    solve threads fdtd-engine -t 4
    if module load openmpi >/dev/null 2>&1; then
      solve mpi mpirun -np 2 --bind-to none -x LD_LIBRARY_PATH -x HOSTALIASES -x ANSYSLMD_LICENSE_FILE \
        -x LUMERICAL_LD_LIBRARY_PATH fdtd-engine-ompi-lcl -t 2
      FILES="threads.fsp mpi.fsp"
    else
      echo "LS SOLVE mpi fail rc=module"
      echo "LS DETAIL module load openmpi failed"
      FILES="threads.fsp"
    fi ;;
  gpu)
    nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | sed 's/^/LS GPU /'
    solve gpu fdtd-engine -gpu
    FILES="gpu.fsp" ;;
esac
timeout 600 "$LUM_PY" read_t.py $FILES > read.log 2>&1
grep '^LS ' read.log || { echo "LS LUMAPI=fail"; grep -v '^\s*$' read.log | tail -4 | sed 's/^/LS DETAIL /'; }
echo "LS DONE $(date '+%F %T')"
