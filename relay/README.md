# relay — GitHub runner yardımcı işleri

Bu klasör, sandbox'ın erişemediği işleri **GitHub Actions runner'ında** yaptırmak için
kullanılır (`.github/workflows/relay.yml` → `bash relay/run.sh`).

## İşler (`relay/job.txt`)

| İş | Ne yapar | Çıktı |
| --- | --- | --- |
| `control` | Orijinal XAPK'yı parçalardan birleştirir, APK'ları **içerik değiştirmeden** yeniden imzalar (v2+v3) | `control-1.17.14` Release'i (`CubeCrafter_control.xapk`) |
| `mod` | `libil2cpp.so`'ya statik yama uygular (`patches-mod1.json`), yeniden imzalar | `mod-1.17.14` Release'i (`CubeCrafter_mod1.xapk`) |
| `mod2` | Kümülatif yama: mod1 + reklam ödülü ×5 + reklam bonusları süresiz (`patches-mod2.json`) | `mod2-1.17.14` Release'i (`CubeCrafter_mod2.xapk`) |
| `mod3` | Kümülatif yama: mod2 + reklamsız anında ödül (`patches-mod3.json`) | `mod3-1.17.14` Release'i (`CubeCrafter_mod3.xapk`) |
| `dump` | `libil2cpp.so` + `global-metadata.dat` çıkarır, Il2CppDumper ile statik döküm alır | `analysis/dump` dalı (`dump.cs`, `script.json`, `stringliteral.json`, `il2cpp.h`) |

Tetikleme: `arena/01a0f685-cub` dalında `relay/**` altında bir değişiklik push etmek
(ör. `relay/trigger.txt` güncellemesi).

## Dosyalar

- `run.sh` — işleri yürüten script (girdileri `relay/cubecraft` dalındaki XAPK parçalarından üretir)
- `build_control.py` — yeniden imzalama + XAPK paketleme (Java gerekmez: `sign-apk-py`)
- `build_mod.py` + `patches-mod1..3.json` — statik IL2CPP yaması (her yamada "eski byte" doğrulaması yapılır;
  eşleşmezse build durur). Yama hedefleri ve anlamları için `notes/static-targets.md`.
- `keys/` — mod build'leri için kullanılan **tek kullanımlık hata ayıklama anahtarı**
  (sırrı yoktur; kontrol ve yamalı sürümlerin aynı anahtarla imzalanıp üst üste kurulabilmesi için repoda tutulur)
- `job.txt`, `trigger.txt` — iş listesi ve tetikleyici
