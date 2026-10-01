#!/usr/bin/env bash
# ---------------------------------------------------------------
# CubeCraft runner yardımcısı
# GitHub Actions (relay.yml) içinden çalışır:  bash relay/run.sh
#
# İşler `relay/job.txt` içinden okunur (satır başına bir iş):
#   dump     → Il2CppDumper ile statik döküm alır, `analysis/dump` dalına push eder
#   control  → içeriği değiştirmeden yeniden imzalar, Release'e yükler
#
# Hiçbir adım diğerini durdurmaz; her işin sonucu loglanır ve `run-status.txt` yazılır.
# ---------------------------------------------------------------
set -uo pipefail

WORK=/tmp/cc
LOG="$WORK/log.txt"
mkdir -p "$WORK"
: > "$LOG"

IL2CPPDUMPER_TAG=v6.7.46
IL2CPPDUMPER_URL="https://github.com/Perfare/Il2CppDumper/releases/download/${IL2CPPDUMPER_TAG}/Il2CppDumper-net6-${IL2CPPDUMPER_TAG}.zip"

log()  { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }
fail() { log "HATA: $*"; }

# actions/checkout'ın bıraktığı Authorization başlığından push token'ını çıkar
git_token() {
  local auth b64
  auth="$(git config --local --get http.https://github.com/.extraheader 2>/dev/null || true)"
  [ -n "$auth" ] || return 1
  case "$auth" in *"basic "*) ;; *) return 1 ;; esac
  b64="${auth##*basic }"
  printf '%s' "$b64" | base64 -d 2>/dev/null | sed 's/^x-access-token://'
}

# ---------------------------------------------------------------
# Orijinal XAPK'yı parçalardan hazırla ve gerekli girdileri çıkar
# ---------------------------------------------------------------
prepare_inputs() {
  log "orijinal XAPK hazırlanıyor (relay/cubecraft dalı)…"
  # actions/checkout dar bir refspec kurar; bu yüzden hedef dalı AÇIK refspec ile çekiyoruz
  git fetch -q origin "+refs/heads/relay/cubecraft:refs/remotes/origin/relay/cubecraft" \
    || { fail "fetch başarısız"; return 1; }
  git rev-parse --verify -q origin/relay/cubecraft >/dev/null \
    || { fail "origin/relay/cubecraft ref'i yok"; return 1; }

  rm -rf "$WORK/orig"; mkdir -p "$WORK/orig"
  git archive origin/relay/cubecraft relay/out | tar -x -C "$WORK/orig" \
    || { fail "arşiv açılamadı"; return 1; }

  cat "$WORK/orig"/relay/out/part-* > "$WORK/original.xapk" || { fail "parçalar birleştirilemedi"; return 1; }
  local size sha
  size=$(stat -c%s "$WORK/original.xapk")
  sha=$(sha256sum "$WORK/original.xapk" | cut -c1-16)
  log "orijinal XAPK: $size bayt · sha256=$sha…"
  if [ "$size" != "262785289" ]; then
    fail "boyut beklenenden farklı (262785289 olmalı)"; return 1
  fi

  rm -rf "$WORK/apk"; mkdir -p "$WORK/apk"
  unzip -o -q "$WORK/original.xapk" -d "$WORK/apk" || { fail "XAPK açılamadı"; return 1; }
  log "XAPK içeriği: $(ls "$WORK/apk" | tr '\n' ' ')"
  return 0
}

