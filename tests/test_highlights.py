import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.highlights import (  # noqa: E402
    AIError,
    build_messages,
    chat,
    coerce_clips,
    extract_clips,
    select_clips,
)


class ExtractTests(unittest.TestCase):
    def test_fenced_object(self):
        text = '```json\n{"clips":[{"start_time":1,"end_time":30,"title":"A"}]}\n```'
        items = extract_clips(text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "A")

    def test_bare_array(self):
        items = extract_clips('[{"start": 5, "end": 20}]')
        self.assertEqual(items[0]["start"], 5)

    def test_truncated_array_is_salvaged(self):
        text = '[{"start":1,"end":21,"title":"one"},{"start":30,"end":55,"title":"two"},{"start":'
        items = extract_clips(text)
        self.assertEqual([item["title"] for item in items], ["one", "two"])

    def test_plain_prose_with_json(self):
        text = 'Here are the clips:\n{"clips":[{"start_time":"1:00","end_time":"1:30"}]}\nHope this helps.'
        items = extract_clips(text)
        self.assertEqual(len(items), 1)


class ClipTests(unittest.TestCase):
    def test_coerce_clamps_and_parses(self):
        items = [
            {"start_time": "0:10", "end_time": "0:40", "title": "ok", "virality_score": "9", "score_reason": "strong hook"},
            {"start": 100, "end": 130, "description": "past the end"},
        ]
        clips = coerce_clips(items, duration=90, min_seconds=10, max_seconds=60)
        self.assertEqual(len(clips), 1)
        self.assertAlmostEqual(clips[0]["start"], 10)
        self.assertAlmostEqual(clips[0]["end"], 40)
        self.assertEqual(clips[0]["virality_score"], 9)
        self.assertEqual(clips[0]["score_reason"], "strong hook")

    def test_score_from_four_dimensions(self):
        items = [
            {
                "start": 0,
                "end": 30,
                "hook_score": 9,
                "emotion_score": 7,
                "clarity_score": 8,
                "loop_score": 6,
                "virality_score": 10,
            }
        ]
        clips = coerce_clips(items, 100, 10, 60)
        self.assertEqual(clips[0]["virality_score"], 7.7)
        self.assertEqual(
            clips[0]["score_breakdown"],
            {"hook_score": 9.0, "emotion_score": 7.0, "clarity_score": 8.0, "loop_score": 6.0},
        )

    def test_score_falls_back_when_dimensions_missing(self):
        clips = coerce_clips(
            [{"start": 10, "end": 40, "hook_score": 9, "virality_score": 6}],
            100,
            10,
            60,
        )
        self.assertEqual(clips[0]["virality_score"], 6.0)
        self.assertEqual(clips[0]["score_breakdown"], {"hook_score": 9.0})

    def test_filters_length(self):
        items = [
            {"start": 0, "end": 4},
            {"start": 10, "end": 200},
            {"start": 300, "end": 330},
        ]
        clips = coerce_clips(items, duration=400, min_seconds=20, max_seconds=120)
        self.assertEqual(len(clips), 1)
        self.assertAlmostEqual(clips[0]["duration"], 30)

    def test_select_drops_overlap_and_ranks(self):
        items = [
            {"start": 0, "end": 30, "title": "low", "virality_score": 2},
            {"start": 5, "end": 35, "title": "overlap", "virality_score": 10},
            {"start": 60, "end": 90, "title": "other", "virality_score": 7},
        ]
        clips = select_clips(items, 5, 200, 10, 60)
        titles = [clip["title"] for clip in clips]
        self.assertEqual(titles, ["overlap", "other"])
        self.assertEqual([clip["start"] for clip in clips], sorted(clip["start"] for clip in clips))

    def test_prompt_contains_rules_and_direction(self):
        messages = build_messages(
            {"title": "Demo", "channel": "Chan", "duration": 600},
            "[0:00] hello",
            3,
            "skip the intro",
            "id",
            20,
            90,
        )
        prompt = messages[-1]["content"]
        self.assertIn("skip the intro", prompt)
        self.assertIn("score_reason", prompt)
        self.assertIn("hook_score", prompt)
        self.assertIn("emotion_score", prompt)
        self.assertIn("clarity_score", prompt)
        self.assertIn("loop_score", prompt)
        self.assertIn("full scale", prompt)
        self.assertIn("Indonesian", prompt)
        self.assertIn("between 20 and 90 seconds", prompt)
        self.assertIn('"clips"', prompt)


class ChatTests(unittest.TestCase):
    def test_openai_compatible_call(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                captured["path"] = self.path
                captured["auth"] = self.headers.get("Authorization")
                captured["body"] = json.loads(self.rfile.read(length))
                data = json.dumps(
                    {
                        "choices": [{"message": {"content": '{"clips": [{"start": 0, "end": 30}]}'}}],
                        "usage": {"total_tokens": 42},
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            content, usage = chat(
                f"http://127.0.0.1:{server.server_address[1]}/v1",
                "sk-test",
                "demo-model",
                [{"role": "user", "content": "hi"}],
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(captured["path"], "/v1/chat/completions")
        self.assertEqual(captured["auth"], "Bearer sk-test")
        self.assertEqual(captured["body"]["model"], "demo-model")
        self.assertEqual(usage["total_tokens"], 42)
        self.assertEqual(extract_clips(content)[0]["end"], 30)

    def test_missing_key_is_clear(self):
        with self.assertRaises(AIError):
            chat("http://127.0.0.1:9/v1", "", "m", [])


if __name__ == "__main__":
    unittest.main()
