"""
Gera o ícone oficial do LoTra (assets/lotra.ico) em múltiplas resoluções:
16x16, 32x32, 48x48, 64x64, 128x128, 256x256.
Design moderno: Fundo escuro com gradiente azul ciano e monograma LT estilizado com símbolo de tradução/leitura.
"""
import os
from PIL import Image, ImageDraw, ImageFont

def generate_lotra_icon(output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Gera imagem base 256x256 em alta resolução
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Fundo arredondado com efeito sutil
    padding = 12
    # Círculo externo ou rounded rectangle
    draw.rounded_rectangle(
        [padding, padding, size - padding, size - padding],
        radius=48,
        fill=(26, 27, 38, 255), # Dark slate #1a1b26
        outline=(59, 130, 246, 255), # Blue border #3b82f6
        width=6
    )
    
    # Fundo interno degradê suave (representado por retângulos concêntricos com transparência)
    draw.rounded_rectangle(
        [padding + 8, padding + 8, size - padding - 8, size - padding - 8],
        radius=40,
        fill=(30, 32, 48, 255)
    )
    
    # Desenho estilizado de leitor / tradução:
    # 1. Página/livro aberto estilizado (duas abas dobradas)
    # Aba esquerda (Azul ciano)
    cyan = (56, 189, 248, 255) # Sky blue #38bdf8
    blue = (99, 102, 241, 255) # Indigo #6366f1
    
    # Formato de livro / documento estilizado
    # Página esquerda
    draw.polygon([
        (60, 80), (120, 95), (120, 185), (60, 170)
    ], fill=(45, 55, 80, 255), outline=blue, width=3)
    
    # Página direita
    draw.polygon([
        (136, 95), (196, 80), (196, 170), (136, 185)
    ], fill=(30, 58, 95, 255), outline=cyan, width=3)
    
    # Linhas de texto representadas nas páginas
    draw.line([(72, 105), (108, 114)], fill=(148, 163, 184, 255), width=3)
    draw.line([(72, 125), (108, 134)], fill=(148, 163, 184, 255), width=3)
    draw.line([(72, 145), (96, 151)], fill=(148, 163, 184, 255), width=3)
    
    draw.line([(148, 114), (184, 105)], fill=cyan, width=3)
    draw.line([(148, 134), (184, 125)], fill=cyan, width=3)
    draw.line([(148, 154), (172, 148)], fill=cyan, width=3)
    
    # Seta de tradução / raio de ultra-rapidez no centro
    draw.polygon([
        (128, 60), (142, 85), (132, 85), (138, 115), (114, 88), (124, 88)
    ], fill=(250, 204, 21, 255)) # Amarelo elétrico
    
    # Monograma inferior "LoTra"
    draw.rounded_rectangle([70, 200, 186, 230], radius=8, fill=(15, 23, 42, 255), outline=(56, 189, 248, 255), width=2)
    draw.text((88, 205), "LoTra", fill=(241, 245, 249, 255))

    # Salva como .ico contendo múltiplos tamanhos diretamente na imagem base
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(
        output_path,
        format="ICO",
        sizes=sizes
    )
    print(f"[OK] Ícone gerado com sucesso em: {output_path}")

if __name__ == "__main__":
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "lotra.ico")
    generate_lotra_icon(target)
