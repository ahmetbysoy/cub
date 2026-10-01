# CubeCraft 1.17.14 — statik yama hedefleri (libil2cpp.so)

Kaynak: `analysis/dump` dalındaki `dump.cs` (Il2CppDumper v6.7.46, metadata v31, il2cpp v29 olarak algılandı).
`Offset` = dosya içi konum (RVA ile aynı görünüyor). Tüm adresler libil2cpp.so içindeki **Offset** değerleridir.

## 1. Para (soft currency)

| Sınıf | Metot | Offset |
|---|---|---|
| MainGame.PlayerMoneyController | `get_MoneyCount()` | `0x1DC3728` |
| MainGame.PlayerMoneyController | `set_MoneyCount(int)` | `0x1DC3730` |
| MainGame.PlayerMoneyController | `AddMoney(int,string,bool)` | `0x1DC37BC` |
| MainGame.PlayerMoneyController | `SubstractMoney(int,string)` | `0x1DC3848` |

- Backing field `<MoneyCount>k__BackingField` nesne başına `+0x18`.
- Basit strateji: `get_MoneyCount` → sabit büyük değer döndür (`mov w0,#...; ret`), `set_MoneyCount` →
  gelen değeri yoksay, hep büyük değer yaz. Böylece hem gösterge hem satın alma kontrolleri geçer.

## 2. Bilet (tickets)

| Sınıf | Metot | Offset |
|---|---|---|
| MainGame.RewardedTicketsController | `get_TicketsCount()` | `0xAF44B4` |
| MainGame.RewardedTicketsController | `set_TicketsCount(int)` | `0xAF44BC` |
| (aynı sınıf) | `get_RewardMultiplier()` | `0xAF3B34` |

## 3. Elmas (premium currency) — ödül üzerinden

| Sınıf | Metot | Offset |
|---|---|---|
| GemsMath.GemsMathController | `GetLevelReward(LevelInfo)` | `0xCFFE80` |
| GemsMath.GemsMathController | `GetQuestsTotalReward(LevelInfo)` | `0xCFFFE0` |

- Bu ikisi seviye bitince/görev tamamlanınca verilecek elması hesaplar → sabit büyük değer döndürmek
  doğrudan elmas kazandırır. (Elmas bakiyesi ayrı bir “gems count” alanı olabilir; ilk turda
  bu iki ödül fonksiyonu yamanacak, sonuç görülünce bakiye fonksiyonu ayrıca aranacak.)

## 4. Reklam ödülü çarpanı / çarpanlar

| Sınıf | Metot | Offset |
|---|---|---|
| MainGame.DropItemConfig | `GetActiveBiomSoftCurrencyMultiply()` | `0x1BDCA60` |
| (Rewarded*) | `get_RewardMultiplier()` | `0xAF3B34` |
| (…) | `get_Multiplier()` | `0xFE2E10` |
| (…) | `get_SpeedMultiplier()` (float) | `0xFE6318` |

## 5. Kilit / açma

| Sınıf | Metot | Offset |
|---|---|---|
| (Thing UI bloğu) | `get_IsLocked()` / `set_IsLocked(bool)` | `0x1DCFDB4` / `0x1DCFDBC` |
| (…) | `IsLocked` alanı `+0x44` | — |

Kilit mantığı birden çok yere dağılmış görünüyor; ilk turda riskli, sonraki turlara bırakıldı.

## Yama tekniği (planlanan)

