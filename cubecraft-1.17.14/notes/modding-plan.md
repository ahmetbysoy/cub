# CubeCraft 1.17.14 — oyun içi değerleri değiştirme planı (araştırma)

> Kapsam: tek oyunculu, ücretsiz bir oyunun **kendi cihazımızdaki kopyasında** değer oynama.
> Modifiye APK dağıtımı yok; Not: bu işlem oyunun kullanım koşullarına (ToS) aykırı olabilir ve
> hesap riski taşır — karar kullanıcıya aittir.

## 1) Teknik tespitler

| Konu | Bulgu |
| --- | --- |
| Motor | Unity + IL2CPP, metadata sürümü **31**, `global-metadata.dat` şifresiz (okunabiliyor) |
| Anti-tamper | **Yok.** `libsigner.so` = Adjust SDK imza yardımcısı (`NativeLibHelper_nSign`), APK imza doğrulaması değil |
| Anti-frida | **Yok.** `libil2cpp.so` içindeki "Frida" eşleşmeleri "Friday" (hafta adları) |
| Kök / emülatör kontrolü | İz bulunamadı (magisk/xposed/jailbreak taramaları yok) |
| Bütünlük kontrolü | İz yok (safetynet/play integrity kodu yok) |
| Ekonomi | Hem yerel hem sunucu tarafı izleri var → karışık model |

### Ekonomi: yerel mi, sunucu mu?

**Yerel tarafta olanlar (değiştirilebilir):**
`MainGame.PlayerMoneyController`, `Shared.UI.FlyingMoneyController`, `GemsMath.GemsMathController`,
`Saves.SavesController`, `MainGame.GameSaveData`, `MainGame.ItemsCountSaveData`,
`Shared.PlayerPrefsIntValue/BoolValue/StringValue`, `Quests.QuestsSaveLoadController`,
`MainGame.Rewarded.RewardedController` (reklam ödülleri), `ShopOffers.*`

**Sunucu tarafı (Nakama) uçları:**
`/v1/user/money`, `/v1/trade/resources`, `/v1/lives`, `/v1/offers/generate`, `/v1/storage/keys`,
`/v1/user_quests`, `/v1/leaderboards`, `giveaways_resources/claim` …

→ Yorum: reklam/ödül ve tek oyunculu ilerleme büyük olasılıkla **yerel + bulut kayıt (cloud save)**
senkronizasyonu; **takas/hediye/etkinlik** değerleri sunucuya bağlı. Yerel değerleri değiştirmek
mümkün, ancak **oyun sunucuya bağlandığında bulut kayıt üzerine yazabilir** — test edilerek
doğrulanacak bir konudur (uçak modu / hesap bağlamama ile test edilmeli).

## 2) Yöntemler

| # | Yöntem | Root | Kalıcılık | Not |
| --- | --- | --- | --- | --- |
| A | **Runtime hook (Frida)** | Gerekmez* | Oturumluk | En esnek: canlı değer değiştirme, metodun ne döndürdüğünü izleme, oyunun kendi metodunu çağırma |
| B | **Statik yama** | Gerekmez* | Kalıcı | A ile RVA bulunur → `lief`+`keystone` ile `libil2cpp.so` yamanır → APK yeniden imzalanır |
| C | Kayıt dosyası düzenleme | **Gerekir** | Kalıcı | `shared_prefs/*.xml` veya `files/` içindeki kayıtlar |

\* Root yoksa: APK'ya `frida-gadget` gömülür (LIEF ile `DT_NEEDED` ekleme veya gadget'ı kütüphane
olarak paketleme) ve yeniden imzalanır. Split APK olduğu için **her iki parça da** aynı anahtarla
imzalanmalı ve `adb install-multiple` veya SAI ile kurulmalıdır.
Root varsa: `frida-server` yeterli — repack/imza yok.

## 3) Termux mini-server mimarisi (önerilen)

