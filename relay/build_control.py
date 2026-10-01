#!/usr/bin/env python3
"""
build_control.py — Orijinal (yamalanmamış) APK'ları yeniden imzalar ve XAPK üretir.

Amaç: "Yeniden imzalama/repack cihazda çalışıyor mu?" sorusunu test eden bir kontrol
paketi üretmek. İçerik **hiç değişmez**; yalnızca imza değişir (v2+v3).

Kullanım:
  python3 build_control.py \
      --base    com.cww.cubecraft.apk \
      --split   config.arm64_v8a.apk \
      --manifest manifest.json \
      --out-dir out \
      [--key key.pem --cert cert.crt]     # yoksa üretilir ve out-dir'e yazılır
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile

try:
    from sign_apk import keys as sa_keys
    from sign_apk import signer as sa_signer
    from sign_apk import verify as sa_verify
except ImportError as exc:  # pragma: no cover
    print(f"Eksik bağımlılık: {exc}\n  pip install lief 'git+https://github.com/adityatelange/sign-apk-py'",
          file=sys.stderr)
    raise SystemExit(2)

V1_SUFFIXES = (".SF", ".RSA", ".DSA", ".EC")
V1_NAMES = {"META-INF/MANIFEST.MF"}


def log(msg: str) -> None:
    print(f"[control] {msg}", flush=True)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_v1(src_apk: str, dst_apk: str) -> int:
    """v1 imza girdilerini atar, diğer her şeyi aynen kopyalar."""
    dropped = 0
    with zipfile.ZipFile(src_apk) as src, zipfile.ZipFile(dst_apk, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as dst:
        for info in src.infolist():
            name = info.filename
            if name in V1_NAMES or name.upper().endswith(V1_SUFFIXES):
                dropped += 1
                continue
            dst.writestr(info, src.read(name))
    return dropped


def write_xapk(out_path: str, members: list[tuple[str, str]]) -> None:
    """members: [(dosya_yolu, arşiv_içindeki_ad)]"""
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as xz:
        for src, arcname in members:
            if not os.path.exists(src):
                log(f"UYARI: {src} yok, atlandı")
                continue
            if arcname == "manifest.json":
                # 1980 öncesi zaman damgaları zipfile tarafından reddedilir
                info = zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(src, "rb") as fh:
                    xz.writestr(info, fh.read())
            else:
                xz.write(src, arcname)


def main() -> int:
    ap = argparse.ArgumentParser(description="Orijinal APK'ları yeniden imzala (içerik değişmez)")
    ap.add_argument("--base", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--out-dir", default="control")
    ap.add_argument("--key", default=None)
    ap.add_argument("--cert", default=None)
    ap.add_argument("--xapk-name", default="CubeCrafter_control.xapk")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    work = os.path.join(args.out_dir, "work")
    os.makedirs(work, exist_ok=True)
    problems: list[str] = []

    # --- 1) v1 imzaları temizle ---
    unsigned_base = os.path.join(work, "base.unsigned.apk")
    unsigned_split = os.path.join(work, "split.unsigned.apk")
    log(f"base  v1 temizliği: {strip_v1(args.base, unsigned_base)} girdi atıldı")
    log(f"split v1 temizliği: {strip_v1(args.split, unsigned_split)} girdi atıldı")

    # --- 2) anahtar ---
    if args.key and args.cert and os.path.exists(args.key) and os.path.exists(args.cert):
        km = sa_keys.load_pem(args.key, args.cert, None)
        log(f"anahtar kullanıldı: {args.key}")
    else:
        km = sa_keys.generate_debug_key(common_name="CubeCraft Mod Debug")
        key_path = os.path.join(args.out_dir, "cubecraft-mod.pem")
        cert_path = os.path.join(args.out_dir, "cubecraft-mod.crt")
        sa_keys.save_pem(km, key_path, cert_path)
        log(f"yeni anahtar üretildi: {key_path}")

    # --- 3) imzala (v2 + v3) ---
    signed_base = os.path.join(args.out_dir, os.path.basename(args.base))
    signed_split = os.path.join(args.out_dir, os.path.basename(args.split))
    sa_signer.sign_apk(unsigned_base, signed_base, km, v2=True, v3=True, min_sdk_version=None)
    sa_signer.sign_apk(unsigned_split, signed_split, km, v2=True, v3=True, min_sdk_version=None)
    log("iki APK imzalandı (v2+v3)")

    # --- 4) doğrula ---
    for path in (signed_base, signed_split):
        try:
            info = sa_verify.verify_apk(path)
            schemes = [k for k, v in info.items() if isinstance(v, dict) and v.get("verified")]
            log(f"doğrulandı: {os.path.basename(path)} → {schemes or info}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{path}: {exc}")
            log(f"DOĞRULAMA HATASI ({os.path.basename(path)}): {exc}")

    # --- 5) XAPK paketi ---
    xapk_path = os.path.join(args.out_dir, args.xapk_name)
    members = [(signed_base, os.path.basename(args.base)), (signed_split, os.path.basename(args.split))]
    if args.manifest:
        members.append((args.manifest, "manifest.json"))
    write_xapk(xapk_path, members)

    summary = {
        "kind": "control-resign",
        "note": "İçerik değişmedi; yalnızca yeniden imzalandı. Amaç: repack+imza testi.",
        "outputs": {"xapk": xapk_path, "base": signed_base, "split": signed_split},
        "xapk_sha256": sha256_of(xapk_path),
        "xapk_size": os.path.getsize(xapk_path),
        "problems": problems,
    }
    with open(os.path.join(args.out_dir, "control-summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    log(f"XAPK: {xapk_path} ({os.path.getsize(xapk_path)/1048576:.1f} MB) "
        f"sha256={summary['xapk_sha256'][:16]}…")
    log("bitti ✔" if not problems else "bitti (uyarılarla)")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
