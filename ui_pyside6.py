import sys  # komut satırı bağımsız değişkenlerine erişmek için #
from PySide6.QtWidgets import (  # PySide6 ana widget bileşenleri #
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QSpinBox, QFrame, QMessageBox, QSplitter, QFormLayout
)
from PySide6.QtCore import Qt  # hizalama ve sabitler #
import pymysql  # MySQL bağlantısı için #

# ==============================
#  Veritabanı yardımcıları
# ==============================
def get_conn():  # Her işlemde taze bağlantı açmak için #
    return pymysql.connect(
        host="localhost", user="root", password="gulsuf201",
        database="yeni_proje", charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )  # bağlantı nesnesi döner #

def db_get_products():  # Ürünleri DB'den çeker #
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT ProductID, ProductName, Price, Stock FROM Products ORDER BY ProductID;")  # ürün sorgu #
        rows = cur.fetchall()  # tüm satırlar #
    # Basit dict dönelim (UI kolay kullansın) #
    return [{"id": r["ProductID"], "title": r["ProductName"], "price": float(r["Price"]), "stock": r["Stock"]} for r in rows]  # liste #

def db_get_customer(cid):  # Müşteri özetini çeker #
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT CustomerID, CustomerName, Budget, TotalSpent, CustomerType FROM Customers WHERE CustomerID=%s", (cid,))  # müşteri #
        m = cur.fetchone()  # tek satır #
    return m  # None olabilir #

def db_order_create(customer_id, product_id, qty):  # Sipariş verir (Processing) #
    with get_conn() as conn, conn.cursor() as cur:
        cur.callproc("sp_siparis_ver", (customer_id, product_id, qty))  # SP çağrısı #
        conn.commit()  # işlemi kaydet #
        cur.execute("SELECT OrderID FROM Orders WHERE CustomerID=%s ORDER BY OrderID DESC LIMIT 1;", (customer_id,))  # son sipariş #
        row = cur.fetchone()  # tek satır #
        if not row:
            raise RuntimeError("Sipariş oluşturulamadı")  # hata #
        return row["OrderID"]  # son order id #

def db_order_complete(order_id):  # Siparişi Completed yapar (TotalSpent artar) #
    with get_conn() as conn, conn.cursor() as cur:
        cur.callproc("sp_siparis_tamamla", (order_id,))  # SP çağrısı #
        conn.commit()  # işlemi kaydet #

# ==============================
#  Basit yardımcılar (UI)
# ==============================
def tl(n):  # TL formatı #
    return f"₺{float(n):.2f}"  # iki ondalık #

class Line(QFrame):  # İnce ayırıcı çizgi #
    def __init__(self):
        super().__init__()  # üst sınıf init #
        self.setFrameShape(QFrame.HLine)  # yatay çizgi #
        self.setFrameShadow(QFrame.Sunken)  # gölgeli görünüm #

