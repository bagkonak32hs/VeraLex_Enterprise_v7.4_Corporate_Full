import os, zipfile, datetime, pathlib, shutil, json

# === Klasör yapılarını tanımla ===
base = pathlib.Path(__file__).parent
target_dir = base / "VeraLex_Enterprise_v7.4_Corporate_Full"
target_zip = base / "VeraLex_Enterprise_v7.4_Corporate_Full.zip"

# === Temiz kurulum klasörü oluştur ===
if target_dir.exists():
    shutil.rmtree(target_dir)
target_dir.mkdir(parents=True)

# === Dosyaları kopyala ===
for file in ["app.py", "db.py", "auth.py"]:
    src = base / file
    if src.exists():
        shutil.copy(src, target_dir / file)

# === Tema dosyası oluştur ===
theme = {
    "name": "Corporate Blue + Gold",
    "background": "#0f172a",
    "panel": "#1e293b",
    "accent": "#2563eb",
    "highlight": "#d4af37",
    "text": "#f8fafc"
}
with open(target_dir / "theme.json", "w", encoding="utf-8") as f:
    json.dump(theme, f, indent=4)

# === Logo oluştur (placeholder) ===
logo_path = target_dir / "logo.png"
with open(logo_path, "wb") as f:
    f.write(b"")  # Gerçek logo daha sonra eklenebilir

# === Yedek klasörleri hazırla ===
for folder in ["backup", "data"]:
    (target_dir / folder).mkdir(exist_ok=True)

# === ZIP oluştur ===
with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, _, files in os.walk(target_dir):
        for file in files:
            fp = pathlib.Path(root) / file
            zipf.write(fp, fp.relative_to(base))

print("✅ VeraLex_Enterprise_v7.4_Corporate_Full.zip oluşturuldu!")
print("Konum:", target_zip)
