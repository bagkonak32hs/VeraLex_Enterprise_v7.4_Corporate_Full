
# VeraLex Enterprise v7 (Corporate)

- Koyu kurumsal tema (theme.json)
- Modüller: Dashboard, Müvekkiller, Borçlular, Dosya Aç, Dosyalar (alacak/masraf/not), Belgeler, Raporlar (CSV/PDF/Pivot), İçe Aktar (CSV sihirbazı), Hatırlatıcılar, Audit, Kullanıcılar (admin).
- İlk kullanıcı: **admin** — ilk yazdığınız parola kalıcı olarak ayarlanır.

## Çalıştırma
```powershell
python app.py
```

## Paketleme (Windows)
```bat
build_windows.bat
```

## Şablondan DOCX/PDF
- `templates/` içine .txt şablon koyun.
- Değişkenler: `{client}`, `{debtor}`, `{file}`, `{court}`, `{today}`.



## Depolama Modu
- **Ayarlar → Depolama** menüsünden **Taşınabilir (klasör)** veya **Uygulama Verisi (APPDATA)** seçebilirsiniz.
- Mod değişince veriler yeni dizine **kopyalanır**; yeniden başlatınız.

## Yedekleme
- **Ayarlar → Yedekleme** menüsünden **Yedekle/Geri Yükle** (zip).

## Raporlar
- Tarih filtreleri + **Aylık Özet PDF** (tahsilat/masraf/net).
