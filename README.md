# 🚗 Araç Takip Botu

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Machine Learning](https://img.shields.io/badge/AI-Random%20Forest-orange.svg)
![GUI](https://img.shields.io/badge/GUI-Tkinter-success.svg)
![Database](https://img.shields.io/badge/Database-SQLite3-lightgrey.svg)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib-yellow.svg)

## 📌 Proje Özeti
**Araç Takip Botu**, ikinci el araç piyasasındaki ilanları otonom olarak tarayan, elde ettiği verileri **Scikit-Learn (`RandomForestRegressor`)** makine öğrenmesi modeli ve istatistiksel emsal analizi ile işleyerek araçların **"Adil Piyasa Değerini (Fair Value)"** hesaplayan uçtan uca bir masaüstü uygulamasıdır.

Sistem, hesaplanan adil değerin **%5 ve daha altında** fiyatlandırılan fırsat araçlarını tespit eder; arayüz üzerindeki canlı dağılım grafiğinde (Scatter Plot) görselleştirir, görsel vitrin kataloğunda listeler ve Telegram üzerinden anlık bildirim olarak iletir.

---

## 🚀 Temel Özellikler

* **🧠 Hibrit Yapay Zeka Fiyatlama Algoritması:** Her taramada mevcut veri setiyle `100` ağaçlı bir **Random Forest Regresyon** modeli eğitilir. Modelin aşırı öğrenmesini (overfitting) engellemek adına; **%60 Yapay Zeka Tahmini + %40 İstatistiksel Emsal Ortalaması** (±20.000 KM bandı) ağırlıklandırmasıyla hibrit bir adil değer kararı verilir.
* **🛡️ Anti-Bot Bypass & TLS Fingerprinting:** Standart HTTP isteklerini engelleyen WAF ve Cloudflare korumalarını aşmak için `curl_cffi` kütüphanesi ile **Chrome TLS Impersonation** (Tarayıcı Taklidi) kullanılır.
* **📊 Canlı Matplotlib Dashboard:** Tkinter arayüzüne gömülü grafik motoru; piyasa emsallerini (mavi noktalar), medyan model yılı bazlı **AI Değer Eğrisini** (yeşil trend çizgisi) ve yakalanan fırsat araçlarını (kırmızı yıldızlar ve fiyat etiketleri) canlı olarak çizer.
* **📋 Görsel Fırsat Vitrini & Önbellekleme (Image Caching):** Yakalanan fırsat araçları ayrı bir katalog penceresinde (`Toplevel`) listelenir. Araç fotoğrafları `Pillow` ile arka planda asenkron olarak indirilir ve RAM'de önbelleğe (cache) alınır. Kullanıcı; **Fiyat (En Ucuz / En Pahalı)**, **Kilometre**, **Yıl** ve **İndirim Oranı** kriterlerine göre tek tıkla anlık sıralama yapabilir.
* **📥 Excel / CSV Raporlama:** Vitrinde listelenen tüm fırsat araçları, Türkçe karakter uyumlu (`utf-8-sig`) ve noktalı virgül (`;`) ayrımlı formatta tek tıkla dışa aktarılabilir.
* **⚡ Multi-Threading Mimari:** Web kazıma, makine öğrenmesi eğitimi, zamanlayıcı döngüsü ve görsel indirme işlemleri ayrı iş parçacıklarında (`threading`) çalıştırılarak arayüzün donması (UI Freezing) tamamen engellenmiştir.
* **📲 Akıllı Telegram Bildirimleri (Spam Korumalı):** Mükerrer bildirimleri önlemek için yalnızca veritabanına yeni eklenen fırsat araçları değerlendirilir. Kullanıcı tarafından belirlenen bildirim limitine göre en uygun fiyatlı araçlar tıklanabilir ilan linkleriyle birlikte telefona gönderilir.

---

## 🛠️ Sistem Mimarisi ve Teknoloji Yığını

| Katman | Kullanılan Teknolojiler / Kütüphaneler | Görevi |
| :--- | :--- | :--- |
| **Arayüz (GUI) & Görsel** | `tkinter`, `Pillow (PIL)`, `webbrowser` | Çok pencereli kullanıcı arayüzü, asenkron görsel vitrin ve tarayıcı yönlendirmesi |
| **Yapay Zeka & Analitik** | `scikit-learn`, `numpy` | `RandomForestRegressor` eğitimi, vektörel hesaplamalar ve adil değer tahmini |
| **Veri Görselleştirme** | `matplotlib` (`FigureCanvasTkAgg`) | Fiyat/KM dağılım grafiği (Scatter Plot) ve AI regresyon eğrisi çizimi |
| **Ağ & Veri Kazıma** | `curl_cffi`, `BeautifulSoup4` | Anti-bot korumalarını aşma, sayfalama (pagination) ve HTML veri ayrıştırma |
| **Veritabanı & Raporlama** | `sqlite3`, `csv` | `UNIQUE(baslik, fiyat)` kısıtlamalı veri depolama ve Excel uyumlu tablo çıktısı |
| **Güvenlik & Bildirim** | `python-dotenv`, `Telegram Bot API` | Ortam değişkenleri izolasyonu (`.env`) ve HTML formatlı anlık mobil bildirim |

---

## ⚙️ Kurulum ve Çalıştırma

### 1. Projeyi Klonlayın
```bash
git clone [https://github.com/omerkirman/arac-takip-ai.git](https://github.com/omerkirman/arac-takip-ai.git)
cd arac-takip-ai
```

### 2. Sanal Ortamı (Virtual Environment) Kurun ve Aktif Edin
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Gerekli Kütüphaneleri Yükleyin
```bash
pip install -r requirements.txt
```

### 4. Ortam Değişkenlerini (`.env`) Yapılandırın
Proje ana dizininde `.env` adında bir dosya oluşturun ve Telegram API bilgilerinizi aşağıdaki formatta ekleyin:
```env
TELEGRAM_TOKEN=1234567890:AAH_sizin_telegram_bot_tokeniniz
TELEGRAM_CHAT_ID=987654321
```

### 5. Uygulamayı Başlatın
```bash
python bot.py
```

---

## 📦 Bağımsız Çalıştırılabilir (`.exe`) Çıktı Alma

Projeyi Python kurulu olmayan bilgisayarlarda da tek tıkla çalıştırabilmek için `PyInstaller` ile derleyebilirsiniz:

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name "Arac_Takip_Botu" bot.py
```
> **Not:** Derleme sonrasında oluşan `Arac_Takip_Botu.exe` dosyasının Telegram bildirimlerini gönderebilmesi için yanına `.env` dosyanızı kopyalamayı unutmayın.

---

## 📖 Kullanım Kılavuzu

1. **İlan Linki:** `arabam.com` üzerinde filtrelediğiniz (marka, model, paket veya ağır hasar filtresi uygulanmış) arama sayfasının linkini yapıştırın.
2. **Kriterler:** İsteğe bağlı olarak *Min/Max Fiyat*, *Min/Max Yıl*, *Maksimum KM* ve tek seferde gelmesini istediğiniz *Bildirim Limiti* değerlerini girin.
3. **Sürekli İzleme (Döngü):** Botun belirli bir süre boyunca aralıklarla piyasayı kontrol etmesini istiyorsanız *Çalışma (Saat / Dakika)* alanlarını doldurun (Tek seferlik tarama için `0` bırakın).
4. **Analiz ve Vitrin:** **🚀 AI Taramayı Başlat** butonuna tıklayın. Tarama bittiğinde sağ panelden piyasa grafiğini inceleyebilir, **📋 Fırsat Araçları Vitrinini Aç** butonuna tıklayarak yakalanan araçları fotoğraflarıyla görüntüleyip **📥 Excel/CSV İndir** butonuyla dışa aktarabilirsiniz.