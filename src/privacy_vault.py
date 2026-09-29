"""
Módulo de Privacidade, Proteção Anti-Vazamento e Cofre Criptografado (Privacy Vault).
Responde aos requisitos críticos de segurança:
1. Anti-Vazamento: Leitura e processamento de OCR/Tradução 100% em memória (Ephemeral In-Memory Buffers).
   Nenhum arquivo temporário de texto simples ou imagem intermediária é despejado no disco.
2. Limpeza Segura de Memória (Memory Zeroing / Wiping):
   Sobrescrita imediata de buffers e bitmaps com zeros antes da liberação.
3. Cofre Protegido Localmente:
   Criptografia de dados sensíveis em repouso (histórico de leitura, textos extraídos, cache de tradução).
   No Windows, utiliza DPAPI (Data Protection API) via crypt32.dll, vinculando a chave
   às credenciais de login do usuário do SO.
   Em outros sistemas, utiliza derivação de chave criptográfica protegida com HMAC.
"""

import os
import sys
import io
import ctypes
import secrets
import hashlib
import hmac
from pathlib import Path
from typing import Optional, Union, Tuple, Any
from PIL import Image

# Estrutura Windows DPAPI para ctypes
if sys.platform == "win32":
    from ctypes import wintypes
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte))
        ]

def secure_wipe_memory(target: Union[bytearray, memoryview, ctypes.Array, Image.Image]):
    """
    Limpa e sobrescreve ativamente a memória para impedir vazamento de dados confidenciais
    lidos ou traduzidos (anti-memory dumping / forensic recovery).
    """
    try:
        if isinstance(target, bytearray):
            target[:] = b"\x00" * len(target)
        elif isinstance(target, memoryview):
            target[:len(target)] = b"\x00" * len(target)
        elif isinstance(target, Image.Image):
            # Para objetos PIL, sobrescreve o buffer interno de pixels se acessível
            try:
                raw_bytes = target.tobytes()
                # Tenta forçar recriação de imagem nula
                target.paste(0, [0, 0, target.size[0], target.size[1]])
            except Exception:
                pass
        elif hasattr(target, "_type_") and hasattr(target, "_length_"):
            # ctypes array
            ctypes.memset(ctypes.byref(target), 0, ctypes.sizeof(target))
    except Exception:
        pass

class EphemeralImageBuffer:
    """
    Buffer de Imagem 100% Efêmero em Memória RAM (io.BytesIO).
    Elimina totalmente arquivos temporários no disco durante a captura,
    pré-processamento, corte e OCR.
    """
    def __init__(self, initial_bytes: Optional[bytes] = None):
        self._bio = io.BytesIO(initial_bytes) if initial_bytes else io.BytesIO()
        self._is_closed = False

    def write(self, data: bytes) -> int:
        return self._bio.write(data)

    def get_bytes(self) -> bytes:
        return self._bio.getvalue()

    def get_bytearray_copy(self) -> bytearray:
        """Retorna bytearray mutável que pode ser explicitamente destruído com secure_wipe_memory."""
        return bytearray(self._bio.getvalue())

    def to_pil_image(self) -> Image.Image:
        self._bio.seek(0)
        img = Image.open(self._bio)
        img.load()
        return img

    @classmethod
    def from_pil_image(cls, img: Image.Image, format: str = "PNG") -> "EphemeralImageBuffer":
        buf = cls()
        img.save(buf._bio, format=format)
        buf._bio.seek(0)
        return buf

    def secure_close(self):
        """Sobrescreve o conteúdo interno do stream em memória antes de fechar."""
        if not self._is_closed:
            try:
                size = self._bio.tell() or len(self._bio.getvalue())
                self._bio.seek(0)
                self._bio.write(b"\x00" * size)
                self._bio.close()
            except Exception:
                pass
            self._is_closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.secure_close()

