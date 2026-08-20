import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).parent


class UiEntrypointTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return ROOT.joinpath(name).read_text(encoding="utf-8")

    def test_ui_modules_are_valid_python(self):
        for name in ("app.py", "every_home_hook.py", "every_home_ui.py"):
            ast.parse(self.read(name), filename=name)

    def test_entrypoint_installs_home_hook_before_game_core(self):
        source = self.read("app.py")

        self.assertIn("install_every_home_hook()", source)
        self.assertIn('runpy.run_module("game_app", run_name="__main__")', source)
        self.assertLess(
            source.index("install_every_home_hook()"),
            source.index('runpy.run_module("game_app", run_name="__main__")'),
        )

    def test_entrypoint_hides_streamlit_chrome(self):
        source = self.read("app.py")
        config = self.read(".streamlit/config.toml")

        self.assertIn('page_title="ラブプラスAI"', source)
        self.assertIn('[data-testid="stHeader"]', source)
        self.assertIn('[data-testid="stToolbar"]', source)
        self.assertIn('[data-testid="stStatusWidget"]', source)
        self.assertIn("padding-top: 0 !important", source)
        self.assertIn('toolbarMode = "minimal"', config)

    def test_hook_targets_only_daily_home_title(self):
        source = self.read("every_home_hook.py")

        self.assertIn('str(body) == "今日の行動"', source)
        self.assertIn("render_every_home(", source)
        self.assertIn("st.stop()", source)
        self.assertIn("EVERY風ホームUIの表示に失敗", source)

    def test_home_ui_does_not_show_unimplemented_fake_values(self):
        source = self.read("every_home_ui.py")

        self.assertNotIn("残りターン", source)
        self.assertNotIn("72%", source)
        self.assertIn("SELECT ACTION", source)
        self.assertIn("TIME", source)
        self.assertIn("WEATHER", source)

    def test_home_stage_uses_html_renderer_not_markdown_parser(self):
        source = self.read("every_home_ui.py")

        self.assertIn("st.html(EVERY_HOME_CSS)", source)
        self.assertIn("st.html(stage_html)", source)
        self.assertIn("def _build_stage_html(", source)
        self.assertNotIn("st.markdown(stage_html", source)

    def test_mobile_action_commands_are_forced_to_one_horizontal_row(self):
        source = self.read("every_home_ui.py")

        self.assertIn("flex-direction: row !important", source)
        self.assertIn("flex-wrap: nowrap !important", source)
        self.assertIn("width: 33.333% !important", source)
        self.assertIn("min-width: 0 !important", source)

    def test_original_game_core_remains_available(self):
        source = self.read("game_app.py")

        self.assertIn('st.title("今日の行動")', source)
        self.assertIn("build_action_scene_state", source)
        self.assertIn("load_recent_memory", source)
        self.assertIn("log_to_spreadsheet", source)


if __name__ == "__main__":
    unittest.main()
