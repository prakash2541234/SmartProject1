import tkinter as tk
from tkinter import filedialog
import threading
import time
import struct
import numpy as np
import cv2
import reedsolo
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from skimage.metrics import peak_signal_noise_ratio as compare_psnr, structural_similarity as compare_ssim

# =====================================================
# 🌪️ CHAOS MAP
# =====================================================
def generate_hybrid_chaos_map(N, seed=(0.1, 0.1, 0.5), a=1.4, b=0.3, r=3.99):
    x, y, z = seed
    total = N * N
    coords = []

    for _ in range(total):
        x = (1 - a * x * x + y) % 1
        y = (b * x) % 1
        z = (r * z * (1 - z)) % 1

        xi = int(x * N) % N
        zi = int(z * N) % N
        coords.append(xi * N + zi)

    # FIX: ensure valid full permutation
    perm = np.argsort(coords)
    inv_perm = np.argsort(perm)

    if len(perm) != total:
        raise ValueError("Permutation size mismatch")

    return perm, inv_perm


# =====================================================
# 🔁 SCRAMBLE
# =====================================================
def scramble(img, perm):
    flat = img.flatten()
    return flat[perm].reshape(img.shape)


def descramble(img, inv_perm):
    flat = img.flatten()
    out = np.empty_like(flat)
    out[inv_perm] = flat
    return out.reshape(img.shape)


# =====================================================
# 🔐 AES ENCRYPTION
# =====================================================
def aes_encrypt(data):
    key = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_GCM)
    ct, tag = cipher.encrypt_and_digest(data)
    return key, cipher.nonce, tag, ct


def aes_decrypt(key, nonce, tag, ct):
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ct, tag)


# =====================================================
# 🧠 RS CODING
# =====================================================
rs = reedsolo.RSCodec(32)

def rs_encode(data):
    return rs.encode(data)


def rs_decode(data):
    return rs.decode(data)[0]


# =====================================================
# 🔢 BIT CONVERSION
# =====================================================
def bits_from_bytes(b):
    return [int(bit) for byte in b for bit in f"{byte:08b}"]


def bytes_from_bits(bits):
    return bytes(
        int("".join(map(str, bits[i:i+8])), 2)
        for i in range(0, len(bits), 8)
    )


# =====================================================
# 🧩 EMBED / EXTRACT
# =====================================================
def embed(cover, bits):
    flat = cover.flatten()
    if len(bits) > len(flat):
        raise ValueError("Cover image too small")

    for i, b in enumerate(bits):
        flat[i] = (flat[i] & 254) | int(b)

    return flat.reshape(cover.shape)


def extract(img, length):
    flat = img.flatten()
    return [flat[i] & 1 for i in range(length)]


# =====================================================
# 📊 QUALITY METRICS
# =====================================================
def quality(original, stego):
    psnr = compare_psnr(original, stego, data_range=255)
    ssim = compare_ssim(original, stego, data_range=255)
    return psnr, ssim


# =====================================================
# 🔐 ENCRYPTION PIPELINE (FIXED)
# =====================================================
def encrypt_pipeline(cover, secret):
    N = secret.shape[0]

    perm, inv_perm = generate_hybrid_chaos_map(N)
    scrambled = scramble(secret, perm)

    key, nonce, tag, ct = aes_encrypt(scrambled.tobytes())

    payload = nonce + tag + ct
    ecc = rs_encode(payload)

    bits = bits_from_bytes(ecc)

    stego = embed(cover.copy(), bits)

    meta = {
        "inv_perm": inv_perm,
        "shape": secret.shape,
        "bit_len": len(bits),
        "aes_key": key
    }

    return stego, meta


# =====================================================
# 🔓 DECRYPTION PIPELINE (FIXED)
# =====================================================
def decrypt_pipeline(stego, meta):

    inv_perm = meta["inv_perm"]
    shape = meta["shape"]
    bit_len = meta["bit_len"]
    aes_key = meta["aes_key"]

    bits = extract(stego, bit_len)
    data = bytes_from_bits(bits)

    payload = rs_decode(data)

    nonce = payload[:16]
    tag = payload[16:32]
    ct = payload[32:]

    plain = aes_decrypt(aes_key, nonce, tag, ct)

    expected = shape[0] * shape[1]

    if len(plain) != expected:
        raise ValueError(f"Size mismatch: got {len(plain)} expected {expected}")

    arr = np.frombuffer(plain, dtype=np.uint8).reshape(shape)

    recovered = descramble(arr, inv_perm)

    return recovered


# =====================================================
# 🖥️ TKINTER UI
# =====================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Stego System (Fixed)")
        self.root.geometry("850x600")

        self.cover = None
        self.secret = None
        self.stego = None
        self.meta = None

        self.log = tk.Text(root, height=25)
        self.log.pack()

        frame = tk.Frame(root)
        frame.pack()

        tk.Button(frame, text="Cover", command=self.load_cover).pack(side="left")
        tk.Button(frame, text="Secret", command=self.load_secret).pack(side="left")
        tk.Button(frame, text="Encrypt", command=self.start_encrypt).pack(side="left")
        tk.Button(frame, text="Decrypt", command=self.start_decrypt).pack(side="left")

    def write(self, msg):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.root.update()

    def load_cover(self):
        path = filedialog.askopenfilename()
        self.cover = cv2.imread(path, 0)
        self.write("📥 Cover loaded")

    def load_secret(self):
        path = filedialog.askopenfilename()
        self.secret = cv2.imread(path, 0)
        self.write("📥 Secret loaded")

    def start_encrypt(self):
        threading.Thread(target=self.encrypt).start()

    def start_decrypt(self):
        threading.Thread(target=self.decrypt).start()

    def encrypt(self):
        self.write("📥 Reading images")
        time.sleep(1)

        self.write("🌪️ Scrambling")
        time.sleep(1)

        self.write("🔐 AES Encryption")
        time.sleep(1)

        self.write("🧩 Embedding")

        self.stego, self.meta = encrypt_pipeline(self.cover, self.secret)

        cv2.imwrite("stego.png", self.stego)

        self.write("✅ Encryption Done")

    def decrypt(self):
        self.write("📤 Extracting")

        recovered = decrypt_pipeline(self.stego, self.meta)

        cv2.imwrite("recovered.png", recovered)

        psnr, ssim = quality(self.secret, recovered)
        accuracy = ssim * 100

        self.write(f"📊 PSNR: {psnr:.2f} dB")
        self.write(f"📊 SSIM: {ssim:.4f}")
        self.write(f"🎯 Accuracy: {accuracy:.2f}%")

        self.write("✅ Decryption Done")


# =====================================================
# 🚀 RUN
# =====================================================
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
