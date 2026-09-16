# ===============================
# 🔐 PRODUCTION-READY STEGANOGRAPHY BACKEND
# ===============================

import json
import logging
import numpy as np
import cv2
import reedsolo
import zlib
import base64  # ✅ FIXED (was missing)

from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes

# ===============================
# ⚙️ CONFIG
# ===============================
class Config:
    RSA_KEY_SIZE = 2048
    AES_KEY_SIZE = 16
    RS_PARITY_BYTES = 32
    CHAOS_SEED = 0.5

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StegoSystem")

# ===============================
# 🔑 KEY MANAGER
# ===============================
class KeyManager:
    def __init__(self):
        self.private_key = RSA.generate(Config.RSA_KEY_SIZE)
        self.public_key = self.private_key.publickey()

    def encrypt_key(self, key):
        cipher = PKCS1_OAEP.new(self.public_key)
        return cipher.encrypt(key)

    def decrypt_key(self, enc_key):
        cipher = PKCS1_OAEP.new(self.private_key)
        return cipher.decrypt(enc_key)

key_manager = KeyManager()

# ===============================
# 🌪️ CHAOS ENGINE
# ===============================
class ChaosEngine:

    @staticmethod
    def generate_map(size, seed):
        x = np.zeros(size)
        x[0] = seed

        for i in range(1, size):
            x[i] = 3.99 * x[i-1] * (1 - x[i-1])

        return np.argsort(x)

    @staticmethod
    def scramble(img):
        flat = img.flatten()
        idx = ChaosEngine.generate_map(len(flat), Config.CHAOS_SEED)
        return flat[idx].reshape(img.shape)

    @staticmethod
    def descramble(img):
        flat = img.flatten()
        idx = ChaosEngine.generate_map(len(flat), Config.CHAOS_SEED)

        original = np.zeros_like(flat)
        original[idx] = flat

        return original.reshape(img.shape)

