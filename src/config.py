from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Data and output folders
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"

# Create outputs folder if it doesn't exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Sensor properties
FRAME_ROWS = 32
FRAME_COLS = 32

# Thresholds for metrics
CONTACT_LOWER_THRESHOLD = 50
MIN_REGION_PIXELS = 10