#!/bin/bash

source .venv/bin/activate &&
gunicorn --config gunicorn_config.py wsgi:app
