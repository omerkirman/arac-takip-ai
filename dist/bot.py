import os
import time
import csv
import sqlite3
import threading
import webbrowser
from io import BytesIO
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime
from dotenv import load_dotenv
from curl_cffi import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageTk
import sys
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.ticker as ticker


load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def telegram_mesaj_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Uyarı: .env dosyasında Telegram ayarları bulunamadı.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, impersonate="chrome")
        print("-> Telegram bildirimi başarıyla telefona iletildi!")
    except Exception as e:
        print(f"-> Telegram Gönderim Hatası: {e}")


def sayfa_getir(url):
    try:
        response = requests.get(url, impersonate="chrome", timeout=15)
        if response.status_code == 200:
            return response.text
        return None
    except Exception:
        return None

def ilanlari_ayikla(html_icerik, filtreler):
    soup = BeautifulSoup(html_icerik, "html.parser")
    ilan_satirlari = soup.find_all("tr", class_="listing-list-item")
    ayiklanan_veriler = []
    
    for satir in ilan_satirlari:
        try:
            sutunlar = satir.find_all("td")
            if len(sutunlar) < 7: continue
            
            # --- 1. ARAÇ GÖRSELİNİ YAKALAMA ---
            img_tag = satir.find("img")
            resim_url = ""
            if img_tag:
                
                resim_url = img_tag.get("data-src") or img_tag.get("data-original") or img_tag.get("src") or ""
                if resim_url.startswith("//"):
                    resim_url = "https:" + resim_url
                elif resim_url.startswith("/"):
                    resim_url = "https://www.arabam.com" + resim_url
                
            baslik = " ".join(sutunlar[2].text.split())
            yil_str = sutunlar[3].text.strip()
            km_str = sutunlar[4].text.strip()
            fiyat_str = sutunlar[6].text.strip()
            
            # --- 2. İLAN LİNKİNİ YAKALAMA ---
            link_tag = sutunlar[2].find("a")
            ilan_linki = ""
            if link_tag and link_tag.has_attr("href"):
                href = link_tag["href"]
                ilan_linki = href if href.startswith("http") else f"https://www.arabam.com{href}"
            
            if "," in fiyat_str: fiyat_str = fiyat_str.split(",")[0]
            if "," in km_str: km_str = km_str.split(",")[0]
            
            temiz_fiyat = int("".join(filter(str.isdigit, fiyat_str))) if any(c.isdigit() for c in fiyat_str) else 0
            temiz_km = int("".join(filter(str.isdigit, km_str))) if any(c.isdigit() for c in km_str) else 0
            temiz_yil = int("".join(filter(str.isdigit, yil_str))) if yil_str.isdigit() else 0
            
            if temiz_fiyat < 50000 or temiz_fiyat > 15000000: continue
            if filtreler['min_fiyat'] and temiz_fiyat < filtreler['min_fiyat']: continue
            if filtreler['max_fiyat'] and temiz_fiyat > filtreler['max_fiyat']: continue
            if filtreler['min_yil'] and temiz_yil < filtreler['min_yil']: continue
            if filtreler['max_yil'] and temiz_yil > filtreler['max_yil']: continue
            if filtreler['max_km'] and temiz_km > filtreler['max_km']: continue

            ayiklanan_veriler.append({
                "Baslik": baslik,
                "Yil": temiz_yil,
                "KM": temiz_km,
                "Fiyat_TL": temiz_fiyat,
                "Link": ilan_linki,
                "Resim": resim_url
            })
        except Exception:
            continue
    return ayiklanan_veriler

