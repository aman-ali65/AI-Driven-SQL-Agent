# chart_generator.py
# =====================================================================
# PURPOSE:
# This is a SHARED module used by Aiza and Aqsa.
# It automatically generates charts from SQL query results.
#
# HOW IT WORKS:
#   1. You pass in SQL results (a list of dictionaries)
#   2. The code inspects the column types
#   3. It selects the most appropriate chart type automatically
#   4. Saves the chart as a PNG image file
#   5. Returns the file path so the API can include it in the response
#
# Chart Type Selection:
#   1 text column  + 1 number column  ->  Bar Chart   (most common)
#   Only 1 number column              ->  Histogram
#   2 or more number columns          ->  Line Chart
#   Any other combination             ->  No chart (returns None)
# =====================================================================

import os
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend — no popup windows
import matplotlib.pyplot as plt
import pandas as pd

# All generated chart images are saved in this folder
CHARTS_FOLDER = "charts"
os.makedirs(CHARTS_FOLDER, exist_ok=True)


def generate_chart(results, query="", filename="chart"):
    """
    Automatically generate a chart from SQL query results.

    Args:
        results (list): SQL results as a list of dictionaries.
                        Example: [{"name": "Ali", "score": 85}, ...]
        query (str):    The original SQL query string (used as the chart title).
        filename (str): The filename to save as (without .png extension).

    Returns:
        str:  The file path of the saved chart image. Example: "charts/chart.png"
        None: If a chart could not be generated (wrong data shape, empty data, error).

    Example Usage:
        results = [
            {"student": "Ali",   "score": 85},
            {"student": "Sara",  "score": 72},
            {"student": "Ahmed", "score": 90}
        ]
        path = generate_chart(results, filename="my_chart")
        # Returns: "charts/my_chart.png"
    """
    # Guard: no data means no chart
    if not results or len(results) == 0:
        return None

    try:
        # Convert the list of dicts to a pandas DataFrame (like a spreadsheet table)
        df = pd.DataFrame(results)

        # Separate columns into text columns and numeric columns
        text_cols = [col for col in df.columns if df[col].dtype == object]
        num_cols  = [col for col in df.columns if df[col].dtype != object]

        chart_path = None

        if len(text_cols) == 1 and len(num_cols) == 1:
            # Case 1: One text column + one number column -> Bar Chart
            # Example: student names vs scores, category vs count
            chart_path = _make_bar_chart(df, text_cols[0], num_cols[0], filename, query)

        elif len(num_cols) == 1 and len(text_cols) == 0:
            # Case 2: Only one numeric column -> Histogram
            # Example: a single list of scores — shows distribution
            chart_path = _make_histogram(df, num_cols[0], filename, query)

        elif len(num_cols) >= 2:
            # Case 3: Two or more numeric columns -> Line Chart
            # Example: score and grade plotted together
            chart_path = _make_line_chart(df, num_cols, filename, query)

        # If no case matched, chart_path remains None
        return chart_path

    except Exception:
        return None  # Never crash the app due to a chart failure


def _make_bar_chart(df, x_col, y_col, filename, title):
    """
    Generate a bar chart comparing categories against a numeric value.
    Best for: student names vs scores, products vs sales, etc.

    Args:
        df (DataFrame): The data to plot.
        x_col (str):    Column name for the X-axis (text/category).
        y_col (str):    Column name for the Y-axis (numeric).
        filename (str): Output filename (without extension).
        title (str):    Chart title (usually the SQL query).

    Returns:
        str: Path to the saved PNG file.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(
        df[x_col].astype(str),
        df[y_col],
        color='steelblue',
        edgecolor='white',
        linewidth=0.8
    )

    ax.set_xlabel(x_col.replace('_', ' ').title(), fontsize=12)
    ax.set_ylabel(y_col.replace('_', ' ').title(), fontsize=12)
    ax.set_title(title if title else f"{y_col} by {x_col}", fontsize=14)

    # Rotate labels if there are many bars to prevent overlap
    if len(df) > 5:
        plt.xticks(rotation=45, ha='right')

    plt.tight_layout()

    path = os.path.join(CHARTS_FOLDER, f"{filename}.png")
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close(fig)  # Free memory

    return path


def _make_histogram(df, col, filename, title):
    """
    Generate a histogram showing the distribution of a single numeric column.
    Best for: showing how scores are spread across a range.

    Args:
        df (DataFrame): The data to plot.
        col (str):      The numeric column to plot.
        filename (str): Output filename (without extension).
        title (str):    Chart title.

    Returns:
        str: Path to the saved PNG file.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.hist(df[col].dropna(), bins=10, color='coral', edgecolor='white')

    ax.set_xlabel(col.replace('_', ' ').title(), fontsize=12)
    ax.set_ylabel('Count', fontsize=12)
    ax.set_title(title if title else f"Distribution of {col}", fontsize=14)

    plt.tight_layout()

    path = os.path.join(CHARTS_FOLDER, f"{filename}.png")
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close(fig)

    return path


def _make_line_chart(df, num_cols, filename, title):
    """
    Generate a line chart for multiple numeric columns plotted over row index.
    Best for: showing trends or comparing multiple numeric metrics together.

    Args:
        df (DataFrame):    The data to plot.
        num_cols (list):   List of numeric column names to plot.
        filename (str):    Output filename (without extension).
        title (str):       Chart title.

    Returns:
        str: Path to the saved PNG file.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    for col in num_cols:
        ax.plot(
            df.index,
            df[col],
            marker='o',
            label=col.replace('_', ' ').title()
        )

    ax.set_xlabel('Row Index', fontsize=12)
    ax.set_ylabel('Values', fontsize=12)
    ax.set_title(title if title else "Trend Chart", fontsize=14)
    ax.legend()

    plt.tight_layout()

    path = os.path.join(CHARTS_FOLDER, f"{filename}.png")
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close(fig)

    return path