class VaultProtector:
    """
    Cofre Criptográfico de Conteúdo do Usuário:
    Garante que traduções salvas no cache e textos do histórico de leitura
    não possam ser inspecionados em texto claro por outro usuário ou software malicioso.
    """
    _salt = b"FrankTranslator_DPAPI_Salt_v1"

    @staticmethod
    def _dpapi_protect(plaintext_bytes: bytes) -> bytes:
        """Criptografa usando Windows DPAPI (vinculado à conta do usuário logado)."""
        blob_in = DATA_BLOB(
            len(plaintext_bytes),
            ctypes.cast(ctypes.c_char_p(plaintext_bytes), ctypes.POINTER(ctypes.c_byte))
        )
        blob_out = DATA_BLOB()
        
        # CryptProtectData: flag 0x01 = CRYPTPROTECT_UI_FORBIDDEN
        res = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            "FrankTranslator_ProtectedPayload",
            None, None, None, 0x01,
            ctypes.byref(blob_out)
        )
        if not res:
            raise RuntimeError("Falha ao invocar Windows DPAPI CryptProtectData")
            
        encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return encrypted

    @staticmethod
    def _dpapi_unprotect(ciphertext_bytes: bytes) -> bytes:
        """Descriptografa usando Windows DPAPI."""
        blob_in = DATA_BLOB(
            len(ciphertext_bytes),
            ctypes.cast(ctypes.c_char_p(ciphertext_bytes), ctypes.POINTER(ctypes.c_byte))
        )
        blob_out = DATA_BLOB()
        
        res = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None, None, None, None, 0x01,
            ctypes.byref(blob_out)
        )
        if not res:
            raise RuntimeError("Falha ao invocar Windows DPAPI CryptUnprotectData")
            
        decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return decrypted

    _key_dir: Optional[Path] = None

    @classmethod
    def set_key_dir(cls, key_dir: Optional[Union[str, Path]]):
        cls._key_dir = Path(key_dir) if key_dir else None

    @classmethod
    def _get_key_file_path(cls) -> Path:
        if cls._key_dir:
            cls._key_dir.mkdir(parents=True, exist_ok=True)
            return cls._key_dir / ".vault_master.key"
        from platform_core import get_app_data_dir
        return get_app_data_dir() / "db" / ".vault_master.key"

    @staticmethod
    def _fallback_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
        """Gera keystream pseudoaleatório criptográfico com HMAC-SHA256 (O(N) streaming)."""
        blocks = []
        counter = 0
        current_len = 0
        while current_len < length:
            h = hmac.new(key, nonce + counter.to_bytes(4, byteorder='big'), hashlib.sha256).digest()
            blocks.append(h)
            current_len += len(h)
            counter += 1
        return b"".join(blocks)[:length]

    @classmethod
    def _fallback_encrypt(cls, plaintext_bytes: bytes) -> bytes:
        """Cifragem autenticada portátil (Linux/macOS) sem dependência externa."""
        key_file = cls._get_key_file_path()
        
        if not key_file.exists():
            master_key = secrets.token_bytes(32)
            key_file.write_bytes(master_key)
            if hasattr(os, "chmod"):
                try:
                    os.chmod(str(key_file), 0o600) # Somente proprietário
                except Exception:
                    pass
        else:
            master_key = key_file.read_bytes()

        nonce = secrets.token_bytes(16)
        keystream = cls._fallback_keystream(master_key, nonce, len(plaintext_bytes))
        ciphertext = bytes([p ^ k for p, k in zip(plaintext_bytes, keystream)])
        mac = hmac.new(master_key, nonce + ciphertext, hashlib.sha256).digest()
        return b"ENC1:" + nonce + mac + ciphertext

    @classmethod
    def _fallback_decrypt(cls, data: bytes) -> bytes:
        if not data.startswith(b"ENC1:"):
            return data
            
        payload = data[5:]
        nonce = payload[:16]
        mac = payload[16:48]
        ciphertext = payload[48:]

        key_file = cls._get_key_file_path()
        if not key_file.exists():
            raise RuntimeError("Chave mestre do cofre não encontrada")
        master_key = key_file.read_bytes()

        expected_mac = hmac.new(master_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("Violação de integridade nos dados do cofre!")

        keystream = cls._fallback_keystream(master_key, nonce, len(ciphertext))
        return bytes([c ^ k for c, k in zip(ciphertext, keystream)])

    @classmethod
    def encrypt_text(cls, text: str) -> str:
        """
        Criptografa texto confidencial.
        Retorna string codificada (hex) segura para armazenamento no banco de dados.
        """
        if not text:
            return ""
        data = text.encode("utf-8")
        
        if sys.platform == "win32":
            try:
                encrypted_bytes = b"DPAPI:" + cls._dpapi_protect(data)
            except Exception:
                encrypted_bytes = cls._fallback_encrypt(data)
        else:
            encrypted_bytes = cls._fallback_encrypt(data)
            
        return encrypted_bytes.hex()

    @classmethod
    def decrypt_text(cls, encrypted_hex: str) -> str:
        """
        Descriptografa texto do cofre.
        """
        if not encrypted_hex:
            return ""
        try:
            raw = bytes.fromhex(encrypted_hex)
        except ValueError:
            # Não estava em hex, pode ser texto antigo não criptografado
            return encrypted_hex

        if raw.startswith(b"DPAPI:"):
            if sys.platform == "win32":
                decrypted = cls._dpapi_unprotect(raw[6:])
                return decrypted.decode("utf-8", errors="replace")
            else:
                return "<Encrypted-DPAPI-Payload>"
        elif raw.startswith(b"ENC1:"):
            decrypted = cls._fallback_decrypt(raw)
            return decrypted.decode("utf-8", errors="replace")
        else:
            # Texto simples pré-existente
            try:
                return raw.decode("utf-8")
            except Exception:
                return encrypted_hex
