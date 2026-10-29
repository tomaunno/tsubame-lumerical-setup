#!/bin/bash
#$ -cwd
#$ -j y
# tsubame-lumerical-setup: unpack Lumerical into DEST and check the license server
# from a compute node, then write DEST/lumenv.sh. Submitted by `lumsetup.py install`:
#     qsub -g GROUP -l cpu_8=1 -l h_rt=1:00:00 install_job.sh INSTALLER.tar.gz DEST PORT@HOST
# Every line the setup script reads starts with "LS ". Errors end the job with exit 0
# after an "LS ERROR <reason>" line, so the reason always reaches the log.
set -u
TARBALL=$1; DEST=$2; SERVER=$3
# libglut.so.3 is needed by the Lumerical CAD and missing on TSUBAME (RHEL 9): take it from Rocky Linux 9.
GLUT_URL=https://dl.rockylinux.org/pub/rocky/9/AppStream/x86_64/os/Packages/f/freeglut-3.2.1-10.el9.x86_64.rpm
GLUT_SHA=7d27717e88edcb760d8c38a2e9230cf932f8cccbdd49916661b7fee649584058
echo "LS START host=$(hostname) $(date '+%F %T')"

# ---- 1. unpack (skipped when an earlier run finished it) ------------------------------
# .lumsetup_unpacked is written only after every rpm came out whole, so a run that died
# halfway (disk quota, time limit) is not mistaken for an install.
MARK=$DEST/.lumsetup_unpacked
if [ -f "$MARK" ]; then
  echo "LS UNPACK=skipped (already installed)"
else
  if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
    if [ -d "$DEST/opt/lumerical" ] && [ -z "$(ls -A "$DEST" | grep -v -x -E 'opt|extra')" ]; then
      echo "LS ERROR partial_install $DEST"      # left by a run that stopped halfway
    else
      echo "LS ERROR dest_not_empty $DEST"
    fi
    exit 0
  fi
  [ -f "$TARBALL" ] || { echo "LS ERROR no_installer $TARBALL"; exit 0; }
  W=${T4TMPDIR:-${TMPDIR:-/tmp}}/lumsetup.$$
  mkdir -p "$W" "$DEST"
  fail() { echo "LS ERROR $1"; rm -rf "$W" "$DEST/opt"; df -h "$DEST" 2>/dev/null | tail -1 | sed 's/^/LS DISK /'; exit 0; }
  tar -xzf "$TARBALL" -C "$W" || fail untar_failed
  # Same as the bundled extract-rpm.sh (rpm2cpio | cpio), without its fallback of
  # unpacking next to itself when DEST is not empty.
  n=0
  while IFS= read -r r; do
    (cd "$DEST" && rpm2cpio "$r" | cpio -idm --quiet) || fail "rpm_extract_failed $(basename "$r")"
    n=$((n + 1)); echo "LS RPM $(basename "$r")"
  done < <(find "$W" -name '*.rpm' -not -path '*/docker/*' | sort)
  rm -rf "$W"
  [ "$n" -gt 0 ] || { echo "LS ERROR no_rpm_in_installer"; exit 0; }
  touch "$MARK"
  echo "LS UNPACK=done"
fi
ROOT=$(ls -d "$DEST"/opt/lumerical/v* 2>/dev/null | sort -V | tail -1)
if [ -z "$ROOT" ] || [ ! -x "$ROOT/bin/fdtd-engine" ]; then echo "LS ERROR no_lumerical_in_installer"; exit 0; fi
echo "LS ROOT=$ROOT"
MAJ=$(sed -n 's/^MAJORRELEASE=//p' "$ROOT/VERSION" 2>/dev/null | tr -d '\r')
MIN=$(sed -n 's/^MINORRELEASE=//p' "$ROOT/VERSION" 2>/dev/null | tr -d '\r')
echo "LS VERSION=$(echo "$MAJ" | sed 's/^\([0-9]\{4\}\)\(R[0-9]*\)$/\1 \2/')${MIN:+.$MIN} ($(basename "$ROOT"))"
echo "LS SIZE=$(du -sh "$DEST" 2>/dev/null | cut -f1)"
[ -x "$ROOT/python/bin/python3" ] && echo "LS PYTHON=ok" || echo "LS PYTHON=missing"

