#!/usr/bin/env bash
export PYTHONPATH=.
python -m uvicorn app:app --reload --port 8000
