"""Streamlit entrypoint for the LovePlus AI game.

Core game logic lives in game_app.py. The entrypoint installs the
EVERY-inspired home UI hook before executing the core module afresh
on every Streamlit rerun.
"""

import runpy

import streamlit as st

from every_home_hook import install_every_home_hook


st.set_page_config(
    page_title="ラブプラスAI",
    page_icon="♡",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        "Get help": None,
        "Report a Bug": None,
        "About": None,
    },
)

# Streamlitは開発基盤として残すが、プレイヤーにはゲーム画面だけを見せる。
# Community Cloud外側の開発者オーバーレイは環境によって別レイヤーのため、
# 下記で消えない場合は公式の ?embed=true 表示を最終導線にする。
st.html(
    r"""
    <style>
    html, body {
        margin: 0 !important;
        padding: 0 !important;
    }

    header[data-testid="stHeader"],
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stStatusWidget"],
    [data-testid="stDecoration"],
    .stAppDeployButton,
    #MainMenu,
    footer {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        min-height: 0 !important;
    }

    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    .stMain {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }

    [data-testid="stAppViewContainer"] .block-container,
    div[data-testid="stAppViewBlockContainer"],
    .stAppViewBlockContainer {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }

    /* Community Cloudの開発者向けフローティングUIを可能な範囲で隠す。 */
    button[aria-label*="Manage app" i],
    a[aria-label*="Manage app" i],
    div[class*="viewerBadge"],
    div[class*="ViewerBadge"],
    div[class*="manageApp"],
    div[class*="ManageApp"] {
        display: none !important;
        visibility: hidden !important;
    }
    </style>
    """
)

install_every_home_hook()
runpy.run_module("game_app", run_name="__main__")