# ---- 2. libraries --------------------------------------------------------------------
EXTRA=$DEST/extra/usr/lib64
mkdir -p "$EXTRA"
if ldconfig -p | grep -q 'libglut\.so\.3 ' || [ -e "$EXTRA/libglut.so.3" ]; then
  echo "LS GLUT=present"
else
  G=$DEST/extra/freeglut.rpm
  if curl -fsSL -o "$G" "$GLUT_URL" && echo "$GLUT_SHA  $G" | sha256sum -c --quiet \
      && (cd "$DEST/extra" && rpm2cpio "$G" | cpio -idm --quiet); then
    echo "LS GLUT=added"
  else
    echo "LS GLUT=failed"
  fi
  rm -f "$G"
fi
# Only the solver engines; the MPI ones find libmpi through `module load openmpi` / `intel-mpi`.
miss=$(for b in "$ROOT"/bin/*-engine*; do
         [ -f "$b" ] && head -c4 "$b" | grep -q ELF && LD_LIBRARY_PATH="$EXTRA" ldd "$b" 2>/dev/null | awk '/not found/{print $1}'
       done | grep -v '^libmpi' | sort -u | tr '\n' ' ')
echo "LS MISSING_LIBS=${miss:-none}"

# ---- 3. license server -----------------------------------------------------------------
# Lumerical asks the license server where its vendor daemon is, and the server answers with
# the name it calls itself (e.g. a bare PC name). When TSUBAME cannot resolve that name,
# HOSTALIASES maps it to a DNS name that does resolve. The Ansys licensing client also
# shortens the server's DNS name to its first label, which needs the same mapping.
LMUTIL=$ROOT/licensingclient/linx64/lmutil
LICBAD=""
licerr() { echo "LS LICERR $*"; LICBAD=1; }
# Built in a new file and moved into place only when the check passes, so a failed re-check
# (wrong address typed) does not break an install the group already uses.
ALIASES=$DEST/hostaliases
NEWALIASES=$ALIASES.new
: > "$NEWALIASES"
if [[ $SERVER == *[,:]* ]]; then          # several servers (port@a,port@b,...): used as given
  LICFILE=$SERVER; MULTI=1
  echo "LS SERVERS=multiple"
else
  PORT=${SERVER%%@*}; HOST=${SERVER#*@}
  if [[ $HOST =~ ^[0-9]+(\.[0-9]+){3}$ ]]; then
    IP=$HOST; DNSNAME=$(getent hosts "$IP" | awk '{print $2; exit}')
  else
    IP=$(getent hosts "$HOST" | awk '{print $1; exit}'); DNSNAME=$HOST
    [ -n "$IP" ] || DNSNAME=""
  fi
  echo "LS HOST=$HOST IP=${IP:-none} DNSNAME=${DNSNAME:-none}"
  if [ -z "$IP" ]; then
    licerr "host_unresolvable"
  elif timeout 5 bash -c "exec 3<>/dev/tcp/$IP/$PORT" 2>/dev/null; then
    echo "LS TCP=ok"
  else
    echo "LS TCP=fail"
    licerr "port_closed"
  fi
  LICFILE=$PORT@${DNSNAME:-${IP:-$HOST}}
  SELF=""
  [ -n "$IP" ] && SELF=$(timeout 60 "$LMUTIL" lmstat -c "$PORT@$IP" 2>&1 | sed -n 's/^License server status: [0-9]*@\([^ ,]*\).*/\1/p' | head -1)
  echo "LS SELFNAME=${SELF:-unknown}"
  add_alias() {            # $1: a single-label name TSUBAME may not resolve
    local n=$1
    [ -n "$n" ] && [[ $n != *.* ]] || return 0
    getent hosts "$n" >/dev/null && return 0
    if [ -n "$DNSNAME" ]; then
      echo "$n $DNSNAME" >> "$NEWALIASES"; echo "LS ALIAS $n $DNSNAME"
    else
      licerr "no_dns_name $n"
    fi
  }
  add_alias "$SELF"
  [ -n "$DNSNAME" ] && add_alias "${DNSNAME%%.*}"
  if [[ $SELF == *.* ]] && ! getent hosts "$SELF" >/dev/null; then licerr "selfname_unresolvable $SELF"; fi
fi
export HOSTALIASES=$NEWALIASES ANSYSLMD_LICENSE_FILE=$LICFILE
echo "LS LICFILE=$LICFILE"
# lmstat gives the counts, but it reaches the server by the name the server calls itself and
# does not read HOSTALIASES: with a server whose own name TSUBAME cannot resolve it reports
# "lmgrd is not running" although Lumerical itself checks licenses out fine. So lmstat
# failing is not a failure here; lmdiag and, in the end, `verify` (a real checkout) decide.
ST=$(timeout 120 "$LMUTIL" lmstat -c "$LICFILE" -a 2>&1)
if echo "$ST" | grep -q "license server UP"; then
  echo "LS LMSTAT=up"
else
  echo "LS LMSTAT=down"
  echo "$ST" | grep -i -E "error|down|cannot|not running" | head -3 | sed 's/^/LS LICDETAIL /'
fi
for f in lum_fdtd_solve lum_fdtd_gui; do
  D=$(timeout 60 "$LMUTIL" lmdiag -c "$LICFILE" -n "$f" 2>&1)
  if echo "$D" | grep -q "can be checked out"; then echo "LS LMDIAG $f ok"; DIAGOK=1
  elif echo "$D" | grep -q "cannot be checked out"; then echo "LS LMDIAG $f fail"
  else echo "LS LMDIAG $f unknown"; fi
done
# several servers and none answered: nothing to fall back on
if [ -n "${MULTI:-}" ] && ! echo "$ST" | grep -q "license server UP" && [ -z "${DIAGOK:-}" ]; then licerr "license_down"; fi
# counts only (lmstat -a also lists who is using what; that is not printed)
echo "$ST" | grep '^Users of lum_' | while IFS= read -r l; do
  f=$(echo "$l" | sed 's/^Users of \([^:]*\):.*/\1/')
  t=$(echo "$l" | grep -o '[0-9]* licenses\? issued' | cut -d' ' -f1)
  u=$(echo "$l" | grep -o '[0-9]* licenses\? in use' | cut -d' ' -f1)
  echo "LS FEATURE $f ${t:-?} ${u:-?}"
done

# ---- 4. the environment every job sources ------------------------------------------------
# Not written when the server cannot be reached or named: a lumenv.sh is what `check` offers to
# other members of the group, so it must only exist for a working setup. An existing one is kept.
if [ -n "$LICBAD" ]; then rm -f "$NEWALIASES"; echo "LS LUMENV=not written"; echo "LS DONE $(date '+%F %T')"; exit 0; fi
mv -f "$NEWALIASES" "$ALIASES"
LMSTAT=down; echo "$ST" | grep -q "license server UP" && LMSTAT=up
cat > "$DEST/lumenv.sh" <<EOF
# Lumerical on TSUBAME: source this at the start of every job.
# Written by tsubame-lumerical-setup on $(date +%F). Lumerical $(echo "$MAJ" | sed 's/^\([0-9]\{4\}\)\(R[0-9]*\)$/\1 \2/')${MIN:+.$MIN}.
# license counts readable from TSUBAME (lmstat): $LMSTAT
export LUM_ROOT=$ROOT
export LUM_PY=\$LUM_ROOT/python/bin/python3
export PATH=\$LUM_ROOT/bin:\$PATH
export LD_LIBRARY_PATH=$EXTRA\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}
export LUMERICAL_LD_LIBRARY_PATH=$EXTRA         # the CAD start scripts reset LD_LIBRARY_PATH
export PYTHONPATH=\$LUM_ROOT/api/python\${PYTHONPATH:+:\$PYTHONPATH}
export ANSYSLMD_LICENSE_FILE=$LICFILE
export HOSTALIASES=$ALIASES     # names of the license server that TSUBAME cannot resolve
export QT_QPA_PLATFORM=offscreen
EOF
chmod -R g+rX "$DEST"     # usable by everyone in the group (one install serves a lab)
echo "LS LUMENV=$DEST/lumenv.sh"
echo "LS DONE $(date '+%F %T')"
