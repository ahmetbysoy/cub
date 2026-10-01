#!/usr/bin/env python3
"""
patch_gadget.py — CubeCraft (IL2CPP) APK'larına frida-gadget gömüp Java'sız imzalar.

Ne yapar?
  1. Split APK'daki bir "taşıyıcı" kütüphaneye (varsayılan: libmain.so) DT_NEEDED
     girdisi ekler  →  uygulama açılırken gadget otomatik yüklenir (root gerekmez).
  2. Gadget .so dosyasını ve yapılandırmasını APK'ya ekler.
  3. Hem base hem split APK'yı **aynı** anahtarla yeniden imzalar (v2+v3).
  4. İmzalı parçaları tekrar bir XAPK arşivinde toplar.

Kullanım:
  python3 patch_gadget.py \
      --base com.cww.cubecraft.apk \
      --split config.arm64_v8a.apk \
      --gadget libfrida-gadget-raw.so \
      --out-dir patched

Notlar:
  * `sign_apk` paketi gerekir: pip install "git+https://github.com/adityatelange/sign-apk-py"
  * `lief` gerekir: pip install lief
  * Gadget varsayılan olarak 127.0.0.1:27042'yi dinler; config ile açıkça yazılır.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone

try:
    import lief
    from sign_apk import keys as sa_keys
    from sign_apk import signer as sa_signer
    from sign_apk import verify as sa_verify
except ImportError as exc:  # pragma: no cover
    print(f"Eksik bağımlılık: {exc}\n"
          "  pip install lief 'git+https://github.com/adityatelange/sign-apk-py'", file=sys.stderr)
    raise SystemExit(2)

V1_SIG_SUFFIXES = (".SF", ".RSA", ".DSA", ".EC")
V1_SIG_NAMES = {"META-INF/MANIFEST.MF"}

GADGET_CONFIG = {
    "interaction": {
        "type": "listen",
        "address": "127.0.0.1",
        "port": 27042,
        "on_port_conflict": "fail",
        "on_load": "resume",
    },
    "runtime": "v8",
}


def log(msg: str) -> None:
    print(f"[patch] {msg}", flush=True)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def patch_carrier_library(split_apk: str, carrier_name: str, gadget_basename: str, work_dir: str) -> bytes:
    """`lib/arm64-v8a/<carrier>` dosyasına DT_NEEDED girdisi ekler, yeni baytları döner."""
    with zipfile.ZipFile(split_apk) as zf:
        carrier_entry = next((n for n in zf.namelist()
                              if n.endswith(os.path.basename(carrier_name))), None)
        if carrier_entry is None:
            raise FileNotFoundError(f"{carrier_name} split içinde bulunamadı")
        data = zf.read(carrier_entry)

    src = os.path.join(work_dir, os.path.basename(carrier_entry))
    with open(src, "wb") as fh:
        fh.write(data)

    binary = lief.ELF.parse(src)
    if binary is None:
        raise RuntimeError(f"{carrier_entry} ELF olarak okunamadı")
    before = list(binary.libraries)
    if gadget_basename in before:
        log(f"{os.path.basename(carrier_entry)} zaten {gadget_basename} içeriyor")
    else:
        binary.add_library(gadget_basename)
    dst = os.path.join(work_dir, os.path.basename(carrier_entry) + ".patched")
    binary.write(dst)

    with open(dst, "rb") as fh:
        patched = fh.read()

    check = lief.ELF.parse(dst)
    libs = list(check.libraries)
    if gadget_basename not in libs:
        raise RuntimeError(f"DT_NEEDED eklenemedi; sonuç: {libs}")
    log(f"{os.path.basename(carrier_entry)}: DT_NEEDED {before} → {libs}")
    return patched


def rebuild_split(split_apk: str, out_apk: str, carrier_entry: str, patched_carrier: bytes,
                  gadget_so: bytes, gadget_basename: str) -> None:
    """Split APK'yı yeniden paketler: taşıyıcıyı değiştirir, gadget + config ekler, v1 imzaları atar."""
    lib_dir = os.path.dirname(carrier_entry)
    gadget_entry = f"{lib_dir}/{gadget_basename}"
    config_json = json.dumps(GADGET_CONFIG, indent=2).encode()
    config_entries = {
        # Paketleyiciler yalnızca `lib*.so` dosyalarını çıkardığı için iki adı da koyuyoruz.
        f"{lib_dir}/{gadget_basename.rsplit('.so', 1)[0]}.config.so": config_json,
        f"{lib_dir}/{gadget_basename.rsplit('.so', 1)[0]}.config.json": config_json,
    }

    dropped = 0
    with zipfile.ZipFile(split_apk) as src, zipfile.ZipFile(out_apk, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as dst:
        for info in src.infolist():
            name = info.filename
            if name in V1_SIG_NAMES or name.upper().endswith(V1_SIG_SUFFIXES):
                dropped += 1
                continue
            if name == carrier_entry:
                continue  # aşağıda yamalı sürümü yazıyoruz
            if name in config_entries or name == gadget_entry:
                continue
            dst.writestr(info, src.read(name))
        dst.writestr(carrier_entry, patched_carrier, compress_type=zipfile.ZIP_DEFLATED)
        dst.writestr(gadget_entry, gadget_so, compress_type=zipfile.ZIP_DEFLATED)
        for name, data in config_entries.items():
            dst.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    log(f"{os.path.basename(out_apk)} paketlendi (atılan v1 imza girdisi: {dropped})")


def sign_one(in_apk: str, out_apk: str, key_material, min_sdk: int | None = None) -> dict:
    result = sa_signer.sign_apk(in_apk, out_apk, key_material, v2=True, v3=True, min_sdk_version=min_sdk)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="CubeCraft APK'larına frida-gadget göm")
    ap.add_argument("--base", required=True, help="base APK (com.cww.cubecraft.apk)")
    ap.add_argument("--split", required=True, help="ABI split APK (config.arm64_v8a.apk)")
    ap.add_argument("--gadget", required=True, help="gadget .so (decompressed, arm64)")
    ap.add_argument("--out-dir", default="patched", help="çıktı dizini")
    ap.add_argument("--carrier", default="libmain.so", help="DT_NEEDED eklenecek taşıyıcı kütüphane")
    ap.add_argument("--gadget-name", default=None, help="APK içindeki gadget dosya adı (varsayılan: gadget soname)")
    ap.add_argument("--key", default=None, help="PEM özel anahtar (yoksa üretilir)")
    ap.add_argument("--cert", default=None, help="PEM sertifika")
    ap.add_argument("--xapk-name", default="CubeCrafter_patched.xapk", help="üretilecek XAPK adı")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    work_dir = os.path.join(args.out_dir, "work")
    os.makedirs(work_dir, exist_ok=True)

    gadget_basename = args.gadget_name
    if not gadget_basename:
        parsed = lief.ELF.parse(args.gadget)
        soname = parsed.get(lief.ELF.DynamicEntry.TAG.SONAME) if parsed else None
        gadget_basename = soname.name if soname else "libfrida-gadget-raw.so"
    log(f"gadget dosya adı: {gadget_basename}")

    with open(args.gadget, "rb") as fh:
        gadget_so = fh.read()
    log(f"gadget: {args.gadget} ({len(gadget_so)/1048576:.1f} MB)")

    # --- 1) taşıyıcı yaması ---
    patched = patch_carrier_library(args.split, args.carrier, gadget_basename, work_dir)
    carrier_entry = next(n for n in zipfile.ZipFile(args.split).namelist()
                         if n.endswith(os.path.basename(args.carrier)))

    # --- 2) split yeniden paketleme ---
    unsigned_split = os.path.join(work_dir, "config.unsigned.apk")
    rebuild_split(args.split, unsigned_split, carrier_entry, patched, gadget_so, gadget_basename)

    # --- 3) imzalama ---
    km = None
    if args.key and args.cert:
        km = sa_keys.load_pem(args.key, args.cert, None)
        log(f"anahtar: {args.key}")
    else:
        km = sa_keys.generate_debug_key(common_name="CubeCraft Mod Debug")
        key_path = os.path.join(args.out_dir, "cubecraft-mod.pem")
        cert_path = os.path.join(args.out_dir, "cubecraft-mod.crt")
        sa_keys.save_pem(km, key_path, cert_path)
        log(f"yeni hata ayıklama anahtarı üretildi: {key_path} / {cert_path}")
        log("  (güncelleme kurarken aynı anahtarı kullanın: --key/--cert)")

    signed_split = os.path.join(args.out_dir, os.path.basename(args.split))
    signed_base = os.path.join(args.out_dir, os.path.basename(args.base))
    sign_one(unsigned_split, signed_split, km)
    log(f"imzalandı: {os.path.basename(signed_split)}")
    sign_one(args.base, signed_base, km)
    log(f"imzalandı: {os.path.basename(signed_base)}")

    # --- 4) doğrulama ---
    problems = []
    for apk in (signed_split, signed_base):
        try:
            info = sa_verify.verify_apk(apk)
            schemes = [k for k, v in info.items() if isinstance(v, dict) and v.get("verified")]
            log(f"doğrulandı: {os.path.basename(apk)} → {schemes or info}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{apk}: {exc}")
            log(f"DOĞRULAMA HATASI ({os.path.basename(apk)}): {exc}")

    with zipfile.ZipFile(signed_split) as zf:
        names = zf.namelist()
        assert f"lib/arm64-v8a/{gadget_basename}" in names, "gadget APK'da yok!"
        assert carrier_entry in names
    log("split içeriği kontrol edildi (gadget + taşıyıcı yerinde)")

    # --- 5) XAPK paketi ---
    manifest_src = os.path.join(os.path.dirname(os.path.abspath(args.base)), "manifest.json")
    xapk_path = os.path.join(args.out_dir, args.xapk_name)
    with zipfile.ZipFile(xapk_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as xz:
        xz.write(signed_base, os.path.basename(signed_base))
        xz.write(signed_split, os.path.basename(signed_split))
        if os.path.exists(manifest_src):
            xz.write(manifest_src, "manifest.json")
        else:
            log("UYARI: manifest.json bulunamadı, XAPK'ya eklenmedi")

    log(f"XAPK: {xapk_path} ({os.path.getsize(xapk_path)/1048576:.1f} MB) sha256={sha256_of(xapk_path)[:16]}…")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gadget": {"file": args.gadget, "basename_in_apk": gadget_basename, "size": len(gadget_so),
                   "sha256": hashlib.sha256(gadget_so).hexdigest()},
        "carrier": carrier_entry,
        "config": GADGET_CONFIG,
        "outputs": {
            "xapk": xapk_path,
            "base": signed_base,
            "split": signed_split,
        },
        "signature": {"schemes": ["v2", "v3"]},
        "problems": problems,
    }
    with open(os.path.join(args.out_dir, "patch-summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    log("bitti ✔" if not problems else "bitti (uyarılarla) — patch-summary.json")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