# ===============================
# 🔐 CRYPTO ENGINE
# ===============================
class CryptoEngine:

    @staticmethod
    def encrypt(data: bytes):
        key = get_random_bytes(Config.AES_KEY_SIZE)

        cipher = AES.new(key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(data)

        enc_key = key_manager.encrypt_key(key)

        return enc_key, cipher.nonce, tag, ciphertext

    @staticmethod
    def decrypt(enc_key, nonce, tag, ciphertext):
        key = key_manager.decrypt_key(enc_key)

        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

# ===============================
# 🧩 ERROR CORRECTION
# ===============================
class ErrorCorrection:
    rs = reedsolo.RSCodec(Config.RS_PARITY_BYTES)

    @staticmethod
    def encode(data):
        return ErrorCorrection.rs.encode(data)

    @staticmethod
    def decode(data):
        return ErrorCorrection.rs.decode(data)[0]

# ===============================
# 🖼️ STEGO ENGINE
# ===============================
class StegoEngine:

    @staticmethod
    def embed(cover, data_bytes):
        bits = ''.join(format(b, '08b') for b in data_bytes)
        flat = cover.flatten()

        if len(bits) > len(flat):
            raise ValueError("Payload too large for cover image")

        for i, bit in enumerate(bits):
            flat[i] = (flat[i] & 254) | int(bit)

        return flat.reshape(cover.shape)

    @staticmethod
    def extract(image, length):
        flat = image.flatten()

        bits = [str(flat[i] & 1) for i in range(length * 8)]

        data = bytearray()
        for i in range(0, len(bits), 8):
            data.append(int(''.join(bits[i:i+8]), 2))

        return bytes(data)

# ===============================
# 🚀 MAIN SERVICE
# ===============================
class StegoService:

    @staticmethod
    def encrypt(secret_path, cover_path):
        logger.info("🔐 Starting encryption...")

        secret = cv2.imread(secret_path, cv2.IMREAD_GRAYSCALE)
        cover = cv2.imread(cover_path, cv2.IMREAD_GRAYSCALE)

        if secret is None or cover is None:
            raise ValueError("Invalid image input")

        scrambled = ChaosEngine.scramble(secret)
        compressed = zlib.compress(scrambled.tobytes())

        enc_key, nonce, tag, ciphertext = CryptoEngine.encrypt(compressed)
        payload = enc_key + nonce + tag + ciphertext

        ecc = ErrorCorrection.encode(payload)

        if len(ecc) * 8 > cover.size:
            raise ValueError("Cover image too small")

        stego = StegoEngine.embed(cover, ecc)

        metadata = {
            "shape": secret.shape,
            "length": len(ecc)
        }

        logger.info("✅ Encryption completed")
        return stego, metadata

    # ===============================
    # 🔥 PIPELINE VERSION (USED BY UI)
    # ===============================
    @staticmethod
    def encrypt_with_updates(secret_path, cover_path):
        updates = []

        try:
            updates.append("📥 Reading images")

            secret = cv2.imread(secret_path, cv2.IMREAD_GRAYSCALE)
            cover = cv2.imread(cover_path, cv2.IMREAD_GRAYSCALE)

            if secret is None or cover is None:
                updates.append("❌ Invalid image input")
                return {'status': 'error', 'updates': updates}

            updates.append("🌪️ Scrambling secret image")
            scrambled = ChaosEngine.scramble(secret)

            updates.append("🗜️ Compressing image")
            compressed = zlib.compress(scrambled.tobytes())

            updates.append("🔐 Encrypting data (AES + RSA)")
            enc_key, nonce, tag, ciphertext = CryptoEngine.encrypt(compressed)

            updates.append("📦 Packing payload")
            payload = enc_key + nonce + tag + ciphertext

            updates.append("🛡️ Applying error correction")
            ecc = ErrorCorrection.encode(payload)

            if len(ecc) * 8 > cover.size:
                updates.append("❌ Cover image too small")
                return {'status': 'error', 'updates': updates}

            updates.append("🖼️ Embedding into cover image")
            stego = StegoEngine.embed(cover, ecc)

            _, buffer = cv2.imencode('.png', stego)
            stego_base64 = base64.b64encode(buffer).decode('utf-8')

            metadata = {
                "shape": secret.shape,
                "length": len(ecc)
            }

            updates.append("✅ Encryption completed")

            return {
                'status': 'success',
                'updates': updates,
                'stego_image': stego_base64,
                'metadata': metadata
            }

        except Exception as e:
            updates.append(f"❌ Error: {str(e)}")
            return {'status': 'error', 'updates': updates}

    # ===============================
    # 🔓 DECRYPT
    # ===============================
    @staticmethod
    def decrypt(stego_path, metadata_json):
        logger.info("🔓 Starting decryption...")

        stego = cv2.imread(stego_path, cv2.IMREAD_GRAYSCALE)
        metadata = json.loads(metadata_json)

        ecc = StegoEngine.extract(stego, metadata['length'])
        payload = ErrorCorrection.decode(ecc)

        enc_key = payload[:256]
        nonce = payload[256:272]
        tag = payload[272:288]
        ciphertext = payload[288:]

        decrypted = CryptoEngine.decrypt(enc_key, nonce, tag, ciphertext)
        decompressed = zlib.decompress(decrypted)

        img_array = np.frombuffer(decompressed, dtype=np.uint8)
        img_array = img_array.reshape(metadata['shape'])

        recovered = ChaosEngine.descramble(img_array)

        logger.info("✅ Decryption completed")
        return recovered
    
    @staticmethod
    def decrypt_with_updates(stego_path, metadata_json):
        updates = []

        try:
            updates.append("📥 Reading stego image")

            stego = cv2.imread(stego_path, cv2.IMREAD_GRAYSCALE)
            metadata = json.loads(metadata_json)

            if stego is None:
                return {"status": "error", "updates": updates + ["❌ Invalid stego image"]}

            updates.append("🧩 Extracting embedded bits")

            ecc = StegoEngine.extract(stego, metadata['length'])

            updates.append("🛡️ Error correction decoding")

            payload = ErrorCorrection.decode(ecc)

            updates.append("🔐 Splitting encrypted payload")

            enc_key = payload[:256]
            nonce = payload[256:272]
            tag = payload[272:288]
            ciphertext = payload[288:]

            updates.append("🔓 AES decryption")

            decrypted = CryptoEngine.decrypt(enc_key, nonce, tag, ciphertext)

            updates.append("🗜️ Decompressing data")

            decompressed = zlib.decompress(decrypted)

            updates.append("📐 Reconstructing image array")

            img_array = np.frombuffer(decompressed, dtype=np.uint8)
            img_array = img_array.reshape(metadata['shape'])

            updates.append("🌪️ Descrambling image")

            recovered = ChaosEngine.descramble(img_array)

            updates.append("✅ Decryption completed")

            return {
                "status": "success",
                "updates": updates,
                "recovered": recovered
            }

        except Exception as e:
            updates.append(f"❌ Error: {str(e)}")
            return {"status": "error", "updates": updates}
