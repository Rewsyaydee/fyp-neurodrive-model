# NeuroDrive

NeuroDrive is an EEG-based anxiety monitoring and reporting project.

## Project Layout

- `main.py` - PyQt application entry point
- `core/` - streaming, session, and model runtime logic
- `ui/` - application tabs and windows
- `utils/` - signal processing, feature extraction, and reporting
- `artifacts/models/` - trained model files and training metrics
- `artifacts/reports/` - generated PDF reports
- `docs/guides/` - setup and usage guides
- `docs/references/` - source methodology documents and extracted text
- `tools/` - helper utilities and diagnostics
- `tests/` - unit tests

## Common Commands

```bash
python main.py
python train_model.py
python simulate_session.py 20
python run_tests.py
```

## Notes

- The report generator now reads model metrics from `artifacts/models/`.
- Session reports are written to `artifacts/reports/`.
- Reference documents live under `docs/references/`.
