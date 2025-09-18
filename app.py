import sys, time, random, threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# Qt
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QSplitter,
    QListWidget, QProgressBar, QMessageBox, QTabWidget,
    QSpinBox, QHBoxLayout, QHeaderView, QLineEdit, QFormLayout,
    QGroupBox, QComboBox
)

import pymysql

# ---- (Opsiyonel) Matplotlib embed: stok grafiği için
try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_OK = True
except Exception:
    MATPLOTLIB_OK = False


# ===================== DB yardımcıları =====================
def baglanti_ac():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="gulsuf201",
        database="yeni_proje",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )

def musteri_listesi():
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.execute("""
            SELECT CustomerID, CustomerName, CustomerType, Budget, TotalSpent
            FROM Customers ORDER BY CustomerID
        """)
        return cur.fetchall()

def musteri_getir(mid: int):
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.execute("""
            SELECT CustomerID, CustomerName, CustomerType, Budget, TotalSpent
            FROM Customers WHERE CustomerID=%s
        """, (mid,))
        return cur.fetchone()

def urunleri_getir() -> List[Dict]:
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.execute("SELECT ProductID, ProductName, Stock, Price, Category FROM Products ORDER BY ProductID")
        return cur.fetchall()


def urun_bilgi_adla(urun_ad: str) -> Optional[Dict]:
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.execute("""
            SELECT ProductID, ProductName, Stock, Price
            FROM Products WHERE ProductName=%s
        """, (urun_ad,))
        return cur.fetchone()

def urun_bilgi_idyle(pid: int) -> Optional[Dict]:
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.execute("""
            SELECT ProductID, ProductName, Stock, Price
            FROM Products WHERE ProductID=%s
        """, (pid,))
        return cur.fetchone()

def urun_ekle(product_name: str, stock: int, price: float, category: str):
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.execute("""
            INSERT INTO Products (ProductName, Stock, Price, Category)
            VALUES (%s, %s, %s, %s)
        """, (product_name, stock, price, category))


def urun_stok_guncelle(product_id: int, new_stock: int):
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.execute("UPDATE Products SET Stock=%s WHERE ProductID=%s", (new_stock, product_id))

def urun_sil(product_id: int):
    with baglanti_ac() as bag, bag.cursor() as cur:
        # Order bağımlılığı varsa RESTRICT olabilir; hata yakalayalım
        cur.execute("DELETE FROM Products WHERE ProductID=%s", (product_id,))

def siparis_olustur_processing(musteri_id: int, urun_id: int, adet: int) -> int:
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.callproc("sp_siparis_ver", (musteri_id, urun_id, adet))
        cur.execute("""
            SELECT OrderID FROM Orders
             WHERE CustomerID=%s ORDER BY OrderID DESC LIMIT 1
        """, (musteri_id,))
        r = cur.fetchone()
        return int(r["OrderID"]) if r else -1

def siparisi_tamamla(order_id: int):
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.callproc("sp_siparis_tamamla", (order_id,))

def oncelik_view_al() -> List[Dict]:
    """vw_siparis_oncelik'ten bekleme/öncelik bilgisini alır."""
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.execute("""
            SELECT CustomerID, CustomerName, CustomerType,
                   BeklemeSuresiSn, OncelikSkoru
            FROM vw_siparis_oncelik
        """)
        return cur.fetchall()

