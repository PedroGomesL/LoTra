"""
Gera páginas de teste simulando PDFs de livros em dois modos:
1. Imagem digital nítida (PDF limpo renderizado a 150 DPI e 300 DPI)
2. Imagem escaneada realista (leve ruído, rotação mínima de 0.5 graus, compressão JPEG de livro digitalizado antigo)
"""
import os
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "test_images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(os.path.join(os.path.dirname(__file__), "dataset.json"), "r", encoding="utf-8") as f:
    DATASET = json.load(f)

def get_font(size=24, serif=True):
    # Procura fontes comuns no Windows
    font_paths = [
        r"C:\Windows\Fonts\times.ttf" if serif else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\georgia.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\arial.ttf"
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def create_page_image(title, text, is_scanned=False, dpi_scale=1.0):
    base_w, base_h = int(800 * dpi_scale), int(600 * dpi_scale)
    bg_color = (255, 255, 255) if not is_scanned else (248, 245, 238)
    img = Image.new("RGB", (base_w, base_h), bg_color)
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(int(22 * dpi_scale), serif=True)
    font_body = get_font(int(18 * dpi_scale), serif=True)
    
    margin_x = int(60 * dpi_scale)
    margin_y = int(60 * dpi_scale)
    max_w = base_w - (2 * margin_x)
    
    # Desenha título
    draw.text((margin_x, margin_y), title, fill=(30, 30, 30), font=font_title)
    
    # Desenha texto
    lines = wrap_text(text, font_body, max_w, draw)
    line_h = int(28 * dpi_scale)
    y = margin_y + int(45 * dpi_scale)
    
    for line in lines:
        draw.text((margin_x, y), line, fill=(20, 20, 20), font=font_body)
        y += line_h
        
    if is_scanned:
        # Simula características reais de escaneamento de livro:
        # 1. Leve ruído de papel
        arr = np.array(img).astype(np.float32)
        noise = np.random.normal(0, 4, arr.shape)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
        
        # 2. Leve rotação de desalinhamento de scanner (0.3 graus)
        img = img.rotate(0.3, resample=Image.BICUBIC, fillcolor=bg_color)
        
        # 3. Levíssimo desfoque de lente de scanner
        img = img.filter(ImageFilter.GaussianBlur(radius=0.4))
        
    return img

def generate_all():
    generated_files = []
    
    # 1. Palavras isoladas e expressões
    for item in DATASET["single_words"] + DATASET["idioms_and_phrasal_verbs"]:
        # Versão digital limpa
        clean_img = create_page_image(f"Book Vocabulary Entry", item["context"], is_scanned=False)
        clean_path = os.path.join(OUTPUT_DIR, f"{item['id']}_digital.png")
        clean_img.save(clean_path)
        
        # Versão escaneada
        scanned_img = create_page_image(f"Book Vocabulary Entry", item["context"], is_scanned=True)
        scanned_path = os.path.join(OUTPUT_DIR, f"{item['id']}_scanned.png")
        scanned_img.save(scanned_path)
        
        generated_files.append((item["id"], clean_path, scanned_path))
        
    # 2. Parágrafos de livros
    for item in DATASET["book_paragraphs"]:
        clean_img = create_page_image(item["title"], item["text"], is_scanned=False, dpi_scale=1.2)
        clean_path = os.path.join(OUTPUT_DIR, f"{item['id']}_digital.png")
        clean_img.save(clean_path)
        
        scanned_img = create_page_image(item["title"], item["text"], is_scanned=True, dpi_scale=1.2)
        scanned_path = os.path.join(OUTPUT_DIR, f"{item['id']}_scanned.png")
        scanned_img.save(scanned_path)
        
        generated_files.append((item["id"], clean_path, scanned_path))
        
    print(f"[OK] Total de {len(generated_files) * 2} imagens geradas em {OUTPUT_DIR}")

if __name__ == "__main__":
    generate_all()
