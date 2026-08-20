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

    def test_original_game_core_remains_available(self):
        source = self.read("game_app.py")

        self.assertIn('st.title("今日の行動")', source)
        self.assertIn("build_action_scene_state", source)
        self.assertIn("load_recent_memory", source)
        self.assertIn("log_to_spreadsheet", source)


if __name__ == "__main__":
    unittest.main()
