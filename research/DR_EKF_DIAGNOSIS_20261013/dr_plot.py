"""Shared static-figure style (reference data-viz palette, light surface): thin lines, recessive grid, one axis."""
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

SERIES = ('#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948')
SURFACE = '#fcfcfb'
TEXT = '#0b0b0b'
TEXT2 = '#52514e'
GRID = '#e4e3df'
BAND = '#d9d8d3'


def style():
    plt.rcParams.update({
        'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE, 'savefig.facecolor': SURFACE,
        'axes.edgecolor': GRID, 'axes.labelcolor': TEXT2, 'axes.titlecolor': TEXT, 'axes.titlesize': 10,
        'axes.labelsize': 9, 'xtick.color': TEXT2, 'ytick.color': TEXT2, 'xtick.labelsize': 8, 'ytick.labelsize': 8,
        'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6, 'axes.spines.top': False,
        'axes.spines.right': False, 'lines.linewidth': 1.6, 'legend.fontsize': 8, 'legend.frameon': False,
        'font.size': 9,
    })


def save(fig, path):
    fig.savefig(path, dpi=120, bbox_inches='tight')
    plt.close(fig)
    return path
