# CubeCraft 1.17.14 — çalışma alanı

APKPure'dan indirilen `CubeCrafter_1.17.14_APKPure.xapk` paketinin yerel çalışma kopyası.
İndirme, GitHub Actions üzerinden çalışan geçici `relay` aktarımıyla yapıldı (sandbox doğrudan
`data.winudf.com`'a erişemiyor).

## Dosyalar

| Dosya | Boyut | Not |
| --- | --- | --- |
| `CubeCrafter_1.17.14_APKPure.xapk` | 262.785.289 B | sha256 `39150c787073b4f8a1931e3dc0c4d399d6f2f73472f6cda1c0f630f4effad8ac` |
| `com.cww.cubecraft.apk` | 225 MB | base APK — Unity IL2CPP + 11 adet `classesN.dex` |
| `config.arm64_v8a.apk` | 26 MB | native kütüphaneler: `libil2cpp.so` (44 MB), `libunity.so`, reklam SDK'ları |
| `manifest.json` | 3.1 KB | XAPK manifesti (sürüm, split listesi) |

## Paket bilgisi

- Paket: `com.cww.cubecraft` · Sürüm: 1.17.14 (versionCode 106) · minSdk 26 / targetSdk 35
- Motor: **Unity + IL2CPP**
  - `assets/bin/Data/Managed/Metadata/global-metadata.dat` (8.2 MB) — IL2CPP meta verisi
  - `lib/arm64-v8a/libil2cpp.so` (44 MB) — derlenmiş oyun kodu
  - `assets/bin/Data/data.unity3d` (112 MB) — ana Unity varlık paketi
- Oyun dışı: `res/` (2511 dosya), reklam/analitik SDK'ları (AppLovin, Moloco, Crashlytics, …)

## Git notu

GitHub'ın **100 MB'lık tek dosya sınırı** nedeniyle `*.xapk` ve `*.apk` dosyaları bu repoya
push edilemez; `.gitignore` ile hariç tutulmuştur ve yalnızca yerelde tutulur. Repoda yalnızca
küçük metin dosyaları (manifest, notlar, betikler, yama/patch çıktıları) saklanmalıdır.
