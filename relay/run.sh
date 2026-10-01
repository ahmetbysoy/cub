#!/usr/bin/env bash
# Relay indirme yardımcısı: dosyayı bir GitHub runner'ında indirir,
# <=45MB parçalara böler ve geçici bir dala push eder.
#
# Kontrol dosyaları:
#   relay/url.txt      – indirilecek URL
#   relay/branch.txt   – parçaların push edileceği dal (varsayılan relay/cubecraft)
#   relay/trigger.txt  – her değişiklikte iş akışını tetikler
#
# NOT: Çıktı dizini "relay/out" — .gitignore'daki `out/` kuralına takılmaması için
#      dosyalar `git add -f` ile zorla eklenir.
set -uo pipefail

OUT="relay/out"
URL="$(tr -d '\r\n' < relay/url.txt)"
BRANCH="$(tr -d '\r\n' < relay/branch.txt 2>/dev/null)"
[ -z "$BRANCH" ] && BRANCH="relay/cubecraft"
EXPECTED="$(printf '%s' "$URL" | sed -nE 's/.*[?&]full_size=([0-9]+).*/\1/p')"
mkdir -p "$OUT"
LOG="$OUT/status.txt"
rm -f "$OUT"/part-* "$LOG"

{
  echo "run_id: ${GITHUB_RUN_ID:-local}"
  echo "started: $(date -u +%FT%TZ)"
  echo "target_url: $URL"
  echo "target_branch: $BRANCH"
  echo "expected_bytes: ${EXPECTED:-unknown}"
} > "$LOG"

curl -fL --retry 3 --retry-delay 5 --max-time 2400 \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36" \
  -e "https://apkpure.com/" \
  -o /tmp/payload.bin "$URL" 2>/tmp/curl.log
rc=$?

if [ "$rc" -ne 0 ]; then
  {
    echo "result: DOWNLOAD_FAILED"
    echo "curl_rc: $rc"
    echo "--- curl log (tail) ---"
    tail -40 /tmp/curl.log
  } >> "$LOG"
else
  SIZE=$(stat -c%s /tmp/payload.bin)
  SHA=$(sha256sum /tmp/payload.bin | cut -d' ' -f1)
  {
    echo "result: OK"
    echo "bytes: $SIZE"
    echo "sha256: $SHA"
    if [ -n "$EXPECTED" ] && [ "$SIZE" != "$EXPECTED" ]; then
      echo "warning: size differs from full_size param"
    fi
  } >> "$LOG"
  split -b 45M -d -a 3 /tmp/payload.bin "$OUT/part-"
fi

ls -l "$OUT" >> "$LOG" 2>&1 || true

git config user.name "relay-bot"
git config user.email "relay-bot@users.noreply.github.com"
git config http.postBuffer 524288000

# Yük ayrı bir (orphan) geçmişe yazılır: geçmiş birikmez, dal sonra silinebilir.
git checkout --orphan relay-payload-tmp >/dev/null 2>&1 || true
git rm -r -q --cached . >/dev/null 2>&1 || true

# .gitignore `out/` kuralına rağmen ekle
git add -f -A "$OUT"

if git commit -q -m "relay payload ($BRANCH)"; then
  echo "commit: ok" >> "$LOG"
else
  echo "commit: FAILED (eklenecek dosya yok?)" >> "$LOG"
fi
git add -f "$LOG" && git commit -q --amend --no-edit

if git push -f origin "HEAD:refs/heads/$BRANCH" 2>&1 | tee -a "$LOG"; then
  echo "push: ok -> $BRANCH" >> "$LOG"
  echo "DONE: $BRANCH"
else
  echo "push: FAILED -> $BRANCH" >> "$LOG"
  echo "FAILED: push reddedildi"
  exit 1
fi
