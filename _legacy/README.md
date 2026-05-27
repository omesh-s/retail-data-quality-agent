## Legacy Quarantine (Phase B)

This folder marks the local CSV / CLI pipeline path as legacy and internal-only.

In this phase, legacy modules are quarantined by:
- Removing them from active product flow (`adk web .` MCP-first path)
- Excluding legacy tests from default `pytest` runs
- Slimming active settings and `.env.example` to MCP-first fields

Physical file moves can be completed in a later follow-up once the MCP-first
path is fully stabilized in production.

### Legacy areas (internal/dev-only)

- Local CSV and pandas detector pipeline (`myagent/pipeline.py`, `myagent/anomaly_detector.py`, `myagent/anomaly_impact.py`)
- Pipeline orchestration and data sources (`myagent/orchestration/pipeline_run.py`, `myagent/data_sources/`)
- CLI scripts (`run_day.py`, `run_daily_report.py`, `evaluate.py`, `schedule_daily_report.py`)
- Wizard/sidecar/reporting stack (`config/setup_wizard.py`, `app/`, reporting modules)
- Legacy tests (now excluded by default in `pytest.ini`)
