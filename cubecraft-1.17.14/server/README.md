# CubeCraft mini panel (prototip)

Termux/Ubuntu üzerinde çalışan, oyun içi değerleri **canlı** kurcalamak için küçük bir
Frida + Python kontrol paneli. Cihazda derleme gerekmez: `frida-il2cpp-bridge` paketinin
hazır `dist/index.js` dosyası doğrudan yüklenir.

```
cubecraft-1.17.14/server/
├── server.py                  # HTTP panel + Frida köprüsü
├── agent/il2cpp_agent.js      # RPC ajanı (ara, izle, sabitle, çağır)
└── README.md
```

## 1) Kurulum (Termux → Ubuntu)

```bash
# Termux
pkg install python nodejs proot-distro
proot-distro install ubuntu && proot-distro login ubuntu

# Ubuntu (proot) içinde
apt update && apt install -y python3 python3-pip nodejs npm
pip install frida                      # (Debian'da gerekirse: --break-system-packages)
mkdir -p ~/panel && cd ~/panel
# server.py ve agent/ klasörünü buraya kopyalayın (repo’dan)
npm i frida-il2cpp-bridge             # dist/index.js buradan gelir
termux-wake-lock                       # arka planda öldürülmesin (Termux tarafı)
```

Alternatif: node kullanmak istemezseniz `dist/index.js` dosyasını başka bir yerden kopyalayıp
`--bridge /yol/index.js` ile verin. Frida sürümü ile `frida-il2cpp-bridge` uyumlu olmalı
(bu prototip **frida 17.x** + **bridge 0.14.0** ile hazırlandı).

## 2) Oyuna bağlanma

| Senaryo | Ne gerekir | Komut |
| --- | --- | --- |
| **Root var** | `frida-server` cihazda çalışıyor | `python3 server.py --host 127.0.0.1:27042 --target com.cww.cubecraft --spawn` |
| **Root yok** | APK'ya gömülü `frida-gadget`, "listen" modu | `python3 server.py --host 127.0.0.1:27042 --target Gadget` |
| USB (PC) | `frida-server` / gadget + USB | `python3 server.py --usb --target com.cww.cubecraft` |

Root yoksa izlenecek yol: `frida-gadget` kütüphanesini APK’ya ekleyip (LIEF ile `DT_NEEDED`
girişi veya doğrudan `lib/arm64-v8a/` içine) **her iki split’i de** yeniden imzalamak
(`sign-apk-py` Java gerektirmez) ve `adb install-multiple` / SAI ile kurmak.

## 3) Panel

`http://127.0.0.1:8080` — sekmeler yerine tek sayfa:

- **Ara**: ör. `Money`, `Gems`, `Rewarded`, `Save` → sınıflar → metodlar
- **İzle (log)**: metodun çağrıldığını ve döndürdüğü değeri canlı görme
- **Sabit**: metodun dönüş değerini sabit sayıya çevirme
- **×N**: sayısal dönüş değerini N ile çarpma
- **Tümünü kaldır**: kurulan tüm modları geri alma
- **Log**: ajanın canlı çıktısı

Sunucu ayrıca `/api/invoke` (oyunun kendi metodunu çağırma) ve `/api/field/read|write`
(statik alan okuma/yazma; singleton varsa örnek alanı) uçlarını sunar — panelden
kullanılmasalar da `curl` ile denenebilir:

```bash
curl -s -X POST localhost:8080/api/invoke -H 'content-type: application/json' \
  -d '{"assembly":"Assembly-CSharp.dll","namespace":"MainGame","name":"PlayerMoneyController",
       "method":"AddMoney","paramCount":1,"args":[999999],"onInstance":true}'
```

## 4) Durum ve sınırlar

- Bu bir **prototiptir**; cihaz üzerinde test edilmedi (sandbox'ta Android yok).
- Değerlerin bir kısmı sunucu tarafında (Nakama) tutuluyor olabilir → bkz.
  `../notes/modding-plan.md` (§1 Ekonomi).
- Bulut kayıt (cloud save) modifiye değerleri geri yazabilir; test ederken hesap bağlamamak
  veya çevrimdışı denemek daha güvenli.
- Yeniden imzalanan APK’da Play Games oturumu çalışmayabilir.
