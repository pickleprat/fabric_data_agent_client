from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, StrictInt, StrictStr, ConfigDict


# Enumerations (strict)
ChartSuggestion = Literal["bar", "line", "pie", "table"]
ColumnType = Literal["string", "number", "date", "datetime"]
ColumnRole = Literal["dimension", "measure", "time"]


class ColumnSpec(BaseModel):
    """Metadata for a single column in the visualization dataset."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: StrictStr = Field(..., description="Column name as it appears in data_preview rows.")
    type: ColumnType = Field(..., description="Logical type of the column.")
    role: ColumnRole = Field(..., description="Visualization role for the column.")


class Provenance(BaseModel):
    """Describes where the data came from and the SQL used, if applicable."""

    model_config = ConfigDict(extra="forbid")

    sql_query: Optional[StrictStr] = Field(
        default=None, description="SQL query used to retrieve the data, if any."
    )
    source: Optional[StrictStr] = Field(
        default=None, description="Data source label (e.g., 'lakehouse')."
    )


class Limits(BaseModel):
    """Indicates dataset limits and preview size."""

    model_config = ConfigDict(extra="forbid")

    row_count: Optional[StrictInt] = Field(
        default=None, description="Total number of rows in the full dataset, if known."
    )
    preview_rows: Optional[StrictInt] = Field(
        default=None, description="Number of rows included in data_preview."
    )


class VisualizationSpec(BaseModel):
    """Strict contract for visualization-ready data and metadata.

    This mirrors the JSON structure returned by get_visualization_spec().
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    intent: StrictStr = Field(..., description="User intent in natural language.")
    chart_suggestion: ChartSuggestion = Field(
        ..., description="Suggested chart type for the provided columns and data."
    )
    dataset_description: StrictStr = Field(
        ..., description="Short description of the dataset represented by data_preview."
    )

    columns: List[ColumnSpec] = Field(
        default_factory=list,
        description="Column metadata used to interpret data_preview for visualization.",
    )

    # Each row is a mapping from column name -> value. Values may be str/number/date-like.
    data_preview: List[Dict[StrictStr, Any]] = Field(
        default_factory=list, description="Small set of rows to plot or display."
    )

    provenance: Provenance = Field(
        default_factory=Provenance,
        description="Provenance information including SQL and data source, if available.",
    )
    limits: Limits = Field(
        default_factory=Limits, description="Dataset size and preview sizing info."
    )
    notes: StrictStr = Field(
        default="", description="Additional notes, assumptions, or caveats."
    )


__all__ = [
    "ChartSuggestion",
    "ColumnType",
    "ColumnRole",
    "ColumnSpec",
    "Provenance",
    "Limits",
    "VisualizationSpec",
]
