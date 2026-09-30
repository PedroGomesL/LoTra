"""
Gerador de Ícone e Logotipo do LoTra
Baseado no design oficial da Lontra (Meio.dc.html):
- Balão de fala na cor Teal (#0f5c6e)
- Lontra simpática estilizada em tons quentes (#ae7f52, #efe3cf, #7a5230, #33231b)
- Bigodes e detalhes com alta definição em antialiasing
- Exportação em múltiplos tamanhos para lotra.ico e lotra.png
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw

def render_lotra_logo(target_size: int = 512) -> Image.Image:
    # Renderizamos em escala 4x maior e reduzimos com LANCZOS para super-sampling / AA perfeito
    scale = 4.0
    dim = int(target_size * scale)
    base_vb = 120.0  # viewBox 0 0 120 120
    s = dim / base_vb

    img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    teal = "#0f5c6e"
    ear_brown = "#7a5230"
    fur_main = "#ae7f52"
    muzzle_light = "#efe3cf"
    nose_dark = "#33231b"
    nose_shine = "#85705f"
    eye_dark = "#21140f"
    eye_shine = "#ffffff"
    mouth_stroke = "#5a4636"
    whisker_stroke = (246, 241, 232, 230)

    # 1. Balão de fala - cauda
    tail = [
        (30 * s, 92 * s),
        (20 * s, 116 * s),
        (50 * s, 98 * s)
    ]
    draw.polygon(tail, fill=teal)

    # 1. Balão de fala - corpo arredondado
    bx0, by0, bx1, by1 = 6 * s, 6 * s, (6 + 108) * s, (6 + 94) * s
    bradius = 36 * s
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=bradius, fill=teal)

    # 2. Orelhas
    r_ear = 8 * s
    draw.ellipse([(30 * s - r_ear, 34 * s - r_ear), (30 * s + r_ear, 34 * s + r_ear)], fill=ear_brown)
    draw.ellipse([(90 * s - r_ear, 34 * s - r_ear), (90 * s + r_ear, 34 * s + r_ear)], fill=ear_brown)

    # 3. Cabeça da Lontra
    draw.ellipse([(60 * s - 34 * s, 58 * s - 30 * s), (60 * s + 34 * s, 58 * s + 30 * s)], fill=fur_main)

    # 4. Focinho / Queixo claro
    draw.ellipse([(60 * s - 22 * s, 70 * s - 15 * s), (60 * s + 22 * s, 70 * s + 15 * s)], fill=muzzle_light)

    # 5. Nariz (Curva Bezier aproximada por polígono suave)
    def bezier_point(p0, p1, p2, t):
        x = (1 - t)**2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
        y = (1 - t)**2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
        return (x, y)

    nose_poly = []
    # Topo: (52.5, 60) Q(60, 55.5) -> (67.5, 60)
    for i in range(11):
        nose_poly.append(bezier_point((52.5 * s, 60 * s), (60 * s, 55.5 * s), (67.5 * s, 60 * s), i / 10.0))
    # Direita / Baixo: (67.5, 60) Q(67.5, 67) -> (60, 68.5)
    for i in range(1, 11):
        nose_poly.append(bezier_point((67.5 * s, 60 * s), (67.5 * s, 67 * s), (60 * s, 68.5 * s), i / 10.0))
    # Esquerda: (60, 68.5) Q(52.5, 67) -> (52.5, 60)
    for i in range(1, 11):
        nose_poly.append(bezier_point((60 * s, 68.5 * s), (52.5 * s, 67 * s), (52.5 * s, 60 * s), i / 10.0))

    draw.polygon(nose_poly, fill=nose_dark)

    # Brilho do nariz
    draw.ellipse([(57 * s - 2.4 * s, 58.6 * s - 1 * s), (57 * s + 2.4 * s, 58.6 * s + 1 * s)], fill=nose_shine)

    # 6. Olhos
    r_eye = 4.6 * s
    draw.ellipse([(45 * s - r_eye, 49 * s - r_eye), (45 * s + r_eye, 49 * s + r_eye)], fill=eye_dark)
    draw.ellipse([(75 * s - r_eye, 49 * s - r_eye), (75 * s + r_eye, 49 * s + r_eye)], fill=eye_dark)

    # Brilho dos olhos
    r_eye_shine = 1.4 * s
    draw.ellipse([(46.5 * s - r_eye_shine, 47.5 * s - r_eye_shine), (46.5 * s + r_eye_shine, 47.5 * s + r_eye_shine)], fill=eye_shine)
    draw.ellipse([(76.5 * s - r_eye_shine, 47.5 * s - r_eye_shine), (76.5 * s + r_eye_shine, 47.5 * s + r_eye_shine)], fill=eye_shine)

    # 7. Boca
    mouth_w = max(1, int(1.8 * s))
    draw.line([(60 * s, 68.5 * s), (60 * s, 72.5 * s)], fill=mouth_stroke, width=mouth_w)
    
    mouth_left = [bezier_point((60 * s, 72.5 * s), (55 * s, 76.5 * s), (50 * s, 73.5 * s), i / 10.0) for i in range(11)]
    for i in range(len(mouth_left) - 1):
        draw.line([mouth_left[i], mouth_left[i+1]], fill=mouth_stroke, width=mouth_w)

    mouth_right = [bezier_point((60 * s, 72.5 * s), (65 * s, 76.5 * s), (70 * s, 73.5 * s), i / 10.0) for i in range(11)]
    for i in range(len(mouth_right) - 1):
        draw.line([mouth_right[i], mouth_right[i+1]], fill=mouth_stroke, width=mouth_w)

    # 8. Bigodes e fios de sobrancelha
    w_w = max(1, int(1.0 * s))
    whiskers = [
        ((50, 67), (32, 60), (13, 62)),
        ((49, 71), (31, 71), (14, 78)),
        ((51, 75), (37, 82), (25, 91)),
        ((70, 67), (88, 60), (107, 62)),
        ((71, 71), (89, 71), (106, 78)),
        ((69, 75), (83, 82), (95, 91)),
        ((46, 34), (42, 24), (37, 14)),
        ((74, 34), (78, 24), (83, 14)),
    ]

    for p0_raw, p1_raw, p2_raw in whiskers:
        p0 = (p0_raw[0] * s, p0_raw[1] * s)
        p1 = (p1_raw[0] * s, p1_raw[1] * s)
        p2 = (p2_raw[0] * s, p2_raw[1] * s)
        pts = [bezier_point(p0, p1, p2, i / 10.0) for i in range(11)]
        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i+1]], fill=whisker_stroke, width=w_w)

    # Reduz para o tamanho desejado com supersampling antialiasing
    result = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
    return result

def main():
    root = Path(__file__).resolve().parent.parent
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Gera imagem PNG em 512x512
    logo_512 = render_lotra_logo(512)
    png_path = assets_dir / "lotra.png"
    logo_512.save(png_path, format="PNG")
    print(f"[OK] PNG salvo em: {png_path}")

    # Gera tamanhos para o arquivo .ico
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icon_images = [render_lotra_logo(sz) for sz in sizes]
    ico_path = assets_dir / "lotra.ico"
    icon_images[-1].save(
        ico_path,
        format="ICO",
        sizes=[(sz, sz) for sz in sizes],
        append_images=icon_images[:-1]
    )
    print(f"[OK] ICO salvo em: {ico_path} com {len(sizes)} resoluções ({sizes})")

if __name__ == "__main__":
    main()
