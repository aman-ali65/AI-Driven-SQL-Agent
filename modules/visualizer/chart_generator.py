"""
Chart Generator Module

Converts SQL query result rows into interactive Plotly chart JSON dicts.
Intelligently selects bar, line, pie, scatter based on data shape + SQL hints.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


DARK_LAYOUT = dict(
    paper_bgcolor="#0B0D12",
    plot_bgcolor="#0B0D12",
    font=dict(family="Inter, sans-serif", color="#94A3B8", size=12),
    xaxis=dict(gridcolor="#2A2D3E", linecolor="#2A2D3E", zerolinecolor="#2A2D3E"),
    yaxis=dict(gridcolor="#2A2D3E", linecolor="#2A2D3E", zerolinecolor="#2A2D3E"),
    margin=dict(t=40, r=16, b=50, l=55),
    height=280,
    colorway=["#2563EB", "#7C3AED", "#059669", "#D97706", "#DC2626",
              "#3B82F6", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444"],
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
)

BLUE_SEQ = ["#1e3a5f", "#2563EB", "#3B82F6", "#60A5FA", "#93C5FD", "#BFDBFE"]
MULTI    = ["#2563EB", "#7C3AED", "#059669", "#D97706", "#DC2626",
            "#3B82F6", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444"]


class ChartGenerator:
    """
    Converts SQL result rows into smart Plotly JSON figures.

    Chart-type logic:
        - time/date column present → Line chart
        - GROUP BY + 1 text + 1 num + few rows → Bar or Pie (≤6 cats → Pie)
        - 1 text + 1 num → Horizontal bar (if many rows) or vertical bar
        - 2 num cols, no text → Scatter (only for correlation, otherwise bar)
        - 1 text col only → Pie (value counts)
        - 1 num col → Bar
    """

    def generate(self, rows: list, sql: str = "") -> dict | None:
        if not rows or len(rows) == 0:
            return None
        try:
            df = pd.DataFrame(rows)
            # Try to coerce object cols that look numeric
            for c in df.columns:
                if df[c].dtype == object:
                    try:
                        df[c] = pd.to_numeric(df[c])
                    except Exception:
                        pass
            return self._auto_chart(df, sql or "")
        except Exception:
            return None

    # ── helpers ──────────────────────────────────────────────────────────────

    def _col_types(self, df):
        text = [c for c in df.columns if df[c].dtype == object]
        num  = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        return text, num

    def _is_time_col(self, name: str) -> bool:
        hints = ["date", "month", "year", "week", "day", "quarter", "time",
                 "period", "hour", "timestamp"]
        return any(h in name.lower() for h in hints)

    def _chart_type(self, df, sql: str) -> str:
        sql_l = sql.lower()
        text, num = self._col_types(df)
        nrows = len(df)

        has_group = "group by" in sql_l
        has_agg   = any(k in sql_l for k in ["count(", "sum(", "avg(", "max(", "min("])
        has_order = "order by" in sql_l
        is_time   = any(self._is_time_col(c) for c in df.columns)
        has_time_sql = any(k in sql_l for k in ["strftime", "date(", "month(", "year("])

        # 1 — Time series → Line
        if (is_time or has_time_sql) and num:
            return "line"

        # 2 — Categorical + numeric
        if text and num:
            # Very few categories → Pie (only when explicitly aggregated)
            if nrows <= 6 and (has_group or has_agg):
                pct_hints = ["percent", "ratio", "share", "portion", "distribution"]
                if any(h in sql_l for h in pct_hints):
                    return "pie"
            # Many rows → horizontal bar for readability
            if nrows > 12:
                return "barh"
            return "bar"

        # 3 — Two numerics
        if len(num) >= 2 and not text:
            # If it's an aggregated result, show as grouped bar
            if has_group or has_agg or nrows <= 15:
                return "bar_multi"
            return "scatter"

        # 4 — Text only → Pie (value counts)
        if text and not num:
            return "pie"

        # 5 — Single numeric → Bar
        if num:
            return "bar"

        return "bar"

    # ── chart builders ────────────────────────────────────────────────────────

    def _auto_chart(self, df, sql: str) -> dict | None:
        text, num = self._col_types(df)
        ctype = self._chart_type(df, sql)
        nrows = len(df)
        fig = None

        if ctype == "line" and num:
            x_col = next((c for c in df.columns if self._is_time_col(c)), df.columns[0])
            y_cols = num[:3]
            fig = px.line(df, x=x_col, y=y_cols,
                          color_discrete_sequence=MULTI, markers=True)
            fig.update_traces(line=dict(width=2.5))

        elif ctype == "pie" and text:
            if num:
                fig = px.pie(df, names=text[0], values=num[0],
                             color_discrete_sequence=MULTI, hole=0.35)
            else:
                counts = df[text[0]].value_counts().reset_index()
                counts.columns = [text[0], "count"]
                fig = px.pie(counts, names=text[0], values="count",
                             color_discrete_sequence=MULTI, hole=0.35)
            fig.update_traces(textposition="inside", textinfo="percent+label")

        elif ctype == "barh" and text and num:
            df_s = df.sort_values(num[0], ascending=True).tail(20)
            fig = px.bar(df_s, x=num[0], y=text[0], orientation="h",
                         color=num[0], color_continuous_scale="Blues")

        elif ctype == "bar_multi" and num:
            # Two numeric columns shown as grouped bars with index as x
            x_col = text[0] if text else df.index.astype(str)
            if text:
                fig = px.bar(df, x=text[0], y=num[:3],
                             barmode="group", color_discrete_sequence=MULTI)
            else:
                df2 = df.reset_index()
                fig = px.bar(df2, x="index", y=num[:3],
                             barmode="group", color_discrete_sequence=MULTI)

        elif ctype == "scatter" and len(num) >= 2:
            color_arg = text[0] if text else None
            fig = px.scatter(df, x=num[0], y=num[1], color=color_arg,
                             color_discrete_sequence=MULTI,
                             trendline="ols" if len(df) > 5 else None)

        else:
            # Default: vertical bar
            if text and num:
                df_s = df.sort_values(num[0], ascending=False).head(25)
                fig = px.bar(df_s, x=text[0], y=num[0],
                             color=num[0], color_continuous_scale="Blues")
            elif num:
                df2 = df.reset_index()
                fig = px.bar(df2, x="index", y=num[0],
                             color_discrete_sequence=["#2563EB"])

        if fig is None:
            return None

        fig.update_layout(**DARK_LAYOUT)
        fig.update_coloraxes(showscale=False)
        return fig.to_dict()
