import numpy as np
from .config import CONTACT_LOWER_THRESHOLD, MIN_REGION_PIXELS

def contact_area_percent(frame):
    """Percentage of pixels above contact threshold."""
    total_pixels = frame.size
    active_pixels = np.sum(frame >= CONTACT_LOWER_THRESHOLD)
    return (active_pixels / total_pixels) * 100

def peak_pressure_index(frame):
    """Returns the maximum pressure value (simple version)."""
    return float(frame.max())

def frame_summary(frame):
    """Returns a dictionary containing metrics for the frame."""
    return {
        "peak_pressure_index": peak_pressure_index(frame),
        "contact_area_percent": contact_area_percent(frame),
        "frame_min": float(frame.min()),
        "frame_max": float(frame.max())
    }