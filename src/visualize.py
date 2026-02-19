import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from .config import OUTPUT_DIR

def plot_heatmap(frame, save_name="heatmap.png"):
    plt.figure(figsize=(5,5))
    sns.heatmap(frame, cmap="viridis")
    plt.title("Pressure Map Heatmap")
    path = OUTPUT_DIR / save_name
    plt.savefig(path)
    plt.close()
    return path