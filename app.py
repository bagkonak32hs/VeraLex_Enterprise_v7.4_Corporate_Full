#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VeraLex Enterprise v7.3 (single-file UI)
- Başlatma sırası ve hata günlükleri düzeltildi
- Tüm sekmelerde wrap'lı toolbar
- İİK hiyerarşik takip türleri (Ana/Alt)
- "Dosya Aç" ekranında türe göre dinamik alanlar
- Dosyalar listesi -> çift tık ile Dosya Detayı sekmesi
- Dosya detayı içinden alacak/masraf/not yönetimi + canlı toplamlar
- TXT/DOCX/PDF şablon üretimi, CSV/PDF raporlar, pivot
Not: db.py ve auth.py mevcut mimaride kalır.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import json, csv, os, datetime, traceback, zipfile, io

# ----------------- Helpers -----------------
def export_treeview_xls(tv, path, title="Veri"):
    rows = [tv.item(i, "values") for i in tv.get_children()]
    headers = [tv.heading(c)["text"] for c in tv["columns"]]
    def cell(v):
        v = str(v).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        return f"<Cell><Data ss:Type='String'>{v}</Data></Cell>"
    xml = [
        "<?xml version='1.0'?>",
        "<?mso-application progid='Excel.Sheet'?>",
        "<Workbook xmlns='urn:schemas-microsoft-com:office:spreadsheet'"
        " xmlns:o='urn:schemas-microsoft-com:office:office'"
        " xmlns:x='urn:schemas-microsoft-com:office:excel'"
        " xmlns:ss='urn:schemas-microsoft-com:office:spreadsheet'>",
        f"<Worksheet ss:Name='{title}'>","<Table>",
        "<Row>" + "".join(cell(h) for h in headers) + "</Row>"
    ]
    for r in rows:
        xml.append("<Row>" + "".join(cell(v) for v in r) + "</Row>")
    xml.append("</Table></Worksheet></Workbook>")
    Path(path).write_text("".join(xml), encoding="utf-8")

class Pager:
    def __init__(self, fetch_fn, page=0, size=100):
        self.fetch_fn = fetch_fn; self.page = page; self.size = size; self.term = ""
    def set_term(self, t): self.term = t; self.page = 0
    def next(self): self.page += 1
    def prev(self): self.page = max(0, self.page - 1)
    def fetch(self): return self.fetch_fn(self.term, self.page, self.size)

# ----------------- App constants & imports -----------------
APP  = "VeraLex Enterprise v7.3"
BASE = Path(__file__).parent

import db, auth  # proje içindeki modüller