# ---------------------------------------------------------------
# JOB: dump  →  Il2CppDumper
# ---------------------------------------------------------------
job_dump() {
  prepare_inputs || return 1

  rm -rf "$WORK/dump-in" "$WORK/dump-out"; mkdir -p "$WORK/dump-in" "$WORK/dump-out"
  unzip -o -q "$WORK/apk/config.arm64_v8a.apk" "lib/arm64-v8a/libil2cpp.so" -d "$WORK/dump-in" \
    || { fail "libil2cpp.so çıkarılamadı"; return 1; }
  unzip -o -q "$WORK/apk/com.cww.cubecraft.apk" "assets/bin/Data/Managed/Metadata/global-metadata.dat" -d "$WORK/dump-in" \
    || { fail "global-metadata.dat çıkarılamadı"; return 1; }

  local so="$WORK/dump-in/lib/arm64-v8a/libil2cpp.so"
  local md="$WORK/dump-in/assets/bin/Data/Managed/Metadata/global-metadata.dat"
  log "girdiler: libil2cpp.so=$(stat -c%s "$so") bayt · global-metadata.dat=$(stat -c%s "$md") bayt"

  log "Il2CppDumper indiriliyor: $IL2CPPDUMPER_TAG"
  curl -fL --retry 3 -o "$WORK/dumper.zip" "$IL2CPPDUMPER_URL" || { fail "dumper indirilemedi"; return 1; }
  rm -rf "$WORK/dumper"; mkdir -p "$WORK/dumper"
  unzip -o -q "$WORK/dumper.zip" -d "$WORK/dumper" || { fail "dumper açılamadı"; return 1; }
  log "dumper içeriği: $(ls "$WORK/dumper" | tr '\n' ' ')"

  log "dotnet kontrolü:"
  if ! command -v dotnet >/dev/null 2>&1; then
    log "dotnet yok → kuruluyor (apt)"
    sudo apt-get update -qq >>"$LOG" 2>&1 || true
    sudo apt-get install -y -qq dotnet-sdk-8.0 >>"$LOG" 2>&1 || fail "dotnet kurulamadı"
  fi
  dotnet --list-runtimes >>"$LOG" 2>&1 || true

  log "döküm alınıyor…"
  local rc=0
  ( cd "$WORK/dumper" && DOTNET_ROLL_FORWARD=LatestMajor DOTNET_NOLOGO=1 \
      dotnet Il2CppDumper.dll "$so" "$md" "$WORK/dump-out" ) >>"$LOG" 2>&1 || rc=$?

  if [ "$rc" -ne 0 ] || [ -z "$(ls -A "$WORK/dump-out" 2>/dev/null)" ]; then
    fail "döküm başarısız (rc=$rc)"
    {
      echo "result: DUMP_FAILED"
      echo "rc: $rc"
      echo "--- log (son 60 satır) ---"
      tail -60 "$LOG"
    } > "$WORK/run-status.txt"
    return 1
  fi

  log "döküm dosyaları:"; ls -l "$WORK/dump-out" | tee -a "$LOG"

  # DummyDll klasörünü at (gereksiz büyük), metin çıktıları tut
  rm -rf "$WORK/dump-out/DummyDll"

  # ---- analysis/dump dalına push ----
  local repo_dir="$PWD"
  rm -rf "$WORK/pub"; mkdir -p "$WORK/pub/analysis/dump"
  cp -r "$WORK/dump-out"/. "$WORK/pub/analysis/dump/" 2>/dev/null || true
  {
    echo "# CubeCraft 1.17.14 — statik IL2CPP dökümü"
    echo
    echo "- Kaynak: relay/cubecraft dalındaki orijinal XAPK (sha256 39150c78…)"
    echo "- libil2cpp.so: $(stat -c%s "$so") bayt"
    echo "- global-metadata.dat: $(stat -c%s "$md") bayt"
    echo "- Il2CppDumper $IL2CPPDUMPER_TAG (runner: $(uname -m), dotnet: $(dotnet --version 2>/dev/null || echo '?'))"
    echo "- Üretim: $(date -u +%FT%TZ)"
    echo
    echo "Dosyalar: dump.cs · script.json · stringliteral.json · il2cpp.h"
  } > "$WORK/pub/analysis/dump/README.md"

  git config user.name "relay-bot"
  git config user.email "relay-bot@users.noreply.github.com"
  git -C "$repo_dir" checkout --orphan analysis-dump-tmp >/dev/null 2>&1
  git -C "$repo_dir" rm -r -q --cached . >/dev/null 2>&1 || true
  mkdir -p "$repo_dir/analysis"
  cp -r "$WORK/pub/analysis/." "$repo_dir/analysis/"
  git -C "$repo_dir" add -f analysis
  git -C "$repo_dir" commit -q -m "analysis: IL2CPP statik döküm (CubeCraft 1.17.14)" || fail "commit boş?"
  git -C "$repo_dir" push -f origin HEAD:refs/heads/analysis/dump || { fail "push edilemedi"; return 1; }
  log "döküm analysis/dump dalına push edildi ✔"
  return 0
}

