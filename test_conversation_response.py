import ast
import html
import json
import re
import unittest
from pathlib import Path


APP_PATH = Path(__file__).with_name("app.py")
SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

ASSIGNMENTS = {
    "STATUS_TAG_PATTERN",
    "VALID_STATUS_TAGS",
    "VALID_EXPRESSIONS",
    "VALID_POSES",
    "CONVERSATION_RESPONSE_SCHEMA",
}
FUNCTIONS = {
    "extract_status_tags",
    "normalize_choice",
    "strip_json_code_fence",
    "parse_conversation_response",
    "format_conversation_reply",
    "serialize_reply_for_model",
    "make_assistant_history_message",
    "html_text",
    "build_loveplus_reply_html",
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

namespace = {"html": html, "json": json, "re": re}
exec(
    compile(ast.Module(body=body, type_ignores=[]), str(APP_PATH), "exec"),
    namespace,
)


class ConversationResponseTests(unittest.TestCase):
    def test_valid_structured_response(self):
        raw = json.dumps(
            {
                "narration": "愛花は小さく手を振った。",
                "dialogue": "お疲れさま。",
                "expression": "smile",
                "pose": "gesture",
                "status_tags": ["LOVE_UP"],
            },
            ensure_ascii=False,
        )

        reply = namespace["parse_conversation_response"](raw)

        self.assertEqual(reply["narration"], "愛花は小さく手を振った。")
        self.assertEqual(reply["dialogue"], "お疲れさま。")
        self.assertEqual(reply["expression"], "smile")
        self.assertEqual(reply["pose"], "gesture")
        self.assertEqual(reply["status_tags"], {"LOVE_UP"})
        self.assertFalse(reply["used_fallback"])

    def test_invalid_values_are_normalized_and_unknown_tags_are_dropped(self):
        raw = json.dumps(
            {
                "narration": "",
                "dialogue": "こんにちは。",
                "expression": "sparkle",
                "pose": "flying",
                "status_tags": ["UNKNOWN", "LEAD_UP"],
            },
            ensure_ascii=False,
        )

        reply = namespace["parse_conversation_response"](raw)

        self.assertEqual(reply["expression"], "neutral")
        self.assertEqual(reply["pose"], "normal")
        self.assertEqual(reply["status_tags"], {"LEAD_UP"})

    def test_legacy_text_falls_back_without_losing_progression_tag(self):
        raw = "（少し照れながら）ありがとう。[LOVE_UP]"

        reply = namespace["parse_conversation_response"](raw)

        self.assertEqual(reply["narration"], "")
        self.assertEqual(reply["dialogue"], "（少し照れながら）ありがとう。")
        self.assertEqual(reply["status_tags"], {"LOVE_UP"})
        self.assertTrue(reply["used_fallback"])

    def test_json_code_fence_is_accepted(self):
        raw = """```json
{"narration":"","dialogue":"やっほー。","expression":"happy","pose":"normal","status_tags":[]}
```"""

        reply = namespace["parse_conversation_response"](raw)

        self.assertEqual(reply["dialogue"], "やっほー。")
        self.assertFalse(reply["used_fallback"])

    def test_tags_accidentally_mixed_into_text_are_hidden(self):
        raw = json.dumps(
            {
                "narration": "愛花は微笑んだ。[LEAD_DOWN]",
                "dialogue": "ありがとう。[LOVE_UP]",
                "expression": "smile",
                "pose": "normal",
                "status_tags": [],
            },
            ensure_ascii=False,
        )

        reply = namespace["parse_conversation_response"](raw)

        self.assertNotIn("[", reply["narration"])
        self.assertNotIn("[", reply["dialogue"])
        self.assertEqual(reply["status_tags"], {"LEAD_DOWN", "LOVE_UP"})

    def test_log_and_model_history_formats(self):
        reply = {
            "narration": "愛花は小さく頷いた。",
            "dialogue": "うん、行こう。",
            "expression": "smile",
            "pose": "normal",
            "status_tags": {"LOVE_UP"},
            "used_fallback": False,
        }

        log_text = namespace["format_conversation_reply"](reply)
        model_text = namespace["serialize_reply_for_model"](reply)
        history_message = namespace["make_assistant_history_message"](reply)

        self.assertIn("【地の文】", log_text)
        self.assertIn("【セリフ】", log_text)
        self.assertNotIn("LOVE_UP", log_text)
        self.assertEqual(json.loads(model_text)["status_tags"], [])
        self.assertEqual(history_message["role"], "assistant")
        self.assertEqual(history_message["reply"]["dialogue"], "うん、行こう。")

    def test_schema_and_generation_config_are_wired(self):
        schema = namespace["CONVERSATION_RESPONSE_SCHEMA"]

        self.assertEqual(schema["type"], "OBJECT")
        self.assertEqual(
            set(schema["required"]),
            {"narration", "dialogue", "expression", "pose", "status_tags"},
        )
        self.assertIn('response_mime_type="application/json"', SOURCE)
        self.assertIn("response_schema=CONVERSATION_RESPONSE_SCHEMA", SOURCE)
        self.assertIn("地の文とセリフを混ぜず", SOURCE)
        self.assertIn("render_assistant_message", SOURCE)

    def test_loveplus_reply_ui_is_integrated_without_narration_label(self):
        reply = {
            "narration": "愛花は少し驚いたように目を丸くした。",
            "dialogue": "あ、のりおくん。\nこんにちは。",
        }

        rendered = namespace["build_loveplus_reply_html"](reply, "愛花")

        self.assertIn('class="loveplus-narration"', rendered)
        self.assertIn('class="loveplus-dialogue-window"', rendered)
        self.assertIn('class="loveplus-speaker-tab">愛花</div>', rendered)
        self.assertIn("あ、のりおくん。<br>こんにちは。", rendered)
        self.assertNotIn("地の文", rendered)
        self.assertEqual(rendered.count("loveplus-dialogue-window"), 1)
        self.assertNotIn("st.container(border=True)", SOURCE)

    def test_loveplus_reply_ui_escapes_generated_html(self):
        reply = {
            "narration": '<script>alert("x")</script>',
            "dialogue": "<b>こんにちは</b>",
        }

        rendered = namespace["build_loveplus_reply_html"](
            reply, '<img src=x onerror="alert(1)">'
        )

        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<b>こんにちは</b>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&lt;b&gt;こんにちは&lt;/b&gt;", rendered)

    def test_loveplus_reply_ui_omits_empty_narration(self):
        rendered = namespace["build_loveplus_reply_html"](
            {"narration": "", "dialogue": "うん。"},
            "愛花",
        )

        self.assertNotIn("loveplus-narration", rendered)
        self.assertIn("うん。", rendered)


if __name__ == "__main__":
    unittest.main()