# ----------------- Tiny PDF & minimal DOCX -----------------
def write_multipage_pdf(path, title, lines):
    def esc(s): return s.replace("\\","\\\\").replace("(","\\(").replace(")","\\)")
    pages=[]; y_start=800; y=y_start
    page_lines=["BT","/F1 12 Tf","0 0 0 rg"]
    page_lines.append(f"1 0 0 1 50 {y} Tm ( {esc(title)} ) Tj"); y -= 24
    for ln in lines:
        if y < 60:
            page_lines.append("ET"); pages.append("\n".join(page_lines).encode("latin-1","ignore"))
            y=y_start; page_lines=["BT","/F1 12 Tf","0 0 0 rg"]
            page_lines.append(f"1 0 0 1 50 {y} Tm ( {esc(title)} ) Tj"); y -= 24
        page_lines.append(f"1 0 0 1 50 {y} Tm ( {esc(str(ln))} ) Tj"); y -= 16
    page_lines.append("ET"); pages.append("\n".join(page_lines).encode("latin-1","ignore"))

    objs=[]; add=lambda o:(objs.append(o), len(objs))[1]
    add("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    add("5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    page_ids=[]
    for content in pages:
        cid=len(objs)+2; add(f"{cid} 0 obj << /Length {len(content)} >> stream\n".encode()+content+b"\nendstream\nendobj\n")
        pid=len(objs)+2; add(f"{pid} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents {cid} 0 R >> endobj\n")
        page_ids.append(pid)
    kids=" ".join(f"{i} 0 R" for i in page_ids)
    objs.insert(1, f"2 0 obj << /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >> endobj\n")
    xref=[]; pdf=b"%PDF-1.4\n"
    for o in objs:
        xref.append(len(pdf)); pdf += o if isinstance(o,bytes) else o.encode("latin-1")
    xrefpos=len(pdf)
    pdf += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
    for off in xref: pdf += f"{off:010d} 00000 n \n".encode()
    pdf += b"trailer << /Size " + str(len(objs)+1).encode() + b" /Root 1 0 R >>\nstartxref\n" + str(xrefpos).encode() + b"\n%%EOF"
    Path(path).write_bytes(pdf)

def write_simple_docx(path, title, lines):
    from zipfile import ZipFile, ZIP_DEFLATED
    head = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>"""
    def p(text, bold=False):
        run=f"<w:r>{'<w:rPr><w:b/></w:rPr>' if bold else ''}<w:t>{text}</w:t></w:r>"
        return f"<w:p>{run}</w:p>"
    esc=lambda t:(t or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    body=[p(title,True)] + [p(esc(ln)) for ln in lines]; tail="</w:body></w:document>"
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    ctypes = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    with ZipFile(path,"w",ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", head + "".join(body) + tail)

# ----------------- Theming -----------------
def theming(style: ttk.Style):
    colors = {
        "bg": "#0E1428",
        "panel": "#1C2439",
        "panel_alt": "#111827",
        "text": "#E5E7EB",
        "accent": "#2D72FF",
        "gold": "#E9C46A"
    }
    style.theme_use("clam")
    style.configure("TLabel", background=colors["panel"], foreground=colors["text"], font=("Segoe UI", 10))
    style.configure("TFrame", background=colors["panel"])
    style.configure("TButton", background=colors["accent"], foreground="white", font=("Segoe UI", 10, "bold"), padding=(8,4))
    style.configure("TNotebook", background=colors["bg"])
    style.configure("TNotebook.Tab", padding=[12, 6])
    style.configure("Treeview", background=colors["panel_alt"], foreground=colors["text"], fieldbackground=colors["panel_alt"])
    style.configure("Treeview.Heading", background=colors["accent"], foreground="white", font=("Segoe UI", 9, "bold"))
    return colors


# ----------------- Shared toolbar (wrap'lı) -----------------
def make_toolbar(parent, buttons, wrap=6):
    bar = ttk.Frame(parent); bar.pack(anchor="w", padx=10, pady=8)
    for i,(text,cmd) in enumerate(buttons):
        r,c = divmod(i, wrap)
        b = ttk.Button(bar, text=text, command=cmd); b.grid(row=r, column=c, padx=6, pady=4, sticky="w")
    for c in range(min(wrap, len(buttons))): bar.columnconfigure(c, weight=0)
    return bar

# ----------------- İİK Takip Türleri (Ana -> Alt tür) -----------------
IIK_TYPES = {
    "İlamsız İcra": [
        "Genel Haciz Yoluyla","Kambiyo Senetlerine Mahsus",
        "Kira Alacağı (Tahliye/Alacak)","Rehnin Paraya Çevrilmesi (İlamsız)",
        "Tahsil/Teminat","İhtiyati Haciz Uygulaması"
    ],
    "İlamlı Takip": [
        "İlamlı Haciz (Alacak)","Tahliye (İlamlı)","Tazminat/Alacak (İlamlı)","Nafaka (İlamlı)"
    ],
    "İflas ve Konkordato": ["İflas Yoluyla Takip","Tasfiye İşlemleri","Konkordato"],
    "Rehnin Paraya Çevrilmesi": ["Taşınır Rehni","Taşınmaz (İpotek) Rehni","Ticari İşletme Rehni"],
    "Dava": ["Alacak Davası","İtirazın İptali","Menfi Tespit","İstirdat","İtirazın Kaldırılması","İcra Mahkemesi Şikayetleri"],
    "Diğer": ["Çek/Senet Takibi","Haksız İcra/Alacak","Yardımcı İşlemler"]
}

# ----------------- Login -----------------
class Login(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Giriş"); self.resizable(False, False); self.result=None
        f=ttk.Frame(self); f.pack(padx=12, pady=12)
        ttk.Label(f,text="Kullanıcı").grid(row=0,column=0,sticky="e",padx=6,pady=6)
        ttk.Label(f,text="Parola").grid(row=1,column=0,sticky="e",padx=6,pady=6)
        self.e_u=ttk.Entry(f); self.e_p=ttk.Entry(f, show="•")
        self.e_u.grid(row=0,column=1); self.e_p.grid(row=1,column=1)
        ttk.Button(f,text="Giriş",command=self.ok).grid(row=2,column=0,columnspan=2,pady=8,sticky="ew")
        self.bind("<Return>", lambda e: self.ok()); self.e_u.focus_set()
    def ok(self):
        u=self.e_u.get().strip(); p=self.e_p.get()
        cred=auth.check_login(u,p)
        if cred: self.result=cred; self.destroy()
        else: messagebox.showerror(APP,"Kullanıcı adı/parola yanlış veya pasif.")

# ----------------- Main App -----------------
class App(ttk.Frame):
    def __init__(self, master, user, role):
        super().__init__(master); self.user=user; self.role=role
        self.colors=theming(ttk.Style()); self.pack(fill="both", expand=True)
        self._case_tabs = {}  # case_id -> {"tab":..., "refresh_totals":fn}
        self.build(); self.refresh_all()
        self.master.bind_all('<Control-n>', lambda e: self.nb.select(self.t_new))
        self.master.bind_all('<Control-f>', lambda e: self.nb.select(self.t_cases))
        self.master.bind_all('<F5>', lambda e: self.refresh_all())
        self.after(30_000, self._auto_backup_tick)

    def skin_text(self, t):
        try:
            t.configure(bg=self.colors.get("panel_alt"), fg=self.colors.get("text"), insertbackground=self.colors.get("text"))
            t.configure(insertbackground="#E5E7EB")
        except Exception:
            pass

    # ---------- UI Builders ----------
    def build(self):
        self.master.option_add("*tearOff", False)
        m=tk.Menu(self.master); self.master.config(menu=m)
        m_i=tk.Menu(m); m.add_cascade(label="Entegrasyonlar", menu=m_i)
        m_i.add_command(label="UYAP Senkronize", command=self.menu_uyap)
        m_i.add_command(label="e-Tebligat Sorgu", command=self.menu_eteb)
        m_i.add_command(label="Muhasebe Aktarım", command=self.menu_acc)
        m_cfg=tk.Menu(m); m.add_cascade(label="Ayarlar", menu=m_cfg)
        m_cfg.add_command(label="Entegrasyon Ayarları", command=self.menu_settings)
        if self.role != "admin": m_cfg.entryconfig(0, state="disabled")

        self.nb=ttk.Notebook(self); self.nb.pack(fill="both", expand=True)
        self.t_dash=ttk.Frame(self.nb); self.nb.add(self.t_dash,text="Dashboard")
        self.t_clients=ttk.Frame(self.nb); self.nb.add(self.t_clients,text="Müvekkiller")
        self.t_debtors=ttk.Frame(self.nb); self.nb.add(self.t_debtors,text="Borçlular")
        self.t_new=ttk.Frame(self.nb); self.nb.add(self.t_new,text="Dosya Aç")
        self.t_cases=ttk.Frame(self.nb); self.nb.add(self.t_cases,text="Dosyalar")
        self.t_docs=ttk.Frame(self.nb); self.nb.add(self.t_docs,text="Belgeler")
        self.t_rep=ttk.Frame(self.nb); self.nb.add(self.t_rep,text="Raporlar")
        self.t_imp=ttk.Frame(self.nb); self.nb.add(self.t_imp,text="İçe Aktar")
        self.t_rem=ttk.Frame(self.nb); self.nb.add(self.t_rem,text="Hatırlatıcılar")
        self.t_aud=ttk.Frame(self.nb); self.nb.add(self.t_aud,text="Audit")
        self.t_logs=ttk.Frame(self.nb); self.nb.add(self.t_logs,text="Günlükler")
        self.t_trash=ttk.Frame(self.nb); self.nb.add(self.t_trash,text="Geri Dönüşüm")
        if self.role == "admin":
            self.t_users=ttk.Frame(self.nb); self.nb.add(self.t_users,text="Kullanıcılar")

        # Sekmeler
        self.ui_dash(self.t_dash)
        self.ui_clients(self.t_clients)
        self.ui_debtors(self.t_debtors)
        self.ui_newcase(self.t_new)
        self.ui_cases(self.t_cases)
        self.ui_docs(self.t_docs)
        self.ui_reports(self.t_rep)
        self.ui_import(self.t_imp)
        self.ui_rem(self.t_rem)
        self.ui_aud(self.t_aud)
        self.ui_logs(self.t_logs)
        self.ui_trash(self.t_trash)
        if self.role == "admin": self.ui_users(self.t_users)

    # ---------- TreeView Utils ----------
    def tv(self, p, cols):
        tv=ttk.Treeview(p, columns=list(range(len(cols))), show="headings")
        for i,h in enumerate(cols):
            tv.heading(i, text=h); tv.column(i, width=140, anchor="w")
        vs=ttk.Scrollbar(p, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=vs.set)
        tv.pack(side="left", fill="both", expand=True); vs.pack(side="right", fill="y")
        return tv
    def tv_sel(self, tv):
        it=tv.selection()
        return tv.item(it[0], "values") if it else None

    # ---------- Dashboard ----------
    def ui_dash(self,p):
        box=ttk.Labelframe(p, text="Genel Durum"); box.pack(fill="x", padx=12, pady=12)
        s=db.q("SELECT COUNT(*) n FROM cases")[0]["n"]
        r=db.q("SELECT COUNT(*) n FROM reminders WHERE done=0")[0]["n"]
        row=ttk.Frame(box); row.pack(fill="x", padx=8, pady=6)
        ttk.Label(row,text="Toplam Dosya:", width=20).pack(side="left"); ttk.Label(row,text=str(s)).pack(side="left")
        row2=ttk.Frame(box); row2.pack(fill="x", padx=8, pady=6)
        ttk.Label(row2,text="Açık Hatırlatıcı:", width=20).pack(side="left")
        ttk.Label(row2,text=str(r), foreground="#F59E0B").pack(side="left")

    # ---------- Clients ----------
    def ui_clients(self,p):
        make_toolbar(p, [("Ekle", self.cli_add), ("Sil", self.cli_del)], wrap=8)
        sbar=ttk.Frame(p); sbar.pack(fill="x", padx=10, pady=(0,6))
        ttk.Label(sbar,text="Ara").pack(side="right", padx=6); e_search=ttk.Entry(sbar); e_search.pack(side="right")
        self.tv_cli = self.tv(p, ["id","Ad","TCKN/VKN","Telefon","Email"])
        make_toolbar(p, [("Listeyi XLS dışa aktar", lambda: self.grid_to_xls(self.tv_cli,"müvekkiller"))], wrap=8)
        self.cli_pager = Pager(lambda term,pg,sz: db.q(
            "SELECT id,name,national_id,phone,email FROM clients "
            "WHERE name LIKE ? OR COALESCE(national_id,'') LIKE ? "
            "ORDER BY id DESC LIMIT ? OFFSET ?", (f"%{term}%", f"%{term}%", sz, pg*sz)))

        e_search.bind("<KeyRelease>", lambda e: (self.cli_pager.set_term(e_search.get().strip()), self.cli_load()))
        make_toolbar(p, [("◀ Önceki", lambda:(self.cli_pager.prev(), self.cli_load())),
                         ("Sonraki ▶", lambda:(self.cli_pager.next(), self.cli_load()))], wrap=8)
        self.cli_load()
    def cli_load(self):
        self.tv_cli.delete(*self.tv_cli.get_children())
        rows = self.cli_pager.fetch() if hasattr(self,'cli_pager') else db.q("SELECT id,name,national_id,phone,email FROM clients ORDER BY id DESC")
        for r in rows:
            self.tv_cli.insert("", "end", values=[r["id"], r["name"], r["national_id"] or "", r["phone"] or "", r["email"] or ""])
    def cli_add(self):
        w=tk.Toplevel(self); w.title("Müvekkil")
        e={k: ttk.Entry(w) for k in ["name","national_id","phone","email","address","poa_no","poa_date","poa_baro","poa_attorney"]}
        layout=[("Ad","name"),("TCKN/VKN","national_id"),("Telefon","phone"),("Email","email"),
                ("Adres","address"),("Vekalet No","poa_no"),("Vekalet Tarih","poa_date"),("Baro","poa_baro"),("Avukat","poa_attorney")]
        for L,K in layout:
            f=ttk.Frame(w); f.pack(fill="x", padx=8, pady=3); ttk.Label(f,text=L, width=16).pack(side="left"); e[K].pack(side="left", fill="x", expand=True)
        tx=tk.Text(w, height=4); tx.pack(fill="x", padx=8, pady=6); self.skin_text(tx)
        def save():
            db.exec("INSERT INTO clients(name,national_id,phone,email,address,poa_no,poa_date,poa_baro,poa_attorney,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (e["name"].get().strip(), e["national_id"].get().strip(), e["phone"].get().strip(), e["email"].get().strip(),
                     e["address"].get().strip(), e["poa_no"].get().strip(), e["poa_date"].get().strip(),
                     e["poa_baro"].get().strip(), e["poa_attorney"].get().strip(), tx.get("1.0","end-1c")))
            w.destroy(); self.cli_load(); self.audit("client_add", e["name"].get().strip())
        make_toolbar(w, [("Kaydet", save)], wrap=6)
    def cli_del(self):
        v=self.tv_sel(self.tv_cli); 
        if not v: return
        row = db.q("SELECT * FROM clients WHERE id=?", (v[0],))
        self.soft_delete("clients", row[0] if row else {"id":v[0]})
        db.exec("DELETE FROM clients WHERE id=?", (v[0],)); self.cli_load(); self.audit("client_del", str(v[0]))

    # ---------- Debtors ----------
    def ui_debtors(self,p):
        make_toolbar(p, [("Ekle", self.deb_add), ("Sil", self.deb_del)], wrap=8)
        sbar=ttk.Frame(p); sbar.pack(fill="x", padx=10, pady=(0,6))
        ttk.Label(sbar,text="Ara").pack(side="right", padx=6); e_search=ttk.Entry(sbar); e_search.pack(side="right")
        self.tv_deb = self.tv(p, ["id","Ad","TCKN/VKN","Telefon","Email"])
        make_toolbar(p, [("Listeyi XLS dışa aktar", lambda: self.grid_to_xls(self.tv_deb,"borçlular"))], wrap=8)
        self.deb_pager = Pager(lambda term,pg,sz: db.q(
            "SELECT id,name,national_id,phone,email FROM debtors "
            "WHERE name LIKE ? OR COALESCE(national_id,'') LIKE ? "
            "ORDER BY id DESC LIMIT ? OFFSET ?", (f"%{term}%", f"%{term}%", sz, pg*sz)))

        e_search.bind("<KeyRelease>", lambda e: (self.deb_pager.set_term(e_search.get().strip()), self.deb_load()))
        make_toolbar(p, [("◀ Önceki", lambda:(self.deb_pager.prev(), self.deb_load())),
                         ("Sonraki ▶", lambda:(self.deb_pager.next(), self.deb_load()))], wrap=8)
        self.deb_load()
    def deb_load(self):
        self.tv_deb.delete(*self.tv_deb.get_children())
        rows = self.deb_pager.fetch() if hasattr(self,'deb_pager') else db.q("SELECT id,name,national_id,phone,email FROM debtors ORDER BY id DESC")
        for r in rows:
            self.tv_deb.insert("", "end", values=[r["id"], r["name"], r["national_id"] or "", r["phone"] or "", r["email"] or ""])
    def deb_add(self):
        w=tk.Toplevel(self); w.title("Borçlu")
        e={k: ttk.Entry(w) for k in ["name","national_id","phone","email","address"]}
        for L,K in [("Ad","name"),("TCKN/VKN","national_id"),("Telefon","phone"),("Email","email"),("Adres","address")]:
            f=ttk.Frame(w); f.pack(fill="x", padx=8, pady=3); ttk.Label(f,text=L, width=16).pack(side="left"); e[K].pack(side="left", fill="x", expand=True)
        tx=tk.Text(w, height=4); tx.pack(fill="x", padx=8, pady=6); self.skin_text(tx)
        def save():
            db.exec("INSERT INTO debtors(name,national_id,phone,email,address,notes) VALUES (?,?,?,?,?,?)",
                    (e["name"].get().strip(), e["national_id"].get().strip(), e["phone"].get().strip(),
                     e["email"].get().strip(), e["address"].get().strip(), tx.get("1.0","end-1c")))
            w.destroy(); self.deb_load(); self.audit("debtor_add", e["name"].get().strip())
        make_toolbar(w, [("Kaydet", save)], wrap=6)
    def deb_del(self):
        v=self.tv_sel(self.tv_deb); 
        if not v: return
        row = db.q("SELECT * FROM debtors WHERE id=?", (v[0],))
        self.soft_delete("debtors", row[0] if row else {"id":v[0]})
        db.exec("DELETE FROM debtors WHERE id=?", (v[0],)); self.deb_load(); self.audit("debtor_del", str(v[0]))

    # ---------- New Case (İİK hiyerarşi + dinamik alanlar) ----------
    def ui_newcase(self,p):
        box=ttk.Labelframe(p, text="Takip/Dava Bilgileri"); box.pack(fill="x", padx=10, pady=8)
        ttk.Label(box,text="Ana Tür").grid(row=0,column=0, sticky="e", padx=6, pady=6)
        cb_main = ttk.Combobox(box, values=list(IIK_TYPES.keys()), state="readonly")
        cb_main.grid(row=0,column=1, sticky="ew", padx=6)
        ttk.Label(box,text="Alt Tür").grid(row=0,column=2, sticky="e", padx=6, pady=6)
        cb_sub  = ttk.Combobox(box, values=[], state="readonly")
        cb_sub.grid(row=0,column=3, sticky="ew", padx=6)
        box.columnconfigure(1, weight=1); box.columnconfigure(3, weight=1)

        def on_main_changed(_e=None):
            subs = IIK_TYPES.get(cb_main.get() or "", [])
            cb_sub["values"] = subs
            if subs: cb_sub.current(0)
        cb_main.bind("<<ComboboxSelected>>", on_main_changed)
        if IIK_TYPES: cb_main.current(0); on_main_changed()

        # Müvekkil / Borçlu / Dosya No
        row1=ttk.Frame(p); row1.pack(fill="x", padx=10, pady=6)
        ttk.Label(row1, text="Müvekkil").pack(side="left")
        cb_c = ttk.Combobox(row1, values=[f"{r['id']} - {r['name']}" for r in db.q("SELECT id,name FROM clients ORDER BY name")])
        cb_c.pack(side="left", padx=6, fill="x", expand=True)
        ttk.Label(row1, text="Borçlu").pack(side="left")
        cb_d = ttk.Combobox(row1, values=[f"{r['id']} - {r['name']}" for r in db.q("SELECT id,name FROM debtors ORDER BY name")])
        cb_d.pack(side="left", padx=6, fill="x", expand=True)
        ttk.Label(row1, text="Dosya No").pack(side="left")
        e_fn = ttk.Entry(row1); e_fn.pack(side="left", padx=6)

        # Dinamik alanlar (İlamsız / İlamlı)
        dyn_state = {"recv_sum": "", "desc": "", "judg_no": "", "judg_dt": "", "court": ""}
        self._dyn_reader = lambda: {}
        dyn_wrap = ttk.Frame(p); dyn_wrap.pack(fill="x", padx=10, pady=6)

        def clear_wrap():
            for w in dyn_wrap.winfo_children(): w.destroy()

        def set_reader(fn):
            self._dyn_reader = fn

        def draw_ilamsiz():
            clear_wrap()
            lf = ttk.Labelframe(dyn_wrap, text="Ek Bilgiler (İlamsız)"); lf.pack(fill="x")
            ttk.Label(lf, text="Alacak Kalem Özeti").grid(row=0, column=0, sticky="e", padx=6, pady=4)
            e_recv = ttk.Entry(lf); e_recv.grid(row=0, column=1, sticky="ew", padx=6, pady=4); e_recv.insert(0, dyn_state["recv_sum"])
            ttk.Label(lf, text="Açıklama").grid(row=0, column=2, sticky="e", padx=6, pady=4)
            e_desc = ttk.Entry(lf); e_desc.grid(row=0, column=3, sticky="ew", padx=6, pady=4); e_desc.insert(0, dyn_state["desc"])
            lf.columnconfigure(1, weight=1); lf.columnconfigure(3, weight=1)
            def read_values():
                dyn_state["recv_sum"] = e_recv.get().strip()
                dyn_state["desc"]     = e_desc.get().strip()
                return {"receivable_summary": dyn_state["recv_sum"], "desc": dyn_state["desc"]}
            set_reader(read_values)

        def draw_ilamli():
            clear_wrap()
            lf = ttk.Labelframe(dyn_wrap, text="Ek Bilgiler (İlamlı)"); lf.pack(fill="x")
            ttk.Label(lf, text="İlam No").grid(row=0, column=0, sticky="e", padx=6, pady=4)
            e_no = ttk.Entry(lf); e_no.grid(row=0, column=1, sticky="ew", padx=6, pady=4); e_no.insert(0, dyn_state["judg_no"])
            ttk.Label(lf, text="İlam Tarihi (YYYY-MM-DD)").grid(row=0, column=2, sticky="e", padx=6, pady=4)
            e_dt = ttk.Entry(lf); e_dt.grid(row=0, column=3, sticky="ew", padx=6, pady=4); e_dt.insert(0, dyn_state["judg_dt"])
            ttk.Label(lf, text="Mahkeme").grid(row=1, column=0, sticky="e", padx=6, pady=4)
            e_ct = ttk.Entry(lf); e_ct.grid(row=1, column=1, sticky="ew", padx=6, pady=4); e_ct.insert(0, dyn_state["court"])
            ttk.Label(lf, text="Açıklama").grid(row=1, column=2, sticky="e", padx=6, pady=4)
            e_desc = ttk.Entry(lf); e_desc.grid(row=1, column=3, sticky="ew", padx=6, pady=4); e_desc.insert(0, dyn_state["desc"])
            lf.columnconfigure(1, weight=1); lf.columnconfigure(3, weight=1)
            def read_values():
                dyn_state["judg_no"] = e_no.get().strip()
                dyn_state["judg_dt"] = e_dt.get().strip()
                dyn_state["court"]   = e_ct.get().strip()
                dyn_state["desc"]    = e_desc.get().strip()
                return {"judgment":{"number":dyn_state["judg_no"],"date":dyn_state["judg_dt"],"court":dyn_state["court"]},
                        "desc": dyn_state["desc"]}
            set_reader(read_values)

        def redraw_dynamic():
            if cb_main.get() == "İlamlı Takip": draw_ilamli()
            else: draw_ilamsiz()
        cb_main.bind("<<ComboboxSelected>>", lambda e: redraw_dynamic())
        redraw_dynamic()

        def parse_id(v):
            if not v: return None
            try: return int(v.split(" - ")[0])
            except:
                try: return int(v)
                except: return None

        def open_case():
            main=cb_main.get() or ""; sub=cb_sub.get() or ""
            typ=f"{main} / {sub}" if sub else main
            meta={"type":{"main":main,"sub":sub},"created_at":datetime.date.today().isoformat()}
            try: extra=self._dyn_reader() if self._dyn_reader else {}
            except Exception: extra={}
            if isinstance(extra,dict): meta.update(extra)
            notes_json=json.dumps({"meta":meta}, ensure_ascii=False)
            db.exec("INSERT INTO cases(case_type, client_id, debtor_id, file_no, status, opened_at, notes) VALUES (?,?,?,?,?,?,?)",
                    (typ, parse_id(cb_c.get()), parse_id(cb_d.get()), e_fn.get().strip(), "Açık",
                     datetime.date.today().isoformat(), notes_json))
            self.refresh_all(); self.audit("case_open", e_fn.get().strip() or typ)
            last=db.q("SELECT id FROM cases ORDER BY id DESC LIMIT 1")
            if last: self.open_case_detail(last[0]["id"])

        make_toolbar(p, [("Dosya Aç", open_case)], wrap=6)

    # ---------- Cases (liste -> çift tıkla detay sekmesi) ----------
    def ui_cases(self,p):
        self.tv_cases = self.tv(p, ["id","Dosya","Tür","Müvekkil","Borçlu","Toplam Alacak","Toplam Masraf"])
        make_toolbar(p, [("Listeyi XLS dışa aktar", lambda: self.grid_to_xls(self.tv_cases,"dosyalar"))], wrap=8)
        self.case_load()
        make_toolbar(p, [("Alacak Ekle", self.recv_add_from_list),
                         ("Masraf Ekle", self.exp_add_from_list),
                         ("Notlar",      self.case_notes_from_list)], wrap=6)
        self.tv_cases.bind("<Double-1>", lambda e: self._on_case_double())
    def _on_case_double(self):
        v=self.tv_sel(self.tv_cases)
        if not v: return
        self.open_case_detail(int(v[0]))
    def case_load(self):
        self.tv_cases.delete(*self.tv_cases.get_children())
        rows = db.q("""
SELECT c.id, c.file_no, c.case_type,
       COALESCE(cl.name,'-') client, COALESCE(d.name,'-') debtor,
       COALESCE((SELECT SUM(r.amount) FROM receivables r WHERE r.case_id=c.id),0) recv,
       COALESCE((SELECT SUM(e.amount) FROM expenses e WHERE e.case_id=c.id),0) exp
FROM cases c
LEFT JOIN clients cl ON cl.id=c.client_id
LEFT JOIN debtors d ON d.id=c.debtor_id
ORDER BY c.id DESC
""")
        for r in rows:
            self.tv_cases.insert("", "end", values=[r["id"], r["file_no"] or "-", r["case_type"] or "-",
                                                    r["client"], r["debtor"], f"{r['recv']:.2f}", f"{r['exp']:.2f}"])

    # --- Listeden hızlı ekleme ---
    def recv_add_from_list(self):
        v=self.tv_sel(self.tv_cases); 
        if not v: return
        self._recv_add_dialog(case_id=int(v[0]), after_save=self.case_load)
    def exp_add_from_list(self):
        v=self.tv_sel(self.tv_cases); 
        if not v: return
        self._exp_add_dialog(case_id=int(v[0]), after_save=self.case_load)
    def case_notes_from_list(self):
        v=self.tv_sel(self.tv_cases); 
        if not v: return
        self._notes_dialog(case_id=int(v[0]), title_suffix=f" - {v[1]}", after_save=self.case_load)

    # ---------- Case Detail ----------
    def open_case_detail(self, case_id:int):
        if case_id in self._case_tabs:
            self.nb.select(self._case_tabs[case_id]["tab"]); return
        tab=ttk.Frame(self.nb); self.nb.add(tab, text=f"Dosya #{case_id}"); self.nb.select(tab)
        self._case_tabs[case_id]={"tab":tab}

        head=db.q("""SELECT c.id, c.file_no, c.case_type,
                            COALESCE((SELECT name FROM clients WHERE id=c.client_id),'-') client,
                            COALESCE((SELECT name FROM debtors WHERE id=c.debtor_id),'-') debtor, c.notes
                     FROM cases c WHERE id=?""", (case_id,))
        info=head[0] if head else {}
        box=ttk.Labelframe(tab, text="Özet"); box.pack(fill="x", padx=10, pady=8)
        ttk.Label(box, text=f"Dosya No: {info.get('file_no','-')}").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(box, text=f"Tür: {info.get('case_type','-')}").grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(box, text=f"Müvekkil: {info.get('client','-')}").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(box, text=f"Borçlu: {info.get('debtor','-')}").grid(row=1, column=1, sticky="w", padx=6, pady=4)

        try: meta=json.loads(info.get("notes") or "{}").get("meta")
        except Exception: meta=None
        if meta:
            tmeta=ttk.Labelframe(tab, text="Meta"); tmeta.pack(fill="x", padx=10, pady=4)
            ttk.Label(tmeta, text=f"Ana Tür: {meta.get('type',{}).get('main','')} / Alt: {meta.get('type',{}).get('sub','')}").pack(anchor="w", padx=8, pady=2)
            if "judgment" in meta:
                j=meta["judgment"]
                ttk.Label(tmeta, text=f"İlam: {j.get('number','')}  Tarih: {j.get('date','')}  Mahkeme: {j.get('court','')}").pack(anchor="w", padx=8, pady=2)
            if meta.get("receivable_summary"):
                ttk.Label(tmeta, text=f"Alacak Özeti: {meta.get('receivable_summary')}").pack(anchor="w", padx=8, pady=2)
            if meta.get("desc"):
                ttk.Label(tmeta, text=f"Açıklama: {meta.get('desc')}").pack(anchor="w", padx=8, pady=2)

        # Alacaklar
        sec1=ttk.Labelframe(tab, text="Alacaklar"); sec1.pack(fill="both", expand=True, padx=10, pady=6)
        tv_r=self.tv(sec1, ["id","Kalem","Tutar","Para","Not"])
        def load_r():
            tv_r.delete(*tv_r.get_children())
            for r in db.q("SELECT id,item,amount,currency,note FROM receivables WHERE case_id=? ORDER BY id DESC",(case_id,)):
                tv_r.insert("", "end", values=[r["id"], r["item"], f"{r['amount']:.2f}", r["currency"] or "TRY", r["note"] or ""])
        make_toolbar(sec1, [("Ekle", lambda: self._recv_add_dialog(case_id, after_save=load_r)),
                            ("Sil", lambda: self._recv_del(tv_r, after_save=load_r))], wrap=10)
        load_r()

        # Masraflar
        sec2=ttk.Labelframe(tab, text="Masraflar"); sec2.pack(fill="both", expand=True, padx=10, pady=6)
        tv_e=self.tv(sec2, ["id","Tür","Tutar","Tarih","Not"])
        def load_e():
            tv_e.delete(*tv_e.get_children())
            rows=db.q("""SELECT e.id, COALESCE((SELECT name FROM dict_expense_types WHERE id=e.etype_id),'?') t,
                                e.amount, e.date, e.note
                         FROM expenses e WHERE e.case_id=? ORDER BY e.id DESC""",(case_id,))
            for r in rows:
                tv_e.insert("", "end", values=[r["id"], r["t"], f"{r['amount']:.2f}", r["date"] or "", r["note"] or ""])
        make_toolbar(sec2, [("Ekle", lambda: self._exp_add_dialog(case_id, after_save=load_e)),
                            ("Sil", lambda: self._exp_del(tv_e, after_save=load_e))], wrap=10)
        load_e()

        # Notlar
        make_toolbar(tab, [("Notları Aç/Düzenle", lambda: self._notes_dialog(case_id, title_suffix=f" - {info.get('file_no','')}"))], wrap=10)

        # Toplamlar
        def totals():
            tot_r=db.q("SELECT COALESCE(SUM(amount),0) t FROM receivables WHERE case_id=?", (case_id,))[0]["t"]
            tot_e=db.q("SELECT COALESCE(SUM(amount),0) t FROM expenses WHERE case_id=?", (case_id,))[0]["t"]
            return tot_r, tot_e, (tot_r - tot_e)
        sec3=ttk.Labelframe(tab, text="Özet"); sec3.pack(fill="x", padx=10, pady=8)
        l1=ttk.Label(sec3, text="Toplam Alacak: 0.00"); l1.pack(side="left", padx=8)
        l2=ttk.Label(sec3, text="Toplam Masraf: 0.00"); l2.pack(side="left", padx=8)
        l3=ttk.Label(sec3, text="NET: 0.00"); l3.pack(side="left", padx=8)
        def refresh_totals():
            a,b,c = totals()
            l1.config(text=f"Toplam Alacak: {a:.2f}"); l2.config(text=f"Toplam Masraf: {b:.2f}"); l3.config(text=f"NET: {c:.2f}")
        refresh_totals()
        self._case_tabs[case_id]["refresh_totals"]=refresh_totals

    # ---- dialogs for receivable/expense/notes ----
    def _recv_add_dialog(self, case_id:int, after_save=None):
        w=tk.Toplevel(self); w.title("Alacak")
        e_item=ttk.Entry(w); e_amt=ttk.Entry(w)
        cb_ty=ttk.Combobox(w, values=[f"{r['id']} - {r['name']}" for r in db.q("SELECT id,name FROM dict_receivable_types")])
        cb_cur=ttk.Combobox(w, values=["TRY","USD","EUR"])
        tx=tk.Text(w, height=4); self.skin_text(tx)
        for L,E in [("Kalem",e_item),("Tutar",e_amt),("Tür",cb_ty),("Para Birimi",cb_cur)]:
            f=ttk.Frame(w); f.pack(fill="x", padx=8, pady=3); ttk.Label(f,text=L, width=14).pack(side="left"); E.pack(side="left", fill="x", expand=True)
        tx.pack(fill="x", padx=8, pady=6)
        def pid(v):
            try: return int(v.split(" - ")[0])
            except: return None
        def save():
            db.exec("INSERT INTO receivables(case_id,rtype_id,item,amount,currency,note) VALUES (?,?,?,?,?,?)",
                    (case_id, pid(cb_ty.get()), e_item.get().strip(),
                     float((e_amt.get() or '0').replace(',','.')), cb_cur.get() or "TRY", tx.get("1.0","end-1c")))
            w.destroy(); 
            if after_save: after_save()
            if case_id in self._case_tabs and self._case_tabs[case_id].get("refresh_totals"): self._case_tabs[case_id]["refresh_totals"]()
            self.audit("recv_add", str(case_id))
        make_toolbar(w, [("Kaydet", save)], wrap=6)

    def _exp_add_dialog(self, case_id:int, after_save=None):
        w=tk.Toplevel(self); w.title("Masraf")
        e_amt=ttk.Entry(w)
        cb_ty=ttk.Combobox(w, values=[f"{r['id']} - {r['name']}" for r in db.q("SELECT id,name FROM dict_expense_types")])
        e_date=ttk.Entry(w); e_date.insert(0, datetime.date.today().isoformat())
        tx=tk.Text(w, height=4); self.skin_text(tx)
        for L,E in [("Tutar",e_amt),("Tür",cb_ty),("Tarih",e_date)]:
            f=ttk.Frame(w); f.pack(fill="x", padx=8, pady=3); ttk.Label(f,text=L, width=14).pack(side="left"); E.pack(side="left", fill="x", expand=True)
        tx.pack(fill="x", padx=8, pady=6)
        def pid(v):
            try: return int(v.split(" - ")[0])
            except: return None
        def save():
            db.exec("INSERT INTO expenses(case_id,etype_id,amount,date,note) VALUES (?,?,?,?,?)",
                    (case_id, pid(cb_ty.get()), float((e_amt.get() or '0').replace(',','.')),
                     e_date.get().strip(), tx.get("1.0","end-1c")))
            w.destroy()
            if after_save: after_save()
            if case_id in self._case_tabs and self._case_tabs[case_id].get("refresh_totals"): self._case_tabs[case_id]["refresh_totals"]()
            self.audit("exp_add", str(case_id))
        make_toolbar(w, [("Kaydet", save)], wrap=6)

    def _recv_del(self, tv, after_save=None):
        it=tv.selection(); 
        if not it: return
        rid=tv.item(it[0],"values")[0]; db.exec("DELETE FROM receivables WHERE id=?", (rid,))
        if after_save: after_save()
        self.audit("recv_del", str(rid))
    def _exp_del(self, tv, after_save=None):
        it=tv.selection(); 
        if not it: return
        eid=tv.item(it[0],"values")[0]; db.exec("DELETE FROM expenses WHERE id=?", (eid,))
        if after_save: after_save()
        self.audit("exp_del", str(eid))
    def _notes_dialog(self, case_id:int, title_suffix="", after_save=None):
        w=tk.Toplevel(self); w.title(f"Notlar{title_suffix}")
        tx=tk.Text(w, height=14); tx.pack(fill="both", expand=True, padx=8, pady=8); self.skin_text(tx)
        row=db.q("SELECT notes FROM cases WHERE id=?", (case_id,))
        if row: tx.insert("1.0", row[0].get("notes") or "")
        def save():
            db.exec("UPDATE cases SET notes=? WHERE id=?", (tx.get("1.0","end-1c"), case_id))
            w.destroy(); 
            if after_save: after_save()
            self.audit("case_notes", str(case_id))
        make_toolbar(w, [("Kaydet", save)], wrap=6)

    # ---------- Documents ----------
    def ui_docs(self,p):
        top=ttk.Frame(p); top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top,text="Şablon").pack(side="left")
        tpl_dir = BASE/"templates"; tpl_dir.mkdir(exist_ok=True)
        self.cb_tpl=ttk.Combobox(top, values=[x.name for x in tpl_dir.glob("*.txt")]); self.cb_tpl.pack(side="left", padx=6)
        def open_folder(d):
            try:
                if hasattr(os, "startfile"): os.startfile(str(d))
                else:
                    import sys, subprocess
                    subprocess.Popen(["open" if sys.platform=="darwin" else "xdg-open", str(d)])
            except Exception:
                messagebox.showinfo(APP, f"Klasör: {d}")
        make_toolbar(p, [("Üret (TXT)", self.tpl_txt),("Üret (DOCX)", self.tpl_docx),
                         ("Üret (PDF)", self.tpl_pdf),("Şablon Klasörü", lambda: open_folder(tpl_dir))], wrap=4)
        ttk.Separator(p, orient="horizontal").pack(fill="x", padx=10, pady=(6,2))
        ttk.Label(p,text="Değişkenler (JSON)").pack(anchor="w", padx=12)
        self.tx_vars=tk.Text(p, height=6); self.tx_vars.pack(fill="x", padx=10, pady=8); self.skin_text(self.tx_vars)
        self.tx_vars.insert("1.0", json.dumps({"client":"","debtor":"","file":"","court":"","today": datetime.date.today().strftime("%d.%m.%Y")}, ensure_ascii=False, indent=2))
    def tpl_render(self):
        if not self.cb_tpl.get(): messagebox.showwarning(APP,"Şablon seçin"); return None
        try: vars=json.loads(self.tx_vars.get("1.0","end-1c"))
        except Exception as e: messagebox.showerror(APP,f"JSON: {e}"); return None
        tpl=(BASE/"templates"/self.cb_tpl.get()).read_text(encoding="utf-8")
        for k,v in vars.items(): tpl=tpl.replace("{{"+k+"}}", str(v))
        return tpl
    def tpl_txt(self):
        out=self.tpl_render()
        if out is None: return
        p=filedialog.asksaveasfilename(defaultextension=".txt")
        if not p: return
        Path(p).write_text(out, encoding="utf-8"); messagebox.showinfo(APP,"TXT kaydedildi"); self.audit("txt_generate", self.cb_tpl.get())
    def tpl_docx(self):
        out=self.tpl_render(); 
        if out is None: return
        p=filedialog.asksaveasfilename(defaultextension=".docx")
        if not p: return
        write_simple_docx(p, "Belge", out.splitlines()); messagebox.showinfo(APP,"DOCX kaydedildi"); self.audit("docx_generate", self.cb_tpl.get())
    def tpl_pdf(self):
        out=self.tpl_render(); 
        if out is None: return
        p=filedialog.asksaveasfilename(defaultextension=".pdf")
        if not p: return
        write_multipage_pdf(p, "Belge", out.splitlines()); messagebox.showinfo(APP,"PDF kaydedildi"); self.audit("pdf_generate", self.cb_tpl.get())

    # ---------- Reports ----------
    def ui_reports(self,p):
        fl=ttk.Labelframe(p, text="Rapor Filtresi"); fl.pack(fill="x", padx=10, pady=8)
        ttk.Label(fl,text="Başlangıç (YYYY-MM-DD)").grid(row=0,column=0,sticky="w",padx=6,pady=4); self.rp_from=ttk.Entry(fl); self.rp_from.grid(row=0,column=1,sticky="ew",padx=6)
        ttk.Label(fl,text="Bitiş (YYYY-MM-DD)").grid(row=0,column=2,sticky="w",padx=6,pady=4); self.rp_to=ttk.Entry(fl); self.rp_to.grid(row=0,column=3,sticky="ew",padx=6)
        fl.columnconfigure(1, weight=1); fl.columnconfigure(3, weight=1)
        make_toolbar(p, [("Alacak CSV", self.rep_recv_csv),("Masraf CSV", self.rep_exp_csv),
                         ("Alacak PDF", self.rep_recv_pdf),("Masraf PDF", self.rep_exp_pdf),
                         ("Dosya Özeti (PDF)", self.rep_case_summary),("Kullanıcı Performans (PDF)", self.rep_user_perf),
                         ("Pivot (Masraf Türü x Ay)", self.rep_pivot)], wrap=4)
    def _dt_range_clause(self, table_alias):
        f=self.rp_from.get().strip(); t=self.rp_to.get().strip()
        where=""; params=()
        if f and t:
            if table_alias=="c": where="WHERE c.opened_at>=? AND (c.drop_date<=? OR c.drop_date IS NULL)"; params=(f,t)
            else: where=f"WHERE {table_alias}.date>=? AND {table_alias}.date<=?"; params=(f,t)
        return where, params
    def rep_recv_pdf(self):
        p=filedialog.asksaveasfilename(defaultextension=".pdf")
        if not p: return
        where, params = self._dt_range_clause("c")
        rows = db.q(f"SELECT c.file_no, SUM(r.amount) amt FROM receivables r JOIN cases c ON r.case_id=c.id {where} GROUP BY c.file_no ORDER BY amt DESC", params)
        lines = [f"{r['file_no']:>12}  {r['amt']:.2f} TL" for r in rows]
        write_multipage_pdf(p, "Alacak Raporu", lines); messagebox.showinfo(APP,"PDF hazır"); self.audit("rpt_recv_pdf", Path(p).name)
    def rep_exp_pdf(self):
        p=filedialog.asksaveasfilename(defaultextension=".pdf")
        if not p: return
        where, params = self._dt_range_clause("e")
        rows = db.q(f"SELECT c.file_no, SUM(e.amount) amt FROM expenses e JOIN cases c ON e.case_id=c.id {where} GROUP BY c.file_no ORDER BY amt DESC", params)
        lines = [f"{r['file_no']:>12}  {r['amt']:.2f} TL" for r in rows]
        write_multipage_pdf(p, "Masraf Raporu", lines); messagebox.showinfo(APP,"PDF hazır"); self.audit("rpt_exp_pdf", Path(p).name)
    def rep_recv_csv(self):
        p=filedialog.asksaveasfilename(defaultextension=".csv"); 
        if not p: return
        where, params = self._dt_range_clause("c")
        rows = db.q(f"SELECT c.file_no, SUM(r.amount) amt FROM receivables r JOIN cases c ON r.case_id=c.id {where} GROUP BY c.file_no ORDER BY amt DESC", params)
        with open(p,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f, delimiter=";"); w.writerow(["Dosya","Toplam Alacak"])
            for r in rows: w.writerow([r["file_no"], f"{r['amt']:.2f}"])
        messagebox.showinfo(APP,"CSV hazır"); self.audit("rpt_recv_csv", Path(p).name)
    def rep_exp_csv(self):
        p=filedialog.asksaveasfilename(defaultextension=".csv"); 
        if not p: return
        where, params = self._dt_range_clause("e")
        rows = db.q(f"SELECT c.file_no, SUM(e.amount) amt FROM expenses e JOIN cases c ON e.case_id=c.id {where} GROUP BY c.file_no ORDER BY amt DESC", params)
        with open(p,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f, delimiter=";"); w.writerow(["Dosya","Toplam Masraf"])
            for r in rows: w.writerow([r["file_no"], f"{r['amt']:.2f}"])
        messagebox.showinfo(APP,"CSV hazır"); self.audit("rpt_exp_csv", Path(p).name)
    def rep_pivot(self):
        rows = db.q("SELECT COALESCE(d.name,'(Belirsiz)') etype, COALESCE(SUBSTR(e.date,1,7),'(Yok)') ym, SUM(e.amount) amt FROM expenses e LEFT JOIN dict_expense_types d ON d.id=e.etype_id GROUP BY etype, ym ORDER BY ym DESC, etype")
        months=sorted({r["ym"] for r in rows}); etypes=sorted({r["etype"] for r in rows})
        data={(r["etype"], r["ym"]): r["amt"] for r in rows}
        w=tk.Toplevel(self); w.title("Pivot - Masraf Türü x Ay"); w.geometry("820x460")
        tv=ttk.Treeview(w, columns=list(range(len(months)+1)), show="headings")
        tv.heading(0, text="Tür"); tv.column(0, width=180, anchor="w")
        for i,m in enumerate(months, start=1): tv.heading(i, text=m); tv.column(i, width=120, anchor="e")
        vs=ttk.Scrollbar(w, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=vs.set)
        tv.pack(side="left", fill="both", expand=True); vs.pack(side="right", fill="y")
        for et in etypes:
            vals=[et] + [f"{data.get((et,m),0.0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") for m in months]
            tv.insert("", "end", values=vals)

    # ---------- Import ----------
    def ui_import(self,p):
        ttk.Label(p,text="CSV İçe Aktarım Sihirbazı").pack(anchor="w", padx=10, pady=(10,2))
        desc=("Şablonları indirip doldurun, sonra içe aktarın. (CSV ayırıcı ; )\n"
              "clients.csv: name,national_id,phone,email,address,poa_no,poa_date,poa_baro,poa_attorney,notes\n"
              "debtors.csv: name,national_id,phone,email,address,notes\n"
              "cases.csv: case_type,client_id,debtor_id,file_no,court,status,opened_at,drop_date,notes\n"
              "receivables.csv: case_id,rtype_id,item,amount,currency,note\n"
              "expenses.csv: case_id,etype_id,amount,date,note")
        ttk.Label(p,text=desc).pack(anchor="w", padx=10, pady=4)
        make_toolbar(p, [("Şablonları İndir (zip)", self.imp_templates),
                         ("CSV Seç ve İçe Aktar", self.imp_run)], wrap=6)
    def imp_templates(self):
        files={
            "clients.csv":["name","national_id","phone","email","address","poa_no","poa_date","poa_baro","poa_attorney","notes"],
            "debtors.csv":["name","national_id","phone","email","address","notes"],
            "cases.csv":["case_type","client_id","debtor_id","file_no","court","status","opened_at","drop_date","notes"],
            "receivables.csv":["case_id","rtype_id","item","amount","currency","note"],
            "expenses.csv":["case_id","etype_id","amount","date","note"]
        }
        p=filedialog.asksaveasfilename(defaultextension=".zip")
        if not p: return
        with zipfile.ZipFile(p,"w",zipfile.ZIP_DEFLATED) as z:
            for name, cols in files.items():
                buf=io.StringIO(); w=csv.writer(buf, delimiter=";"); w.writerow(cols)
                z.writestr(name, buf.getvalue().encode("utf-8"))
        messagebox.showinfo(APP,"Şablonlar indirildi")
    def imp_run(self):
        paths=filedialog.askopenfilenames(title="CSV Dosyaları Seç", filetypes=[("CSV","*.csv")])
        if not paths: return
        total=0
        for pth in paths:
            name=Path(pth).name.lower()
            with open(pth,"r",encoding="utf-8") as f:
                rd=csv.reader(f, delimiter=";"); cols=next(rd, [])
                for row in rd:
                    vals=dict(zip(cols,row))
                    if name=="clients.csv":
                        db.exec("INSERT INTO clients(name,national_id,phone,email,address,poa_no,poa_date,poa_baro,poa_attorney,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (vals.get("name",""),vals.get("national_id",""),vals.get("phone",""),vals.get("email",""),vals.get("address",""),
                             vals.get("poa_no",""),vals.get("poa_date",""),vals.get("poa_baro",""),vals.get("poa_attorney",""),vals.get("notes","")))
                    elif name=="debtors.csv":
                        db.exec("INSERT INTO debtors(name,national_id,phone,email,address,notes) VALUES (?,?,?,?,?,?)",
                            (vals.get("name",""),vals.get("national_id",""),vals.get("phone",""),vals.get("email",""),vals.get("address",""),vals.get("notes","")))
                    elif name=="cases.csv":
                        db.exec("INSERT INTO cases(case_type,client_id,debtor_id,file_no,court,status,opened_at,drop_date,notes) VALUES (?,?,?,?,?,?,?,?,?)",
                            (vals.get("case_type",""), vals.get("client_id") or None, vals.get("debtor_id") or None, vals.get("file_no",""),
                             vals.get("court",""), vals.get("status",""), vals.get("opened_at",""), vals.get("drop_date",""), vals.get("notes","")))
                    elif name=="receivables.csv":
                        amt=float((vals.get("amount") or "0").replace(",", "."))
                        db.exec("INSERT INTO receivables(case_id,rtype_id,item,amount,currency,note) VALUES (?,?,?,?,?,?)",
                            (vals.get("case_id"), vals.get("rtype_id") or None, vals.get("item",""), amt, vals.get("currency","TRY"), vals.get("note","")))
                    elif name=="expenses.csv":
                        amt=float((vals.get("amount") or "0").replace(",", "."))
                        db.exec("INSERT INTO expenses(case_id,etype_id,amount,date,note) VALUES (?,?,?,?,?)",
                            (vals.get("case_id"), vals.get("etype_id") or None, amt, vals.get("date",""), vals.get("note","")))
                    total += 1
        messagebox.showinfo(APP, f"İçe aktarıldı: {total} satır"); self.refresh_all(); self.audit("import_csv", str(total))

    # ---------- Reminders ----------
    def ui_rem(self,p):
        make_toolbar(p, [("Ekle", self.rem_add), ("Tamamlandı", self.rem_done), ("Sil", self.rem_del)], wrap=8)
        self.tv_rem = self.tv(p, ["id","Dosya","Başlık","Vade","Öncelik","Not","Durum"]); self.rem_load()
        self.after(20000, self.rem_check)
    def rem_load(self):
        self.tv_rem.delete(*self.tv_rem.get_children())
        for r in db.q("SELECT r.id, COALESCE(c.file_no,'-') file_no, r.title, r.due_date, r.priority, r.note, CASE r.done WHEN 1 THEN '✔' ELSE '' END st FROM reminders r LEFT JOIN cases c ON c.id=r.case_id ORDER BY r.due_date ASC, r.id DESC"):
            self.tv_rem.insert("", "end", values=[r["id"], r["file_no"], r["title"], r["due_date"] or "", r["priority"] or "", r["note"] or "", r["st"]])
    def rem_add(self):
        cases=db.q("SELECT id,file_no FROM cases ORDER BY id DESC")
        w=tk.Toplevel(self); w.title("Hatırlatıcı")
        cb=ttk.Combobox(w,values=[f"{r['id']} - {r['file_no']}" for r in cases]); e_t=ttk.Entry(w); e_d=ttk.Entry(w); e_p=ttk.Combobox(w,values=["düşük","orta","yüksek"]); e_n=ttk.Entry(w)
        for L,E in [("Dosya",cb),("Başlık",e_t),("Vade (YYYY-MM-DD HH:MM)",e_d),("Öncelik",e_p),("Not",e_n)]:
            f=ttk.Frame(w); f.pack(fill="x", padx=8, pady=4); ttk.Label(f,text=L,width=20).pack(side="left"); E.pack(side="left", fill="x", expand=True)
        def save():
            cid=None
            if cb.get():
                try: cid=int(cb.get().split(" - ")[0])
                except:
                    try: cid=int(cb.get())
                    except: cid=None
            db.exec("INSERT INTO reminders(case_id,title,due_date,priority,note) VALUES (?,?,?,?,?)",
                    (cid, e_t.get().strip(), e_d.get().strip(), e_p.get().strip(), e_n.get().strip()))
            w.destroy(); self.rem_load(); self.audit("reminder_add", e_t.get().strip())
        make_toolbar(w, [("Kaydet", save)], wrap=6)
    def rem_done(self):
        v=self.tv_sel(self.tv_rem); 
        if not v: return
        db.exec("UPDATE reminders SET done=1 WHERE id=?", (v[0],)); self.rem_load(); self.audit("reminder_done", str(v[0]))
    def rem_del(self):
        v=self.tv_sel(self.tv_rem); 
        if not v: return
        db.exec("DELETE FROM reminders WHERE id=?", (v[0],)); self.rem_load(); self.audit("reminder_delete", str(v[0]))
    def rem_check(self):
        now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        rows=db.q("SELECT id,title FROM reminders WHERE done=0 AND due_date IS NOT NULL AND due_date<>'' AND due_date<=?", (now,))
        if rows:
            try: messagebox.showwarning(APP, f"Vadesi gelen: {rows[0]['title']}")
            except: pass
        self.after(60000, self.rem_check)

    # ---------- Audit ----------
    def ui_aud(self,p):
        self.tv_aud = self.tv(p, ["Zaman","Kullanıcı","İşlem","Detay"]); self.audit_load()
    def audit(self, action, detail):
        db.exec("INSERT INTO audit(at,user,action,detail) VALUES (?,?,?,?)",
                (datetime.datetime.now().isoformat(timespec="seconds"), self.user, action, detail))
        self.audit_load()
    def audit_load(self):
        self.tv_aud.delete(*self.tv_aud.get_children())
        for r in db.q("SELECT at,user,action,detail FROM audit ORDER BY id DESC LIMIT 500"):
            self.tv_aud.insert("", "end", values=[r["at"], r["user"], r["action"], r["detail"]])

    # ---------- Users (admin) ----------
    def ui_users(self,p):
        make_toolbar(p, [("Ekle", self.user_add), ("Şifre Sıfırla", self.user_reset), ("Sil", self.user_del)], wrap=8)
        self.tv_users = self.tv(p, ["id","Kullanıcı","Rol","Aktif"]); self.user_load()
    def user_load(self):
        if self.role != "admin": return
        self.tv_users.delete(*self.tv_users.get_children())
        for r in db.q("SELECT id,username,role,active FROM users ORDER BY id"):
            self.tv_users.insert("", "end", values=[r["id"], r["username"], r["role"], "✔" if r["active"] else ""])
    def user_add(self):
        if self.role != "admin": return
        w=tk.Toplevel(self); w.title("Kullanıcı")
        e_u=ttk.Entry(w); cb_r=ttk.Combobox(w, values=["admin","avukat","stajyer","operatör"])
        for L,E in [("Kullanıcı Adı",e_u),("Rol",cb_r)]:
            f=ttk.Frame(w); f.pack(fill="x", padx=8, pady=4); ttk.Label(f,text=L,width=16).pack(side="left"); E.pack(side="left", fill="x", expand=True)
        def save():
            u=e_u.get().strip(); r=cb_r.get().strip() or "operatör"
            if not u: return
            db.exec("INSERT INTO users(username,pass_hash,role,active) VALUES (?,?,?,1)", (u,"TO_BE_SET",r))
            w.destroy(); self.user_load(); self.audit("user_add", u)
        make_toolbar(w, [("Kaydet", save)], wrap=6)
    def user_reset(self):
        if self.role != "admin": return
        v=self.tv_sel(self.tv_users); 
        if not v: return
        db.exec("UPDATE users SET pass_hash='TO_BE_SET' WHERE id=?", (v[0],)); self.user_load(); self.audit("user_reset", str(v[0]))
        messagebox.showinfo(APP,"Parola ilk girişte tekrar belirlenecek.")
    def user_del(self):
        if self.role != "admin": return
        v=self.tv_sel(self.tv_users); 
        if not v: return
        db.exec("DELETE FROM users WHERE id=?", (v[0],)); self.user_load(); self.audit("user_delete", str(v[0]))

    # ---------- Logs ----------
    def ui_logs(self, p):
        make_toolbar(p,[("startup_error.log Aç", self._open_startup_error),
                        ("Audit'i CSV Dışa Aktar", self.audit_csv)],wrap=6)
        tx = tk.Text(p, height=18); tx.pack(fill="both", expand=True, padx=10, pady=8); self.skin_text(tx)
        try:
            rows = db.q("SELECT at,user,action,detail FROM audit ORDER BY id DESC LIMIT 200")
            lines = [f"{r['at']} | {r['user']} | {r['action']} | {r['detail']}" for r in rows]
            tx.insert("1.0", "\n".join(lines))
        except Exception:
            tx.insert("1.0", "Audit kayıtları yüklenemedi (henüz tablo oluşmamış olabilir).")
    def _open_startup_error(self):
        p = BASE / "startup_error.log"
        if not p.exists():
            messagebox.showinfo(APP, "startup_error.log bulunamadı."); return
        try:
            if hasattr(os, "startfile"): os.startfile(str(p))
            else:
                import sys, subprocess
                subprocess.Popen(["open" if sys.platform=="darwin" else "xdg-open", str(p)])
        except Exception as e:
            messagebox.showinfo(APP, f"Log dosyasını açamadım.\nKonum: {p}\nDetay: {e}")
    def audit_csv(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv")
        if not p: return
        try:
            rows = db.q("SELECT at,user,action,detail FROM audit ORDER BY id")
        except Exception as e:
            messagebox.showerror(APP, f"Audit çekilemedi: {e}"); return
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["at", "user", "action", "detail"])
            for r in rows: w.writerow([r["at"], r["user"], r["action"], r["detail"]])
        messagebox.showinfo(APP, "Audit CSV hazır"); self.audit("audit_csv", Path(p).name)

    # ---------- Trash ----------
    def ui_trash(self,p):
        make_toolbar(p, [("Geri Yükle", self.trash_restore), ("Kalıcı Sil", self.trash_delete)], wrap=8)
        self.tv_trash = self.tv(p, ["id","Tablo","Silinme","Kullanıcı","Özet"]); self.trash_load()
    def trash_load(self):
        self.tv_trash.delete(*self.tv_trash.get_children())
        for r in db.q("SELECT id,tname,deleted_at,user,substr(payload,1,80) p FROM trash ORDER BY id DESC"):
            self.tv_trash.insert("", "end", values=[r["id"], r["tname"], r["deleted_at"], r["user"], r["p"]])
    def soft_delete(self, tname, row_dict):
        import json as _json
        db.exec("INSERT INTO trash(tname,payload,deleted_at,user) VALUES (?,?,?,?)",
                (tname, _json.dumps(row_dict, ensure_ascii=False), datetime.datetime.now().isoformat(timespec="seconds"), self.user))
        self.trash_load()
    def trash_restore(self):
        v=self.tv_sel(self.tv_trash); 
        if not v: return
        rec=db.q("SELECT tname, payload FROM trash WHERE id=?", (v[0],))
        if not rec: return
        import json as _json
        tname=rec[0]["tname"]; row=_json.loads(rec[0]["payload"])
        cols=",".join(row.keys()); vals=tuple(row.values()); placeholders=",".join(["?"]*len(vals))
        try:
            db.exec(f"INSERT INTO {tname}({cols}) VALUES ({placeholders})", vals)
            db.exec("DELETE FROM trash WHERE id=?", (v[0],))
            self.trash_load(); self.refresh_all(); self.audit("restore", f"{tname}:{row.get('id','?')}")
        except Exception as e:
            messagebox.showerror(APP, f"Geri yükleme hatası: {e}")
    def trash_delete(self):
        v=self.tv_sel(self.tv_trash); 
        if not v: return
        db.exec("DELETE FROM trash WHERE id=?", (v[0],)); self.trash_load(); self.audit("trash_delete", str(v[0]))

    # ---------- Grid export helper ----------
    def grid_to_xls(self, tv, name):
        p=filedialog.asksaveasfilename(defaultextension=".xls", title=f"{name} dışa aktar")
        if not p: return
        export_treeview_xls(tv, p, title=name); messagebox.showinfo(APP,"XLS hazır"); self.audit("grid_xls", name)

    # ---------- Reports helpers ----------
    def rep_case_summary(self):
        v=self.tv_sel(self.tv_cases)
        if not v: messagebox.showwarning(APP,"Önce bir dosya seçin."); return
        cid=int(v[0])
        head=db.q("SELECT file_no, case_type, COALESCE((SELECT name FROM clients WHERE id=client_id),'-') c, COALESCE((SELECT name FROM debtors WHERE id=debtor_id),'-') d FROM cases WHERE id=?", (cid,))
        recs=db.q("SELECT item, amount, currency FROM receivables WHERE case_id=?", (cid,))
        exps=db.q("SELECT COALESCE((SELECT name FROM dict_expense_types WHERE id=etype_id),'?') t, amount, date FROM expenses WHERE case_id=?", (cid,))
        lines=[]
        if head:
            h=head[0]; lines += [f"Dosya: {h['file_no']}  Tür: {h['case_type']}", f"Müvekkil: {h['c']}  Borçlu: {h['d']}", ""]
        lines.append("Alacaklar:"); tot_r=0.0
        for r in recs: tot_r+=r["amount"]; lines.append(f" - {r['item']}: {r['amount']:.2f} {r['currency']}")
        lines.append(f"Toplam Alacak: {tot_r:.2f}"); lines.append("")
        lines.append("Masraflar:"); tot_e=0.0
        for e in exps: tot_e+=e["amount"]; lines.append(f" - {e['t']} ({e['date']}): {e['amount']:.2f}")
        lines.append(f"NET: {tot_r - tot_e:.2f}")
        p=filedialog.asksaveasfilename(defaultextension=".pdf")
        if not p: return
        write_multipage_pdf(p, "Dosya Özeti", lines); messagebox.showinfo(APP,"PDF hazır"); self.audit("rpt_case_summary", str(cid))
    def rep_user_perf(self):
        rows=db.q("SELECT user, COUNT(*) n FROM audit GROUP BY user ORDER BY n DESC")
        lines=["Kullanıcı    İşlem Sayısı"] + [f"{r['user']:<12} {r['n']}" for r in rows]
        p=filedialog.asksaveasfilename(defaultextension=".pdf")
        if not p: return
        write_multipage_pdf(p, "Kullanıcı Performans", lines); messagebox.showinfo(APP,"PDF hazır"); self.audit("rpt_user_perf", "all")

    # ---------- Integration stubs ----------
    def active_case_id(self):
        try:
            v=self.tv_sel(self.tv_cases); 
            return int(v[0]) if v else None
        except: return None
    def menu_uyap(self):
        cid=self.active_case_id(); messagebox.showinfo(APP, f"UYAP senkronizasyon (stub) – case_id={cid}")
        self.audit("uyap_sync", str(cid))
    def menu_eteb(self):
        cid=self.active_case_id(); messagebox.showinfo(APP, f"e-Tebligat sorgu (stub) – case_id={cid}")
        self.audit("etebligat_fetch", str(cid))
    def menu_acc(self):
        cid=self.active_case_id(); messagebox.showinfo(APP, f"Muhasebe aktarım (stub) – case_id={cid}")
        self.audit("accounting_export", str(cid))
    def menu_settings(self):
        messagebox.showinfo(APP, "Ayarlar (stub) – entegrasyon anahtarlarını burada düzenleyebilirsiniz.")

    # ---------- Refresh & Auto-backup ----------
    def refresh_all(self):
        try:
            if hasattr(self,"cli_load"): self.cli_load()
            if hasattr(self,"deb_load"): self.deb_load()
            if hasattr(self,"case_load"): self.case_load()
            if hasattr(self,"audit_load"): self.audit_load()
            if hasattr(self,"rem_load"): self.rem_load()
            if hasattr(self,"trash_load"): self.trash_load()
        except Exception:
            pass
    def _auto_backup_tick(self):
        try:
            now=datetime.datetime.now()
            if now.hour==21 and now.minute<2:
                data_dir = BASE/"data"
                (BASE/"backups").mkdir(exist_ok=True)
                p=(BASE/"backups"/f"backup_{now.strftime('%Y%m%d')}.zip")
                with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
                    if data_dir.exists():
                        for f in data_dir.glob("**/*"):
                            if f.is_file(): z.write(f, f.relative_to(data_dir))
                self.audit("auto_backup", p.name)
        except Exception:
            pass
        self.after(60_000, self._auto_backup_tick)

# ----------------- ensure schema -----------------
def ensure_schema():
    # Temel sözlükler ve loglar
    db.exec("""
    CREATE TABLE IF NOT EXISTS trash(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tname TEXT NOT NULL,
        payload TEXT NOT NULL,
        deleted_at TEXT,
        user TEXT
    )""")
    db.exec("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, user TEXT, action TEXT, detail TEXT)")
    db.exec("CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER, title TEXT, due_date TEXT, priority TEXT, note TEXT, done INTEGER DEFAULT 0)")
    db.exec("CREATE TABLE IF NOT EXISTS dict_receivable_types(id INTEGER PRIMARY KEY, name TEXT)")
    db.exec("CREATE TABLE IF NOT EXISTS dict_expense_types(id INTEGER PRIMARY KEY, name TEXT)")
    # Esas tablolar – garanti
    db.exec("CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, national_id TEXT, phone TEXT, email TEXT, address TEXT, poa_no TEXT, poa_date TEXT, poa_baro TEXT, poa_attorney TEXT, notes TEXT)")
    db.exec("CREATE TABLE IF NOT EXISTS debtors(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, national_id TEXT, phone TEXT, email TEXT, address TEXT, notes TEXT)")
    db.exec("CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY AUTOINCREMENT, case_type TEXT, client_id INTEGER, debtor_id INTEGER, file_no TEXT, court TEXT, status TEXT, opened_at TEXT, drop_date TEXT, notes TEXT)")
    db.exec("CREATE TABLE IF NOT EXISTS receivables(id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER, rtype_id INTEGER, item TEXT, amount REAL, currency TEXT, note TEXT)")
    db.exec("CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY AUTOINCREMENT, case_id INTEGER, etype_id INTEGER, amount REAL, date TEXT, note TEXT)")
    db.exec("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, pass_hash TEXT, role TEXT, active INTEGER DEFAULT 1)")

# ----------------- Main -----------------
def main():
    try:
        (BASE/"data").mkdir(parents=True, exist_ok=True)

        # Başlatma izleri
        trace_log = BASE/"startup_trace.log"
        def trace(msg):
            try:
                prev = trace_log.read_text(encoding="utf-8") if trace_log.exists() else ""
                trace_log.write_text(prev + msg + "\n", encoding="utf-8")
            except Exception:
                pass

        trace("1) db.init()")
        db.init()                      # ÖNCE init
        trace("2) ensure_schema()")
        ensure_schema()                # SONRA tablo güvence

        trace("3) auth.ensure_first_user()")
        with auth.connect() as c:
            auth.ensure_first_user(c)

        trace("4) Tk başlıyor")
        root=tk.Tk(); root.title(APP)
        root.withdraw()
        dlg=Login(root); root.wait_window(dlg)
        if not dlg.result:
            root.destroy(); return
        root.deiconify()
        trace("5) App oluşturuluyor")
        App(root, *dlg.result)
        root.geometry("1200x780"); root.minsize(1000,640)
        trace("6) mainloop()")
        root.mainloop()
    except Exception as e:
        err_path = BASE/"startup_error.log"
        try:
            err_path.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        try:
            messagebox.showerror(APP, f"Başlatma hatası:\n{e}\nDetay: {err_path}")
        except Exception:
            pass
        raise

if __name__=="__main__":
    main()
