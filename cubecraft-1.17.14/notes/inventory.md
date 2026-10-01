# CubeCraft 1.17.14 — paket & varlık envanteri

> Yerel çalışma dizini: **`/home/user/out/cubecraft`** (snapshot dışı; ağır dosyalar burada tutulur).
> Bu klasörde yalnızca küçük metin notları saklanır.

## Paket kimliği

| Alan | Değer |
| --- | --- |
| Uygulama | CubeCraft / CubeCrafter |
| Yayıncı | SayGames Ltd (ücretsiz, tek oyunculu sandbox) |
| Paket adı | `com.cww.cubecraft` — sürüm 1.17.14 (versionCode 106) |
| SDK | min 26 / target 35, arm64-v8a |
| XAPK sha256 | `39150c787073b4f8a1931e3dc0c4d399d6f2f73472f6cda1c0f630f4effad8ac` (262.785.289 B) |

## Dosya yapısı (yerel çalışma dizininde)

```
out/cubecraft/
├── CubeCrafter_1.17.14_APKPure.xapk   251 MB  orijinal XAPK
├── apk/com.cww.cubecraft.apk          215 MB  base APK
├── apk/config.arm64_v8a.apk            26 MB  native split
├── extracted/base/                    248 MB  base APK açılmış (2825 dosya)
├── extracted/native/                   73 MB  split açılmış (26 dosya)
└── work/                                      monoscripts.txt, containers.txt
```

- base APK: `classes.dex` … `classes11.dex` (11 adet), `res/` 2511 dosya, `assets/` 143 MB
- native split: `libil2cpp.so` (44 MB), `libunity.so`, `libmain.so` + SDK kütüphaneleri

## Unity katmanı

- Motor: **Unity + IL2CPP**
- `assets/bin/Data/data.unity3d` — 112 MB ana varlık paketi
- `assets/bin/Data/Managed/Metadata/global-metadata.dat` — 8.2 MB IL2CPP meta verisi

Öne çıkan nesne sayıları (data.unity3d geneli):

| Tür | Adet | Tür | Adet |
| --- | --- | --- | --- |
| GameObject | 292.554 | Texture2D | 692 |
| Transform | 267.553 | AnimationClip | 673 |
| MeshRenderer | 238.886 | Material | 565 |
| MeshFilter | 238.357 | Sprite | 379 |
| MonoBehaviour | 56.120 | AudioClip | 304 |
| Animator | 3.499 | Mesh | 716 |

## Kod (IL2CPP)

`monoscripts.txt` içinde **3074 sınıf** kayıtlı. Assembly dağılımı (ilk sıralar):

| Assembly | Sınıf | Not |
| --- | --- | --- |
| Assembly-CSharp.dll | 717 | oyun kodu |
| Unity.VisualScripting.* | 831 | görsel betikleme |
| SayGames.Services.dll | 283 | yayıncı servisleri |
| Nakama.dll | 125 | çok oyunculu/backend istemcisi |
| Unity.ProBuilder.dll | 112 | seviye düzenleme |
| StompyRobot.SRDebugger.dll | 109 | hata ayıklama menüsü |
| SayKit.Internal.dll | 109 | SayGames SDK |

`Assembly-CSharp` namespace dağılımı: `MainGame` (276), `Shared` (100), `Quests` (49),
`GameUI` (42), `BridgeRace` (38), `Creatures` (22), `ShopOffers` (17), `MapMeta` (14), `AI` (8) …

## Üçüncü taraf SDK'lar (native kütüphanelerden)

AppLovin (+crash reporter), Crashlytics/Firebase, Moloco, Mintegral (`mbridge`), ByteDance/Pangle
(`libpglarmor`, `libbuffer_pgl`), Cronet (6.5 MB), TensorFlow Lite (GMS), Lofelt, APMInsight, `saykit_*`
yapılandırma dosyaları ve 11 dil için lokalizasyon dosyaları.