# ==============================
#  Ana Pencere
# ==============================
class MainWindow(QMainWindow):  # ana uygulama penceresi #
    def __init__(self, customer_id=3):
        super().__init__()  # üst sınıf init #
        self.setWindowTitle("Shoply – Masaüstü (PySide6)")  # pencere başlığı #
        self.resize(1200, 720)  # başlangıç boyutu #

        self.customer_id = customer_id  # örnek müşteri #
        self.products = []  # ürün listesi (filtrelenmiş) #
        self.products_raw = []  # ham ürün listesi (tümü) #
        self.cart = []  # sepet (dict: id,title,price,qty) #

        # ---- Üst kapsayıcı: splitter ile sol-orta-sağ bölmek ---- #
        splitter = QSplitter(Qt.Horizontal)  # yatay bölücü #
        splitter.setChildrenCollapsible(False)  # daralınca otomatik yok etmesin #
        self.setCentralWidget(splitter)  # merkezi widget #

        # ---- Sol: Filtre paneli ---- #
        self.left = QWidget()  # sol panel #
        left_layout = QVBoxLayout(self.left)  # dikey yerleşim #
        left_layout.setContentsMargins(10, 10, 10, 10)  # kenar boşluk #
        left_layout.addWidget(QLabel("🔎 Filtreler"))  # başlık #

        self.search_input = QLineEdit()  # arama kutusu #
        self.search_input.setPlaceholderText("Ürün/marka ara...")  # ipucu #
        left_layout.addWidget(self.search_input)  # ekle #

        form = QFormLayout()  # fiyat aralığı formu #
        self.min_price = QLineEdit()  # min #
        self.min_price.setPlaceholderText("Min")  # ipucu #
        self.max_price = QLineEdit()  # max #
        self.max_price.setPlaceholderText("Max")  # ipucu #
        form.addRow("Fiyat min:", self.min_price)  # etiket+alan #
        form.addRow("Fiyat max:", self.max_price)  # etiket+alan #
        left_layout.addLayout(form)  # ekle #

        self.sort_box = QComboBox()  # sıralama kutusu #
        self.sort_box.addItems(["Popüler", "Fiyat Artan", "Fiyat Azalan", "En Yeni"])  # seçenekler #
        left_layout.addWidget(QLabel("Sırala:"))  # etiket #
        left_layout.addWidget(self.sort_box)  # kutu #

        btn_apply = QPushButton("Filtreleri Uygula")  # buton #
        btn_apply.clicked.connect(self.apply_filters)  # tıklama olayı #
        left_layout.addWidget(btn_apply)  # ekle #

        left_layout.addStretch()  # boşluk doldur #
        splitter.addWidget(self.left)  # splittere ekle #
        splitter.setStretchFactor(0, 0)  # sol sabit #

        # ---- Orta: Ürün listesi (basit liste) ---- #
        self.center = QWidget()  # orta panel #
        center_layout = QVBoxLayout(self.center)  # dikey yerleşim #
        center_layout.setContentsMargins(10, 10, 10, 10)  # kenar boşluk #
        top_bar = QHBoxLayout()  # üst çubuk #
        self.lbl_count = QLabel("0 ürün bulundu")  # sonuç sayacı #
        self.search_btn = QPushButton("Ara")  # arama butonu #
        self.search_btn.clicked.connect(self.apply_filters)  # arama = filtre uygula #
        top_bar.addWidget(self.lbl_count)  # ekle #
        top_bar.addStretch()  # boşluk #
        top_bar.addWidget(self.search_btn)  # ekle #
        center_layout.addLayout(top_bar)  # üst çubuğu ekle #

        self.list_products = QListWidget()  # ürün listesi #
        self.list_products.setSpacing(6)  # öğeler arası boşluk #
        center_layout.addWidget(self.list_products)  # ekle #

        splitter.addWidget(self.center)  # splittere ekle #
        splitter.setStretchFactor(1, 1)  # orta esnek #

        # ---- Sağ: Sepet + Müşteri özeti ---- #
        self.right = QWidget()  # sağ panel #
        right_layout = QVBoxLayout(self.right)  # dikey yerleşim #
        right_layout.setContentsMargins(10, 10, 10, 10)  # kenar boşluk #

        right_layout.addWidget(QLabel("🧑 Müşteri Özeti"))  # başlık #
        self.lbl_customer = QLabel("-")  # müşteri satırı #
        right_layout.addWidget(self.lbl_customer)  # ekle #

        right_layout.addWidget(Line())  # çizgi #

        right_layout.addWidget(QLabel("🛒 Sepet"))  # başlık #
        self.list_cart = QListWidget()  # sepet listesi #
        right_layout.addWidget(self.list_cart)  # ekle #

        totals = QFormLayout()  # toplamlar #
        self.lbl_sub = QLabel("₺0.00")  # ara toplam #
        self.lbl_total = QLabel("₺0.00")  # genel toplam #
        totals.addRow("Ara Toplam:", self.lbl_sub)  # satır #
        totals.addRow("Toplam:", self.lbl_total)  # satır #
        right_layout.addLayout(totals)  # ekle #

        splitter.addWidget(self.right)  # splittere ekle #
        splitter.setStretchFactor(2, 0)  # sağ sabit #

        # ---- İlk yükleme ---- #
        self.reload_customer()  # müşteri bilgisini yükle #
        self.reload_products()  # ürünleri yükle #

        # ---- Ürün listesinde tıklama ile sepete ekleme ---- #
        self.list_products.itemClicked.connect(self.on_product_click)  # tıklama olayı #

    # ==============================
    #  Veri yükleme / yenileme
    # ==============================
    def reload_customer(self):  # müşteri özetini yeniler #
        m = db_get_customer(self.customer_id)  # DB'den müşteri #
        if not m:
            self.lbl_customer.setText("Müşteri bulunamadı")  # hata #
            return  # çık #
        text = f"ID: {m['CustomerID']} | Ad: {m['CustomerName']} | Bütçe: {tl(m['Budget'])} | Harcama: {tl(m['TotalSpent'])} | Tip: {m['CustomerType']}"  # özet #
        self.lbl_customer.setText(text)  # etikete yaz #

    def reload_products(self):  # ürün listesini yeniler #
        self.products_raw = db_get_products()  # tüm ürünler #
        self.products = list(self.products_raw)  # kopya #
        self.render_products(self.products)  # listeyi çiz #

    # ==============================
    #  Filtre / Sıralama / Arama
    # ==============================
    def apply_filters(self):  # filtre ve arama uygular #
        q = self.search_input.text().strip().lower()  # arama metni #
        minv = self._to_float(self.min_price.text(), 0)  # min fiyat #
        maxv = self._to_float(self.max_price.text(), 1e12)  # max fiyat #

        arr = [p for p in self.products_raw if (q in (p["title"] + " shoply").lower()) and (minv <= p["price"] <= maxv)]  # basit filtre #
        sort = self.sort_box.currentText()  # seçilen sıralama #
        if sort == "Fiyat Artan":
            arr.sort(key=lambda x: x["price"])  # artan #
        elif sort == "Fiyat Azalan":
            arr.sort(key=lambda x: x["price"], reverse=True)  # azalan #
        elif sort == "En Yeni":
            arr = list(reversed(arr))  # basit simülasyon #
        self.products = arr  # güncelle #
        self.render_products(arr)  # listeyi çiz #

    def _to_float(self, s, default):  # güvenli float çeviri #
        try:
            return float(s.replace(",", "."))  # virgül-nokta uyumu #
        except:
            return default  # hata varsa varsayılan #

    # ==============================
    #  Ürün ve sepet işlemleri
    # ==============================
    def render_products(self, items):  # ürünleri QListWidget'e çizer #
        self.list_products.clear()  # temizle #
        for p in items:
            it = QListWidgetItem(f"{p['title']}  |  {tl(p['price'])}  |  Stok: {p['stock']}  |  (Tıkla: Sepete 1 adet ekle)")  # metin #
            it.setData(Qt.UserRole, p)  # ürün objesi #
            self.list_products.addItem(it)  # ekle #
        self.lbl_count.setText(f"{len(items)} ürün bulundu")  # sayaç #

    def on_product_click(self, item):  # ürün tıklanınca #
        p = item.data(Qt.UserRole)  # ürün objesi #
        self.add_to_cart(p)  # sepete ekle #
        self.try_order(p)  # DB sipariş + tamamla #

    def add_to_cart(self, p):  # UI sepetine 1 adet ekler #
        # Sepette var mı? qty artır #
        for row in self.cart:
            if row["id"] == p["id"]:
                row["qty"] += 1  # adet artır #
                break  # dur #
        else:
            self.cart.append({"id": p["id"], "title": p["title"], "price": p["price"], "qty": 1})  # yeni ekle #
        self.render_cart()  # sepeti çiz #

    def render_cart(self):  # sepet listesini çizer #
        self.list_cart.clear()  # temizle #
        sub = 0.0  # ara toplam #
        for row in self.cart:
            line = f"{row['title']} x{row['qty']}  →  {tl(row['price']*row['qty'])}"  # satır metni #
            self.list_cart.addItem(line)  # ekle #
            sub += row["price"] * row["qty"]  # toplam ekle #
        self.lbl_sub.setText(tl(sub))  # ara toplam #
        self.lbl_total.setText(tl(sub))  # kargo=0 kabul #

    # ==============================
    #  DB sipariş akışı
    # ==============================
    def try_order(self, p):  # DB'de sipariş ver + tamamla #
        try:
            oid = db_order_create(self.customer_id, p["id"], 1)  # 1 adet sipariş #
            db_order_complete(oid)  # siparişi tamamla #
            self.reload_customer()  # müşteri özetini yenile #
        except Exception as e:
            QMessageBox.warning(self, "Sipariş Hatası", str(e))  # kullanıcıya göster #

# ==============================
#  Uygulama başlatma
# ==============================
if __name__ == "__main__":  # doğrudan çalıştırıldığında #
    app = QApplication(sys.argv)  # Qt uygulaması #
    w = MainWindow(customer_id=3)  # örnek müşteri ID 3 #
    w.show()  # pencere göster #
    sys.exit(app.exec())  # döngü #