# ---------------------------------------------------------------
# JOB: control  →  sadece yeniden imzalı paket + Release
# ---------------------------------------------------------------
job_control() {
  prepare_inputs || return 1

  log "Python bağımlılıkları (venv) kuruluyor…"
  rm -rf "$WORK/venv"
  python3 -m venv "$WORK/venv" >>"$LOG" 2>&1 || { fail "venv oluşturulamadı"; return 1; }
  "$WORK/venv/bin/pip" install -q --disable-pip-version-check --upgrade pip >>"$LOG" 2>&1 || true
  "$WORK/venv/bin/pip" install -q --disable-pip-version-check lief "git+https://github.com/adityatelange/sign-apk-py" \
    >>"$LOG" 2>&1 || { fail "pip kurulumu başarısız"; return 1; }

  local key_args=()
  if [ -f relay/keys/cubecraft-mod.pem ] && [ -f relay/keys/cubecraft-mod.crt ]; then
    key_args=(--key relay/keys/cubecraft-mod.pem --cert relay/keys/cubecraft-mod.crt)
    log "mevcut imza anahtarı kullanılıyor (relay/keys/)"
  else
    log "imza anahtarı repoda yok → yeni üretilecek"
  fi

  "$WORK/venv/bin/python" relay/build_control.py \
      --base "$WORK/apk/com.cww.cubecraft.apk" \
      --split "$WORK/apk/config.arm64_v8a.apk" \
      --manifest "$WORK/apk/manifest.json" \
      --out-dir "$WORK/control" \
      "${key_args[@]}" >>"$LOG" 2>&1 || { fail "kontrol build başarısız"; return 1; }

  local xapk="$WORK/control/CubeCrafter_control.xapk"
  [ -f "$xapk" ] || { fail "XAPK üretilmedi"; return 1; }
  log "kontrol XAPK: $(stat -c%s "$xapk") bayt · sha256=$(sha256sum "$xapk" | cut -c1-16)…"

  # ---- Release oluştur (checkout token'ı ile) ----
  if [ -n "${CC_SKIP_RELEASE:-}" ]; then
    log "CC_SKIP_RELEASE ayarlı → Release adımı atlandı (yerel test)"
  else
  local auth b64 token
  auth="$(git config --local --get http.https://github.com/.extraheader 2>/dev/null || true)"
  token=""
  if [[ "$auth" == *"basic "* ]]; then
    b64="${auth##*basic }"
    token="$(printf '%s' "$b64" | base64 -d 2>/dev/null | sed 's/^x-access-token://')"
  fi
  if [ -z "$token" ]; then
    fail "token alınamadı → Release oluşturulamadı"
  else
    export GH_TOKEN="$token" GITHUB_TOKEN="$token"
    local tag="control-1.17.14"
    gh release view "$tag" >/dev/null 2>&1 || \
      gh release create "$tag" --title "CubeCraft 1.17.14 — KONTROL (sadece yeniden imzalı)" \
        --notes "İçerik değişmedi; yalnızca v2+v3 yeniden imzalandı. Amaç: repack+imzanın cihazda çalışıp çalışmadığını test etmek. sha256 ve boyut için içindeki control-summary.json / run-status.txt dosyalarına bakın." \
        >>"$LOG" 2>&1
    gh release upload "$tag" "$xapk" --clobber >>"$LOG" 2>&1 \
      && log "Release güncellendi: $tag ✔" \
      || fail "Release yüklenemedi"
    if [ -f "$WORK/control/control-summary.json" ]; then
      { echo "--- kontrol özeti ---"; cat "$WORK/control/control-summary.json"; } > "$WORK/control-summary.txt" 2>/dev/null || true
      gh release upload "$tag" "$WORK/control-summary.txt" --clobber >>"$LOG" 2>&1 || true
    fi
  fi
  fi

  return 0
}

