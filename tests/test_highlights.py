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
    translate_groups,
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

    def test_truncated_wrapper_object_is_salvaged(self):
        text = '{"clips":[{"start_time":1,"end_time":30,"title":"one"},{"start_time":40,"end_time":70,"title":"two"},{"start_time":'
        items = extract_clips(text)
        self.assertEqual([item["title"] for item in items], ["one", "two"])

    def test_prose_with_brackets_and_fences(self):
        prose_obj = 'Here are [5] clips:\n{"clips":[{"start_time":10,"end_time":45,"title":"ok"}]}'
        self.assertEqual([item["title"] for item in extract_clips(prose_obj)], ["ok"])
        fenced = 'Sure, here is the JSON:\n```json\n{"clips":[{"start_time":10,"end_time":45,"title":"fenced"}]}\n```'
        self.assertEqual([item["title"] for item in extract_clips(fenced)], ["fenced"])

    def test_reasoning_think_block_with_example_fence_still_extracts_final_clips(self):
        text = (
            "<think>\nSchema example:\n```json\n{\"example\": true}\n```\nDone thinking.\n</think>\n"
            '```json\n{"clips":[{"start_time":12,"end_time":42,"title":"final answer"}]}\n```'
        )
        self.assertEqual([item["title"] for item in extract_clips(text)], ["final answer"])


class ClipTests(unittest.TestCase):
    def test_coerce_clamps_and_parses(self):
        items = [
            {"start_time": "0:10", "end_time": "0:40", "title": "ok", "virality_score": "9", "score_reason": "strong hook"},
            {"start_time": 0, "end_time": 30, "title": "from zero"},
            {"start": 100, "end": 130, "description": "past the end"},
        ]
        clips = coerce_clips(items, duration=90, min_seconds=10, max_seconds=60)
        self.assertEqual(len(clips), 2)
        self.assertAlmostEqual(clips[0]["start"], 10)
        self.assertAlmostEqual(clips[0]["end"], 40)
        self.assertEqual(clips[0]["virality_score"], 9)
        self.assertEqual(clips[0]["score_reason"], "strong hook")
        self.assertAlmostEqual(clips[1]["start"], 0)
        self.assertEqual(clips[1]["title"], "from zero")

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

    def test_rejects_non_http_base_url(self):
        for bad in ("file:///C:/Windows/win.ini", "ftp://example.com/v1"):
            with self.assertRaises(AIError):
                chat(bad, "sk-test", "m", [{"role": "user", "content": "hi"}])

    def test_api_key_is_not_forwarded_on_redirect(self):
        stolen = {}
        holder = {}

        class Redirect(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{holder['port']}/steal")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        class Steal(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                stolen["path"] = self.path
                stolen["auth"] = self.headers.get("Authorization")
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        steal = ThreadingHTTPServer(("127.0.0.1", 0), Steal)
        holder["port"] = steal.server_address[1]
        redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        threads = [
            threading.Thread(target=server.serve_forever, daemon=True)
            for server in (steal, redirect)
        ]
        for thread in threads:
            thread.start()
        try:
            with self.assertRaises(AIError):
                chat(f"http://127.0.0.1:{redirect.server_address[1]}/v1", "sk-secret", "m", [])
        finally:
            for server in (steal, redirect):
                server.shutdown()
                server.server_close()
        self.assertNotIn("auth", stolen)


class TranslateTests(unittest.TestCase):
    def _translate(self, texts, content):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                captured["body"] = json.loads(self.rfile.read(length))
                data = json.dumps(
                    {"choices": [{"message": {"content": content}}]}
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
            result = translate_groups(
                texts, "Indonesian", f"http://127.0.0.1:{server.server_address[1]}/v1", "k", "m"
            )
        finally:
            server.shutdown()
            server.server_close()
        return result, captured

    def test_translate_groups_parses_json_array(self):
        out, captured = self._translate(["Hello", "World"], '["Halo","Dunia"]')
        self.assertEqual(out, ["Halo", "Dunia"])
        self.assertEqual(captured["body"]["messages"][0]["role"], "system")

    def test_translate_groups_rejects_wrong_count(self):
        with self.assertRaises(AIError):
            self._translate(["a", "b"], '["only one"]')

    def test_translate_groups_rejects_non_array(self):
        with self.assertRaises(AIError):
            self._translate(["a"], '{"wrong":"shape"}')

    def test_translate_groups_extracts_array_from_prose(self):
        out, _ = self._translate(["Hello", "World"], 'Translation:\n["Halo","Dunia"]')
        self.assertEqual(out, ["Halo", "Dunia"])


class ExactCountPromptTests(unittest.TestCase):
    def test_prompt_requests_exact_count_and_excludes(self):
        messages = build_messages(
            {"title": "Demo", "duration": 600},
            "transcript",
            5,
            "",
            "auto",
            20,
            120,
            exclude=[{"start": 60, "end": 120, "title": "First"}],
        )
        text = messages[1]["content"]
        self.assertIn("Return exactly 5", text)
        self.assertIn("EXISTING CLIPS", text)
        self.assertIn("1:00-2:00 First", text)
        self.assertNotIn("Choose up to 5", text)

    def test_two_batches_fill_requested_count(self):
        first = [{"start": 0, "end": 30, "virality_score": 9}]
        extra = [{"start": 100, "end": 130, "virality_score": 8}]
        clips = select_clips(first + extra, 2, 600, 20, 120)
        self.assertEqual(len(clips), 2)

    def test_chat_retries_without_temperature_when_model_rejects_it(self):
        bodies = []

        class ReasoningHandler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length))
                bodies.append(payload)
                if "temperature" in payload:
                    err = b'{"error":{"message":"Unsupported value: \'temperature\' does not support 0.6"}}'
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err)))
                    self.end_headers()
                    self.wfile.write(err)
                    return
                ok = b'{"choices":[{"message":{"content":"{\\"clips\\":[]}"}}],"usage":{"total_tokens":10}}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(ok)))
                self.end_headers()
                self.wfile.write(ok)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), ReasoningHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            content, _ = chat(f"http://127.0.0.1:{server.server_address[1]}/v1", "sk-test", "o3-mini", [{"role": "user", "content": "hi"}])
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(len(bodies), 2)
        self.assertIn("temperature", bodies[0])
        self.assertNotIn("temperature", bodies[1])
        self.assertIn("clips", content)


if __name__ == "__main__":
    unittest.main()
