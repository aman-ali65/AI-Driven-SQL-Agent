"""
Chart Generator Module

Converts SQL query result rows into static PNG charts using Seaborn/Matplotlib.
Returns a base64-encoded PNG string so the frontend can display via <img>.

Chart-type logic:
    - time/date column present → Line chart
    - GROUP BY + 1 text + 1 num + few rows → Bar or Pie (≤6 cats → Pie)
    - 1 text + 1 num → Horizontal bar (if many rows) or vertical bar
    - 2 num cols, no text → Scatter or grouped bar
    - 1 text col only → Pie (value counts)
    - 1 num col → Bar
"""

import io
import base64
import warnings
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — safe for Flask threads
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore")

# ── visual theme ──────────────────────────────────────────────────────────────
PALETTE   = ["#2563EB", "#7C3AED", "#059669", "#D97706", "#DC2626",
             "#3B82F6", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444"]
BG_COLOR  = "#0B0D12"
TEXT_COLOR = "#94A3B8"
GRID_COLOR = "#2A2D3E"

sns.set_theme(style="darkgrid", rc={
    "axes.facecolor":  BG_COLOR,
    "figure.facecolor": BG_COLOR,
    "axes.edgecolor":  GRID_COLOR,
    "axes.labelcolor": TEXT_COLOR,
    "xtick.color":     TEXT_COLOR,
    "ytick.color":     TEXT_COLOR,
    "grid.color":      GRID_COLOR,
    "text.color":      TEXT_COLOR,
    "axes.titlecolor": TEXT_COLOR,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
})


class ChartGenerator:
    """
    Converts SQL result rows into a base64-encoded PNG chart.
    Returns {"type": "image", "src": "data:image/png;base64,..."}
    or None if no chart can be generated.
    """

    def generate(self, rows: list, sql: str = "") -> dict | None:
        """
        Entry point: accepts raw row dicts and the SQL string.
        Returns image dict or None.
        """
        if not rows:
            return None
        try:
            df = pd.DataFrame(rows)
            # Coerce object cols that look numeric
            for c in df.columns:
                if df[c].dtype == object:
                    try:
                        df[c] = pd.to_numeric(df[c])
                    except Exception:
                        pass
            return self._auto_chart(df, sql or "")
        except Exception:
            return None

    # ── helpers ───────────────────────────────────────────────────────────────

    def _col_types(self, df):
        text = [c for c in df.columns if df[c].dtype == object]
        num  = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        return text, num

    def _is_time_col(self, name: str) -> bool:
        hints = ["date", "month", "year", "week", "day", "quarter",
                 "time", "period", "hour", "timestamp"]
        return any(h in name.lower() for h in hints)

    def _chart_type(self, df, sql: str) -> str:
        sql_l = sql.lower()
        text, num = self._col_types(df)
        nrows = len(df)

        has_group    = "group by" in sql_l
        has_agg      = any(k in sql_l for k in ["count(", "sum(", "avg(", "max(", "min("])
        is_time      = any(self._is_time_col(c) for c in df.columns)
        has_time_sql = any(k in sql_l for k in ["strftime", "date(", "month(", "year("])

        if (is_time or has_time_sql) and num:
            return "line"
        if text and num:
            if nrows <= 6 and (has_group or has_agg):
                pct = ["percent", "ratio", "share", "portion", "distribution"]
                if any(h in sql_l for h in pct):
                    return "pie"
            if nrows > 12:
                return "barh"
            return "bar"
        if len(num) >= 2 and not text:
            if has_group or has_agg or nrows <= 15:
                return "bar_multi"
            return "scatter"
        if text and not num:
            return "pie"
        if num:
            return "bar"
        return "bar"

    def _fig_to_b64(self, fig) -> str:
        """Save figure to PNG bytes and return base64 string."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight",
                    facecolor=BG_COLOR, dpi=120)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    # ── chart builders ────────────────────────────────────────────────────────

    def _auto_chart(self, df: pd.DataFrame, sql: str) -> dict | None:
        text, num = self._col_types(df)
        ctype = self._chart_type(df, sql)
        fig, ax = plt.subplots(figsize=(8, 3.8))
        ax.set_facecolor(BG_COLOR)
        fig.patch.set_facecolor(BG_COLOR)

        drawn = False

        try:
            if ctype == "line" and num:
                x_col = next((c for c in df.columns if self._is_time_col(c)), df.columns[0])
                y_cols = num[:3]
                for i, y in enumerate(y_cols):
                    ax.plot(df[x_col], df[y], marker="o", linewidth=2,
                            color=PALETTE[i % len(PALETTE)], label=y, markersize=4)
                ax.set_xlabel(x_col)
                plt.xticks(rotation=30, ha="right")
                if len(y_cols) > 1:
                    ax.legend(fontsize=9, facecolor=BG_COLOR, edgecolor=GRID_COLOR,
                              labelcolor=TEXT_COLOR)
                drawn = True

            elif ctype == "pie" and text:
                wedge_colors = PALETTE[:min(len(df), len(PALETTE))]
                if num:
                    vals   = df[num[0]].abs()
                    labels = df[text[0]]
                else:
                    vc     = df[text[0]].value_counts()
                    vals   = vc.values
                    labels = vc.index
                ax.pie(vals, labels=labels, colors=wedge_colors,
                       autopct="%1.1f%%", startangle=90,
                       textprops={"color": TEXT_COLOR, "fontsize": 9},
                       wedgeprops={"edgecolor": BG_COLOR, "linewidth": 1.5})
                drawn = True

            elif ctype == "barh" and text and num:
                df_s = df.sort_values(num[0], ascending=True).tail(20)
                colors = [PALETTE[i % len(PALETTE)] for i in range(len(df_s))]
                ax.barh(df_s[text[0]], df_s[num[0]], color=colors)
                ax.set_xlabel(num[0])
                drawn = True

            elif ctype == "bar_multi" and num:
                if text:
                    x_col = text[0]
                    y_cols = num[:3]
                else:
                    x_col = num[0]
                    y_cols = num[1:4] if len(num) > 1 else num[:1]
                    
                x_vals = df[x_col].astype(str) if isinstance(x_col, str) else df.index.astype(str)
                x_pos  = range(len(x_vals))
                width  = 0.8 / max(1, len(y_cols))
                
                for i, col in enumerate(y_cols):
                    offsets = [p + i * width for p in x_pos]
                    ax.bar(offsets, df[col], width=width,
                           color=PALETTE[i % len(PALETTE)], label=col)
                           
                center_offset = width/2 * (len(y_cols)-1) if len(y_cols) > 0 else 0
                ax.set_xticks([p + center_offset for p in x_pos])
                ax.set_xticklabels(list(x_vals), rotation=30, ha="right")
                ax.set_xlabel(str(x_col))
                
                ax.legend(fontsize=9, facecolor=BG_COLOR, edgecolor=GRID_COLOR,
                          labelcolor=TEXT_COLOR)
                drawn = True

            elif ctype == "scatter" and len(num) >= 2:
                color_col = df[text[0]] if text else None
                if color_col is not None:
                    unique_cats = color_col.unique()
                    color_map   = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(unique_cats)}
                    colors_list = [color_map[v] for v in color_col]
                else:
                    colors_list = PALETTE[0]
                ax.scatter(df[num[0]], df[num[1]], c=colors_list, alpha=0.7, s=50)
                ax.set_xlabel(num[0])
                ax.set_ylabel(num[1])
                drawn = True

            else:
                # Default: vertical bar
                if text and num:
                    df_s   = df.sort_values(num[0], ascending=False).head(25)
                    colors = [PALETTE[i % len(PALETTE)] for i in range(len(df_s))]
                    ax.bar(df_s[text[0]], df_s[num[0]], color=colors)
                    ax.set_xlabel(text[0])
                    ax.set_ylabel(num[0])
                    plt.xticks(rotation=30, ha="right")
                    drawn = True
                elif num:
                    df2    = df.reset_index()
                    colors = [PALETTE[i % len(PALETTE)] for i in range(len(df2))]
                    ax.bar(df2["index"].astype(str), df2[num[0]], color=colors)
                    plt.xticks(rotation=30, ha="right")
                    drawn = True

        except Exception:
            plt.close(fig)
            return None

        if not drawn:
            plt.close(fig)
            return None

        # Style ticks / spines
        for spine in ax.spines.values():
            spine.set_edgecolor(GRID_COLOR)
        ax.tick_params(colors=TEXT_COLOR)
        plt.tight_layout(pad=0.8)

        b64 = self._fig_to_b64(fig)
        return {"type": "image", "src": f"data:image/png;base64,{b64}"}
