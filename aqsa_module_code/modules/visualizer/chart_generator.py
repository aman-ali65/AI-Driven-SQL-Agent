# chart_generator.py
# This module automatically generates charts from SQL query results.
# It's designed to be easy to understand — even for beginners!
#
# HOW IT WORKS (simple explanation):
# 1. You pass in a list of dictionaries (SQL results)
# 2. The code looks at what columns exist
# 3. It picks the best chart type automatically
# 4. Saves the chart as a PNG image file
# 5. Returns the file path so the API can send it back

import os
import matplotlib
matplotlib.use('Agg') # Important: use non-interactive mode (no popup windows)
import matplotlib.pyplot as plt
import pandas as pd

# Where to save chart images
CHARTS_FOLDER = "charts"
os.makedirs(CHARTS_FOLDER, exist_ok=True)

def generate_chart(results, query="", filename="chart"):
    """
    Main function — takes SQL results and makes a chart automatically.
    Args:
        results (list): List of dictionaries from SQL query.
                        Example: [{"name": "Ali", "score": 85}, ...]
        query (str): The original SQL query (used for chart title)
        filename (str): Name to save the file as (without extension)
    Returns:
        str: Path to saved chart image, or None if chart couldn't be made.
        
    EXAMPLE:
        results = [
            {"student": "Ali", "score": 85},
            {"student": "Sara", "score": 72},
            {"student": "Ahmed", "score": 90}
        ]
        path = generate_chart(results)
        # Returns: "charts/chart.png"
    """
    # Step 1: Make sure we have data
    if not results or len(results) == 0:
        return None # No data = no chart
        
    # Step 2: Convert to a pandas DataFrame (easier to work with)
    # A DataFrame is like a spreadsheet table in Python
    df = pd.DataFrame(results)
    
    # Step 3: Separate columns into text columns and number columns
    text_cols = [col for col in df.columns if df[col].dtype == object]
    num_cols = [col for col in df.columns if df[col].dtype != object]
    
    # Step 4: Pick the right chart type
    chart_path = None
    
    if len(text_cols) == 1 and len(num_cols) == 1:
        # CASE 1: One text column + one number column → Bar Chart
        # Example: name vs score, category vs count
        chart_path = _make_bar_chart(df, text_cols[0], num_cols[0], filename, query)
    elif len(num_cols) == 1 and len(text_cols) == 0:
        # CASE 2: Only one number column → Histogram
        # Example: just a list of scores
        chart_path = _make_histogram(df, num_cols[0], filename, query)
    elif len(num_cols) >= 2:
        # CASE 3: Multiple number columns → Line Chart
        # Example: scores and grades together
        chart_path = _make_line_chart(df, num_cols, filename, query)
        
    # If none of the cases matched, return None (no chart)
    return chart_path

def _make_bar_chart(df, x_col, y_col, filename, title):
    """
    Makes a bar chart. Best for comparing categories.
    Example: student names on X-axis, scores on Y-axis.
    """
    fig, ax = plt.subplots(figsize=(10, 6)) # Create a 10x6 inch figure
    
    # Draw the bars
    ax.bar(df[x_col].astype(str), df[y_col], color='steelblue', edgecolor='white')
    
    # Add labels
    ax.set_xlabel(x_col.replace('_', ' ').title(), fontsize=12)
    ax.set_ylabel(y_col.replace('_', ' ').title(), fontsize=12)
    ax.set_title(title if title else f"{y_col} by {x_col}", fontsize=14)
    
    # Rotate x-axis labels if there are many bars (so they don't overlap)
    if len(df) > 5:
        plt.xticks(rotation=45, ha='right')
        
    plt.tight_layout() # Adjust spacing
    
    # Save the chart
    path = os.path.join(CHARTS_FOLDER, f"{filename}.png")
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close(fig) # Close to free memory
    
    return path

def _make_histogram(df, col, filename, title):
    """
    Makes a histogram. Best for showing distribution of one number.
    Example: how scores are spread (most students got 70-80?).
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
    Makes a line chart. Best for showing trends across multiple columns.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    
    for col in num_cols:
        ax.plot(df.index, df[col], marker='o', label=col.replace('_', ' ').title())
        
    ax.set_xlabel('Row Index', fontsize=12)
    ax.set_ylabel('Values', fontsize=12)
    ax.set_title(title if title else "Trend Chart", fontsize=14)
    
    ax.legend()
    plt.tight_layout()
    
    path = os.path.join(CHARTS_FOLDER, f"{filename}.png")
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close(fig)
    
    return path
