"""
Interface Gráfica Principal (GUI) do LoTra:
Substitui o terminal por uma janela moderna e responsiva na área de trabalho.
Alinhada esteticamente com a identidade visual oficial da Lontra (Meio.dc.html):
- Fundo em creme suave (#f6f1e8)
- Acentos e cabeçalho em Teal profundo (#0f5c6e)
- Painel informativo dos 2 atalhos globais: [Alt + Q] e [Alt + W]
- Campo interativo para testar traduções diretamente
- Indicador em tempo real de hardware, status e motor 100% offline
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, Any
from PIL import Image, ImageTk

from resource_utils import get_resource_path
from hud_tooltip import normalize_text_spacing, set_windows_clipboard_text

class LoTraMainWindow:
    """Janela principal de controle e status do LoTra."""

    def __init__(self, app: Any):
        self.app = app
        self.root = tk.Tk()
        self.root.title("LoTra - Tradução e Leitura Fluida")
        self.root.geometry("640x600")
        self.root.minsize(580, 520)

        # Paleta oficial extraída de Meio.dc.html
        self.c_bg = "#f6f1e8"          # Creme suave de fundo
        self.c_teal = "#0f5c6e"        # Teal oficial do balão
        self.c_teal_dark = "#093844"   # Teal escuro para contrastes
        self.c_teal_hover = "#147287"  # Teal claro para hover
        self.c_card_bg = "#ffffff"     # Fundo branco dos cards
        self.c_border = "#e2d9cc"      # Borda sutil
        self.c_text = "#2c3b3f"        # Texto primário escuro
        self.c_text_muted = "#66777b"  # Texto secundário
        self.c_green = "#1b8a5a"       # Verde de status ativo
        self.c_cream = "#efe3cf"       # Creme claro da logo

        self.root.configure(bg=self.c_bg)

        # Configura ícone da janela
        self._set_app_icon()

        # Constrói os componentes visuais
        self._build_header()
        self._build_hotkey_cards()
        self._build_interactive_translator()
        self._build_hardware_footer()

        # Protocolo de fechamento: pergunta se quer encerrar ou minimizar
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_requested)

    def _set_app_icon(self):
        """Define o ícone oficial da janela e da barra de tarefas."""
        try:
            ico_path = get_resource_path("assets/lotra.ico")
            if ico_path.exists():
                self.root.iconbitmap(str(ico_path))
        except Exception:
            pass

    def _build_header(self):
        """Cabeçalho estilizado com logo da Lontra e subtítulo oficial."""
        header_frame = tk.Frame(self.root, bg=self.c_teal, padx=20, pady=14)
        header_frame.pack(fill=tk.X)

        # Container horizontal para logo e textos
        inner_box = tk.Frame(header_frame, bg=self.c_teal)
        inner_box.pack(fill=tk.X)

        # Imagem do logo (Lontra no balão de fala)
        self.logo_img = None
        try:
            png_path = get_resource_path("assets/lotra.png")
            if png_path.exists():
                pil_img = Image.open(png_path).resize((52, 52), Image.Resampling.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(pil_img)
                lbl_logo = tk.Label(inner_box, image=self.logo_img, bg=self.c_teal)
                lbl_logo.pack(side=tk.LEFT, padx=(0, 14))
        except Exception:
            pass

        # Textos de Branding
        text_box = tk.Frame(inner_box, bg=self.c_teal)
        text_box.pack(side=tk.LEFT, fill=tk.Y)

        title_lbl = tk.Label(
            text_box,
            text="LoTra",
            font=("Georgia", 22, "bold"),
            fg="#ffffff",
            bg=self.c_teal
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            text_box,
            text="traduza com fluidez  •  100% offline e privativo",
            font=("DM Sans", 10),
            fg=self.c_cream,
            bg=self.c_teal
        )
        subtitle_lbl.pack(anchor="w")

        # Indicador de Status à direita
        status_box = tk.Frame(inner_box, bg=self.c_teal)
        status_box.pack(side=tk.RIGHT, fill=tk.Y)

        badge_frame = tk.Frame(status_box, bg=self.c_teal_dark, padx=10, pady=5)
        badge_frame.pack(anchor="e")

        ollama_active = False
        ollama_model = ""
        if hasattr(self.app, "translator") and self.app.translator._is_ollama_available():
            ollama_model = self.app.translator._get_available_ollama_model("qwen2.5:1.5b") or ""
            ollama_active = bool(ollama_model)

        dot_color = "#4ade80" if ollama_active else "#f59e0b"
        status_str = f"LLM Ativa ({ollama_model})" if ollama_active else "Offline (Dicionário)"

        self.lbl_status_dot = tk.Label(badge_frame, text="●", font=("Arial", 11), fg=dot_color, bg=self.c_teal_dark)
        self.lbl_status_dot.pack(side=tk.LEFT, padx=(0, 5))

        self.lbl_status_text = tk.Label(badge_frame, text=status_str, font=("Arial", 9, "bold"), fg="#ffffff", bg=self.c_teal_dark)
        self.lbl_status_text.pack(side=tk.LEFT)

    def _build_hotkey_cards(self):
        """Card explicativo dos 2 atalhos globais suportados."""
        card_container = tk.Frame(self.root, bg=self.c_bg, padx=20, pady=12)
        card_container.pack(fill=tk.X)

        section_lbl = tk.Label(
            card_container,
            text="ATALHOS GLOBAIS ATIVOS (DISPONÍVEIS EM QUALQUER APLICATIVO)",
            font=("Arial", 8, "bold"),
            fg=self.c_text_muted,
            bg=self.c_bg
        )
        section_lbl.pack(anchor="w", pady=(0, 6))

        grid_frame = tk.Frame(card_container, bg=self.c_bg)
        grid_frame.pack(fill=tk.X)

        # Card 1: Alt + Q
        card_q = tk.Frame(grid_frame, bg=self.c_card_bg, highlightbackground=self.c_border, highlightthickness=1, padx=12, pady=10)
        card_q.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        tag_q = tk.Label(card_q, text=" Alt + Q ", font=("Arial", 9, "bold"), bg=self.c_teal, fg="#ffffff", padx=6, pady=2)
        tag_q.pack(anchor="w", pady=(0, 4))

        lbl_q_title = tk.Label(card_q, text="Traduzir Seleção Direta", font=("Arial", 10, "bold"), fg=self.c_text, bg=self.c_card_bg)
        lbl_q_title.pack(anchor="w")

        lbl_q_desc = tk.Label(
            card_q,
            text="Selecione qualquer texto e aperte Alt+Q. Não precisa de Ctrl+C prévio.",
            font=("Arial", 8),
            fg=self.c_text_muted,
            bg=self.c_card_bg,
            wraplength=230,
            justify=tk.LEFT
        )
        lbl_q_desc.pack(anchor="w", pady=(2, 0))

        # Card 2: Alt + W
        card_w = tk.Frame(grid_frame, bg=self.c_card_bg, highlightbackground=self.c_border, highlightthickness=1, padx=12, pady=10)
        card_w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        tag_w = tk.Label(card_w, text=" Alt + W ", font=("Arial", 9, "bold"), bg=self.c_teal, fg="#ffffff", padx=6, pady=2)
        tag_w.pack(anchor="w", pady=(0, 4))

        lbl_w_title = tk.Label(card_w, text="Recorte de Tela com OCR", font=("Arial", 10, "bold"), fg=self.c_text, bg=self.c_card_bg)
        lbl_w_title.pack(anchor="w")

        lbl_w_desc = tk.Label(
            card_w,
            text="Selecione uma área da tela para ler o texto na imagem e traduzir no HUD.",
            font=("Arial", 8),
            fg=self.c_text_muted,
            bg=self.c_card_bg,
            wraplength=230,
            justify=tk.LEFT
        )
        lbl_w_desc.pack(anchor="w", pady=(2, 0))

    def _build_interactive_translator(self):
        """Painel de teste de tradução interativa rápida."""
        main_box = tk.Frame(self.root, bg=self.c_card_bg, highlightbackground=self.c_border, highlightthickness=1, padx=14, pady=12)
        main_box.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        lbl_sec = tk.Label(main_box, text="Teste Rápido de Tradução", font=("Arial", 10, "bold"), fg=self.c_text, bg=self.c_card_bg)
        lbl_sec.pack(anchor="w")

        # Entrada de Texto
        self.txt_input = tk.Text(
            main_box,
            height=3,
            font=("Times New Roman", 11),
            fg=self.c_text,
            bg="#fcfbf9",
            highlightbackground=self.c_border,
            highlightthickness=1,
            relief=tk.FLAT,
            padx=8,
            pady=6
        )
        self.txt_input.pack(fill=tk.X, pady=(6, 8))
        self.txt_input.insert(tk.END, "Recent advances in generative ai continue to evolve.")

        # Linha com Botões
        btn_bar = tk.Frame(main_box, bg=self.c_card_bg)
        btn_bar.pack(fill=tk.X, pady=(0, 8))

        btn_translate = tk.Button(
            btn_bar,
            text="Traduzir Texto",
            font=("Arial", 9, "bold"),
            bg=self.c_teal,
            fg="#ffffff",
            activebackground=self.c_teal_hover,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=16,
            pady=5,
            cursor="hand2",
            command=self._do_manual_translate
        )
        btn_translate.pack(side=tk.LEFT)

        btn_clear = tk.Button(
            btn_bar,
            text="Limpar",
            font=("Arial", 9),
            bg="#e5e0d8",
            fg=self.c_text,
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._clear_fields
        )
        btn_clear.pack(side=tk.LEFT, padx=(8, 0))

        self.lbl_stats = tk.Label(btn_bar, text="", font=("Arial", 8), fg=self.c_text_muted, bg=self.c_card_bg)
        self.lbl_stats.pack(side=tk.RIGHT)

        # Saída da Tradução
        lbl_out = tk.Label(main_box, text="Resultado Traduzido:", font=("Arial", 9, "bold"), fg=self.c_text, bg=self.c_card_bg)
        lbl_out.pack(anchor="w", pady=(2, 4))

        self.txt_output = tk.Text(
            main_box,
            height=4,
            font=("Times New Roman", 11),
            fg=self.c_teal_dark,
            bg="#f4f7f6",
            highlightbackground=self.c_border,
            highlightthickness=1,
            relief=tk.FLAT,
            padx=8,
            pady=6
        )
        self.txt_output.pack(fill=tk.BOTH, expand=True)

    def _build_hardware_footer(self):
        """Barra de rodapé com diagnóstico de hardware e botões de gerenciamento."""
        footer_frame = tk.Frame(self.root, bg=self.c_bg, padx=20, pady=10)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # Informação de hardware
        try:
            hw = self.app.profile_hardware()
            engine_str = "Offline (Dicionário)"
            if hasattr(self.app, "translator") and self.app.translator._is_ollama_available():
                m = self.app.translator._get_available_ollama_model("qwen2.5:3b")
                if m:
                    engine_str = f"Ollama Local ({m})"
            hw_str = f"Hardware: {hw['cpu_cores']} núcleos CPU | RAM: {hw['avail_ram_gb']}GB livre | GPU: {hw['gpu_name']} | Motor: {engine_str}"
        except Exception:
            hw_str = "Modo: 100% Offline e Seguro | Princípio Read-Only ativo"

        lbl_hw = tk.Label(footer_frame, text=hw_str, font=("Arial", 7), fg=self.c_text_muted, bg=self.c_bg)
        lbl_hw.pack(anchor="w", pady=(0, 6))

        # Botões de ação
        action_bar = tk.Frame(footer_frame, bg=self.c_bg)
        action_bar.pack(fill=tk.X)

        btn_minimize = tk.Button(
            action_bar,
            text="Minimizar (Manter Atalhos Ativos)",
            font=("Arial", 9),
            bg="#e2dad0",
            fg=self.c_text,
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.root.iconify
        )
        btn_minimize.pack(side=tk.LEFT)

        btn_exit = tk.Button(
            action_bar,
            text="Encerrar LoTra",
            font=("Arial", 9),
            bg="#fce8e6",
            fg="#c5221f",
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._exit_app
        )
        btn_exit.pack(side=tk.RIGHT)

    def _do_manual_translate(self):
        """Executa tradução manual do texto digitado no campo de teste."""
        raw_text = self.txt_input.get("1.0", tk.END).strip()
        if not raw_text:
            return

        res = self.app.translate_text(raw_text)
        self.txt_output.delete("1.0", tk.END)
        self.txt_output.insert(tk.END, res["translated_text"])

        lat = res.get("latency_ms", 0.0)
        engine = res.get("engine_used", "LoTra Engine")
        self.lbl_stats.config(text=f"Latência: {lat:.1f}ms | {engine}")

    def _clear_fields(self):
        """Limpa campos de teste."""
        self.txt_input.delete("1.0", tk.END)
        self.txt_output.delete("1.0", tk.END)
        self.lbl_stats.config(text="")

    def _on_close_requested(self):
        """Ao clicar no botão de fechar (X), minimiza ou confirma saída."""
        self.root.iconify()

    def _exit_app(self):
        """Encerra a aplicação completamente."""
        self.app.stop_hud_service()
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def process_incoming_queue(self):
        """Drena itens da fila de eventos para exibir o HUD Tooltip flutuante thread-safe."""
        while not self.app._ui_queue.empty():
            try:
                item = self.app._ui_queue.get_nowait()
                if isinstance(item, dict) and item.get("_action") == "start_native_snip":
                    self.app._handle_native_snip()
                    continue

                res = item
                self.app.hud.show(
                    translated_text=res["translated_text"],
                    source_text=res.get("source_text", ""),
                    latency_ms=res.get("latency_ms", 0.0),
                    engine_name=res.get("engine_used", "LoTra Engine"),
                    timeout_sec=0.0,
                    cursor_pos=res.get("cursor_pos")
                )
            except Exception:
                break

        self.app.hud.pump_events()
        if self.app._is_serving:
            self.root.after(40, self.process_incoming_queue)

    def start_main_loop(self):
        """Inicia o loop visual da aplicação."""
        self.root.after(100, self.process_incoming_queue)
        self.root.mainloop()
