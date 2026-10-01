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
