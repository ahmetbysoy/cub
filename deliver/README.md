# CubeCraft 1.17.14 — gadget'lı (yamalı) paket

Bu dal, **sadece dosya dağıtımı** için kullanılan geçici bir daldır (repo geçmişiyle ilgisi yok).

## Ne var?

| Dosya | Boyut | Not |
| --- | --- | --- |
| `deliver/part-00` | 80 MiB | `CubeCrafter_patched.xapk` parçası 1/2 |
| `deliver/part-01` | 78,8 MiB | parça 2/2 |

Parçalar `CubeCrafter_patched.xapk` dosyasının bölünmüş hâlidir (166.497.613 bayt).
Birleştirilmiş dosyanın doğrulaması:

```
sha256: 191fc7260aaa6bc301d45d18d5e30d70ddf219b077088a0662e0fbc97e499e10
boyut : 166.497.613 bayt
```

## Ne içeriyor?

Play sürümüyle **birebir aynı** içerik + root gerektirmeyen Frida gadget:

1. `lib/arm64-v8a/libmain.so` → `DT_NEEDED libfrida-gadget-raw.so` eklendi
2. `lib/arm64-v8a/libfrida-gadget-raw.so` (Frida 17.19.0) + `127.0.0.1:27042` config eklendi
3. Base ve split APK aynı hata ayıklama anahtarıyla v2+v3 imzalandı
   (base APK'nın içeriği değişmedi — yalnızca imza bloğu)

Ayrıntı ve kurulum: `notes/install-gadget.md` (ana dala bakın).

## Tek dosya olarak indirmek

`patched-release` workflow'u (Actions) bu parçaları birleştirip bir **Release** oluşturur;
oradan tek dosya hâlinde indirilebilir.
