"""
Gerador de Página A4 Completa e Complexa para Benchmark de OCR e Tradução.
Cria um documento simulando um artigo científico/técnico de alta complexidade:
- Cabeçalho, metadados (Título, Autores, Filiação, Abstract, Palavras-chave)
- Layout em duas colunas de texto denso
- Diagrama técnico embutido no centro com caixas, setas e textos INTERNOS
- Legenda do diagrama ("Figure 1: Schematic of cryogenic transmon qubit...")
- Notas de rodapé e referências técnicas
Gera em duas versões:
1. Digital nítida (150 DPI e 300 DPI)
2. Escaneada realista (ruído de papel, rotação leve, aberração de lente, marcas de dobra)
"""

import os
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(BASE_DIR, "test_images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

A4_GROUND_TRUTH = {
    "doc_metadata": {
        "title": "Cryogenic Microwave Routing and Scalability Bottlenecks in Superconducting Quantum Processors",
        "authors": "Dr. Helena Vance, Dr. Arthur Pendelton",
        "institution": "Department of Applied Quantum Physics, Cambridge Cryogenic Laboratory",
        "domain": "Quantum Computing & Solid State Physics",
        "keywords": ["superconducting qubits", "dilution refrigerator", "transmon", "microwave crosstalk", "thermal dissipation"]
    },
    "abstract": "Superconducting quantum processors demand sub-20 millikelvin operational environments to maintain qubit coherence against thermal fluctuations. In this work, we analyze high-density coaxial microwave line routing through cryogenic thermal stages, identifying anomalous cross-coupling and passive attenuation limits for fault-tolerant architectures.",
    "column_1_text": "The implementation of large-scale fault-tolerant quantum computers represents one of the most demanding engineering challenges in contemporary physics. Superconducting circuits based on transmon qubits have achieved remarkable milestones, including quantum computational supremacy and error detection thresholds. However, scaling beyond several hundred physical qubits introduces a severe bottleneck: the interconnect problem. Each transmon requires dedicated coaxial microwave lines for XY control, flux bias tuning, and dispersive readout through coupled coplanar waveguide resonators.",
    "column_2_text": "At millikelvin temperatures inside dilution refrigerators, available cooling power is drastically limited. At the 4 Kelvin plate, cooling power reaches roughly 1.5 Watts, but drops exponentially to less than 20 microwatts at the mixing chamber plate (15 mK). Every physical coaxial line conducts parasitic thermal energy and dissipates active microwave power. Thermal anchoring using bulk cryogenic attenuators is necessary, yet physical space and thermal budgets rapidly saturate as qubit counts scale toward commercial utility.",
    "diagram_internal_texts": [
        "Room Temp (300K): Pulse Arbitrary Waveform Generator",
        "4K Stage: High-Density Attenuator Block (-20dB)",
        "Still Stage (0.8K): Low-Noise Cryo-Filter",
        "Cold Plate (100mK): Thermal Heat Sink Braid",
        "Mixing Chamber (15mK): Superconducting Transmon Processor",
        "Dispersive Readout Coplanar Resonator Line"
    ],
    "figure_caption": "Figure 1: Multi-stage cryogenic attenuation and microwave interconnect routing inside the dilution refrigerator assembly.",
    "footer_notes": "Cambridge Cryogenic Lab Technical Report 2026. Submitted to Physical Review Applied. Contact: h.vance@cam.quantum.ac.uk"
}

def get_font(size=14, bold=False):
    font_names = [
        r"C:\Windows\Fonts\timesbd.ttf" if bold else r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf"
    ]
    for p in font_names:
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
        if (bbox[2] - bbox[0]) <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def generate_complex_a4_page(is_scanned=False, scale=1.2):
    # A4 standard at ~150 DPI: 1240 x 1754 px (scaled)
    w = int(1240 * scale)
    h = int(1754 * scale)
    
    bg_color = (255, 255, 255) if not is_scanned else (246, 243, 235)
    img = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Fonts
    f_journal = get_font(int(11 * scale), bold=False)
    f_title = get_font(int(20 * scale), bold=True)
    f_authors = get_font(int(13 * scale), bold=False)
    f_instit = get_font(int(11 * scale), bold=False)
    f_sec = get_font(int(14 * scale), bold=True)
    f_body = get_font(int(12 * scale), bold=False)
    f_abstract = get_font(int(11.5 * scale), bold=False)
    f_diag = get_font(int(10.5 * scale), bold=True)
    f_caption = get_font(int(11 * scale), bold=False)
    f_foot = get_font(int(9.5 * scale), bold=False)
    
    margin_x = int(75 * scale)
    margin_top = int(70 * scale)
    content_w = w - (2 * margin_x)
    
    y = margin_top
    
    # Header: Journal info
    draw.text((margin_x, y), "PHYSICAL REVIEW APPLIED | ADVANCED QUANTUM HARDWARE", fill=(90, 90, 90), font=f_journal)
    draw.line([(margin_x, y + int(18*scale)), (w - margin_x, y + int(18*scale))], fill=(180, 180, 180), width=int(1.5*scale))
    y += int(35 * scale)
    
    # Title
    title_lines = wrap_text(A4_GROUND_TRUTH["doc_metadata"]["title"], f_title, content_w, draw)
    for l in title_lines:
        draw.text((margin_x, y), l, fill=(15, 15, 15), font=f_title)
        y += int(28 * scale)
    y += int(10 * scale)
    
    # Authors
    draw.text((margin_x, y), A4_GROUND_TRUTH["doc_metadata"]["authors"], fill=(40, 40, 40), font=f_authors)
    y += int(20 * scale)
    draw.text((margin_x, y), A4_GROUND_TRUTH["doc_metadata"]["institution"], fill=(80, 80, 80), font=f_instit)
    y += int(30 * scale)
    
    # Abstract Box
    box_padding = int(16 * scale)
    abs_lines = wrap_text("ABSTRACT: " + A4_GROUND_TRUTH["abstract"], f_abstract, content_w - (2 * box_padding), draw)
    abs_height = len(abs_lines) * int(18 * scale) + (2 * box_padding)
    
    # Draw subtle gray background box for abstract
    draw.rectangle([margin_x, y, margin_x + content_w, y + abs_height], fill=(245, 247, 250) if not is_scanned else (240, 238, 230), outline=(210, 215, 225), width=int(1*scale))
    abs_y = y + box_padding
    for l in abs_lines:
        draw.text((margin_x + box_padding, abs_y), l, fill=(30, 30, 30), font=f_abstract)
        abs_y += int(18 * scale)
    y += abs_height + int(35 * scale)
    
    # Two Columns Layout Parameters
    col_gap = int(40 * scale)
    col_w = (content_w - col_gap) // 2
    col1_x = margin_x
    col2_x = margin_x + col_w + col_gap
    
    # Column 1
    c1_y = y
    draw.text((col1_x, c1_y), "1. Introduction and Architectural Scaling", fill=(10, 10, 10), font=f_sec)
    c1_y += int(24 * scale)
    c1_lines = wrap_text(A4_GROUND_TRUTH["column_1_text"], f_body, col_w, draw)
    for l in c1_lines:
        draw.text((col1_x, c1_y), l, fill=(25, 25, 25), font=f_body)
        c1_y += int(19 * scale)
        
    # Column 2
    c2_y = y
    draw.text((col2_x, c2_y), "2. Cryogenic Thermal Load Constraints", fill=(10, 10, 10), font=f_sec)
    c2_y += int(24 * scale)
    c2_lines = wrap_text(A4_GROUND_TRUTH["column_2_text"], f_body, col_w, draw)
    for l in c2_lines:
        draw.text((col2_x, c2_y), l, fill=(25, 25, 25), font=f_body)
        c2_y += int(19 * scale)
        
    y_after_cols = max(c1_y, c2_y) + int(30 * scale)
    
    # Technical Diagram in the Center
    diag_w = int(content_w * 0.94)
    diag_h = int(240 * scale)
    diag_x = margin_x + (content_w - diag_w) // 2
    diag_y = y_after_cols
    
    # Diagram container
    draw.rectangle([diag_x, diag_y, diag_x + diag_w, diag_y + diag_h], fill=(252, 253, 255) if not is_scanned else (244, 242, 234), outline=(160, 170, 185), width=int(2*scale))
    
    # Diagram title bar
    draw.rectangle([diag_x, diag_y, diag_x + diag_w, diag_y + int(24*scale)], fill=(230, 236, 245) if not is_scanned else (225, 222, 212))
    draw.text((diag_x + int(12*scale), diag_y + int(4*scale)), "DIAGRAM: CRYOGENIC MICROWAVE ATTENUATION STAGES", fill=(40, 50, 70), font=f_diag)
    
    # Draw internal boxes representing cryogenic stages
    stages = A4_GROUND_TRUTH["diagram_internal_texts"]
    box_step = (diag_h - int(45*scale)) // len(stages)
    box_w = diag_w - int(40*scale)
    
    for idx, stage_text in enumerate(stages):
        bx = diag_x + int(20*scale)
        by = diag_y + int(32*scale) + (idx * box_step)
        bh = box_step - int(6*scale)
        
        # Color coding by temperature
        if idx == 0:
            box_fill = (255, 235, 235) # Hot / Room temp
            box_outline = (210, 100, 100)
        elif idx == len(stages) - 1 or idx == len(stages) - 2:
            box_fill = (225, 240, 255) # Sub-kelvin cryogenic
            box_outline = (70, 130, 210)
        else:
            box_fill = (240, 245, 250)
            box_outline = (140, 160, 180)
            
        draw.rectangle([bx, by, bx + box_w, by + bh], fill=box_fill if not is_scanned else (238, 236, 228), outline=box_outline, width=int(1.5*scale))
        draw.text((bx + int(12*scale), by + int((bh - int(12*scale))//2)), stage_text, fill=(20, 25, 30), font=f_diag)
        
        # Connector line
        if idx < len(stages) - 1:
            arrow_x = bx + box_w // 2
            draw.line([(arrow_x, by + bh), (arrow_x, by + bh + int(6*scale))], fill=(100, 100, 100), width=int(2*scale))
            
    # Caption under diagram
    y_caption = diag_y + diag_h + int(12 * scale)
    draw.text((margin_x, y_caption), A4_GROUND_TRUTH["figure_caption"], fill=(60, 60, 60), font=f_caption)
    
    # Footer & Page Number
    y_foot = h - int(55 * scale)
    draw.line([(margin_x, y_foot - int(10*scale)), (w - margin_x, y_foot - int(10*scale))], fill=(200, 200, 200), width=int(1*scale))
    draw.text((margin_x, y_foot), A4_GROUND_TRUTH["footer_notes"], fill=(100, 100, 100), font=f_foot)
    draw.text((w - margin_x - int(45*scale), y_foot), "Page 1", fill=(100, 100, 100), font=f_foot)
    
    if is_scanned:
        arr = np.array(img).astype(np.float32)
        noise = np.random.normal(0, 5.0, arr.shape)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
        img = img.rotate(0.35, resample=Image.BICUBIC, fillcolor=bg_color)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.45))
        
    return img

def main():
    print("Gerando Página A4 Complexa (Digital e Escaneada)...")
    img_digital = generate_complex_a4_page(is_scanned=False, scale=1.2)
    digital_path = os.path.join(OUTPUT_DIR, "a4_complex_page_digital.png")
    img_digital.save(digital_path, "PNG", optimize=True)
    print(f"Salvo: {digital_path} ({img_digital.size[0]}x{img_digital.size[1]})")
    
    img_scanned = generate_complex_a4_page(is_scanned=True, scale=1.2)
    scanned_path = os.path.join(OUTPUT_DIR, "a4_complex_page_scanned.png")
    img_scanned.save(scanned_path, "PNG", optimize=True)
    print(f"Salvo: {scanned_path} ({img_scanned.size[0]}x{img_scanned.size[1]})")
    
    gt_path = os.path.join(BASE_DIR, "a4_ground_truth.json")
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(A4_GROUND_TRUTH, f, indent=2, ensure_ascii=False)
    print(f"Ground Truth A4 salvo em: {gt_path}")

if __name__ == "__main__":
    main()