# ---------------------------------------------------------------
# Durum/log yayını — her koşulda çalışır (trap)
# ---------------------------------------------------------------
publish_status() {
  local repo_dir="$PWD"
  {
    echo "# relay koşu durumu"
    echo
    echo '```'
    cat "$WORK/run-status.txt" 2>/dev/null || echo "(run-status yok)"
    echo '```'
  } > "$WORK/analysis-status.md"

  rm -rf "$repo_dir/analysis"
  mkdir -p "$repo_dir/analysis/status"
  cp "$WORK/run-status.txt" "$repo_dir/analysis/status/run-status.txt" 2>/dev/null || true
  tail -c 300000 "$WORK/log.txt" > "$repo_dir/analysis/status/log.txt" 2>/dev/null || true
  cp "$WORK/analysis-status.md" "$repo_dir/analysis/status/README.md" 2>/dev/null || true

  git -C "$repo_dir" checkout --orphan analysis-status-tmp >/dev/null 2>&1 || true
  git -C "$repo_dir" rm -r -q --cached . >/dev/null 2>&1 || true
  git -C "$repo_dir" add -f analysis >/dev/null 2>&1 || true
  git -C "$repo_dir" commit -q -m "relay: koşu durumu ($(date -u +%FT%TZ))" >/dev/null 2>&1 || true

  local token; token="$(git_token || true)"
  local url="origin"
  if [ -n "$token" ]; then
    url="https://x-access-token:${token}@github.com/ahmetbysoy/cub.git"
  fi
  if git -C "$repo_dir" push -f "$url" HEAD:refs/heads/analysis/status >>"$LOG" 2>&1; then
    echo "[status] analysis/status dalına push edildi"
  else
    echo "[status] UYARI: durum push edilemedi (token=$( [ -n "$token" ] && echo var || echo yok ))"
    echo "[status] origin URL: $(git -C "$repo_dir" remote get-url origin 2>&1)"
  fi
}
trap publish_status EXIT

# ---------------------------------------------------------------
# Ana döngü
# ---------------------------------------------------------------
log "iş listesi: $(tr '\n' ' ' < relay/job.txt)"
FAILED=0
echo "run: ${GITHUB_RUN_ID:-local}" > "$WORK/run-status.txt"
echo "repo: $(git rev-parse --short HEAD 2>/dev/null || echo '?')" >> "$WORK/run-status.txt"
echo "started: $(date -u +%FT%TZ)" >> "$WORK/run-status.txt"

for job in $(grep -v '^[[:space:]]*#' relay/job.txt | tr -d '\r' | tr -s '\n' ' '); do
  [ -n "$job" ] || continue
  log "=== İŞ: $job ==="
  if "job_$job"; then
    echo "result: ${job^^}_OK" >> "$WORK/run-status.txt"
  else
    FAILED=1
    log "!!! $job başarısız"
    echo "result: ${job^^}_FAILED" >> "$WORK/run-status.txt"
  fi
done

echo "finished: $(date -u +%FT%TZ)" >> "$WORK/run-status.txt"
log "bitti. Özet:"
tail -20 "$WORK/run-status.txt" | tee -a "$LOG"

exit "$FAILED"
