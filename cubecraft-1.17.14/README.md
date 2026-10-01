# CubeCraft 1.17.14 — çalışma alanı

APKPure'dan indirilen `CubeCrafter_1.17.14_APKPure.xapk` paketinin yerel çalışma kopyası.
İndirme, GitHub Actions üzerinden çalışan geçici `relay` aktarımıyla yapıldı (sandbox doğrudan
`data.winudf.com`'a erişemiyor).

## Dosyalar

| Nerede | Ne |
| --- | --- |
| `/home/user/out/cubecraft/` | ağır dosyalar (XAPK, APK'lar, açılmış ağaçlar). Snapshot ve git dışında tutulur. |
| `cubecraft-1.17.14/manifest.json` | XAPK manifesti (sürüm, split listesi) |
| `cubecraft-1.17.14/notes/inventory.md` | paket, Unity ve kod envanteri |

Ağır dosyaların ayrıntılı yerleşimi ve boyutları için `notes/inventory.md` dosyasına bakın.

## Paket bilgisi

- Paket: `com.cww.cubecraft` · Sürüm: 1.17.14 (versionCode 106) · minSdk 26 / targetSdk 35
- Motor: **Unity + IL2CPP**
  - `assets/bin/Data/Managed/Metadata/global-metadata.dat` (8.2 MB) — IL2CPP meta verisi
  - `lib/arm64-v8a/libil2cpp.so` (44 MB) — derlenmiş oyun kodu
  - `assets/bin/Data/data.unity3d` (112 MB) — ana Unity varlık paketi
- Oyun dışı: `res/` (2511 dosya), reklam/analitik SDK'ları (AppLovin, Moloco, Crashlytics, …)

## Git notu

GitHub'ın **100 MB'lık tek dosya sınırı** nedeniyle `*.xapk` ve `*.apk` dosyaları repoya
push edilemez; ağır dosyalar `/home/user/out/cubecraft` altında (snapshot dışı) tutulur ve
`.gitignore` ile hariç bırakılır. Repoda yalnızca küçük metin dosyaları (manifest, notlar,
betikler, yama/patch çıktıları) saklanır.
