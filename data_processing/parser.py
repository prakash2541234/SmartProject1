"""
data_processing/parser.py
Parses Graphene Trace sensor CSV files (32×32 frames) and computes analytics.
"""
import csv, io, os, zipfile
from datetime import datetime, timedelta
import numpy as np

ROWS = COLS = 32
SIZE = ROWS * COLS   # 1024


def parse_filename(filename):
    """Extract (user_hash, date_str) from '1c0fd777_20251011.csv'."""
    base = os.path.basename(filename)
    name, _ = os.path.splitext(base)
    parts = name.split('_')
    if len(parts) < 2:
        raise ValueError(f"Unrecognised filename: {filename}")
    return parts[0], parts[-1]


def date_str_to_dt(date_str):
    return datetime.strptime(date_str, '%Y%m%d')


def parse_csv_frames(file_obj):
    """Read CSV text → list of flat 1024-int lists (one per frame)."""
    reader   = csv.reader(file_obj)
    all_rows = []
    for row in reader:
        if not row: continue
        try:
            vals = [int(float(v)) for v in row if v.strip()]
        except ValueError:
            continue
        if len(vals) < COLS: vals += [0] * (COLS - len(vals))
        else: vals = vals[:COLS]
        all_rows.append(vals)

    frames = []
    for i in range(0, len(all_rows) - ROWS + 1, ROWS):
        chunk = all_rows[i:i + ROWS]
        if len(chunk) == ROWS:
            frames.append([v for row in chunk for v in row])
    return frames


def analyse_frame(flat, contact_thresh=50, min_region=10):
    """Compute peak pressure (PPI), contact area %, avg pressure."""
    arr = np.array(flat, dtype=np.float32).reshape(ROWS, COLS)
    contact_area_pct = float((arr > contact_thresh).sum()) / SIZE * 100.0
    nz = arr[arr > 0]
    avg_pressure = float(nz.mean()) if len(nz) else 0.0
    peak = _ppi(arr, contact_thresh, min_region)
    return {
        'peak_pressure':    round(peak, 2),
        'contact_area_pct': round(contact_area_pct, 2),
        'avg_pressure':     round(avg_pressure, 2),
    }


def _ppi(arr, threshold, min_pixels):
    """Peak Pressure Index via BFS connected-component flood fill."""
    binary  = arr > threshold
    visited = np.zeros_like(binary, dtype=bool)
    best    = 0.0
    for r in range(ROWS):
        for c in range(COLS):
            if binary[r, c] and not visited[r, c]:
                region, queue = [], [(r, c)]
                visited[r, c] = True
                while queue:
                    cr, cc = queue.pop()
                    region.append((cr, cc))
                    for dr, dc in ((-1,0),(1,0),(0,-1),(0,1)):
                        nr, nc = cr+dr, cc+dc
                        if 0 <= nr < ROWS and 0 <= nc < COLS and binary[nr,nc] and not visited[nr,nc]:
                            visited[nr,nc] = True
                            queue.append((nr,nc))
                if len(region) >= min_pixels:
                    rmax = max(float(arr[pr, pc]) for pr, pc in region)
                    if rmax > best: best = rmax
    return best if best > 0 else float(arr.max())


def check_alert(peak, threshold=500):
    """Returns (should_alert, severity, message)."""
    if peak >= threshold * 1.5:
        return True, 'critical', f"Critical pressure detected ({peak:.0f}). Immediate repositioning required."
    elif peak >= threshold:
        return True, 'warning',  f"High pressure detected ({peak:.0f}). Consider repositioning."
    return False, 'info', ''


def generate_explanation(peak, contact_pct, avg, recent_alerts=0):
    """Plain-English summary for patient."""
    parts = []
    if   peak > 1500: parts.append("Very high pressure detected — serious skin damage risk.")
    elif peak > 800:  parts.append("Significant pressure concentrated in one area of your body.")
    elif peak > 300:  parts.append("Moderate pressure — within a normal range for most people.")
    else:             parts.append("Pressure is low and well distributed across the mat.")

    if   contact_pct > 70: parts.append(f"{contact_pct:.0f}% of the mat is in contact — a good balanced position.")
    elif contact_pct > 40: parts.append(f"About {contact_pct:.0f}% coverage — you may be slightly off-centre.")
    else:                  parts.append(f"Only {contact_pct:.0f}% coverage — consider adjusting your position.")

    if   recent_alerts > 5: parts.append("Several recent alerts — please speak with your clinician soon.")
    elif recent_alerts > 0: parts.append("A few pressure alerts recorded today. Try to reposition regularly.")
    return " ".join(parts)


def frames_to_timestamps(base_dt, count, interval_sec=5):
    return [base_dt + timedelta(seconds=i * interval_sec) for i in range(count)]


def extract_csvs_from_zip(zip_bytes):
    """Returns list of (filename, bytes) from a ZIP."""
    results = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name.lower().endswith('.csv') and '__MACOSX' not in name:
                results.append((os.path.basename(name), zf.read(name)))
    return results