```
┌─ Android telefon ───────────────────────────────────────────────┐
│  CubeCraft (gadget gömülü, yeniden imzalı)                      │
│      └─ frida-gadget  →  127.0.0.1:27042 (listen)               │
│                                                                 │
│  Termux → Ubuntu (proot-distro)                                 │
│   ├─ python3 server.py  (bu depo: cubecraft-1.17.14/server)     │
│   │    ├─ frida ile gadget'a bağlanır                           │
│   │    ├─ dist/index.js (frida-il2cpp-bridge) + agent.js yükler │
│   │    └─ http://127.0.0.1:8080 → tarayıcıdan kontrol paneli    │
│   └─ (opsiyonel) statik yama + sign-apk-py ile imzalama         │
└─────────────────────────────────────────────────────────────────┘
```

Panelden yapılabilenler: sınıf/metod arama, bir metodun dönüş değerini canlı izleme (log),
"şu metodu sabit değer döndür" gibi mod şablonları, oyunun kendi metodunu çağırma
(ör. para ekleme metodu), tüm modları aç/kapat, log akışı.

## 4) Araç zinciri (sandbox'ta kuruldu ve doğrulandı)

| Araç | Sürüm | Rol |
| --- | --- | --- |
| `frida` (Python) | 17.19.0 | cihaza bağlanma, ajan yükleme |
| `frida-il2cpp-bridge` | 0.14.0 | IL2CPP'yi runtime'da çözümleme — **derleme gerekmez**, `dist/index.js` tek dosya ve `globalThis.Il2Cpp` tanımlıyor |
| `lief` | 1.0 | ELF yamalama, `DT_NEEDED` ekleme, APK yeniden paketleme |
| `keystone` / `capstone` | 0.9.2 / 5.0.7 | ARM64 assembly ↔ makine kodu (statik yama) |
| `sign-apk-py` | git | **Java'sız** APK imzalama (v2/v3/v4, zipalign gerekmez) |
| Termux `apksigner` | — | Termux paketi (`pkg install apksigner`), yedek yol |
| `node` + `npm` | 22 / 10 | (isteğe bağlı) `frida-il2cpp-bridge` paketini indirmek için |

Not: IL2CPP statik dökümcüler (Il2CppDumper vb.) bu yapıda sendeletildi — Python portu
(`Il2CppDumper-Python`) v31 yapısında `invokerPointers` sayısını yanlış okuyup çöküyor.
Bu yüzden **RVA/offset bilgisini cihaz üstü Frida dökümünden** almak daha güvenilir
(`Il2Cpp.Method.relativeVirtualAddress`).

## 5) Yol haritası

1. **Hedef seç** (para/elmas, bekleme süreleri, reklam ödülü, kilitli içerik…).
2. **Bağlantı kur**: root → `frida-server`; root yok → gadget gömme + imza.
3. **Keşif**: panelden anahtar kelimeyle sınıf/metod ara (ör. "Money"), dökümü al.
4. **Doğrula**: metodu izle, çağrı sıklığını ve dönen değeri gör (yerel mi sunucu mu?).
5. **Modla**: hazır şablonlarla (sabit dönüş, çarpan, no-op) veya oyunun kendi metodunu çağırarak.
6. **Test**: çevrimdışı/çevrimiçi davranış ve bulut kayıt etkisini gözle.
7. (Opsiyonel) **Statik yamaya çevir** → kalıcı mod, Frida'sız oyna.

## 6) Riskler ve dikkat

- Bulut kayıt (Nakama/Play Games) modifiye değerleri sunucuya yazabilir veya sıfırlayabilir.
- Yeniden imzalama → Play Games oturumu/hesap bağlama davranışı değişebilir.
- Reklam ödülleri SDK tarafında doğrulanıyorsa sunucu reddedebilir.
- Oyun güncellemeleri offsetleri değiştirir (statik yama kırılır; runtime hook isim tabanlı olduğu için dayanıklıdır).
