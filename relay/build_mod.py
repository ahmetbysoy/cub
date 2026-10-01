#!/usr/bin/env python3
"""
build_mod.py — Statik IL2CPP yaması uygular, yeniden imzalar ve XAPK üretir.

Fark: build_control.py içeriği değiştirmez; bu script libil2cpp.so içindeki
belirli adreslere önceden tanımlı byte yamalarını uygular (relay/patches-*.json)
ve sonucu aynı imza anahtarıyla (relay/keys/) imzalar. Böylece kontrol sürümünün
üstüne sorunsuz kurulabilir.

Güvenlik: her yama için "eski" byte dizisi dosyada doğrulanır; eşleşmezse
build durur (yanlış sürüme yama yapılmasını engeller).

Kullanım:
  python3 build_mod.py --base com.cww.cubecraft.apk --split config.arm64_v8a.apk \
      --manifest manifest.json --patches relay/patches-mod1.json \
      --out-dir out/mod1 --key relay/keys/cubecraft-mod.pem --cert relay/keys/cubecraft-mod.crt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_control import sha256_of, write_xapk  # noqa: E402  (aynı dizindeki yardımcılar)

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
    print(f"[mod] {msg}", flush=True)


def is_v1(name: str) -> bool:
    return name in V1_NAMES or name.upper().endswith(V1_SUFFIXES)


def hx(s: str) -> bytes:
    return bytes.fromhex(s.replace(" ", ""))


def apply_patches(so_bytes: bytes, patches: list[dict]) -> bytes:
    buf = bytearray(so_bytes)
    for p in patches:
        off = int(p["off"], 16)
        old, new = hx(p["old"]), hx(p["new"])
        if len(old) != len(new):
            raise SystemExit(f"yama boyu uyuşmuyor: {p['desc']}")
        cur = bytes(buf[off:off + len(old)])
        if cur != old:
            raise SystemExit(
                f"DOĞRULAMA HATASI: {p['desc']} @{p['off']}\n"
                f"  beklenen: {old.hex(' ')}\n  bulunan : {cur.hex(' ')}")
        buf[off:off + len(new)] = new
        log(f"yama uygulandı: {p['desc']} @{p['off']} ({len(new)} bayt)")
    return bytes(buf)


def repack_split(src_apk: str, dst_apk: str, entry: str, new_data: bytes) -> int:
    """v1 imzalarını atar; `entry` girdisini new_data ile değiştirir; kalanı aynen kopyalar."""
    replaced = 0
    with zipfile.ZipFile(src_apk) as src, zipfile.ZipFile(dst_apk, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as dst:
        for info in src.infolist():
            if is_v1(info.filename):
                continue
            data = src.read(info.filename)
            if info.filename == entry:
                data = new_data
                replaced = 1
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            dst.writestr(zi, data)
    if not replaced:
        raise SystemExit(f"girdi bulunamadı: {entry}")
    return replaced


def main() -> int:
    ap = argparse.ArgumentParser(description="Statik IL2CPP yaması + yeniden imza")
    ap.add_argument("--base", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--patches", required=True)
    ap.add_argument("--out-dir", default="mod")
    ap.add_argument("--key", default=None)
    ap.add_argument("--cert", default=None)
    ap.add_argument("--xapk-name", default="CubeCrafter_mod1.xapk")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    work = os.path.join(args.out_dir, "work")
    os.makedirs(work, exist_ok=True)
    problems: list[str] = []

    spec = json.load(open(args.patches, encoding="utf-8"))
    entry = "lib/arm64-v8a/libil2cpp.so"
    log(f"yama dosyası: {args.patches} ({len(spec['targets'])} hedef, sabit {spec['value']})")

    # --- 1) .so oku, yamala, doğrula ---
    with zipfile.ZipFile(args.split) as z:
        so = z.read(entry)
    import hashlib
    log(f"libil2cpp.so: {len(so)} bayt · sha256={hashlib.sha256(so).hexdigest()[:16]}…")
    patched = apply_patches(so, spec["targets"])

    # yamaların gerçekten yerinde olduğunu tekrar oku
    for p in spec["targets"]:
        off = int(p["off"], 16)
        got = patched[off:off + len(hx(p["new"]))]
        if got != hx(p["new"]):
            problems.append(f"yama yerinde değil: {p['desc']}")
    log("yama doğrulaması: " + ("TAMAM" if not problems else "HATA"))

    # --- 2) APK'ları yeniden paketle (v1 temizliği + .so değişimi) ---
    from build_control import strip_v1
    unsigned_base = os.path.join(work, "base.unsigned.apk")
    unsigned_split = os.path.join(work, "split.unsigned.apk")
    log(f"base  v1 temizliği: {strip_v1(args.base, unsigned_base)} girdi atıldı")
    repack_split(args.split, unsigned_split, entry, patched)
    log("split yeniden paketlendi (libil2cpp.so yamalı)")

    # --- 3) anahtar ---
    if args.key and args.cert and os.path.exists(args.key) and os.path.exists(args.cert):
        km = sa_keys.load_pem(args.key, args.cert, None)
        log(f"anahtar kullanıldı: {args.key}")
    else:
        km = sa_keys.generate_debug_key(common_name="CubeCraft Mod Debug")
        sa_keys.save_pem(km, os.path.join(args.out_dir, "cubecraft-mod.pem"),
                         os.path.join(args.out_dir, "cubecraft-mod.crt"))
        log("yeni anahtar üretildi")

    # --- 4) imzala + doğrula ---
    signed_base = os.path.join(args.out_dir, os.path.basename(args.base))
    signed_split = os.path.join(args.out_dir, os.path.basename(args.split))
    sa_signer.sign_apk(unsigned_base, signed_base, km, v2=True, v3=True, min_sdk_version=None)
    sa_signer.sign_apk(unsigned_split, signed_split, km, v2=True, v3=True, min_sdk_version=None)
    log("iki APK imzalandı (v2+v3)")
    for path in (signed_base, signed_split):
        try:
            info = sa_verify.verify_apk(path)
            schemes = [k for k, v in info.items() if isinstance(v, dict) and v.get("verified")]
            log(f"doğrulandı: {os.path.basename(path)} → {schemes or info}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{path}: {exc}")
            log(f"DOĞRULAMA HATASI ({os.path.basename(path)}): {exc}")

    # --- 5) imzalı APK'dan .so'yu geri oku ve yamaları doğrula ---
    with zipfile.ZipFile(signed_split) as z:
        so_back = z.read(entry)
    for p in spec["targets"]:
        off = int(p["off"], 16)
        if so_back[off:off + len(hx(p["new"]))] != hx(p["new"]):
            problems.append(f"imzalı pakette yama kayıp: {p['desc']}")
    log("imzalı paket içi yama kontrolü: " + ("TAMAM" if not problems else "HATA"))

    # --- 6) XAPK ---
    xapk_path = os.path.join(args.out_dir, args.xapk_name)
    members = [(signed_base, os.path.basename(args.base)), (signed_split, os.path.basename(args.split))]
    if args.manifest:
        members.append((args.manifest, "manifest.json"))
    write_xapk(xapk_path, members)

    summary = {
        "kind": spec.get("name", "mod"),
        "note": "Statik IL2CPP yaması: para/bilet/elmas sabit değere sabitlendi.",
        "value": spec["value"],
        "patches": spec["targets"],
        "so_sha256": hashlib.sha256(patched).hexdigest(),
        "outputs": {"xapk": xapk_path, "base": signed_base, "split": signed_split},
        "xapk_sha256": sha256_of(xapk_path),
        "xapk_size": os.path.getsize(xapk_path),
        "problems": problems,
    }
    with open(os.path.join(args.out_dir, "mod-summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    log(f"XAPK: {xapk_path} ({summary['xapk_size']/1048576:.1f} MB) sha256={summary['xapk_sha256'][:16]}…")
    log("bitti ✔" if not problems else "bitti (uyarılarla)")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
