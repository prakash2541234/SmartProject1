import pandas as pd
import numpy as np
from pathlib import Path
from .config import FRAME_ROWS, FRAME_COLS

def load_frames_from_csv(csv_path: Path):
    """
    Loads 32x32 pressure map frames from a CSV file.
    Assumes the CSV contains stacked 32 rows per frame.
    """
    df = pd.read_csv(csv_path, header=None)
    arr = df.values

    # Validate shape
    if arr.shape[1] != FRAME_COLS or arr.shape[0] % FRAME_ROWS != 0:
        raise ValueError(f"CSV shape incorrect: {arr.shape}")

    num_frames = arr.shape[0] // FRAME_ROWS

    for i in range(num_frames):
        frame = arr[i*32:(i+1)*32, :32]
        yield frame.astype(float)