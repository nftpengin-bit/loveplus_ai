import ast
import unittest
from pathlib import Path


APP_PATH = Path(__file__).with_name("app.py")
SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

ASSIGNMENTS = {
    "CHARACTERS",
    "DEFAULT_LOCATION_ID",
    "LOCATIONS",
    "CONVERSATION_LOG_HEADERS",
    "SCENE_COMMIT_HEADERS",
    "MAX_COMMITTED_MEMORY_TURNS",
}
FUNCTIONS = {
    "resolve_location_id",
    "get_location",
    "rows_to_records",
    "build_conversation_log_row",
    "build_scene_commit_row",
    "select_committed_memory_rows",
    "format_committed_memory",
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


class MemoryCommitTests(unittest.TestCase):
    def setUp(self):
        self.scene = {
            "scene_id": "scene-001",
            "character": "愛花",
            "game_date": "2026-08-20",
            "weekday": "木曜日",
            "time_slot": "放課後",
            "weather": "晴れ",
            "location_id": "school_tennis_court",
            "scene_type": "encounter",
            "action_id": "tennis_club",
        }
        self.reply = {
            "narration": "愛花は小さく手を振った。",
            "dialogue": "お疲れさま。",
            "expression": "smile",
            "pose": "gesture",
        }

    def test_raw_turn_is_saved_as_pending_with_scene_context(self):
        row = namespace["build_conversation_log_row"](
            self.scene,
            "愛花",
            "やほー",
            self.reply,
            "2026-08-20 20:00:00",
        )
        record = namespace["rows_to_records"](
            namespace["CONVERSATION_LOG_HEADERS"],
            [row],
        )[0]

        self.assertEqual(len(row), len(namespace["CONVERSATION_LOG_HEADERS"]))
        self.assertEqual(record["scene_id"], "scene-001")
        self.assertEqual(record["memory_status"], "pending")
        self.assertEqual(record["location_name"], "テニスコート")
        self.assertEqual(record["dialogue"], "お疲れさま。")

    def test_scene_end_creates_committed_marker(self):
        row = namespace["build_scene_commit_row"](
            self.scene,
            "2026-08-20 20:10:00",
            "returned_home",
        )
        record = namespace["rows_to_records"](
            namespace["SCENE_COMMIT_HEADERS"],
            [row],
        )[0]

        self.assertEqual(len(row), len(namespace["SCENE_COMMIT_HEADERS"]))
        self.assertEqual(record["memory_status"], "committed")
        self.assertEqual(record["end_reason"], "returned_home")

    def test_only_committed_scenes_for_current_character_become_memory(self):
        records = [
            {
                "scene_id": "unfinished",
                "character": "愛花",
                "user_message": "途中の話",
            },
            {
                "scene_id": "scene-001",
                "character": "愛花",
                "user_message": "確定した話",
            },
            {
                "scene_id": "scene-001",
                "character": "凛子",
                "user_message": "別の相手",
            },
        ]

        selected = namespace["select_committed_memory_rows"](
            records,
            {"scene-001"},
            "愛花",
        )

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["user_message"], "確定した話")

    def test_committed_memory_includes_place_and_separated_text(self):
        record = namespace["rows_to_records"](
            namespace["CONVERSATION_LOG_HEADERS"],
            [
                namespace["build_conversation_log_row"](
                    self.scene,
                    "愛花",
                    "やほー",
                    self.reply,
                    "2026-08-20 20:00:00",
                )
            ],
        )[0]

        memory = namespace["format_committed_memory"]("愛花", [record])

        self.assertIn("愛花との確定済みの思い出", memory)
        self.assertIn("2026-08-20・放課後・テニスコート", memory)
        self.assertIn("ユーザー: やほー", memory)
        self.assertIn("地の文: 愛花は小さく手を振った。", memory)
        self.assertIn("愛花: お疲れさま。", memory)

    def test_memory_commit_is_wired_to_scene_exit_and_not_logout(self):
        self.assertIn("commit_scene_memory(current_scene_state)", SOURCE)
        self.assertIn("load_recent_memory(character)", SOURCE)
        self.assertIn("log_to_spreadsheet(\n                scene_state,", SOURCE)
        self.assertIn('"chat_histories",\n        "recent_memory",', SOURCE)
        self.assertNotIn("commit_scene_memory(st.session_state.scene_state)", SOURCE)


if __name__ == "__main__":
    unittest.main()
