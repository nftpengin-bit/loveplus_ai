"""Streamlit entrypoint for the LovePlus AI game.

Core game logic lives in game_app.py. The entrypoint installs the
EVERY-inspired home UI hook before executing the core module afresh
on every Streamlit rerun.
"""

import runpy

from every_home_hook import install_every_home_hook


install_every_home_hook()
runpy.run_module("game_app", run_name="__main__")
