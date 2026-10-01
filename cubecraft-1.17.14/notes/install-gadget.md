# Yamalı APK kurulumu (root'suz Frida gadget)

Bu belge, `tools/patch_gadget.py` ile üretilen **gadget gömülü** XAPK'nın telefona nasıl
kurulacağını ve panelin nasıl çalıştırılacağını anlatır.

## Üretilen dosyalar

| Dosya | Ne |
| --- | --- |
| `patched/CubeCrafter_patched.xapk` | Kurulacak paket (base + config + gadget) — 159 MB |
| `patched/com.cww.cubecraft.apk` | Yeniden imzalı base APK (içerik birebir aynı, yalnızca imza değişti) |
| `patched/config.arm64_v8a.apk` | Yeniden imzalı split (gadget + DT_NEEDED yaması burada) |
| `patched/cubecraft-mod.pem` / `.crt` | İmzalama anahtarı — **sakla**, güncelleme yaparken aynısı gerekir |
| `patched/patch-summary.json` | Üretim özeti (hash'ler, config, imza şemaları) |

Yapılan değişiklikler:
1. `lib/arm64-v8a/libmain.so` dosyasına `DT_NEEDED libfrida-gadget-raw.so` eklendi → oyun
  açılırken gadget otomatik yükleniyor.
2. `lib/arm64-v8a/libfrida-gadget-raw.so` (Frida 17.19.0, arm64) eklendi.
3. `libfrida-gadget-raw.config.so` / `.config.json` eklendi → `127.0.0.1:27042` dinleme modu.
4. Her iki APK aynı hata ayıklama anahtarıyla **v2+v3** imzalandı (eski `META-INF/BNDLTOOL.*`
  imzaları kaldırıldı).

### Üretim sonrası doğrulamalar (bu depoda çalıştırıldı)

| Kontrol | Sonuç |
| --- | --- |
| `libmain.so` DT_NEEDED | `[…] → ['libfrida-gadget-raw.so', 'liblog.so', 'libm.so', 'libdl.so', 'libc.so']` ✔ |
| Split içeriği | gadget + `.config.so` + `.config.json` eklendi; yalnızca `libmain.so` değişti ✔ |
| Base APK içeriği | **0 girdi değişti**, `classes.dex`/`AndroidManifest.xml` birebir aynı, zip sağlam ✔ |
| İmzalar | iki APK da v2+v3, aynı sertifika (`CN=CubeCraft Mod Debug`) ✔ |
| XAPK | base + split + `manifest.json` (orijinaliyle birebir) ✔ |

## 1) Kurulum

**Önemli:** İmza değiştiği için Play Store sürümüyle yan yana kurulamaz; önce onu kaldırman
gerekir (bulut kaydın varsa geri yüklenebilir).

**a) SAI (Split APKs Installer) ile — telefonda:**
1. `CubeCrafter_1.17.14_gadget.xapk` dosyasını indir.
2. SAI → *Install APKs/XAPK* → dosyayı seç → kur.

**b) adb ile — bilgisayardan:**
```bash
adb install-multiple -r com.cww.cubecraft.apk config.arm64_v8a.apk
```

## 2) Panelin çalıştırılması (Termux)

```bash
pkg install python proot-distro
proot-distro install ubuntu && proot-distro login ubuntu
apt update && apt install -y python3 python3-pip unzip
pip install --break-system-packages frida          # frida 17.x

# repodan panel klasörünü al (özel depo/gizli depo gerekmez)
#   cubecraft-1.17.14/server/  →  ~/panel
termux-wake-lock
```

Node/npm gerekmez: `frida-il2cpp-bridge` derlenmiş hâli depoda (`server/vendor/…js`).

```bash
cd ~/panel
python3 server.py --host 127.0.0.1:27042 --target Gadget
# → Panel: http://127.0.0.1:8080
```

Telefonun tarayıcısından `http://127.0.0.1:8080` adresini aç, ya da aynı ağdaki
bilgisayardan `http://<telefon-ip>:8080` ile bağlan.

**Sıra önemli:** Önce paneli başlatıp "bağlı değil" durumunu gör, sonra oyunu aç
(gadget 27042'de dinlemeye başlar; sunucu bağlanınca ajan yüklenir). Ya da önce oyunu açıp
panelin "Yenile" düğmesine bas.

## 3) Ne yapabilirsin?

- Sınıf/metod ara: `Money`, `Gems`, `Rewarded`, `Save`, `Timer`, `Chest`
- Bir metodun dönüşünü izle (yerel mi, sunucu mu geldiğini gör)
- "Sabit döndür" / "×N çarp" şablonlarıyla modla
- `/api/invoke` ile oyunun kendi metodlarını çağır (ör. para ekleme metodu)
- **Döküm al**: “Döküm al” bölümünden `Assembly-CSharp.dll` → `server/dumps/*.json` dosyasını
  indir. Bu dosya, sınıf/metod adlarının tam listesini içerir; kesin mod şablonları bu dökümden
  yazılır (panelden tek tıkla kurulabilecek şekilde).

## 4) Geri alma

- Uygulamayı kaldır, Play Store'dan temiz sürümü kur. Cihazda kalıcı bir değişiklik
  bırakılmaz (her şey APK'nın içinde).
- Sorun çıkarsa: `patched/cubecraft-mod.pem` ile aynı anahtarı kullanarak yeniden
  yamalayıp kurabilirsin (`tools/patch_gadget.py --key … --cert …`), böylece veri kaybı olmaz.

## 5) Kendi paketini üretmek

```bash
pip install lief "git+https://github.com/adityatelange/sign-apk-py"
python3 tools/patch_gadget.py \
    --base   com.cww.cubecraft.apk \
    --split  config.arm64_v8a.apk \
    --gadget libfrida-gadget.so \
    --out-dir patched --key patched/cubecraft-mod.pem --cert patched/cubecraft-mod.crt
```

Gadget ikilisi: `server/gadget/frida-gadget-17.19.0-android-arm64.so.xz` (depoda, hash'i
`SHA256SUMS.txt` ile doğrulanabilir) → `unxz` ile açınca `libfrida-gadget.so`.
