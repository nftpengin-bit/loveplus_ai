import ast
import unittest
from pathlib import Path


APP_PATH = Path(__file__).with_name("app.py")
SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

ASSIGNMENTS = {
    "CHARACTERS",
    "SCREEN_DAILY",
    "SCREEN_SCENE",
    "DEFAULT_GAME_TIME_SLOT",
    "SCENE_ACTIONS",
}
FUNCTIONS = {
    "build_scene_context",
    "build_free_talk_context",
    "format_scene_instruction",
    "get_love_level",
    "is_free_talk_unlocked",
}

body = []
for node in TREE.body:
    if isinstance(node, ast.Assign):
        names = {
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        if names & ASSIGNMENTS:
            body.append(node)
    elif isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        body.append(node)

namespace = {}
exec(
    compile(ast.Module(body=body, type_ignores=[]), str(APP_PATH), "exec"),
    namespace,
)


class SceneFlowTests(unittest.TestCase):
    def test_daily_actions_cover_all_three_characters(self):
        actions = namespace["SCENE_ACTIONS"]

        self.assertEqual(
            {action["character"] for action in actions.values()},
            {"愛花", "凛子", "寧々"},
        )
        self.assertEqual(actions["tennis_club"]["location"], "テニスコート")
        self.assertEqual(actions["library"]["location"], "図書室")
        self.assertEqual(actions["restaurant_shift"]["location"], "デキシーズ")

    def test_build_encounter_scene_context(self):
        context = namespace["build_scene_context"](
            "tennis_club",
            "2026-08-20",
        )

        self.assertEqual(context["scene_kind"], "encounter")
        self.assertEqual(context["character"], "愛花")
        self.assertEqual(context["location"], "テニスコート")
        self.assertEqual(context["time_slot"], "放課後")
        self.assertEqual(context["game_date"], "2026-08-20")
        self.assertIn("愛花", context["intro"])

    def test_action_time_can_differ_or_be_overridden(self):
        build_scene_context = namespace["build_scene_context"]

        restaurant = build_scene_context("restaurant_shift", "2026-08-20")
        overridden = build_scene_context(
            "restaurant_shift",
            "2026-08-20",
            "夜",
        )

        self.assertEqual(restaurant["time_slot"], "夕方")
        self.assertEqual(overridden["time_slot"], "夜")

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            namespace["build_scene_context"]("unknown", "2026-08-20")

    def test_free_talk_context_is_separate_from_encounter(self):
        context = namespace["build_free_talk_context"](
            "寧々",
            "2026-08-20",
        )

        self.assertEqual(context["scene_kind"], "free_talk")
        self.assertEqual(context["character"], "寧々")
        self.assertEqual(context["location"], "いつもの待ち合わせ場所")

        with self.assertRaises(ValueError):
            namespace["build_free_talk_context"]("unknown", "2026-08-20")

    def test_free_talk_unlocks_at_level_two_saved_points(self):
        is_unlocked = namespace["is_free_talk_unlocked"]

        self.assertFalse(is_unlocked(0))
        self.assertFalse(is_unlocked(2))
        self.assertTrue(is_unlocked(3))
        self.assertTrue(is_unlocked(7))

    def test_scene_instruction_contains_fixed_context(self):
        build_scene_context = namespace["build_scene_context"]
        format_scene_instruction = namespace["format_scene_instruction"]
        context = build_scene_context("library", "2026-08-20")

        instruction = format_scene_instruction(context)

        self.assertIn("日常行動中の遭遇", instruction)
        self.assertIn("2026-08-20", instruction)
        self.assertIn("放課後", instruction)
        self.assertIn("図書室", instruction)
        self.assertIn(context["intro"], instruction)

    def test_daily_and_scene_ui_are_wired(self):
        self.assertIn('st.title("今日の行動")', SOURCE)
        self.assertIn('st.title(scene_context["location"])', SOURCE)
        self.assertIn('"← 日常へ戻る"', SOURCE)
        self.assertIn('st.subheader("いつでも会う")', SOURCE)
        self.assertIn("scene_context,", SOURCE)
        self.assertNotIn("とのチャットルーム", SOURCE)


if __name__ == "__main__":
    unittest.main()