def veritabani_kur():
    conn = sqlite3.connect("arac_piyasasi.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ilanlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            baslik TEXT,
            yil INTEGER,
            km INTEGER,
            fiyat INTEGER,
            link TEXT,
            resim TEXT,
            kayit_tarihi TEXT,
            UNIQUE(baslik, fiyat)
        )
    ''')
    # Eski veritabanı tablolarını kırmadan yeni sütunları ekle
    try: cursor.execute("ALTER TABLE ilanlar ADD COLUMN link TEXT")
    except Exception: pass
    try: cursor.execute("ALTER TABLE ilanlar ADD COLUMN resim TEXT")
    except Exception: pass
        
    conn.commit()
    return conn

def tum_sayfalari_tara(base_url, filtreler, is_active_func):
    tum_araclar = []
    sayfa_no = 1
    
    print("\n🌐 Piyasa Süpürme İşlemi Başladı...")
    while True:
        if not is_active_func():
            print("\n[!] Tarama işlemi kullanıcı tarafından iptal edildi.")
            break
            
        ayirici = "&" if "?" in base_url else "?"
        aktif_url = f"{base_url}{ayirici}page={sayfa_no}"
        print(f"Taraniyor -> Sayfa {sayfa_no}")
        
        html = sayfa_getir(aktif_url)
        if not html: break
            
        sayfadaki_araclar = ilanlari_ayikla(html, filtreler)
        if len(sayfadaki_araclar) == 0:
            print(f"Sayfa {sayfa_no} filtrelenen/boş. Tarama tamamlandı!")
            break
            
        tum_araclar.extend(sayfadaki_araclar)
        sayfa_no += 1
        
        for _ in range(2):
            if not is_active_func(): break
            time.sleep(1)
        
    return tum_araclar

def verileri_kaydet_ve_analiz_et(conn, arac_listesi, max_bildirim):
    cursor = conn.cursor()
    yeni_eklenenler = []
    
    print(f"\n1. AŞAMA: Piyasa Verileri Yükleniyor (İşlenecek Araç: {len(arac_listesi)})")
    for arac in arac_listesi:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO ilanlar (baslik, yil, km, fiyat, link, resim, kayit_tarihi)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (arac["Baslik"], arac["Yil"], arac["KM"], arac["Fiyat_TL"], arac["Link"], arac["Resim"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            
            if cursor.rowcount > 0: yeni_eklenenler.append(arac)
        except Exception: continue
            
    conn.commit()
    print(f"-> Veritabanı güncellendi. Yeni Eklenen Araç Sayısı: {len(yeni_eklenenler)}")
    
    print("\n2. AŞAMA: Yapay Zeka (Random Forest) Modeli Eğitiliyor...")
    ml_aktif = False
    model = None
    
    if len(arac_listesi) >= 10:
        try:
            X_train = np.array([[a["Yil"], a["KM"]] for a in arac_listesi])
            y_train = np.array([a["Fiyat_TL"] for a in arac_listesi])
            
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X_train, y_train)
            ml_aktif = True
            print(f"🧠 Yapay Zeka Modeli {len(arac_listesi)} araç verisiyle başarıyla eğitildi!")
        except Exception as e:
            print(f"ML Eğitim Hatası (Klasik yönteme geçiliyor): {e}")
    else:
        print("ℹ️ Araç sayısı 10'dan az olduğu için klasik istatistiksel ortalama kullanılıyor.")
    
    tum_firsatlar_grafik_icin = []
    yeni_firsat_araclari = []
    
    for arac in arac_listesi:
        tahmini_deger = None
        
        if ml_aktif and model is not None:
            tahmin = model.predict(np.array([[arac["Yil"], arac["KM"]]]))[0]
            alt_km = max(0, arac["KM"] - 20000)
            ust_km = arac["KM"] + 20000
            cursor.execute("SELECT AVG(fiyat), COUNT(fiyat) FROM ilanlar WHERE yil = ? AND km BETWEEN ? AND ?", (arac["Yil"], alt_km, ust_km))
            ort, say = cursor.fetchone()
            
            if say and say >= 3 and ort:
                tahmini_deger = (tahmin * 0.6) + (ort * 0.4)
            else:
                tahmini_deger = tahmin
        else:
            alt_km = max(0, arac["KM"] - 20000)
            ust_km = arac["KM"] + 20000
            cursor.execute("SELECT AVG(fiyat), COUNT(fiyat) FROM ilanlar WHERE yil = ? AND km BETWEEN ? AND ?", (arac["Yil"], alt_km, ust_km))
            ort, say = cursor.fetchone()
            if say and say >= 3 and ort:
                tahmini_deger = ort
                
        if tahmini_deger:
            hedef_fiyat = tahmini_deger * 0.95  # %5
            if arac["Fiyat_TL"] <= hedef_fiyat:
                indirim_orani = ((tahmini_deger - arac["Fiyat_TL"]) / tahmini_deger) * 100
                firsat_obj = {"arac": arac, "ortalama": tahmini_deger, "indirim": indirim_orani}
                tum_firsatlar_grafik_icin.append(firsat_obj)
                
                if arac in yeni_eklenenler:
                    yeni_firsat_araclari.append(firsat_obj)
    
    tum_firsatlar_grafik_icin.sort(key=lambda x: (x['arac']['Fiyat_TL'], -x['indirim']))
    
    if yeni_firsat_araclari:
        yeni_firsat_araclari.sort(key=lambda x: (x['arac']['Fiyat_TL'], -x['indirim']))
        top_firsatlar = yeni_firsat_araclari[:max_bildirim]
        
        print(f"\nToplam {len(yeni_firsat_araclari)} YENİ fırsat bulundu. En uygun {len(top_firsatlar)} tanesi Telegram'a gönderiliyor...")
        
        for sira, f in enumerate(top_firsatlar, 1):
            a = f["arac"]
            link_satiri = f"\n\n🔗 <a href='{a['Link']}'>İlana Gitmek İçin Tıkla</a>" if a.get("Link") else ""
            
            telegram_mesaj_gonder(
                f"🤖 <b>AI TOP {sira} FIRSAT ARACI!</b> 🚨\n\n"
                f"🚗 <b>Model:</b> {a['Baslik']}\n"
                f"📅 <b>Yıl:</b> {a['Yil']}\n"
                f"🛣 <b>KM:</b> {a['KM']:,}\n\n"
                f"💰 <b>İlan Fiyatı:</b> {a['Fiyat_TL']:,} TL\n"
                f"🧠 <b>AI Adil Değer Tahmini:</b> {int(f['ortalama']):,} TL\n"
                f"📉 <b>Durum:</b> AI Değerlemesinden %{f['indirim']:.1f} DAHA UCUZ!"
                f"{link_satiri}"
            )
            time.sleep(1)
            
        if len(yeni_firsat_araclari) > max_bildirim:
            print(f"Geriye kalan {len(yeni_firsat_araclari) - max_bildirim} yeni fırsat aracı limite takıldı.")
    else:
        print(f"-> Yeni eklenen bir fırsat bulunamadı. (Vitrinde ve Grafikte mevcut {len(tum_firsatlar_grafik_icin)} fırsat hazır)")
        
    return tum_firsatlar_grafik_icin, model

# --- KONSOL ÇIKTILARINI ARAYÜZE YÖNLENDİRME ---
class PrintLogger:
    def __init__(self, text_widget):
        self.text_widget = text_widget
    def write(self, text):
        self.text_widget.insert(tk.END, text)
        self.text_widget.see(tk.END)
    def flush(self):
        pass

# --- AÇILIR LİSTE  ---
class FirsatlarPenceresi:
    def __init__(self, parent, firsat_listesi):
        self.top = tk.Toplevel(parent)
        self.top.title(f"📋 Yakalanan Fırsat Araçları Vitrini ({len(firsat_listesi)} Araç)")
        self.top.geometry("980x680")
        self.top.configure(padx=15, pady=15, bg="#F5F5F5")
        
        self.firsat_listesi = list(firsat_listesi)
        self.resim_referanslari = {} # Tkinter garbage collector referans tutucu
        
        # --- SIRALAMA KONTROLLERİ ---
        ust_frame = tk.Frame(self.top, bg="#E0E0E0", padx=10, pady=10, relief=tk.RAISED, bd=1)
        ust_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(ust_frame, text="🔍 Sıralama Ölçütü:", font=("Arial", 10, "bold"), bg="#E0E0E0").pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(ust_frame, text="💰 Fiyat (En Ucuz)", font=("Arial", 9, "bold"), bg="#FFFFFF", command=lambda: self.sirala("fiyat_artan")).pack(side=tk.LEFT, padx=4)
        tk.Button(ust_frame, text="💰 Fiyat (En Pahalı)", font=("Arial", 9), bg="#FFFFFF", command=lambda: self.sirala("fiyat_azalan")).pack(side=tk.LEFT, padx=4)
        tk.Button(ust_frame, text="🛣 KM (En Düşük)", font=("Arial", 9, "bold"), bg="#FFFFFF", command=lambda: self.sirala("km_artan")).pack(side=tk.LEFT, padx=4)
        tk.Button(ust_frame, text="📅 Yıl (En Yeni)", font=("Arial", 9, "bold"), bg="#FFFFFF", command=lambda: self.sirala("yil_azalan")).pack(side=tk.LEFT, padx=4)
        tk.Button(ust_frame, text="📉 İndirim Oranı (% En Yüksek)", font=("Arial", 9, "bold"), bg="#FFCDD2", command=lambda: self.sirala("indirim_azalan")).pack(side=tk.LEFT, padx=4)
        tk.Button(ust_frame, text="📥 Excel/CSV İndir", font=("Arial", 9, "bold"), bg="#2E7D32", fg="white", cursor="hand2", command=self.csv_disa_aktar).pack(side=tk.RIGHT, padx=4)
        
        # --- KAYDIRILABİLİR (SCROLLABLE) ARAÇ LİSTESİ ---
        container = tk.Frame(self.top, bg="#F5F5F5")
        container.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(container, bg="#F5F5F5", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        
        self.liste_frame = tk.Frame(self.canvas, bg="#F5F5F5")
        self.liste_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.liste_frame, anchor="nw")
        self.canvas.bind("<Configure>", self.canvas_genislik_ayarla)
        
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.top.protocol("WM_DELETE_WINDOW", self._pencere_kapat)
        
        self.listeyi_olustur()

    def csv_disa_aktar(self):
        if not self.firsat_listesi:
            messagebox.showwarning("Uyarı", "Dışa aktarılacak araç bulunamadı.", parent=self.top)
            return
            
        varsayilan_ad = f"firsat_araclari_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        dosya_yolu = filedialog.asksaveasfilename(
            parent=self.top,
            title="Fırsat Araçlarını Kaydet",
            initialfile=varsayilan_ad,
            defaultextension=".csv",
            filetypes=[("Excel CSV Dosyası", "*.csv"), ("Tüm Dosyalar", "*.*")]
        )
        
        if not dosya_yolu:
            return
            
        try:
            with open(dosya_yolu, mode="w", newline="", encoding="utf-8-sig") as f:
                yazici = csv.writer(f, delimiter=";")
                yazici.writerow(["Sıra", "İlan Başlığı", "Model Yılı", "Kilometre (KM)", "İlan Fiyatı (TL)", "AI Adil Değer Tahmini (TL)", "İndirim Oranı (%)", "İlan Linki"])
                
                for idx, item in enumerate(self.firsat_listesi, 1):
                    arac = item["arac"]
                    yazici.writerow([
                        idx,
                        arac["Baslik"],
                        arac["Yil"],
                        arac["KM"],
                        arac["Fiyat_TL"],
                        int(item["ortalama"]),
                        f"{item['indirim']:.1f}",
                        arac.get("Link", "")
                    ])
            messagebox.showinfo("Başarılı", f"Liste başarıyla kaydedildi:\n{dosya_yolu}", parent=self.top)
        except Exception as e:
            messagebox.showerror("Hata", f"Dosya kaydedilirken hata oluştu:\n{e}", parent=self.top)

    def canvas_genislik_ayarla(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _pencere_kapat(self):
        self.canvas.unbind_all("<MouseWheel>")
        self.top.destroy()

    def sirala(self, kriter):
        if kriter == "fiyat_artan":
            self.firsat_listesi.sort(key=lambda x: x["arac"]["Fiyat_TL"])
        elif kriter == "fiyat_azalan":
            self.firsat_listesi.sort(key=lambda x: x["arac"]["Fiyat_TL"], reverse=True)
        elif kriter == "km_artan":
            self.firsat_listesi.sort(key=lambda x: x["arac"]["KM"])
        elif kriter == "yil_azalan":
            self.firsat_listesi.sort(key=lambda x: x["arac"]["Yil"], reverse=True)
        elif kriter == "indirim_azalan":
            self.firsat_listesi.sort(key=lambda x: x["indirim"], reverse=True)
            
        self.listeyi_olustur()

    def listeyi_olustur(self):
        for widget in self.liste_frame.winfo_children():
            widget.destroy()
            
        if not self.firsat_listesi:
            tk.Label(self.liste_frame, text="Gösterilecek fırsat aracı bulunamadı.", font=("Arial", 12), bg="#F5F5F5").pack(pady=30)
            return

        for idx, f in enumerate(self.firsat_listesi, 1):
            arac = f["arac"]
            
            kart = tk.Frame(self.liste_frame, bg="white", relief=tk.SOLID, bd=1, padx=10, pady=10)
            kart.pack(fill=tk.X, pady=6, padx=5)
            
            # Araç Görseli Kutusu
            img_label = tk.Label(kart, text="📷 Fotoğraf\nYükleniyor...", width=18, height=6, bg="#EEEEEE", fg="#666666", font=("Arial", 8))
            img_label.pack(side=tk.LEFT, padx=(0, 15))
            
            resim_url = arac.get("Resim", "")
            if resim_url:
                threading.Thread(target=self.resim_indir_ve_goster, args=(resim_url, img_label, idx), daemon=True).start()
            else:
                img_label.config(text="📷 Görsel Yok")
                
            # Araç Bilgileri
            bilgi_frame = tk.Frame(kart, bg="white")
            bilgi_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            tk.Label(bilgi_frame, text=f"#{idx} - {arac['Baslik']}", font=("Arial", 11, "bold"), bg="white", fg="#212121", anchor="w", justify="left", wraplength=520).pack(fill=tk.X)
            
            detay_metni = f"📅 Yıl: {arac['Yil']}   |   🛣 KM: {arac['KM']:,} km"
            tk.Label(bilgi_frame, text=detay_metni, font=("Arial", 10), bg="white", fg="#424242", anchor="w").pack(fill=tk.X, pady=(4, 4))
            
            fiyat_metni = f"💰 İlan Fiyatı: {arac['Fiyat_TL']:,} TL   (🧠 AI Adil Değer: {int(f['ortalama']):,} TL)"
            tk.Label(bilgi_frame, text=fiyat_metni, font=("Arial", 10, "bold"), bg="white", fg="#1565C0", anchor="w").pack(fill=tk.X)
            
            # İndirim Rozeti ve İlana Git Butonu
            sag_kutu = tk.Frame(kart, bg="white")
            sag_kutu.pack(side=tk.RIGHT, padx=10)
            
            rozet = tk.Label(sag_kutu, text=f"%{f['indirim']:.1f} UCUZ", font=("Arial", 10, "bold"), bg="#E53935", fg="white", padx=8, pady=4)
            rozet.pack(pady=(0, 8))
            
            link = arac.get("Link", "")
            if link:
                git_btn = tk.Button(sag_kutu, text="🔗 İlana Git", font=("Arial", 9, "bold"), bg="#1E88E5", fg="white", cursor="hand2", command=lambda url=link: webbrowser.open(url))
                git_btn.pack(fill=tk.X)

    def resim_indir_ve_goster(self, url, label_widget, idx):
        try:
            # URL daha önce indirildiyse önbellekten (cache) kullan
            if url in self.resim_referanslari:
                photo = self.resim_referanslari[url]
                label_widget.after(0, lambda: self._etikete_resim_koy(label_widget, photo))
                return
                
            resp = requests.get(url, impersonate="chrome", timeout=10)
            if resp.status_code == 200:
                img_data = BytesIO(resp.content)
                pil_img = Image.open(img_data)
                pil_img = pil_img.resize((135, 95), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(pil_img)
                
                self.resim_referanslari[url] = photo
                label_widget.after(0, lambda: self._etikete_resim_koy(label_widget, photo))
            else:
                label_widget.after(0, lambda: label_widget.config(text="📷 Yüklenemedi"))
        except Exception:
            try:
                label_widget.after(0, lambda: label_widget.config(text="📷 Hata"))
            except Exception:
                pass

    def _etikete_resim_koy(self, label_widget, photo):
        try:
            if label_widget.winfo_exists():
                label_widget.config(image=photo, text="", width=135, height=95)
        except Exception:
            pass


# --- KULLANICI ARAYÜZÜ (GUI) ---
class AracBotuGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Araç Takip Botu")
        self.root.geometry("1280x780")
        self.root.configure(padx=15, pady=15)
        
        self.tarama_aktif = False
        self.son_firsat_listesi = [] 
        
        sol_panel = tk.Frame(root, width=550)
        sol_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 15))
        
        sag_panel = tk.Frame(root, bg="white", relief=tk.RIDGE, bd=2)
        sag_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # --- KONTROLLER ---
        tk.Label(sol_panel, text="🚗 Araç Takip Botu", font=("Arial", 15, "bold")).pack(pady=(0, 15))
        
        frame = tk.Frame(sol_panel)
        frame.pack(fill=tk.X)
        
        tk.Label(frame, text="Arabam.com Linki:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.url_entry = tk.Entry(frame, width=42)
        self.url_entry.grid(row=0, column=1, columnspan=3, pady=5, padx=5)
        
        tk.Label(frame, text="Min Fiyat:").grid(row=1, column=0, sticky="w", pady=5)
        self.min_fiyat_entry = tk.Entry(frame, width=13)
        self.min_fiyat_entry.grid(row=1, column=1, sticky="w", padx=5)
        
        tk.Label(frame, text="Max Fiyat:").grid(row=1, column=2, sticky="w", pady=5)
        self.max_fiyat_entry = tk.Entry(frame, width=13)
        self.max_fiyat_entry.grid(row=1, column=3, sticky="w", padx=5)
        
        tk.Label(frame, text="Min Yıl:").grid(row=2, column=0, sticky="w", pady=5)
        self.min_yil_entry = tk.Entry(frame, width=13)
        self.min_yil_entry.grid(row=2, column=1, sticky="w", padx=5)
        
        tk.Label(frame, text="Max Yıl:").grid(row=2, column=2, sticky="w", pady=5)
        self.max_yil_entry = tk.Entry(frame, width=13)
        self.max_yil_entry.grid(row=2, column=3, sticky="w", padx=5)
        
        tk.Label(frame, text="Maksimum KM:").grid(row=3, column=0, sticky="w", pady=5)
        self.max_km_entry = tk.Entry(frame, width=13)
        self.max_km_entry.grid(row=3, column=1, sticky="w", padx=5)
        
        tk.Label(frame, text="Bildirim Limiti:").grid(row=3, column=2, sticky="w", pady=5)
        self.max_bildirim_entry = tk.Entry(frame, width=13)
        self.max_bildirim_entry.insert(0, "3")
        self.max_bildirim_entry.grid(row=3, column=3, sticky="w", padx=5)
        
        tk.Label(frame, text="Çalışma (Saat):", fg="blue", font=("Arial", 9, "bold")).grid(row=4, column=0, sticky="w", pady=10)
        self.saat_entry = tk.Entry(frame, width=13)
        self.saat_entry.insert(0, "0")
        self.saat_entry.grid(row=4, column=1, sticky="w", padx=5)
        
        tk.Label(frame, text="Çalışma (Dakika):", fg="blue", font=("Arial", 9, "bold")).grid(row=4, column=2, sticky="w", pady=10)
        self.dakika_entry = tk.Entry(frame, width=13)
        self.dakika_entry.insert(0, "0")
        self.dakika_entry.grid(row=4, column=3, sticky="w", padx=5)

        btn_frame = tk.Frame(sol_panel)
        btn_frame.pack(pady=(10, 5), fill=tk.X)
        
        self.baslat_btn = tk.Button(btn_frame, text="🚀 AI Taramayı Başlat", font=("Arial", 11, "bold"), bg="#4CAF50", fg="white", command=self.thread_baslat)
        self.baslat_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
        
        self.durdur_btn = tk.Button(btn_frame, text="🛑 Durdur", font=("Arial", 11, "bold"), bg="#F44336", fg="white", state=tk.DISABLED, command=self.taramayi_durdur)
        self.durdur_btn.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=3)
        
        self.vitrin_btn = tk.Button(sol_panel, text="📋 Fırsat Araçları Vitrinini Aç (0 Araç)", font=("Arial", 11, "bold"), bg="#FF9800", fg="white", state=tk.DISABLED, command=self.firsat_vitrinini_ac)
        self.vitrin_btn.pack(pady=(5, 10), fill=tk.X, padx=3)
        
        tk.Label(sol_panel, text="Sistem Kayıtları (Log):", font=("Arial", 10, "bold")).pack(anchor="w")
        self.log_ekrani = scrolledtext.ScrolledText(sol_panel, width=60, height=16, bg="black", fg="#00FF00", font=("Consolas", 9))
        self.log_ekrani.pack(fill=tk.BOTH, expand=True)
        
        # --- MATPLOTLIB DASHBOARD ---
        tk.Label(sag_panel, text="📊 Random Forest AI Piyasa Eğrisi ve Fırsat Analizi", font=("Arial", 12, "bold"), bg="white").pack(pady=10)
        
        self.fig = Figure(figsize=(6, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Veri Bekleniyor...", fontsize=11)
        self.ax.set_xlabel("Kilometre (KM)")
        self.ax.set_ylabel("Fiyat (TL)")
        self.ax.grid(True, linestyle="--", alpha=0.5)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=sag_panel)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        sys.stdout = PrintLogger(self.log_ekrani)

    def firsat_vitrinini_ac(self):
        if not self.son_firsat_listesi:
            messagebox.showinfo("Bilgi", "Henüz yakalanmış bir fırsat aracı bulunmuyor.")
            return
        FirsatlarPenceresi(self.root, self.son_firsat_listesi)

    def grafigi_ciz(self, tum_araclar, firsat_araclari, ml_model):
        self.son_firsat_listesi = firsat_araclari
        if firsat_araclari:
            self.vitrin_btn.config(state=tk.NORMAL, text=f"📋 Fırsat Araçları Vitrinini Aç ({len(firsat_araclari)} Araç)")
        else:
            self.vitrin_btn.config(state=tk.DISABLED, text="📋 Fırsat Araçları Vitrinini Aç (0 Araç)")

        self.ax.clear()
        
        if not tum_araclar:
            self.ax.set_title("Gösterilecek Veri Bulunamadı")
            self.canvas.draw()
            return
            
        firsat_linkleri = set(f["arac"]["Link"] for f in firsat_araclari if f["arac"].get("Link"))
        
        normal_km = [a["KM"] for a in tum_araclar if a.get("Link") not in firsat_linkleri]
        normal_fiyat = [a["Fiyat_TL"] for a in tum_araclar if a.get("Link") not in firsat_linkleri]
        
        firsat_km = [f["arac"]["KM"] for f in firsat_araclari]
        firsat_fiyat = [f["arac"]["Fiyat_TL"] for f in firsat_araclari]
        
        self.ax.scatter(normal_km, normal_fiyat, color="#1E88E5", alpha=0.5, s=40, label=f"Piyasa Emsalleri ({len(normal_km)})")
        
        if ml_model is not None and len(tum_araclar) >= 10:
            try:
                medyan_yil = int(np.median([a["Yil"] for a in tum_araclar]))
                min_km = min(a["KM"] for a in tum_araclar)
                max_km = max(a["KM"] for a in tum_araclar)
                
                if max_km > min_km:
                    km_cizgisi = np.linspace(min_km, max_km, 100)
                    X_egri = np.array([[medyan_yil, k] for k in km_cizgisi])
                    y_egri = ml_model.predict(X_egri)
                    
                    self.ax.plot(km_cizgisi, y_egri, color="#2E7D32", linestyle="-", linewidth=2.5, zorder=4, label=f"AI Değer Eğrisi ({medyan_yil} Model Bazlı)")
            except Exception:
                pass
        
        if firsat_km:
            self.ax.scatter(firsat_km, firsat_fiyat, color="#E53935", marker="*", s=180, zorder=5, label=f"AI Fırsatları ({len(firsat_km)})")
            
            for f in firsat_araclari[:3]:
                km_deger = f["arac"]["KM"]
                fiyat_deger = f["arac"]["Fiyat_TL"]
                self.ax.annotate(
                    f"{fiyat_deger:,} TL\n(%{f['indirim']:.1f} Ucuz)",
                    (km_deger, fiyat_deger),
                    textcoords="offset points",
                    xytext=(0, -22),
                    ha="center",
                    fontsize=8,
                    fontweight="bold",
                    color="#B71C1C",
                    bbox=dict(boxstyle="round,pad=0.2", fc="#FFEBEE", ec="#E53935", alpha=0.9)
                )
        
        self.ax.set_title(f"AI Piyasa Dağılımı (Toplam {len(tum_araclar)} Araç)", fontsize=11, fontweight="bold")
        self.ax.set_xlabel("Kilometre (KM)", fontsize=10)
        self.ax.set_ylabel("Fiyat (TL)", fontsize=10)
        
        self.ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f'{int(x):,}'))
        self.ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, pos: f'{int(y):,}'))
        
        self.ax.grid(True, linestyle="--", alpha=0.5)
        self.ax.legend(loc="upper right")
        self.fig.tight_layout()
        
        self.canvas.draw()

    def int_cevir(self, deger):
        try: return int(deger)
        except: return None
        
    def taramayi_durdur(self):
        self.tarama_aktif = False
        print("\n[!] DİKKAT: Kullanıcı işlemi durdurdu. Mevcut adım bitince sistem kapanacak...")
        self.durdur_btn.config(state=tk.DISABLED)

    def thread_baslat(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Hata", "Lütfen bir ilan linki yapıştırın!")
            return
            
        self.tarama_aktif = True
        self.baslat_btn.config(state=tk.DISABLED, text="⏳ AI Çalışıyor...")
        self.durdur_btn.config(state=tk.NORMAL)
        
        limit_verisi = self.int_cevir(self.max_bildirim_entry.get())
        if limit_verisi is None or limit_verisi <= 0: limit_verisi = 3
            
        filtreler = {
            'min_fiyat': self.int_cevir(self.min_fiyat_entry.get()),
            'max_fiyat': self.int_cevir(self.max_fiyat_entry.get()),
            'min_yil': self.int_cevir(self.min_yil_entry.get()),
            'max_yil': self.int_cevir(self.max_yil_entry.get()),
            'max_km': self.int_cevir(self.max_km_entry.get()),
            'max_bildirim': limit_verisi
        }
        
        saat = self.int_cevir(self.saat_entry.get()) or 0
        dakika = self.int_cevir(self.dakika_entry.get()) or 0
        
        threading.Thread(target=self.bot_islemleri, args=(url, filtreler, saat, dakika), daemon=True).start()

    def bot_islemleri(self, url, filtreler, saat, dakika):
        toplam_saniye = (saat * 3600) + (dakika * 60)
        bitis_zamani = time.time() + toplam_saniye
        dongu = 1
        
        while self.tarama_aktif:
            if toplam_saniye > 0:
                kalan_saniye = int(bitis_zamani - time.time())
                if kalan_saniye <= 0:
                    print("\n⏰ BELİRLENEN SÜRE DOLDU. Tarama başarıyla sonlandırılıyor...")
                    break
                k_saat, k_dakika = kalan_saniye // 3600, (kalan_saniye % 3600) // 60
                print(f"\n--- {dongu}. DÖNGÜ (Kalan Süre: {k_saat} Saat {k_dakika} Dakika) ---")
            else:
                print(f"\n--- TEKLİ TARAMA (AI & ML Modu Aktif) ---")
            
            db_baglantisi = veritabani_kur()
            toplam_arac_listesi = tum_sayfalari_tara(url, filtreler, lambda: self.tarama_aktif)
            
            if not self.tarama_aktif:
                db_baglantisi.close()
                break
                
            if toplam_arac_listesi:
                firsat_listesi, egitilen_model = verileri_kaydet_ve_analiz_et(db_baglantisi, toplam_arac_listesi, filtreler['max_bildirim'])
                self.root.after(0, self.grafigi_ciz, toplam_arac_listesi, firsat_listesi, egitilen_model)
            else:
                print("Kriterlere uygun araç bulunamadı.")
                
            db_baglantisi.close()
            
            if toplam_saniye <= 0:
                break
                
            if self.tarama_aktif:
                print("\nSistemin engellenmemesi için 60 saniye dinlenmeye geçiliyor...")
                for _ in range(60):
                    if not self.tarama_aktif: break
                    time.sleep(1)
                    
            dongu += 1

        print("\n--- İŞLEM TAMAMLANDI VEYA DURDURULDU ---")
        self.baslat_btn.config(state=tk.NORMAL, text="🚀 AI Taramayı Başlat")
        self.durdur_btn.config(state=tk.DISABLED)
        self.tarama_aktif = False

if __name__ == "__main__":
    root = tk.Tk()
    app = AracBotuGUI(root)
    root.mainloop()