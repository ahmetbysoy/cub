#!/usr/bin/env bash
# Relay indirme yardımcısı: dosyayı bir GitHub runner'ında indirir,
# <=45MB parçalara böler ve geçici bir dala push eder.
#
# Kontrol dosyaları:
#   relay/url.txt      – indirilecek URL
#   relay/branch.txt   – parçaların push edileceği dal (varsayılan relay/cubecraft)
#   relay/trigger.txt  – her değişiklikte iş akışını tetikler
set -uo pipefail

OUT="relay/out"
URL="$(tr -d '\r\n' < relay/url.txt)"
BRANCH="$(tr -d '\r\n' < relay/branch.txt 2>/dev/null)"
[ -z "$BRANCH" ] && BRANCH="relay/cubecraft"
EXPECTED="$(printf '%s' "$URL" | sed -nE 's/.*[?&]full_size=([0-9]+).*/\1/p')"
mkdir -p "$OUT"
LOG="$OUT/status.txt"
rm -f "$OUT"/part-*

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
echo "finished: $(date -u +%FT%TZ)" >> "$LOG"

git config user.name "relay-bot"
git config user.email "relay-bot@users.noreply.github.com"
git config http.postBuffer 524288000

# Payload'ı geçici (orphan) bir dala yazar; geçmiş birikmez, sonra silinebilir.
# NOTE: `rm --cached` indirilen parçaları diskte bırakır (commit için gerekli).
git checkout --orphan relay-payload-tmp
git rm -r -q --cached .
git add -A "$OUT"
if git commit -q -m "relay payload ($BRANCH)"; then
  echo "commit: ok" >> "$LOG"
else
  echo "commit: nothing-to-commit/failed" >> "$LOG"
fi

if git push -f origin "HEAD:refs/heads/$BRANCH" 2>&1 | tee -a "$LOG"; then
  echo "push: ok → $BRANCH" >> "$LOG"
else
  echo "push: FAILED → $BRANCH" >> "$LOG"
  exit 1
fi

echo "finished: $(date -u +%FT%TZ)" >> "$LOG"
git add -A "$OUT" && git commit -q --amend -m "relay payload ($BRANCH)" --no-edit
git push -f origin "HEAD:refs/heads/$BRANCH"
echo "pushed → $BRANCH"
