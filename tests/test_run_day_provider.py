"""run_day.py uses provider-backed pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import Settings

import pandas as pd

from myagent.pipeline import PipelineResult


@patch("run_day.get_settings")
@patch("run_day.load_dotenv")
@patch("run_day._run_agent", new_callable=AsyncMock, return_value="LLM summary")
@patch("run_day.run_anomaly_pipeline")
def test_run_day_main_uses_run_anomaly_pipeline(
    mock_pipeline, mock_agent, _load_dotenv, mock_get_settings
):
    mock_pipeline.return_value = MagicMock(
        pipeline=PipelineResult(
            anomalies=[],
            anomalies_for_llm=[],
            formatted_anomaly_block="",
            formatted_prompt="summary input",
            as_of=pd.Timestamp("2024-05-20"),
            as_of_str="2024-05-20",
        ),
        data_source="local_csv",
    )
    mock_get_settings.return_value = Settings(
        llm_provider="googlegenai",
        google_api_key="test-key",
    )
    mock_get_settings.cache_clear = MagicMock()

    with patch("sys.argv", ["run_day.py", "--date", "2024-05-20", "--csv", "data/x.csv"]):
        import run_day

        run_day.main()

    mock_pipeline.assert_called_once()
    assert mock_pipeline.call_args.kwargs["csv_path"] is not None
    mock_agent.assert_awaited_once()
