from __future__ import annotations

from typing import List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from visualization_models import (
    VisualizationSpec,
    ColumnSpec,
)


class Visualizer:
    """Turn a VisualizationSpec into a Plotly chart.

    Usage:
        viz = Visualizer()
        chart_type = viz.pick_chart_type(spec)  # or pass None to render() to auto-pick
        fig = viz.render(spec, chart_type)
    """

    def pick_chart_type(self, spec: VisualizationSpec) -> str:
        """Choose a chart type using simple rules, respecting valid agent suggestions."""
        suggestion = spec.chart_suggestion or "table"
        if self._valid_by_data(spec, suggestion):
            return suggestion

        dims = self._dimensions(spec)
        measures = self._measures(spec)
        has_time = self._has_time(spec)

        if has_time and measures:
            return "line"

        if len(dims) >= 1 and len(measures) >= 1:
            cat_count = self._unique_count(spec, dims[0].name)
            if cat_count > 0 and cat_count <= 6:
                return "pie"
            return "bar"

        if len(dims) >= 1 and len(measures) >= 2:
            return "bar"

        return "table"

    def to_dataframe(self, spec: VisualizationSpec) -> pd.DataFrame:
        """Convert spec.data_preview to a DataFrame, coercing dtypes from column metadata."""
        df = pd.DataFrame(spec.data_preview)
        if df.empty:
            return df

        colmap = {c.name: c for c in spec.columns}
        # Coerce types per column metadata
        for name, col in colmap.items():
            if name not in df.columns:
                continue
            if col.type == "number":
                df[name] = pd.to_numeric(df[name], errors="coerce")
            elif col.type in ("date", "datetime"):
                df[name] = pd.to_datetime(df[name], errors="coerce")
            else:
                df[name] = df[name].astype(str)
        return df

    def render(
        self,
        spec: VisualizationSpec,
        chart_type: Optional[str] = None,
        *,
        x: Optional[str] = None,
        y: Optional[str] = None,
        measures: Optional[List[str]] = None,
        color: Optional[str] = None,
        pie_names: Optional[str] = None,
        pie_values: Optional[str] = None,
    ) -> go.Figure:
        """Return a Plotly figure based on the spec and selected chart type.

        If chart_type is None, choose via pick_chart_type().
        """
        ctype = (chart_type or self.pick_chart_type(spec)).lower()
        df = self.to_dataframe(spec)
        fig: go.Figure

        # Fallback to table if we lack data
        if df.empty:
            return self._table_fig_from_df(df)

        dims = self._dimensions(spec)
        measures = self._measures(spec)
        time_cols = [c for c in spec.columns if c.role == "time"]

        if ctype == "line" and time_cols and self._measures(spec):
            x_col = x or time_cols[0].name
            y_col = y or (self._measures(spec)[0].name)
            color_col = color or (dims[0].name if dims else None)
            fig = px.line(df, x=x_col, y=y_col, color=color_col, title=spec.intent)
            return fig

        if ctype == "bar" and dims and self._measures(spec):
            x_col = x or dims[0].name
            # allow multiple measures
            measure_cols = measures or [self._measures(spec)[0].name]
            if len(measure_cols) > 1:
                melt = df.melt(id_vars=[x_col], value_vars=measure_cols, var_name="Measure", value_name="Value")
                fig = px.bar(melt, x=x_col, y="Value", color="Measure", barmode="group", title=spec.intent)
            else:
                y_col = measure_cols[0]
                fig = px.bar(df, x=x_col, y=y_col, title=spec.intent)
            return fig

        if ctype == "pie" and dims and self._measures(spec):
            names_col = pie_names or dims[0].name
            values_col = pie_values or (self._measures(spec)[0].name)
            fig = px.pie(df, names=names_col, values=values_col, title=spec.intent, hole=0)
            return fig

        # Default: show as table
        return self._table_fig_from_df(df)

    # ---------- helpers ----------

    def _has_time(self, spec: VisualizationSpec) -> bool:
        return any(c.role == "time" for c in spec.columns)

    def _measures(self, spec: VisualizationSpec) -> List[ColumnSpec]:
        return [c for c in spec.columns if c.role == "measure"]

    def _dimensions(self, spec: VisualizationSpec) -> List[ColumnSpec]:
        return [c for c in spec.columns if c.role == "dimension"]

    def _unique_count(self, spec: VisualizationSpec, column_name: str) -> int:
        try:
            values = [row.get(column_name) for row in spec.data_preview if column_name in row]
            return len(set(values))
        except Exception:
            return 0

    def _valid_by_data(self, spec: VisualizationSpec, suggestion: str) -> bool:
        s = (suggestion or "").lower()
        if s == "table":
            return True
        if s == "line":
            return self._has_time(spec) and len(self._measures(spec)) >= 1
        if s == "bar":
            return len(self._measures(spec)) >= 1
        if s == "pie":
            dims = self._dimensions(spec)
            if not dims:
                return False
            return self._unique_count(spec, dims[0].name) <= 6 and len(self._measures(spec)) >= 1
        return False

    def _table_fig_from_df(self, df: pd.DataFrame) -> go.Figure:
        # Gracefully handle empty
        if df.empty:
            return go.Figure(data=[go.Table(header=dict(values=["No data"]), cells=dict(values=[[" "]]))])
        header_vals = list(df.columns)
        cell_vals = [df[col].astype(str).tolist() for col in df.columns]
        fig = go.Figure(data=[go.Table(header=dict(values=header_vals), cells=dict(values=cell_vals))])
        return fig
