import ast
import datetime
import unittest
import uuid
from pathlib import Path


APP_PATH = Path(__file__).with_name("app.py")
SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

ASSIGNMENTS = {
    "JST",
    "CHARACTERS",
    "SCREEN_DAILY",
    "SCREEN_SCENE",
    "DEFAULT_GAME_TIME_SLOT",
    "DEFAULT_WEATHER",
    "DEFAULT_LOCATION_ID",
    "SCENE_TYPE_DAILY",
    "SCENE_TYPE_ENCOUNTER",
    "SCENE_TYPE_FREE_TALK",
    "SCENE_TYPE_MOVE",
    "SCENE_TYPE_DATE",
    "SCENE_TYPE_EVENT",
    "VALID_SCENE_TYPES",
    "SCENE_TYPE_LABELS",
    "WEEKDAY_LABELS",
    "LOCATIONS",
    "BACKGROUND_ASSETS",
    "LEGACY_LOCATION_IDS",
    "SCENE_ACTIONS",
}
FUNCTIONS = {
    "get_weekday_label",
    "resolve_location_id",
    "get_location",
    "get_background_variant",
    "get_scene_background_asset",
    "create_scene_state",
    "build_daily_scene_state",
    "build_action_scene_state",
    "build_free_talk_scene_state",
    "migrate_legacy_scene_context",
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

namespace = {"datetime": datetime, "uuid": uuid}
exec(
    compile(ast.Module(body=body, type_ignores=[]), str(APP_PATH), "exec"),
    namespace,
)


class SceneStateTests(unittest.TestCase):
    def build_daily(self):
        return namespace["build_daily_scene_state"](
            game_date="2026-08-20",
            weather="晴れ",
        )

    def test_registered_locations_are_ready_for_background_mapping(self):
        locations = namespace["LOCATIONS"]
        actions = namespace["SCENE_ACTIONS"]

        self.assertEqual(
            set(locations),
            {
                "home_room",
                "school_tennis_court",
                "school_library",
                "family_restaurant",
                "meeting_spot",
            },
        )
        for location_id, location in locations.items():
            self.assertTrue(location["name"])
            self.assertTrue(location["detail"])
            self.assertEqual(location["background_id"], location_id)

        self.assertEqual(
            {action["character"] for action in actions.values()},
            {"愛花", "凛子", "寧々"},
        )
        self.assertTrue(
            all(action["location_id"] in locations for action in actions.values())
        )

    def test_home_background_uses_day_asset_with_safe_fallbacks(self):
        scene_state = self.build_daily()
        get_variant = namespace["get_background_variant"]
        get_asset = namespace["get_scene_background_asset"]

        self.assertEqual(get_variant(scene_state), "day")
        self.assertEqual(
            get_asset(scene_state),
            "backgrounds/home/bg_protagonist_room_day.png",
        )

        evening_state = {**scene_state, "time_slot": "夕方"}
        self.assertEqual(get_variant(evening_state), "sunset")
        self.assertEqual(
            get_asset(evening_state),
            "backgrounds/home/bg_protagonist_room_day.png",
        )

        rainy_state = {**scene_state, "weather": "雨"}
        self.assertEqual(get_variant(rainy_state), "rain")
        self.assertEqual(
            get_asset(rainy_state),
            "backgrounds/home/bg_protagonist_room_day.png",
        )

        tennis_state = {**scene_state, "location_id": "school_tennis_court"}
        self.assertEqual(get_asset(tennis_state), "")
        self.assertTrue(
            APP_PATH.with_name("backgrounds")
            .joinpath("home", "bg_protagonist_room_day.png")
            .is_file()
        )

    def test_daily_state_contains_full_scene_fields(self):
        scene_state = self.build_daily()

        self.assertEqual(
            set(scene_state),
            {
                "scene_id",
                "location_id",
                "previous_location_id",
                "game_date",
                "weekday",
                "time_slot",
                "weather",
                "scene_type",
                "scene_changed",
                "character",
                "action_id",
                "intro",
            },
        )
        self.assertEqual(scene_state["location_id"], "home_room")
        self.assertEqual(scene_state["scene_id"], "")
        self.assertEqual(scene_state["previous_location_id"], "home_room")
        self.assertEqual(scene_state["game_date"], "2026-08-20")
        self.assertEqual(scene_state["weekday"], "木曜日")
        self.assertEqual(scene_state["time_slot"], "放課後")
        self.assertEqual(scene_state["weather"], "晴れ")
        self.assertEqual(scene_state["scene_type"], "daily")
        self.assertFalse(scene_state["scene_changed"])
        self.assertIsNone(scene_state["character"])

    def test_action_moves_from_home_to_registered_encounter(self):
        daily_state = self.build_daily()
        build_action = namespace["build_action_scene_state"]

        tennis = build_action("tennis_club", daily_state)
        restaurant = build_action("restaurant_shift", daily_state)

        self.assertEqual(tennis["location_id"], "school_tennis_court")
        self.assertTrue(tennis["scene_id"])
        self.assertEqual(tennis["previous_location_id"], "home_room")
        self.assertEqual(tennis["scene_type"], "encounter")
        self.assertTrue(tennis["scene_changed"])
        self.assertEqual(tennis["character"], "愛花")
        self.assertEqual(tennis["weekday"], "木曜日")
        self.assertEqual(restaurant["location_id"], "family_restaurant")
        self.assertEqual(restaurant["time_slot"], "夕方")
        self.assertEqual(restaurant["character"], "寧々")
        self.assertNotEqual(tennis["scene_id"], restaurant["scene_id"])

    def test_unregistered_location_keeps_current_location(self):
        daily_state = self.build_daily()
        create_scene_state = namespace["create_scene_state"]

        attempted_move = create_scene_state(
            location_id="ai_invented_place",
            game_date="2026-08-20",
            time_slot="放課後",
            weather="晴れ",
            scene_type="move",
            character=None,
            previous_state=daily_state,
        )

        self.assertEqual(attempted_move["location_id"], "home_room")
        self.assertEqual(attempted_move["previous_location_id"], "home_room")
        self.assertFalse(attempted_move["scene_changed"])

    def test_returning_home_records_previous_location(self):
        daily_state = self.build_daily()
        restaurant = namespace["build_action_scene_state"](
            "restaurant_shift",
            daily_state,
        )

        returned_home = namespace["build_daily_scene_state"](
            previous_state=restaurant,
            game_date=restaurant["game_date"],
            time_slot=restaurant["time_slot"],
            weather=restaurant["weather"],
        )

        self.assertEqual(returned_home["location_id"], "home_room")
        self.assertEqual(
            returned_home["previous_location_id"],
            "family_restaurant",
        )
        self.assertEqual(returned_home["time_slot"], "夕方")
        self.assertTrue(returned_home["scene_changed"])
        self.assertEqual(
            returned_home["intro"],
            "夕方になった。今日はどこへ行こう？",
        )

    def test_invalid_action_scene_type_and_character_are_rejected(self):
        daily_state = self.build_daily()

        with self.assertRaises(ValueError):
            namespace["build_action_scene_state"]("unknown", daily_state)

        with self.assertRaises(ValueError):
            namespace["create_scene_state"](
                location_id="home_room",
                game_date="2026-08-20",
                time_slot="放課後",
                weather="晴れ",
                scene_type="unknown",
                character=None,
            )

        with self.assertRaises(ValueError):
            namespace["create_scene_state"](
                location_id="home_room",
                game_date="2026-08-20",
                time_slot="放課後",
                weather="晴れ",
                scene_type="event",
                character="unknown",
            )

    def test_free_talk_state_is_separate_from_encounter(self):
        daily_state = self.build_daily()
        build_free_talk = namespace["build_free_talk_scene_state"]

        free_talk = build_free_talk("寧々", daily_state)

        self.assertEqual(free_talk["scene_type"], "free_talk")
        self.assertEqual(free_talk["location_id"], "meeting_spot")
        self.assertEqual(free_talk["previous_location_id"], "home_room")
        self.assertTrue(free_talk["scene_changed"])
        self.assertEqual(free_talk["character"], "寧々")

        with self.assertRaises(ValueError):
            build_free_talk("unknown", daily_state)

    def test_legacy_scene_context_is_migrated(self):
        legacy = {
            "scene_kind": "encounter",
            "action_id": "restaurant_shift",
            "game_date": "2026-08-20",
            "time_slot": "夕方",
            "location": "デキシーズ",
            "character": "寧々",
            "intro": "以前の場面情報",
        }

        migrated = namespace["migrate_legacy_scene_context"](legacy)

        self.assertEqual(migrated["location_id"], "family_restaurant")
        self.assertEqual(migrated["previous_location_id"], "home_room")
        self.assertEqual(migrated["scene_type"], "encounter")
        self.assertEqual(migrated["weekday"], "木曜日")
        self.assertEqual(migrated["weather"], "晴れ")
        self.assertTrue(migrated["scene_changed"])

    def test_scene_instruction_contains_world_state(self):
        daily_state = self.build_daily()
        scene_state = namespace["build_action_scene_state"](
            "library",
            daily_state,
        )

        instruction = namespace["format_scene_instruction"](scene_state)

        self.assertIn("日常行動中の遭遇", instruction)
        self.assertIn("2026-08-20（木曜日）", instruction)
        self.assertIn("天気: 晴れ", instruction)
        self.assertIn("現在地ID: school_library", instruction)
        self.assertIn("現在地: 図書室", instruction)
        self.assertIn("直前の場所: 自宅", instruction)
        self.assertIn("場所変更: あり", instruction)
        self.assertIn("登録されていない場所を作らず", instruction)

    def test_free_talk_unlocks_at_level_two_saved_points(self):
        is_unlocked = namespace["is_free_talk_unlocked"]

        self.assertFalse(is_unlocked(0))
        self.assertFalse(is_unlocked(2))
        self.assertTrue(is_unlocked(3))
        self.assertTrue(is_unlocked(7))

    def test_scene_state_ui_is_wired(self):
        self.assertIn('st.title("今日の行動")', SOURCE)
        self.assertIn("render_scene_background(daily_scene_state)", SOURCE)
        self.assertIn("st.image(str(asset_path), use_container_width=True)", SOURCE)
        self.assertIn('st.title(scene_location["name"])', SOURCE)
        self.assertIn('"← 会話を終えて帰宅"', SOURCE)
        self.assertIn('st.subheader("いつでも会う")', SOURCE)
        self.assertIn("st.session_state.scene_state", SOURCE)
        self.assertIn("build_action_scene_state", SOURCE)
        self.assertIn("build_free_talk_scene_state", SOURCE)
        self.assertNotIn("def build_scene_context", SOURCE)
        self.assertNotIn(
            "scene_context = st.session_state.scene_context",
            SOURCE,
        )
        self.assertNotIn("とのチャットルーム", SOURCE)


if __name__ == "__main__":
    unittest.main()