def log_yaz(log_type: str, customer_id: Optional[int], customer_type: Optional[str],
            product_name: Optional[str], qty: Optional[int], result_text: str,
            order_id: Optional[int] = None):
    """
    Logs tablosu (varsa) için bir yardımcı.
    Schema: LogType, CustomerID, CustomerType, ProductName, Qty, ResultText, OrderID, LogDate (DEFAULT).
    """
    try:
        with baglanti_ac() as bag, bag.cursor() as cur:
            cur.execute("""
                INSERT INTO Logs (LogType, CustomerID, CustomerType, ProductName, Qty, ResultText, OrderID)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (log_type, customer_id, customer_type, product_name, qty, result_text, order_id))
    except Exception:
        # Logs tablosu yoksa projeyi kırmamak için yutuyoruz.
        pass

def ensure_initial_customers():
    """
    Veritabanında yeterli müşteri yoksa tek seferlik başlangıç verisi ekler.
    Koşul: Başlangıçta atanan Premium müşterilerin TotalSpent (ToplamHarcama) >= 2000 olmalı.
    """
    with baglanti_ac() as bag, bag.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM Customers")
        sayi = cur.fetchone()["c"]

    
    if sayi >= 5:
        return

    import random
    hedef_adet = random.randint(5, 10)
    musteri_adlari = [f"Müşteri {chr(65+i)}" for i in range(hedef_adet)]
    eklenen_idler = []


    with baglanti_ac() as bag, bag.cursor() as cur:
        for ad in musteri_adlari:
            butce = random.randint(500, 3000)              
            cur.execute(
                """
                INSERT INTO Customers(CustomerName, Budget, CustomerType, TotalSpent)
                VALUES (%s, %s, 'Standard', 0.00)
                """,
                (ad, butce)
            )
            eklenen_idler.append(cur.lastrowid)

    
    premium_adet = min(2, len(eklenen_idler))
    premium_idler = random.sample(eklenen_idler, k=premium_adet)

    for cid in premium_idler:
        toplam_harcama = random.randint(2000, 5000)       
        with baglanti_ac() as bag, bag.cursor() as cur:
            cur.execute(
                """
                UPDATE Customers
                   SET CustomerType = 'Premium',
                       TotalSpent   = %s
                 WHERE CustomerID   = %s
                """,
                (toplam_harcama, cid)
            )




@dataclass
class SiparisTalebi:
    musteri_id: int; musteri_ad: str; musteri_tip: str
    urun_id: int; urun_ad: str; adet: int; fiyat: float
    kuyruga_giris: float = field(default_factory=lambda: time.time())
    isleme_baslangic: Optional[float] = None  
    
    @property
    def temel(self) -> int:
        return 20 if self.musteri_tip == "Premium" else 10

    def skor(self) -> float:
        bekleme = max(0.0, time.time() - self.kuyruga_giris)
        return self.temel + 0.5 * bekleme



class SiparisIslemeMerkezi(QThread):
    log = Signal(str, str)
    kuyruk_snapshot = Signal(list)
    islem_sonucu = Signal(str, dict)  
    is_processing = Signal(bool)     

    def __init__(self, timeout_s=15, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._kuyruk: List[SiparisTalebi] = []
        self._run = True
        self.timeout_s = timeout_s
        self._admin_lock = threading.RLock()

    def kuyruga_ekle(self, t: SiparisTalebi):
        with self._lock:
            self._kuyruk.append(t)
        self.log.emit("Bilgi", f"Kuyruğa eklendi → {t.musteri_ad}/{t.urun_ad} x{t.adet}")
        log_yaz("Bilgi", t.musteri_id, t.musteri_tip, t.urun_ad, t.adet, "Kuyruğa eklendi")
        self._emit_snapshot()

    def durdur(self):
        self._run = False

    def _sec(self) -> Optional[SiparisTalebi]:
        if not self._kuyruk:
            return None
        self._kuyruk.sort(key=lambda x: x.skor(), reverse=True)
        return self._kuyruk.pop(0)

    def _emit_snapshot(self):
        with self._lock:
            snap = [{
                "musteri": t.musteri_ad, "tip": t.musteri_tip,
                "urun": t.urun_ad, "adet": t.adet,
                "bekleme": int(time.time() - t.kuyruga_giris),
                "skor": round(t.skor(), 1)
            } for t in sorted(self._kuyruk, key=lambda x: x.skor(), reverse=True)]
        self.kuyruk_snapshot.emit(snap)

    def run(self):
        while self._run:
            t = None
            with self._lock:
                if self._kuyruk:
                    t = self._sec()
            if not t:
                self.msleep(200)
                continue

            
            t.isleme_baslangic = time.time()
            self.is_processing.emit(True)
            self.log.emit("Bilgi", f"İşleniyor: {t.musteri_ad} → {t.urun_ad} x{t.adet}")
            log_yaz("Bilgi", t.musteri_id, t.musteri_tip, t.urun_ad, t.adet, "İşleme alındı")

           
            self.msleep(2000)

           
            if (time.time() - (t.isleme_baslangic or t.kuyruga_giris)) >= self.timeout_s:
                msg = f"Zaman aşımı: {t.musteri_ad} / {t.urun_ad}"
                self.log.emit("Hata", msg)
                log_yaz("Hata", t.musteri_id, t.musteri_tip, t.urun_ad, t.adet, "Zaman aşımı")
                self.islem_sonucu.emit("timeout", {"mesaj": msg})
                self._emit_snapshot()
                self.is_processing.emit(False)
                continue

            
            try:
                with self._admin_lock:
                    oid = siparis_olustur_processing(t.musteri_id, t.urun_id, t.adet)
                    siparisi_tamamla(oid)

                ok_msg = f"Tamamlandı: {t.musteri_ad} → {t.urun_ad} x{t.adet}"
                self.log.emit("Bilgi", ok_msg)
                log_yaz("Bilgi", t.musteri_id, t.musteri_tip, t.urun_ad, t.adet, ok_msg, order_id=oid)
                self.islem_sonucu.emit("basari", {"mesaj": ok_msg})

               
                mus = musteri_getir(t.musteri_id)
                if mus and float(mus["TotalSpent"]) >= 2000 and mus["CustomerType"] != "Premium":
                    with baglanti_ac() as bag, bag.cursor() as cur:
                        cur.execute("""
                            UPDATE Customers
                            SET CustomerType='Premium'
                            WHERE CustomerID=%s
                        """, (t.musteri_id,))
                    self.log.emit("Bilgi", f"{mus['CustomerName']} artık Premium müşteri oldu! 🎉")
                    log_yaz("Bilgi", t.musteri_id, mus["CustomerType"], None, None, "Premium'a yükseltildi")

            except Exception as e:
                err = str(e)
                self.log.emit("Hata", err)
                if "stock" in err.lower() or "stok" in err.lower():
                    log_yaz("Hata", t.musteri_id, t.musteri_tip, t.urun_ad, t.adet, "Yetersiz stok")
                elif "balance" in err.lower() or "bakiye" in err.lower() or "budget" in err.lower():
                    log_yaz("Hata", t.musteri_id, t.musteri_tip, t.urun_ad, t.adet, "Yetersiz bakiye")
                else:
                    log_yaz("Hata", t.musteri_id, t.musteri_tip, t.urun_ad, t.adet, "Veritabanı hatası: " + err)
                self.islem_sonucu.emit("hata", {"mesaj": err})

            self._emit_snapshot()
            
            self.is_processing.emit(False)




class AnaPencere(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sipariş & Stok Yönetim Sistemi")
        self.resize(1500, 900)

        self.worker = SiparisIslemeMerkezi()
        self.worker.log.connect(self._log)
        self.worker.kuyruk_snapshot.connect(self._prio_guncelle)
        self.worker.islem_sonucu.connect(self._islem_sonucu_ele_al)
        self.worker.is_processing.connect(self._processing_anim_toggle)
        self.worker.start()

     
        self.aktif_musteri = musteri_getir(1)
        self.aktif_kategori: Optional[str] = None

        bolucu = QSplitter(Qt.Horizontal)
        self.setCentralWidget(bolucu)

        orta = QTabWidget()

      
        wid_urun = QWidget(); lay = QVBoxLayout(wid_urun)

        
        kat_lay = QHBoxLayout()
        self.kategori_urunleri = self._kategori_listesi()
        for kategori in self.kategori_urunleri.keys():
            btn = QPushButton(kategori)
            btn.setStyleSheet(
                "QPushButton {background:#e67e22; color:white; font-weight:bold; padding:6px; border-radius:6px;}"
                "QPushButton:hover { background:#ff9336; }"
            )
            btn.clicked.connect(lambda _, kat=kategori: self._urunleri_kategoriden_yukle(kat))
            kat_lay.addWidget(btn)
        kat_lay.addStretch()
        lay.addLayout(kat_lay)

        self.tbl_urun = QTableWidget(0, 5)
        self.tbl_urun.setHorizontalHeaderLabels(["Ad", "Stok", "Fiyat", "Stok Durumu", "Sipariş"])
        header = self.tbl_urun.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.tbl_urun.horizontalHeader().setStretchLastSection(False)
        lay.addWidget(self.tbl_urun)

        legend = QLabel("🟢 Yüksek stok   🟡 Azalan stok   🔴 Kritik stok")
        legend.setStyleSheet("padding:6px; font-weight:bold;")
        lay.addWidget(legend)
        orta.addTab(wid_urun, "📦 Ürünler")

       
        wid_mus = QWidget(); lay2 = QVBoxLayout(wid_mus)
        self.tbl_mus = QTableWidget(0, 7)
        self.tbl_mus.setHorizontalHeaderLabels(["ID", "Ad", "Tür", "Bütçe", "Toplam Harcama", "Bekleme(sn)", "Skor"])
        self.tbl_mus.setAlternatingRowColors(True)
        self.tbl_mus.setStyleSheet("""
            QHeaderView::section {
                background-color: #ff7d14;
                color: white;
                font-weight: bold;
                padding: 6px;
            }
            QTableWidget {
                font-size: 13px;
                gridline-color: #ddd;
                alternate-background-color: #f9f9f9;
            }
        """)
        self.tbl_mus.verticalHeader().setDefaultSectionSize(30)
        self.tbl_mus.cellClicked.connect(self._musteri_sec)
        lay2.addWidget(self.tbl_mus)
        orta.addTab(wid_mus, "🧑 Müşteri Paneli")

        
        wid_graf = QWidget(); graf_lay = QVBoxLayout(wid_graf)
        if MATPLOTLIB_OK:
            self.fig = Figure(figsize=(5, 3))
            self.canvas = FigureCanvas(self.fig)
            graf_lay.addWidget(self.canvas)
            self.btn_graf_yenile = QPushButton("Grafiği Yenile")
            self.btn_graf_yenile.clicked.connect(self._stok_grafik_guncelle)
            graf_lay.addWidget(self.btn_graf_yenile)
        else:
            graf_lay.addWidget(QLabel("Matplotlib bulunamadı. (Grafik için matplotlib kurun)"))
        orta.addTab(wid_graf, "📊 Stok Grafiği")

     
        wid_admin = QWidget(); admin_lay = QVBoxLayout(wid_admin)

      
        gb_ekle = QGroupBox("Yeni Ürün Ekle")
        form1 = QFormLayout(gb_ekle)

        self.inp_new_name = QLineEdit()
        self.inp_new_stock = QLineEdit(); self.inp_new_stock.setPlaceholderText("Örn: 50")
        self.inp_new_price = QLineEdit(); self.inp_new_price.setPlaceholderText("Örn: 199.99")

  
        self.cmb_new_category = QComboBox()
        self.cmb_new_category.addItem("")  
        self.cmb_new_category.addItems([
            "Giyim","Ayakkabı","Çanta",
            "Saat & Aksesuar","Spor & Outdoor","Elektronik"
        ])

        btn_add = QPushButton("Ekle")
        btn_add.clicked.connect(self._admin_urun_ekle)

        form1.addRow("Ürün Adı:", self.inp_new_name)
        form1.addRow("Stok:", self.inp_new_stock)
        form1.addRow("Fiyat:", self.inp_new_price)
        form1.addRow("Kategori:", self.cmb_new_category)  
        form1.addRow(btn_add)
        
     
        gb_stok = QGroupBox("Stok Güncelle")
        form2 = QFormLayout(gb_stok)
        self.cmb_stok_p = QComboBox()
        self.inp_new_stock2 = QLineEdit(); self.inp_new_stock2.setPlaceholderText("Yeni stok")
        btn_stok = QPushButton("Güncelle")
        btn_stok.clicked.connect(self._admin_stok_guncelle)
        form2.addRow("Ürün:", self.cmb_stok_p)
        form2.addRow("Yeni Stok:", self.inp_new_stock2)
        form2.addRow(btn_stok)

       
        gb_sil = QGroupBox("Ürün Sil")
        form3 = QFormLayout(gb_sil)
        self.cmb_sil_p = QComboBox()
        btn_del = QPushButton("Sil")
        btn_del.clicked.connect(self._admin_urun_sil)
        form3.addRow("Ürün:", self.cmb_sil_p)
        form3.addRow(btn_del)

        admin_lay.addWidget(gb_ekle)
        admin_lay.addWidget(gb_stok)
        admin_lay.addWidget(gb_sil)
        admin_lay.addStretch(1)

        orta.addTab(wid_admin, "🛠️ Admin")

        bolucu.addWidget(orta)

       
        sag = QWidget(); sag_l = QVBoxLayout(sag)
        self.btn_sim = QPushButton("▶ Simülasyonu Başlat")
        self.btn_sim.setCheckable(True)
        self.btn_sim.toggled.connect(self._sim_toggle)
        sag_l.addWidget(self.btn_sim)

        sag_l.addWidget(QLabel("İşlem Animasyonu"))
        self.pb_anim = QProgressBar()
        self.pb_anim.setRange(0, 1)  
        self.pb_anim.setValue(0)
        self.pb_anim.setTextVisible(False)
        sag_l.addWidget(self.pb_anim)

        sag_l.addWidget(QLabel("Log Paneli"))
        self.lst_log = QListWidget()
        self.lst_log.setStyleSheet("QListWidget { font-size: 13px; background:#fafafa; }")
        sag_l.addWidget(self.lst_log, 2)

        sag_l.addWidget(QLabel("Dinamik Öncelik"))
        self.tbl_prio = QTableWidget(0, 6)
        self.tbl_prio.setHorizontalHeaderLabels(["Müşteri", "Tür", "Ürün", "Adet", "Bekleme", "Skor"])
        sag_l.addWidget(self.tbl_prio, 1)

        bolucu.addWidget(sag)

        
        self.sim_timer = QTimer(self)
        self.sim_timer.timeout.connect(self._simulasyon)

       
        QTimer.singleShot(0, self._ilk_yukleme)

    
  
    def _log(self, tip, msg):
        it = f"({tip}) {msg}"
        self.lst_log.addItem(it)

   
    def _processing_anim_toggle(self, is_on: bool):
        if is_on:
           
            self.pb_anim.setRange(0, 0)
        else:
            self.pb_anim.setRange(0, 1)
            self.pb_anim.setValue(0)


    def _urunleri_kategoriden_yukle(self, kategori):
        self.aktif_kategori = kategori
        urunler = urunleri_getir()
        urunler = [u for u in urunler if u["Category"] == kategori]
        self.tbl_urun.setRowCount(len(urunler))
        for i, u in enumerate(urunler):
            self.tbl_urun.setItem(i, 0, QTableWidgetItem(u["ProductName"]))
            self.tbl_urun.setItem(i, 1, QTableWidgetItem(str(u["Stock"])))
            self.tbl_urun.setItem(i, 2, QTableWidgetItem(str(u["Price"])))
            pb = QProgressBar()
            pb.setMaximum(100)
            yuzde = min(100, int(u["Stock"]))  # basit ölçek
            pb.setValue(yuzde)
            if u["Stock"] < 15:
                pb.setStyleSheet("QProgressBar::chunk { background-color: red; }")
            elif u["Stock"] < 50:
                pb.setStyleSheet("QProgressBar::chunk { background-color: yellow; }")
            else:
                pb.setStyleSheet("QProgressBar::chunk { background-color: green; }")
            self.tbl_urun.setCellWidget(i, 3, pb)
            cell = QWidget()
            h = QHBoxLayout(cell); h.setContentsMargins(0,0,0,0)
            spn = QSpinBox(); spn.setRange(1,5); spn.setFixedWidth(50)
            btn = QPushButton("Sipariş Ver")
            btn.setStyleSheet("QPushButton {background:#ff7d14; color:white; border-radius:6px; padding:4px;} "
                              "QPushButton:hover { background:#ff9336; }")
            btn.clicked.connect(lambda _, urun=u, spin=spn: self._siparis_ver_urun(urun, spin.value()))
            h.addWidget(spn); h.addWidget(btn)
            self.tbl_urun.setCellWidget(i, 4, cell)

   
    def _musterileri_yukle(self):
        mus = musteri_listesi()
       
        oncs = oncelik_view_al()
        bekleme_map: Dict[int, int] = {}
        skor_map: Dict[int, float] = {}
        for r in oncs:
            cid = int(r["CustomerID"])
            bek = int(r["BeklemeSuresiSn"] or 0)
            skor = float(r["OncelikSkoru"] or 0.0)
            
            if cid not in bekleme_map or bek > bekleme_map[cid]:
                bekleme_map[cid] = bek
            if cid not in skor_map or skor > skor_map[cid]:
                skor_map[cid] = skor

        self.tbl_mus.setRowCount(len(mus))
        for i, m in enumerate(mus):
            self.tbl_mus.setItem(i, 0, QTableWidgetItem(str(m["CustomerID"])))
            self.tbl_mus.setItem(i, 1, QTableWidgetItem(m["CustomerName"]))
            self.tbl_mus.setItem(i, 2, QTableWidgetItem(m["CustomerType"]))
            self.tbl_mus.setItem(i, 3, QTableWidgetItem(str(m["Budget"])))
            self.tbl_mus.setItem(i, 4, QTableWidgetItem(str(m["TotalSpent"])))
            self.tbl_mus.setItem(i, 5, QTableWidgetItem(str(bekleme_map.get(m["CustomerID"], 0))))
            self.tbl_mus.setItem(i, 6, QTableWidgetItem(str(round(skor_map.get(m["CustomerID"], 0.0), 1))))

    def _ilk_yukleme(self):
        try:
            ensure_initial_customers()   
            self._musterileri_yukle()
            self._admin_combo_doldur()
            if MATPLOTLIB_OK:
                self._stok_grafik_guncelle()
        except Exception as e:
            self._log("Hata", str(e))


   
    def _musteri_sec(self, row, col):
        cid = int(self.tbl_mus.item(row, 0).text())
        self.aktif_musteri = musteri_getir(cid)
        self._log("Bilgi", f"Aktif müşteri değişti → {self.aktif_musteri['CustomerName']}")

   
    def _siparis_ver_kategori(self, urun_ad, adet, fiyat):
        try:
            urun = urun_bilgi_adla(urun_ad)
            if not urun:
                QMessageBox.warning(self, "Uyari", f"{urun_ad} ürün tablosunda bulunamadı!")
                return
            product_id = int(urun["ProductID"])
            fiyat = float(urun["Price"])
            musteri = self.aktif_musteri
            t = SiparisTalebi(musteri["CustomerID"], musteri["CustomerName"], musteri["CustomerType"],
                              product_id, urun_ad, adet, fiyat)
            self.worker.kuyruga_ekle(t)
        except Exception as e:
            self._log("Hata", f"Sipariş verilemedi: {str(e)}")
            QMessageBox.critical(self, "Hata", f"Sipariş verilemedi:\n{str(e)}")

   
    def _prio_guncelle(self, snap):
        self.tbl_prio.setRowCount(len(snap))
        for i, row in enumerate(snap):
            for j, k in enumerate(["musteri","tip","urun","adet","bekleme","skor"]):
                item = QTableWidgetItem(str(row[k]))
                if k in ("adet","bekleme","skor"):
                    item.setTextAlignment(Qt.AlignCenter)
                self.tbl_prio.setItem(i, j, item)


    def _sim_toggle(self, acik: bool):
        if acik:
            self.btn_sim.setText("⏸ Simülasyonu Durdur")
            self.sim_timer.start(8000)
        else:
            self.btn_sim.setText("▶ Simülasyonu Başlat")
            self.sim_timer.stop()

   
    def _simulasyon(self):
        try:
            ms = musteri_listesi()
            if not ms:
                return

            aktif_id = self.aktif_musteri["CustomerID"] if self.aktif_musteri else None
            adaylar = [m for m in ms if m["CustomerID"] != aktif_id]
            if not adaylar:
                return

            m = random.choice(adaylar)
            kategori = random.choice(list(self.kategori_urunleri.keys()))
            urun_ad = random.choice(self.kategori_urunleri[kategori])

            u = urun_bilgi_adla(urun_ad)
            if not u:
                self._log("Hata", f"Simülasyon ürünü bulunamadı: {urun_ad}")
                return

            adet = random.randint(1, 3)
            t = SiparisTalebi(
                m["CustomerID"], m["CustomerName"], m["CustomerType"],
                int(u["ProductID"]), urun_ad, adet, float(u["Price"])
            )
            self.worker.kuyruga_ekle(t)
            self._log("Bilgi", f"Simülasyon → Rastgele müşteri: {m['CustomerName']} / {urun_ad} x{adet}")
        except Exception as e:
            self._log("Hata", f"Simülasyon hatası: {e}")

    def _siparis_ver_urun(self, urun, adet):
        try:
            urun_db = urun_bilgi_adla(urun["ProductName"])
            if not urun_db:
                QMessageBox.warning(self, "Uyari", f"{urun['ProductName']} ürün tablosunda bulunamadı!")
                return

            product_id = int(urun_db["ProductID"])
            fiyat = float(urun_db["Price"])

          
            musteri = self.aktif_musteri
            toplam_tutar = adet * fiyat
            if musteri and float(musteri.get("Budget") or 0) < toplam_tutar:
                QMessageBox.warning(self, "Uyari", f"{musteri['CustomerName']} için yeterli bütçe yok!")
                return

            t = SiparisTalebi(
                musteri["CustomerID"],
                musteri["CustomerName"],
                musteri["CustomerType"],
                product_id,
                urun["ProductName"],
                int(adet),
                fiyat
            )
            self.worker.kuyruga_ekle(t)
            self._log("Bilgi", f"Kuyruğa eklendi → {musteri['CustomerName']} / {urun['ProductName']} x{adet}")

        except Exception as e:
            self._log("Hata", f"Sipariş verilemedi: {str(e)}")
            QMessageBox.critical(self, "Hata", f"Sipariş verilemedi:\n{str(e)}")

   
    def _islem_sonucu_ele_al(self, tip: str, detay: dict):
        self._tablolari_yenile()

    def _tablolari_yenile(self):
        try:
            self._musterileri_yukle()
        except Exception as e:
            self._log("Hata", f"Müşteri yenileme hatası: {e}")
        try:
            if self.aktif_kategori:
                self._urunleri_kategoriden_yukle(self.aktif_kategori)
        except Exception as e:
            self._log("Hata", f"Ürün yenileme hatası: {e}")
        try:
            if MATPLOTLIB_OK:
                self._stok_grafik_guncelle()
            self._admin_combo_doldur()
        except Exception as e:
            self._log("Hata", f"Admin/grafik yenileme hatası: {e}")

    def _stok_grafik_guncelle(self):
        if not MATPLOTLIB_OK:
            return
        urunler = urunleri_getir()
        if not urunler:
            return

       
        urunler_sorted = sorted(urunler, key=lambda x: x["Stock"])[:10]
        adlar = [u["ProductName"] for u in urunler_sorted]
        stoklar = [u["Stock"] for u in urunler_sorted]

       
        positions = list(range(len(adlar)))

        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.bar(positions, stoklar)  
        ax.set_title("En Düşük Stoklu 10 Ürün")
        ax.set_ylabel("Stok")

       
        ax.set_xticks(positions)
        ax.set_xticklabels(adlar, rotation=45, ha="right")

        self.fig.tight_layout()
        self.canvas.draw_idle()


    #
    def _admin_combo_doldur(self):
        urunler = urunleri_getir()
        self.cmb_stok_p.clear()
        self.cmb_sil_p.clear()
        for u in urunler:
            text = f"{u['ProductID']} - {u['ProductName']} (Stok: {u['Stock']})"
            self.cmb_stok_p.addItem(text, u["ProductID"])
            self.cmb_sil_p.addItem(text, u["ProductID"])

 
    def _admin_urun_ekle(self):
        try:
            with self.worker._admin_lock:  
                ad = self.inp_new_name.text().strip()
                stok = int(self.inp_new_stock.text().strip())
                fiyat = float(self.inp_new_price.text().strip())
                kategori = self.cmb_new_category.currentText()  

                if not ad:
                    QMessageBox.warning(self, "Uyarı", "Ürün adı boş olamaz.")
                    return
                if stok < 0 or fiyat < 0:
                    QMessageBox.warning(self, "Uyarı", "Stok ve fiyat negatif olamaz.")
                    return
                if not kategori or kategori.strip() == "":
                    QMessageBox.warning(self, "Uyarı", "Kategori seçmek zorunludur.")
                    return

                urun_ekle(ad, stok, fiyat, kategori)   
                self._log("Bilgi", f"Admin: Ürün eklendi → {ad} (Stok: {stok}, Fiyat: {fiyat}, Kategori: {kategori})")
                self._tablolari_yenile()

              
                self.inp_new_name.clear()
                self.inp_new_stock.clear()
                self.inp_new_price.clear()
                self.cmb_new_category.setCurrentIndex(0)  

        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Ürün ekleme hatası:\n{e}")


    def _admin_stok_guncelle(self):
        try:
            with self.worker._admin_lock:  
                pid = int(self.cmb_stok_p.currentData())
                yeni_stok = int(self.inp_new_stock2.text().strip())
                if yeni_stok < 0:
                    QMessageBox.warning(self, "Uyari", "Stok negatif olamaz.")
                    return
                urun_stok_guncelle(pid, yeni_stok)
                u = urun_bilgi_idyle(pid)
                self._log("Bilgi", f"Admin: Stok güncellendi → {u['ProductName']} = {yeni_stok}")
                self._tablolari_yenile()
                self.inp_new_stock2.clear()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Stok güncelleme hatası:\n{e}")

 
    def _admin_urun_sil(self):
        try:
            with self.worker._admin_lock:   
                pid = int(self.cmb_sil_p.currentData())
                u = urun_bilgi_idyle(pid)
                urun_sil(pid)
                self._log("Bilgi", f"Admin: Ürün silindi → {u['ProductName']}")
                self._tablolari_yenile()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Ürün silme hatası:\n{e}")

   
    def _kategori_listesi(self):
        kategoriler = {}
        with baglanti_ac() as bag, bag.cursor() as cur:
            cur.execute("SELECT DISTINCT Category FROM Products ORDER BY Category")
            for row in cur.fetchall():
                kategoriler[row["Category"]] = []

           
            cur.execute("SELECT ProductName, Category FROM Products")
            for row in cur.fetchall():
                if row["Category"] in kategoriler:
                    kategoriler[row["Category"]].append(row["ProductName"])
        return kategoriler



    def closeEvent(self, event):
        try:
            self.worker.durdur()
            self.worker.wait()
        finally:
            super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    w = AnaPencere(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
