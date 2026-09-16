# ===============================
# 📦 IMPORTS
# ===============================
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

import cv2
import numpy as np
import base64
import json
import traceback
import os
import uuid

from app.backend_code import StegoService


# ===============================
# 🏠 HOME
# ===============================
def index(request):
    return render(request, 'index.html')


# ===============================
# 🛠️ UTIL FUNCTIONS
# ===============================
def save_temp_image(image_array):
    """Save image to temporary file safely"""
    filename = f"temp_{uuid.uuid4().hex}.png"
    cv2.imwrite(filename, image_array)
    return filename


def delete_file(path):
    """Safely delete temp file"""
    try:
        if os.path.exists(path):
            os.remove(path)
    except:
        pass


def image_to_base64(image):
    """Convert image array → base64"""
    _, buffer = cv2.imencode('.png', image)
    return base64.b64encode(buffer).decode('utf-8')


# ===============================
# 🔐 ENCRYPTION VIEW
# ===============================
@csrf_exempt
def encryption_view(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

    cover_path = None
    secret_path = None

    try:
        cover_file = request.FILES.get('cover_image')
        secret_file = request.FILES.get('secret_image')

        if not cover_file or not secret_file:
            return JsonResponse({
                'status': 'error',
                'message': 'Both cover and secret images are required'
            })

        # Decode images
        cover = cv2.imdecode(
            np.frombuffer(cover_file.read(), np.uint8),
            cv2.IMREAD_GRAYSCALE
        )
        secret = cv2.imdecode(
            np.frombuffer(secret_file.read(), np.uint8),
            cv2.IMREAD_GRAYSCALE
        )

        if cover is None or secret is None:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid image format'
            })

        # ===============================
        # 🔥 AUTO RESIZE (FIX FOR ERROR)
        # ===============================
        if secret.size * 8 > cover.size:
            scale = (cover.size / (secret.size * 8)) ** 0.5

            new_w = max(1, int(secret.shape[1] * scale))
            new_h = max(1, int(secret.shape[0] * scale))

            secret = cv2.resize(secret, (new_w, new_h))

        # Save temp images
        cover_path = save_temp_image(cover)
        secret_path = save_temp_image(secret)

        # Encrypt
        stego, metadata = StegoService.encrypt(secret_path, cover_path)

        return JsonResponse({
            'status': 'success',
            'stego_image': image_to_base64(stego),
            'metadata': metadata,
            'message': 'Encryption successful'
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })

    finally:
        delete_file(cover_path)
        delete_file(secret_path)


# ===============================
# 🔓 DECRYPTION VIEW
# ===============================
@csrf_exempt
def decryption_view(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

    stego_path = None

    try:
        stego_file = request.FILES.get('stego_image')
        metadata = request.POST.get('metadata')

        if not stego_file or not metadata:
            return JsonResponse({
                'status': 'error',
                'message': 'Stego image and metadata are required'
            })

        # Parse metadata safely
        try:
            metadata_json = json.loads(metadata)
        except:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid metadata format (must be JSON)'
            })

        # Read stego image
        stego = cv2.imdecode(
            np.frombuffer(stego_file.read(), np.uint8),
            cv2.IMREAD_GRAYSCALE
        )

        if stego is None:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid stego image'
            })

        # Save temp file
        stego_path = save_temp_image(stego)

        # Decrypt
        result = StegoService.decrypt_with_updates(
            stego_path,
            json.dumps(metadata_json)
        )

        if result["status"] == "success":
            return JsonResponse({
                'status': 'success',
                'recovered_image': image_to_base64(result["recovered"]),
                'updates': result["updates"],
                'message': 'Decryption successful'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'updates': result["updates"],
                'message': 'Decryption failed'
            })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })

    finally:
        delete_file(stego_path)


# ===============================
# 📷 OPTIONAL IMAGE PROCESS VIEW
# ===============================
@csrf_exempt
def process_images(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

    try:
        image_file = request.FILES.get('image')

        if not image_file:
            return JsonResponse({
                'status': 'error',
                'message': 'No image provided'
            })

        image = cv2.imdecode(
            np.frombuffer(image_file.read(), np.uint8),
            cv2.IMREAD_COLOR
        )

        if image is None:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid image format'
            })

        # Example processing
        processed = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        return JsonResponse({
            'status': 'success',
            'processed_image': image_to_base64(processed),
            'message': 'Image processed successfully'
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })
