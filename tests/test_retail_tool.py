"""ADK tool uses shared pipeline orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from config.settings import Settings
from myagent.anomaly_detector import normalize_metrics_dataframe
from myagent.pipeline import PipelineResult
from myagent import retail_tool


@patch("myagent.retail_tool.run_anomaly_pipeline")
def test_retail_tool_delegates_to_run_anomaly_pipeline(mock_run):
    mock_run.return_value = MagicMock(
        pipeline=PipelineResult(
            anomalies=[],
            anomalies_for_llm=[],
            formatted_anomaly_block="block",
            formatted_prompt="prompt text",
            as_of=pd.Timestamp("2024-05-20"),
            as_of_str="2024-05-20",
        ),
        data_source="local_csv",
    )

    out = retail_tool.run_retail_data_quality_analysis(
        user_message="check 2024-05-20",
        as_of_date=None,
    )
    assert out == "prompt text"
    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs["user_message"] == "check 2024-05-20"
