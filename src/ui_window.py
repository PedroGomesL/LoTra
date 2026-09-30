"""
Interface Gráfica Principal (GUI) Moderna do LoTra:
Substitui o terminal por uma aplicação desktop moderna estilo Web / Dashboard SaaS (/goal /boost).
Alinhada esteticamente com a identidade visual oficial da Lontra (Meio.dc.html):
- Fundo em creme suave (#f6f1e8)
- Acentos e cabeçalho em Teal profundo (#0f5c6e)
- Navegação por Abas Segmentadas: [ ⚡ Tradutor Rápido ] | [ 📚 Histórico & Cache ] | [ ⚙️ Hardware & Diagnóstico ]
- Cards modernos com cantos arredondados, bordas sutis e sombras suaves
- Keycaps modernos para os 2 atalhos globais: [Alt + Q] e [Alt + W]
- Campo interativo com contagem em tempo real de caracteres/palavras e chips de amostras
- Botão elegante de copiar para clipboard com feedback visual instantâneo (toast "✓ Copiado!")
- Indicador em tempo real de hardware, status e motor 100% offline
"""

import sys
import time
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple
from PIL import Image, ImageTk

from resource_utils import get_resource_path
from hud_tooltip import normalize_text_spacing, set_windows_clipboard_text

class LoTraMainWindow:
    """Janela principal moderna de controle, tradução e status do LoTra."""

    def __init__(self, app: Any):
        self.app = app
        if hasattr(self.app, "get_tk_root"):
            self.root = self.app.get_tk_root()
            try:
                self.root.deiconify()
            except Exception:
                self.root = tk.Tk()
        else:
            self.root = tk.Tk()
        self.root.title("LoTra - Tradução e Leitura Fluida")
        self.root.geometry("680x680")
        self.root.minsize(620, 560)

        # Paleta oficial e moderna inspirada na identidade visual Lontra & Web SaaS
        self.c_bg = "#f6f1e8"            # Creme suave de fundo principal
        self.c_teal = "#0f5c6e"          # Teal oficial da marca
        self.c_teal_dark = "#0b2329"     # Deep Teal para cabeçalho e contrastes
        self.c_teal_hover = "#147287"    # Teal vibrante para hover de botões
        self.c_teal_light = "#e8f3f5"    # Fundo de pills e badges suaves
        self.c_card_bg = "#ffffff"       # Branco puro dos cards elevados
        self.c_card_inner = "#fcfbfa"    # Fundo interno suave de inputs
        self.c_border = "#e2d9cc"        # Borda sutil dos containers
        self.c_border_focus = "#0f5c6e"  # Borda ao focar campos
        self.c_text = "#2c3b3f"          # Texto primário contrastante
        self.c_text_muted = "#66777b"    # Texto secundário e legendas
        self.c_text_placeholder = "#9eabae"  # Texto do placeholder
        self.c_green = "#1b8a5a"         # Verde sucesso / ativo
        self.c_green_light = "#e4f4ec"   # Fundo suave de badge ativo
        self.c_amber = "#d97706"         # Âmbar de aviso/carregamento
        self.c_cream = "#efe3cf"         # Creme claro de suporte
        self.c_keycap_bg = "#f4efe6"     # Fundo de teclas dos atalhos
        self.c_keycap_border = "#d8cdbc" # Borda das teclas
        self.c_output_bg = "#f5f9f8"     # Fundo do painel de resultado

        self.root.configure(bg=self.c_bg)

        # Estado das abas e widgets
        self.current_tab = "translate"
        self._placeholder_text = "Digite ou cole qualquer texto em inglês para traduzir instantaneamente..."
        self._history_items_data: Dict[str, Tuple[str, str, float]] = {}
        self._is_translating: bool = False
        self._is_running_selftest: bool = False
        self._gui_callback_queue: queue.Queue = queue.Queue()

        # Configura ícone da janela
        self._set_app_icon()

        # Constrói a interface moderna
        self._build_header()
        self._build_navigation_tabs()
        
        # Container dinâmico das páginas/abas
        self.tab_container = tk.Frame(self.root, bg=self.c_bg)
        self.tab_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 0))

        # Constrói as 3 abas
        self._build_tab_translator()
        self._build_tab_history()
        self._build_tab_hardware()

        # Exibe a aba inicial (Tradutor Rápido)
        self._switch_tab("translate")

        # Rodapé com diagnóstico e botões de controle
        self._build_hardware_footer()

        # Escuta contínua de callbacks entre threads
        self.root.after(25, self.process_gui_callbacks)

        # Protocolo de fechamento: minimiza para manter atalhos ativos
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
        """Cabeçalho moderno em Teal profundo com logo, tipografia e badge de status em tempo real."""
        header_frame = tk.Frame(self.root, bg=self.c_teal_dark, padx=22, pady=12)
        header_frame.pack(fill=tk.X)

        inner_box = tk.Frame(header_frame, bg=self.c_teal_dark)
        inner_box.pack(fill=tk.X)

        # Imagem do logo da Lontra
        self.logo_img = None
        try:
            png_path = get_resource_path("assets/lotra.png")
            if png_path.exists():
                pil_img = Image.open(png_path).resize((46, 46), Image.Resampling.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(pil_img)
                lbl_logo = tk.Label(inner_box, image=self.logo_img, bg=self.c_teal_dark)
                lbl_logo.pack(side=tk.LEFT, padx=(0, 14))
        except Exception:
            pass

        # Textos de Branding (Título e Tagline)
        text_box = tk.Frame(inner_box, bg=self.c_teal_dark)
        text_box.pack(side=tk.LEFT, fill=tk.Y)

        title_lbl = tk.Label(
            text_box,
            text="LoTra",
            font=("Georgia", 20, "bold"),
            fg="#ffffff",
            bg=self.c_teal_dark
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            text_box,
            text="traduza com fluidez  •  100% offline e privativo",
            font=("Segoe UI", 9),
            fg=self.c_cream,
            bg=self.c_teal_dark
        )
        subtitle_lbl.pack(anchor="w")

        # Status Pill à direita
        status_box = tk.Frame(inner_box, bg=self.c_teal_dark)
        status_box.pack(side=tk.RIGHT, fill=tk.Y)

        badge_frame = tk.Frame(status_box, bg="#133842", padx=10, pady=5, highlightbackground="#1b4b57", highlightthickness=1)
        badge_frame.pack(anchor="e")

        ollama_active = False
        ollama_model = ""
        if hasattr(self.app, "translator") and self.app.translator._is_ollama_available():
            ollama_model = self.app.translator._get_available_ollama_model("qwen2.5:1.5b") or ""
            ollama_active = bool(ollama_model)

        dot_color = "#4ade80" if ollama_active else "#fbbf24"
        status_str = f"LLM Ativa ({ollama_model})" if ollama_active else "Offline Seguro (Dicionário)"

        self.lbl_status_dot = tk.Label(badge_frame, text="●", font=("Segoe UI", 10), fg=dot_color, bg="#133842")
        self.lbl_status_dot.pack(side=tk.LEFT, padx=(0, 5))

        self.lbl_status_text = tk.Label(badge_frame, text=status_str, font=("Segoe UI", 8, "bold"), fg="#ffffff", bg="#133842")
        self.lbl_status_text.pack(side=tk.LEFT)

    def _build_navigation_tabs(self):
        """Barra de abas segmentadas estilo Web App moderno (/goal /boost)."""
        nav_bar = tk.Frame(self.root, bg=self.c_bg)
        nav_bar.pack(fill=tk.X, padx=20, pady=(10, 0))

        tabs_wrapper = tk.Frame(nav_bar, bg="#e8dfd2", padx=3, pady=3)
        tabs_wrapper.pack(anchor="w")

        # Botão Aba 1: Tradutor Rápido
        self.btn_tab_translate = tk.Button(
            tabs_wrapper,
            text="⚡ Tradutor Rápido",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=14,
            pady=4,
            cursor="hand2",
            command=lambda: self._switch_tab("translate")
        )
        self.btn_tab_translate.pack(side=tk.LEFT, padx=(0, 2))

        # Botão Aba 2: Histórico & Cache
        self.btn_tab_history = tk.Button(
            tabs_wrapper,
            text="📚 Histórico & Cache",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=14,
            pady=4,
            cursor="hand2",
            command=lambda: self._switch_tab("history")
        )
        self.btn_tab_history.pack(side=tk.LEFT, padx=(0, 2))

        # Botão Aba 3: Hardware & Diagnóstico
        self.btn_tab_hardware = tk.Button(
            tabs_wrapper,
            text="⚙️ Hardware & Diagnóstico",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            padx=14,
            pady=4,
            cursor="hand2",
            command=lambda: self._switch_tab("hardware")
        )
        self.btn_tab_hardware.pack(side=tk.LEFT)

    def _switch_tab(self, tab_id: str):
        """Alterna a exibição das abas com estilos dinâmicos ativos/inativos."""
        self.current_tab = tab_id

        # Atualiza cores dos botões
        for tid, btn in [
            ("translate", self.btn_tab_translate),
            ("history", self.btn_tab_history),
            ("hardware", self.btn_tab_hardware)
        ]:
            if tid == tab_id:
                btn.config(bg=self.c_teal, fg="#ffffff", font=("Segoe UI", 9, "bold"))
            else:
                btn.config(bg="#e8dfd2", fg=self.c_text, font=("Segoe UI", 9))

        # Mostra/Oculta containers
        self.frame_translate.pack_forget()
        self.frame_history.pack_forget()
        self.frame_hardware.pack_forget()

        if tab_id == "translate":
            self.frame_translate.pack(fill=tk.BOTH, expand=True)
        elif tab_id == "history":
            self._refresh_history_list()
            self.frame_history.pack(fill=tk.BOTH, expand=True)
        elif tab_id == "hardware":
            self.frame_hardware.pack(fill=tk.BOTH, expand=True)

    def _build_tab_translator(self):
        """Aba 1: Tradutor Rápido com Hotkey Cards e Workbench de Tradução."""
        self.frame_translate = tk.Frame(self.tab_container, bg=self.c_bg)

        # 1. Hotkey Cards
        self._build_hotkey_cards_into(self.frame_translate)

        # 2. Interactive Translation Card
        self._build_interactive_translator_into(self.frame_translate)

    def _build_hotkey_cards_into(self, parent: tk.Widget):
        """Cards modernos estilo Web com keycaps 3D para Alt+Q e Alt+W."""
        card_container = tk.Frame(parent, bg=self.c_bg, pady=6)
        card_container.pack(fill=tk.X)

        grid_frame = tk.Frame(card_container, bg=self.c_bg)
        grid_frame.pack(fill=tk.X)

        # Card 1: Alt + Q
        card_q = tk.Frame(
            grid_frame, 
            bg=self.c_card_bg, 
            highlightbackground=self.c_border, 
            highlightthickness=1, 
            padx=12, 
            pady=8
        )
        card_q.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        q_head = tk.Frame(card_q, bg=self.c_card_bg)
        q_head.pack(fill=tk.X, pady=(0, 4))

        # Keycap badges [Alt] + [Q]
        self._create_keycap(q_head, "Alt")
        lbl_plus = tk.Label(q_head, text="+", font=("Segoe UI", 9, "bold"), fg=self.c_text_muted, bg=self.c_card_bg)
        lbl_plus.pack(side=tk.LEFT, padx=3)
        self._create_keycap(q_head, "Q")

        lbl_q_pill = tk.Label(
            q_head, 
            text=" Tradução Direta ", 
            font=("Segoe UI", 8, "bold"), 
            bg=self.c_teal_light, 
            fg=self.c_teal, 
            padx=6, 
            pady=1
        )
        lbl_q_pill.pack(side=tk.RIGHT)

        lbl_q_desc = tk.Label(
            card_q,
            text="Selecione qualquer texto e aperte Alt+Q. Não precisa de Ctrl+C prévio.",
            font=("Segoe UI", 8),
            fg=self.c_text_muted,
            bg=self.c_card_bg,
            wraplength=250,
            justify=tk.LEFT
        )
        lbl_q_desc.pack(anchor="w")

        # Card 2: Alt + W
        card_w = tk.Frame(
            grid_frame, 
            bg=self.c_card_bg, 
            highlightbackground=self.c_border, 
            highlightthickness=1, 
            padx=12, 
            pady=8
        )
        card_w.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        w_head = tk.Frame(card_w, bg=self.c_card_bg)
        w_head.pack(fill=tk.X, pady=(0, 4))

        self._create_keycap(w_head, "Alt")
        lbl_plus2 = tk.Label(w_head, text="+", font=("Segoe UI", 9, "bold"), fg=self.c_text_muted, bg=self.c_card_bg)
        lbl_plus2.pack(side=tk.LEFT, padx=3)
        self._create_keycap(w_head, "W")

        lbl_w_pill = tk.Label(
            w_head, 
            text=" Recorte OCR ", 
            font=("Segoe UI", 8, "bold"), 
            bg=self.c_teal_light, 
            fg=self.c_teal, 
            padx=6, 
            pady=1
        )
        lbl_w_pill.pack(side=tk.RIGHT)

        lbl_w_desc = tk.Label(
            card_w,
            text="Recorte uma área da tela com a mira para ler o texto na imagem e traduzir no HUD.",
            font=("Segoe UI", 8),
            fg=self.c_text_muted,
            bg=self.c_card_bg,
            wraplength=250,
            justify=tk.LEFT
        )
        lbl_w_desc.pack(anchor="w")

    def _create_keycap(self, parent: tk.Widget, key_text: str):
        """Cria um botão com aparência física de tecla moderna de teclado."""
        cap = tk.Label(
            parent,
            text=f" {key_text} ",
            font=("Segoe UI", 8, "bold"),
            bg=self.c_keycap_bg,
            fg=self.c_text,
            highlightbackground=self.c_keycap_border,
            highlightthickness=1,
            padx=5,
            pady=1
        )
        cap.pack(side=tk.LEFT)

    def _build_interactive_translator_into(self, parent: tk.Widget):
        """Workbench de Tradução Interativa rápida com layout de card SaaS."""
        main_box = tk.Frame(
            parent, 
            bg=self.c_card_bg, 
            highlightbackground=self.c_border, 
            highlightthickness=1, 
            padx=14, 
            pady=10
        )
        main_box.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        # Top Bar da Caixa de Entrada: Badge + Contador + Botão Limpar
        in_top_bar = tk.Frame(main_box, bg=self.c_card_bg)
        in_top_bar.pack(fill=tk.X, pady=(0, 4))

        badge_in = tk.Label(
            in_top_bar,
            text=" EN  Inglês (Fonte) ",
            font=("Segoe UI", 8, "bold"),
            bg=self.c_teal_light,
            fg=self.c_teal,
            padx=6,
            pady=2
        )
        badge_in.pack(side=tk.LEFT)

        btn_clear = tk.Label(
            in_top_bar,
            text=" ✕ Limpar ",
            font=("Segoe UI", 8),
            bg="#f1ede6",
            fg=self.c_text_muted,
            cursor="hand2",
            padx=6,
            pady=2
        )
        btn_clear.pack(side=tk.RIGHT)
        btn_clear.bind("<Button-1>", lambda e: self._clear_fields())

        self.lbl_char_count = tk.Label(
            in_top_bar,
            text="0 caracteres",
            font=("Segoe UI", 8),
            fg=self.c_text_muted,
            bg=self.c_card_bg
        )
        self.lbl_char_count.pack(side=tk.RIGHT, padx=(0, 10))

        # Campo de Entrada de Texto com Estilo Moderno
        self.txt_input = tk.Text(
            main_box,
            height=3,
            font=("Segoe UI", 10),
            fg=self.c_text,
            bg=self.c_card_inner,
            highlightbackground=self.c_border,
            highlightcolor=self.c_border_focus,
            highlightthickness=1,
            relief=tk.FLAT,
            padx=10,
            pady=6,
            wrap=tk.WORD
        )
        self.txt_input.pack(fill=tk.X, pady=(2, 8))
        self.txt_input.insert(tk.END, "Recent advances in generative ai continue to evolve.")
        self.txt_input.bind("<KeyRelease>", self._on_input_changed)
        self.txt_input.bind("<FocusIn>", self._on_input_focus_in)
        self.txt_input.bind("<FocusOut>", self._on_input_focus_out)
        self.txt_input.bind("<Control-Return>", lambda e: (self._do_manual_translate(async_mode=True), "break"))
        self.txt_input.bind("<Control-KP_Enter>", lambda e: (self._do_manual_translate(async_mode=True), "break"))
        self._update_char_count()

        # Barra de Ações Centrais
        action_bar = tk.Frame(main_box, bg=self.c_card_bg)
        action_bar.pack(fill=tk.X, pady=(0, 8))

        # Botão Primário: Traduzir
        self.btn_translate = tk.Button(
            action_bar,
            text="⚡ Traduzir Texto",
            font=("Segoe UI", 9, "bold"),
            bg=self.c_teal,
            fg="#ffffff",
            activebackground=self.c_teal_hover,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=16,
            pady=5,
            cursor="hand2",
            command=lambda: self._do_manual_translate(async_mode=True)
        )
        self.btn_translate.pack(side=tk.LEFT)

        # Chips de Amostra Rápida
        lbl_chip_hint = tk.Label(action_bar, text="Amostras:", font=("Segoe UI", 8), fg=self.c_text_muted, bg=self.c_card_bg)
        lbl_chip_hint.pack(side=tk.LEFT, padx=(10, 4))

        self._create_sample_chip(action_bar, "Artigo", "Human deskilling and diminished cognitive engagement in AI environments.")
        self._create_sample_chip(action_bar, "Técnico", "Superconducting transmon qubit and cryogenic attenuation stages.")
        self._create_sample_chip(action_bar, "Expressão", "Hit the nail on the head and bite the bullet.")

        # Botão Copiar Tradução
        self.btn_copy = tk.Label(
            action_bar,
            text=" 📋 Copiar ",
            font=("Segoe UI", 8, "bold"),
            bg=self.c_teal_light,
            fg=self.c_teal,
            cursor="hand2",
            padx=8,
            pady=4
        )
        self.btn_copy.pack(side=tk.RIGHT)
        self.btn_copy.bind("<Button-1>", self._copy_output_to_clipboard)

        # Micro-interações de hover nos botões
        def _on_hover_in(lbl, bg, fg=None):
            lbl.config(bg=bg)
            if fg:
                lbl.config(fg=fg)

        def _on_hover_out(lbl, bg, fg=None):
            lbl.config(bg=bg)
            if fg:
                lbl.config(fg=fg)

        self.btn_copy.bind("<Enter>", lambda e: _on_hover_in(self.btn_copy, "#d8edf1"))
        self.btn_copy.bind("<Leave>", lambda e: _on_hover_out(self.btn_copy, self.c_teal_light))
        btn_clear.bind("<Enter>", lambda e: _on_hover_in(btn_clear, "#e5ded4", self.c_text))
        btn_clear.bind("<Leave>", lambda e: _on_hover_out(btn_clear, "#f1ede6", self.c_text_muted))

        # Label de Estatísticas (Latência e Motor)
        self.lbl_stats = tk.Label(
            action_bar,
            text="",
            font=("Segoe UI", 8),
            fg=self.c_text_muted,
            bg=self.c_card_bg
        )
        self.lbl_stats.pack(side=tk.RIGHT, padx=(0, 8))

        # Top Bar da Caixa de Saída: Badge PT-BR + Motor Badge
        out_top_bar = tk.Frame(main_box, bg=self.c_card_bg)
        out_top_bar.pack(fill=tk.X, pady=(2, 4))

        badge_out = tk.Label(
            out_top_bar,
            text=" PT-BR  Português (Resultado) ",
            font=("Segoe UI", 8, "bold"),
            bg=self.c_green_light,
            fg=self.c_green,
            padx=6,
            pady=2
        )
        badge_out.pack(side=tk.LEFT)

        self.lbl_engine_badge = tk.Label(
            out_top_bar,
            text="",
            font=("Segoe UI", 8),
            fg=self.c_text_muted,
            bg=self.c_card_bg
        )
        self.lbl_engine_badge.pack(side=tk.RIGHT)

        # Campo de Saída Traduzido
        self.txt_output = tk.Text(
            main_box,
            height=4,
            font=("Segoe UI", 10),
            fg=self.c_teal_dark,
            bg=self.c_output_bg,
            highlightbackground=self.c_border,
            highlightthickness=1,
            relief=tk.FLAT,
            padx=10,
            pady=6,
            wrap=tk.WORD
        )
        self.txt_output.pack(fill=tk.BOTH, expand=True)

    def _create_sample_chip(self, parent: tk.Widget, label: str, text_to_set: str):
        """Cria um chip/pill interativo de amostra rápida com hover states."""
        chip = tk.Label(
            parent,
            text=f" {label} ",
            font=("Segoe UI", 8),
            bg="#efeae1",
            fg=self.c_text,
            cursor="hand2",
            padx=5,
            pady=2
        )
        chip.pack(side=tk.LEFT, padx=2)
        chip.bind("<Button-1>", lambda e: self._set_input_text(text_to_set))
        chip.bind("<Enter>", lambda e: chip.config(bg="#e2dad0"))
        chip.bind("<Leave>", lambda e: chip.config(bg="#efeae1"))

    def _on_input_focus_in(self, event=None):
        """Manipula ganho de foco: limpa placeholder se presente e destaca borda."""
        self.txt_input.config(highlightbackground=self.c_border_focus)
        raw = self.txt_input.get("1.0", tk.END).strip()
        if raw == self._placeholder_text:
            self.txt_input.delete("1.0", tk.END)
            self.txt_input.config(fg=self.c_text)
            self._update_char_count()

    def _on_input_focus_out(self, event=None):
        """Manipula perda de foco: restaura placeholder se campo estiver vazio e reseta borda."""
        self.txt_input.config(highlightbackground=self.c_border)
        raw = self.txt_input.get("1.0", tk.END).strip()
        if not raw or raw == self._placeholder_text:
            self.txt_input.delete("1.0", tk.END)
            self.txt_input.insert(tk.END, self._placeholder_text)
            self.txt_input.config(fg=self.c_text_placeholder)
        self._update_char_count()

    def _set_input_text(self, text: str):
        """Define texto no campo de entrada e atualiza contador."""
        self.txt_input.delete("1.0", tk.END)
        self.txt_input.config(fg=self.c_text)
        self.txt_input.insert(tk.END, text)
        self._update_char_count()

    def _on_input_changed(self, event=None):
        """Atualiza contador de caracteres e palavras ao digitar."""
        raw = self.txt_input.get("1.0", tk.END).strip()
        if raw != self._placeholder_text and self.txt_input.cget("fg") == self.c_text_placeholder:
            self.txt_input.config(fg=self.c_text)
        self._update_char_count()

    def _update_char_count(self):
        """Calcula caracteres e palavras do campo de entrada."""
        raw = self.txt_input.get("1.0", tk.END).strip()
        if raw == self._placeholder_text:
            chars = 0
            words = 0
        else:
            chars = len(raw)
            words = len(raw.split()) if raw else 0
        self.lbl_char_count.config(text=f"{chars} caracteres • {words} palavras")

    def _copy_output_to_clipboard(self, event=None):
        """Copia o texto traduzido para a área de transferência com feedback toast."""
        out_text = self.txt_output.get("1.0", tk.END).strip()
        if not out_text:
            return
        set_windows_clipboard_text(out_text)
        self.btn_copy.config(text=" ✓ Copiado! ", bg=self.c_green, fg="#ffffff")
        self.root.after(1400, lambda: self.btn_copy.config(text=" 📋 Copiar ", bg=self.c_teal_light, fg=self.c_teal))

    # Compatibilidade com a arquitetura antiga
    def _build_hotkey_cards(self):
        pass

    def _build_interactive_translator(self):
        pass

    def _build_tab_history(self):
        """Aba 2: Histórico e visualização do cache ACID do cofre SQLite."""
        self.frame_history = tk.Frame(self.tab_container, bg=self.c_bg)

        card = tk.Frame(self.frame_history, bg=self.c_card_bg, highlightbackground=self.c_border, highlightthickness=1, padx=14, pady=12)
        card.pack(fill=tk.BOTH, expand=True)

        top_row = tk.Frame(card, bg=self.c_card_bg)
        top_row.pack(fill=tk.X, pady=(0, 8))

        lbl_hist_title = tk.Label(top_row, text="Traduções em Cache (ACID SQLite)", font=("Segoe UI", 10, "bold"), fg=self.c_text, bg=self.c_card_bg)
        lbl_hist_title.pack(side=tk.LEFT)

        btn_refresh = tk.Button(
            top_row,
            text="🔄 Atualizar",
            font=("Segoe UI", 8),
            bg=self.c_teal_light,
            fg=self.c_teal,
            relief=tk.FLAT,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._refresh_history_list
        )
        btn_refresh.pack(side=tk.RIGHT)

        # Lista de itens
        columns = ("source", "translation", "latency")
        self.tree_history = ttk.Treeview(card, columns=columns, show="headings", height=9)
        self.tree_history.heading("source", text="Texto Original (EN)")
        self.tree_history.heading("translation", text="Tradução Salva (PT-BR)")
        self.tree_history.heading("latency", text="Latência")

        self.tree_history.column("source", width=220)
        self.tree_history.column("translation", width=260)
        self.tree_history.column("latency", width=65, anchor="center")
        self.tree_history.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.tree_history.bind("<Double-1>", lambda e: self._load_selected_history_item())

        # Ações na parte inferior da aba de histórico
        actions_row = tk.Frame(card, bg=self.c_card_bg)
        actions_row.pack(fill=tk.X)

        btn_load = tk.Button(
            actions_row,
            text="⚡ Carregar no Tradutor",
            font=("Segoe UI", 9, "bold"),
            bg=self.c_teal,
            fg="#ffffff",
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._load_selected_history_item
        )
        btn_load.pack(side=tk.LEFT)

        btn_copy_hist = tk.Button(
            actions_row,
            text="📋 Copiar Tradução",
            font=("Segoe UI", 9),
            bg="#f1ede6",
            fg=self.c_text,
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._copy_selected_history_item
        )
        btn_copy_hist.pack(side=tk.LEFT, padx=(8, 0))

    def _refresh_history_list(self):
        """Carrega as traduções recentes armazenadas no DocumentContextVault mantendo o texto completo íntegro."""
        self._history_items_data.clear()
        for item in self.tree_history.get_children():
            self.tree_history.delete(item)

        if not hasattr(self.app, "vault") or not self.app.vault:
            return

        try:
            with self.app.vault._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT source_text, translated_text, latency_ms FROM translation_cache ORDER BY created_at DESC LIMIT 60"
                )
                rows = cur.fetchall()
                for r in rows:
                    src = r["source_text"]
                    trans = r["translated_text"]
                    if hasattr(self.app.vault, "enable_privacy") and self.app.vault.enable_privacy:
                        from privacy_vault import VaultProtector
                        try:
                            src = VaultProtector.decrypt_text(src)
                        except Exception:
                            pass
                        try:
                            trans = VaultProtector.decrypt_text(trans)
                        except Exception:
                            pass
                    lat_val = r["latency_ms"]
                    lat = f"{lat_val:.1f}ms"

                    disp_src = src.replace("\n", " ").strip()
                    if len(disp_src) > 55:
                        disp_src = disp_src[:52] + "..."
                    disp_trans = trans.replace("\n", " ").strip()
                    if len(disp_trans) > 65:
                        disp_trans = disp_trans[:62] + "..."

                    item_id = self.tree_history.insert("", tk.END, values=(disp_src, disp_trans, lat))
                    self._history_items_data[item_id] = (src, trans, lat_val)
        except Exception as e:
            print(f"[LoTra History Error] {e}")

    def _load_selected_history_item(self):
        """Carrega o item selecionado do histórico de volta ao Tradutor Rápido com o texto completo íntegro."""
        sel = self.tree_history.selection()
        if not sel:
            return
        item_id = sel[0]
        if item_id in self._history_items_data:
            full_src, full_trans, _ = self._history_items_data[item_id]
        else:
            vals = self.tree_history.item(item_id, "values")
            full_src = vals[0] if vals else ""
            full_trans = vals[1] if vals and len(vals) > 1 else ""

        if full_src:
            self._set_input_text(full_src)
            self.txt_output.delete("1.0", tk.END)
            self.txt_output.insert(tk.END, full_trans)
            self._switch_tab("translate")

    def _copy_selected_history_item(self):
        """Copia a tradução completa selecionada do histórico para o clipboard."""
        sel = self.tree_history.selection()
        if not sel:
            return
        item_id = sel[0]
        if item_id in self._history_items_data:
            _, full_trans, _ = self._history_items_data[item_id]
        else:
            vals = self.tree_history.item(item_id, "values")
            full_trans = vals[1] if vals and len(vals) > 1 else ""

        if full_trans:
            set_windows_clipboard_text(full_trans)

    def _build_tab_hardware(self):
        """Aba 3: Diagnóstico de Hardware em tempo real e verificação de subsistemas."""
        self.frame_hardware = tk.Frame(self.tab_container, bg=self.c_bg)

        card = tk.Frame(self.frame_hardware, bg=self.c_card_bg, highlightbackground=self.c_border, highlightthickness=1, padx=16, pady=14)
        card.pack(fill=tk.BOTH, expand=True)

        lbl_hw_title = tk.Label(card, text="Diagnóstico de Hardware & Segurança", font=("Segoe UI", 11, "bold"), fg=self.c_text, bg=self.c_card_bg)
        lbl_hw_title.pack(anchor="w", pady=(0, 10))

        hw = {}
        try:
            hw = self.app.profile_hardware()
        except Exception:
            pass

        grid = tk.Frame(card, bg=self.c_card_bg)
        grid.pack(fill=tk.X, pady=(0, 12))

        # Card CPU
        self._create_metric_card(grid, "CPU & Núcleos", f"{hw.get('cpu_cores', 8)} Cores (AVX2: Ativo)", 0, 0)
        # Card RAM
        self._create_metric_card(grid, "Memória RAM", f"{hw.get('avail_ram_gb', 0)}GB Livre / {hw.get('total_ram_gb', 0)}GB", 0, 1)
        # Card GPU
        self._create_metric_card(grid, "GPU & Aceleração", f"{hw.get('gpu_name', 'iGPU')} ({hw.get('gpu_backend', 'DirectML')})", 1, 0)
        # Card Motor
        self._create_metric_card(grid, "Tier Recomendado", f"{hw.get('recommended_tier', 'small').upper()} ({hw.get('recommended_model', 'qwen2.5:1.5b')})", 1, 1)

        # Card Privacidade
        priv_frame = tk.Frame(card, bg=self.c_teal_light, padx=12, pady=10, highlightbackground=self.c_teal, highlightthickness=1)
        priv_frame.pack(fill=tk.X, pady=(6, 12))

        lbl_priv = tk.Label(
            priv_frame,
            text="🔒 Princípio Read-Only & 100% Offline Garantidos\n"
                 "• Zero comunicação com servidores externos ou APIs remotas.\n"
                 "• Banco e cache criptografados em repouso com Windows DPAPI.\n"
                 "• Buffers efêmeros de imagem de OCR destruídos na RAM após tradução.",
            font=("Segoe UI", 8),
            fg=self.c_teal_dark,
            bg=self.c_teal_light,
            justify=tk.LEFT
        )
        lbl_priv.pack(anchor="w")

        # Botão Executar Auto-Diagnóstico Completo
        self.btn_run_selftest = tk.Button(
            card,
            text="🚀 Executar Auto-Diagnóstico Completo (Self-Test)",
            font=("Segoe UI", 9, "bold"),
            bg=self.c_teal,
            fg="#ffffff",
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor="hand2",
            command=lambda: self._run_gui_self_test(async_mode=True)
        )
        self.btn_run_selftest.pack(anchor="w")

        self.lbl_selftest_res = tk.Label(card, text="", font=("Segoe UI", 8), fg=self.c_text_muted, bg=self.c_card_bg)
        self.lbl_selftest_res.pack(anchor="w", pady=(6, 0))

    def _create_metric_card(self, parent: tk.Widget, title: str, value: str, row: int, col: int):
        """Cria um mini card de métrica de hardware."""
        c = tk.Frame(parent, bg="#faf8f5", highlightbackground=self.c_border, highlightthickness=1, padx=10, pady=8)
        c.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
        parent.columnconfigure(col, weight=1)

        lbl_t = tk.Label(c, text=title, font=("Segoe UI", 7, "bold"), fg=self.c_text_muted, bg="#faf8f5")
        lbl_t.pack(anchor="w")

        lbl_v = tk.Label(c, text=value, font=("Segoe UI", 9, "bold"), fg=self.c_text, bg="#faf8f5")
        lbl_v.pack(anchor="w", pady=(2, 0))

    def _schedule_on_ui_thread(self, fn):
        """Agenda execução de uma função com segurança na thread da interface gráfica."""
        if threading.current_thread() is threading.main_thread():
            try:
                fn()
            except Exception:
                pass
        else:
            self._gui_callback_queue.put(fn)

    def process_gui_callbacks(self):
        """Drena e executa callbacks de threads de segundo plano na thread da UI."""
        while not self._gui_callback_queue.empty():
            try:
                fn = self._gui_callback_queue.get_nowait()
                fn()
            except Exception:
                pass
        if hasattr(self, "root") and self.root:
            try:
                self.root.after(25, self.process_gui_callbacks)
            except Exception:
                pass

    def _run_gui_self_test(self, async_mode: bool = False):
        """Executa auto-teste de integridade e exibe o resultado diretamente na UI de forma thread-safe."""
        if self._is_running_selftest:
            return

        self._is_running_selftest = True
        self.lbl_selftest_res.config(text="Executando diagnóstico dos subsistemas...", fg=self.c_teal)
        if hasattr(self, "btn_run_selftest"):
            self.btn_run_selftest.config(state=tk.DISABLED)
        self.root.update_idletasks()

        def _finalize(res):
            try:
                if res.get("all_passed", False):
                    self.lbl_selftest_res.config(text="✓ Todos os subsistemas operando com integridade 100%!", fg=self.c_green)
                else:
                    self.lbl_selftest_res.config(text="⚠ Atenção: Um ou mais subsistemas reportaram avisos.", fg=self.c_amber)
            finally:
                self._is_running_selftest = False
                if hasattr(self, "btn_run_selftest"):
                    self.btn_run_selftest.config(state=tk.NORMAL)

        def _worker():
            try:
                res = self.app.run_self_test()
            except Exception as e:
                res = {"all_passed": False, "error": str(e)}
            self._schedule_on_ui_thread(lambda: _finalize(res))

        if async_mode:
            threading.Thread(target=_worker, daemon=True, name="LoTra_SelfTest_Worker").start()
        else:
            try:
                res = self.app.run_self_test()
            except Exception as e:
                res = {"all_passed": False, "error": str(e)}
            _finalize(res)

    def _build_hardware_footer(self):
        """Barra de rodapé com diagnóstico de hardware e botões de gerenciamento."""
        footer_frame = tk.Frame(self.root, bg=self.c_bg, padx=20, pady=10)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM)

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

        self.lbl_hw = tk.Label(footer_frame, text=hw_str, font=("Segoe UI", 8), fg=self.c_text_muted, bg=self.c_bg)
        self.lbl_hw.pack(anchor="w", pady=(0, 6))

        # Botões de ação do rodapé
        action_bar = tk.Frame(footer_frame, bg=self.c_bg)
        action_bar.pack(fill=tk.X)

        btn_minimize = tk.Button(
            action_bar,
            text="🗕 Minimizar (Manter Atalhos Ativos)",
            font=("Segoe UI", 9),
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
            text="✕ Encerrar LoTra",
            font=("Segoe UI", 9),
            bg="#fce8e6",
            fg="#c5221f",
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._exit_app
        )
        btn_exit.pack(side=tk.RIGHT)

    def _do_manual_translate(self, async_mode: bool = False):
        """Executa tradução do texto digitado no campo de teste com streaming responsivo e não-bloqueante."""
        if self._is_translating:
            return

        raw_text = self.txt_input.get("1.0", tk.END).strip()
        if raw_text == self._placeholder_text or not raw_text:
            return

        self._is_translating = True
        self.txt_output.delete("1.0", tk.END)
        self.lbl_stats.config(text="Traduzindo...", fg=self.c_teal)
        if hasattr(self, "btn_translate"):
            self.btn_translate.config(text="⏳ Traduzindo...", state=tk.DISABLED)
        self.root.update_idletasks()

        def stream_cb(delta: str, full_so_far: str):
            def _update():
                try:
                    self.txt_output.delete("1.0", tk.END)
                    self.txt_output.insert(tk.END, full_so_far)
                    self.txt_output.see(tk.END)
                except Exception:
                    pass
            self._schedule_on_ui_thread(_update)

        def _finalize(res):
            try:
                self.txt_output.delete("1.0", tk.END)
                self.txt_output.insert(tk.END, res.get("translated_text", ""))
                lat = res.get("latency_ms", 0.0)
                engine = res.get("engine_used", "LoTra Engine")
                self.lbl_stats.config(text=f"Latência: {lat:.1f}ms | {engine}", fg=self.c_text_muted)
                if hasattr(self, "lbl_engine_badge"):
                    self.lbl_engine_badge.config(text=f"⏱ {lat:.1f}ms • {engine}")
            finally:
                self._is_translating = False
                if hasattr(self, "btn_translate"):
                    self.btn_translate.config(text="⚡ Traduzir Texto", state=tk.NORMAL)

        def _worker():
            try:
                try:
                    res = self.app.translate_text(raw_text, stream_callback=stream_cb)
                except TypeError:
                    res = self.app.translate_text(raw_text)
            except Exception as e:
                res = {
                    "translated_text": f"Erro durante a tradução: {e}",
                    "latency_ms": 0.0,
                    "engine_used": "Falha"
                }
            self._schedule_on_ui_thread(lambda: _finalize(res))

        if async_mode:
            threading.Thread(target=_worker, daemon=True, name="LoTra_Manual_Translate_Worker").start()
        else:
            try:
                try:
                    res = self.app.translate_text(raw_text, stream_callback=lambda d, f: None)
                except TypeError:
                    res = self.app.translate_text(raw_text)
            except Exception as e:
                res = {
                    "translated_text": f"Erro durante a tradução: {e}",
                    "latency_ms": 0.0,
                    "engine_used": "Falha"
                }
            _finalize(res)

    def _clear_fields(self):
        """Limpa campos de teste e restaura placeholder de forma elegante."""
        self.txt_input.delete("1.0", tk.END)
        self.txt_input.insert(tk.END, self._placeholder_text)
        self.txt_input.config(fg=self.c_text_placeholder)
        self.txt_output.delete("1.0", tk.END)
        self.lbl_stats.config(text="")
        if hasattr(self, "lbl_engine_badge"):
            self.lbl_engine_badge.config(text="")
        self._update_char_count()

    def _on_close_requested(self):
        """Ao clicar no botão de fechar (X), minimiza mantendo os atalhos globais ativos."""
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
        if not getattr(self, "app", None) or not hasattr(self.app, "_ui_queue"):
            return
        while not self.app._ui_queue.empty():
            try:
                item = self.app._ui_queue.get_nowait()
                if isinstance(item, dict):
                    act = item.get("_action")
                    trans_id = item.get("trans_id")
                    if trans_id is not None and hasattr(self.app, "_active_translation_id") and trans_id < self.app._active_translation_id:
                        continue

                    if act == "start_native_snip":
                        self.app._handle_native_snip()
                        continue
                    elif act == "stream_start":
                        self.app.hud.start_stream(cursor_pos=item.get("cursor_pos"))
                        continue
                    elif act == "stream_chunk":
                        self.app.hud.update_stream(item.get("delta", ""), item.get("full_text", ""))
                        continue
                    elif act == "stream_end":
                        r = item.get("res", {})
                        self.app.hud.finish_stream(
                            final_text=r.get("translated_text", ""),
                            latency_ms=r.get("latency_ms", 0.0),
                            engine_name=r.get("engine_used", "LoTra Engine")
                        )
                        continue

                res = item
                self.app.hud.show(
                    translated_text=res["translated_text"],
                    source_text=res.get("source_text", ""),
                    latency_ms=res.get("latency_ms", 0.0),
                    engine_name=res.get("engine_used", "LoTra Engine"),
                    timeout_sec=res.get("timeout_sec", 0.0),
                    cursor_pos=res.get("cursor_pos")
                )
            except Exception:
                break

        if self.app._is_serving:
            self.root.after(30, self.process_incoming_queue)

    def start_main_loop(self):
        """Inicia o loop visual da aplicação."""
        self.root.after(100, self.process_incoming_queue)
        self.root.mainloop()