1. `script.json`'dan hedef metotların RVA'larını doğrula (RVA → dosya offset dönüşümü: `.so` program
   header'ları; pratikte offset == RVA çıktı, yine de LIEF ile doğrulanacak).
2. LIEF ile `.so`'ya yeni bir segment/bölüm ekle (code cave) → yamalarımızı oraya yaz.
3. Hedef metot gövdesinin başına `ldr x16, #8; br x16; .quad <cave_adresi>` yaz (8 bayt hizalı dallanma).
4. Yeni bölümü eklerken `p_align` değerini sayfa hizasına (0x1000) ayarla → 16 KB sayfa cihazlarda da OK.
5. XAPK'yı yeniden paketle + `relay/keys/cubecraft-mod.*` ile v2+v3 imzala + Release'e yükle.

## İlk mod (öneri)

- Para: `get_MoneyCount` + `set_MoneyCount`
- Bilet: `get_TicketsCount`
- Elmas: `GetLevelReward` + `GetQuestsTotalReward`
- (onay gelirse) reklam çarpanı: `get_RewardMultiplier`, `GetActiveBiomSoftCurrencyMultiply`

---

## Uygulanan sürüm: mod1 (yayınlandı)

Sabit değer: **9.961.472** (`0x00980000` — tek komutla yazılabilen ~10 milyon değeri).
Yama tanımı: `relay/patches-mod1.json` · build: `relay/build_mod.py` · Release: `mod-1.17.14`

| # | Adres | Değişiklik | Anlam |
|---|---|---|---|
| 1 | `0x1DC3728` | `ldr w0,[x0,#0x18]; ret` → `mov w0,#0x980000; ret` | Para göstergesi/kontrolleri hep 9.961.472 görür |
| 2 | `0x1DC3800` | `ldr w1,[x23,#0x18]` → `mov w1,#0x980000` | Para değişim olayı sabit değeri yayınlar (arayüz 0 göstermez) |
| 3 | `0x1DC38EC` | `ldr w1,[x21,#0x18]` → `mov w1,#0x980000` | Harcama sonrası da arayüz sabit değeri gösterir |
| 4 | `0xAF44B4` | `ldr w0,[x0,#0x20]; ret` → `mov w0,#0x980000; ret` | Bilet sayısı hep 9.961.472 |
| 5 | `0xCFFE80` | gövde → `mov w0,#0x980000; ret` | Seviye bitişi elmas ödülü sabit |
| 6 | `0xCFFF30` | gövde → `mov w0,#0x980000; ret` | Görev elmas ödülü sabit |

Toplam değişen byte: 44 MB'lık `libil2cpp.so` içinde **30 bayt** (yalnızca yukarıdaki 6 nokta).
Doğrulama: yamalı `libil2cpp.so` sha256 = `06fe14cbffc8d7fe600487f229cf7be89787e7ed4ce5b50970ebe1946e2b054d`
(CI çıktısı ile birebir aynı). İmza: v2+v3, `CN=CubeCraft Mod Debug` (kontrol sürümüyle aynı anahtar).

---

## Uygulanan sürüm: mod2 (yayınlandı)

`relay/patches-mod2.json` = mod1 yamaları (6 hedef) **+** aşağıdaki 3 yeni hedef (kümülatif).
Release: `mod2-1.17.14` · yamalı `libil2cpp.so` sha256 = `8537e51dbdf3b0ea15f0c3e88c260b7ea8ea347888a87e487af40c2df7fee8d4`

| # | Adres | Değişiklik | Anlam |
|---|---|---|---|
| 7 | `0xAF3B34` | gövde → `mov w0,#5; ret` | Reklam izleme ödülü **×5** (`RewardedRemoteInfo.RewardsMultiply` yerine sabit) |
| 8 | `0xFE3F4C` | `ldrb w0,[x0,#0x20]` → `mov w0,#1; ret` | `BaseAspect.IsInfinite` → **true** (tüm reklam bonusları "sonsuz") |
| 9 | `0xFE26D4` | gövde → `mov w0,#0; ret` | `BaseAspect.IsFinished` → **false** (bonus süresi hiç bitmez) |

Kapsam: sırt çantası (Backpack), büyülü aletler (EnchantedTools), binek hayvanı (RidingAnimal),
ekstra çiftçiler (SeveralFarmers) ve fabrika hızlandırma (SpeedUpSeveralFactories) — hepsi
`BaseAspect` tabanlı olduğu için tek noktadan kapsanır.

Not: Kilitli içerik (eşya/yükseltme/hayvan) oyunda ağırlıkla **para ve elmas** ile açılır; mod1'in
sabit para/elmas değerleriyle bu kilitler pratikte kalkar. Kalan gerçek kilit: biyom/seviye ilerlemesi
(`LevelsController.FindLastLevel` + PlayerPrefs anahtarı `BMS_CLDKN`) — riskli olduğu için yamalanmadı.
