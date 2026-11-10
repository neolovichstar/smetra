"""Adaptive context-window regression checks: bounded size without lost history."""
import unittest

from backend.context_window import (
    estimate_tokens, pack_history, MAX_MESSAGES_IN_PROMPT, enforce_round_budget
)


def line(idx, role, message):
    return {"id": f"item-{idx:05d}", "role": role, "content": message, "created_at": idx}


class ContextWindowTests(unittest.TestCase):
    def test_compacts_old_messages_and_keeps_latest_in_order(self):
        rows = [
            line(i, "user" if i % 2 else "assistant",
                 f"Сообщение {i}: " + ("Материалы проекта: шпаклёвка." if i == 8 else "обсудили работы и сроки. ") +
                 ("Подтвердили важное решение по ремонту. " if i == 8 else "") +
                 "дополнительный текст " * 25)
            for i in range(150)
        ]
        recent, compressed, stats = pack_history(
            list(reversed(rows)), "Какие материалы проекта были выбраны?",
            fixed_tokens=15500, total_tokens=32768
        )
        self.assertLessEqual(len(recent), MAX_MESSAGES_IN_PROMPT)
        self.assertTrue(recent)
        self.assertIn("Сообщение 149", recent[-1]["content"])
        self.assertTrue(compressed)
        self.assertIn("Материалы проекта", compressed)
        self.assertIn("истории", compressed)
        self.assertGreater(stats["compressed_excerpts"], 0)
        self.assertLess(estimate_tokens(compressed), 3500)

    def test_tiny_budget_clips_extreme_messages(self):
        very_long = "Очень большой текст. " * 6000
        messages, _, stat = pack_history([
            line(i,"user",very_long) for i in range(25,0,-1)
        ], "Продолжай", fixed_tokens=25000, total_tokens=12000)
        self.assertTrue(messages)
        self.assertLess(len(messages[0]["content"]),len(very_long))
        self.assertLess(stat["estimated_recent_tokens"],2500)

    def test_empty_history_and_bounded_context_tuning(self):
        from unittest.mock import patch
        from backend.context_window import configured_total
        with patch.dict("os.environ",{"SMETRA_ASSISTANT_CONTEXT_TOKENS":"-100000"}):
            self.assertEqual(configured_total(),12000)
        with patch.dict("os.environ",{"SMETRA_ASSISTANT_CONTEXT_TOKENS":"81920"}):
            self.assertEqual(configured_total(),81920)
        self.assertEqual(pack_history([], "Есть новости?")[0],[])

    def test_old_history_never_hallucinates_a_summary(self):
        # It cites exact historical text only; passwords must be filtered when
        # an old message gets compacted.
        old = line(1,"user","Для работы выбрали грунтовку. password=SUPER_SECRET_TOKEN_1234567")
        messages = [line(i,"assistant","Совсем недавний ответ " * 80) for i in range(50,1,-1)]
        recent, summary, stats = pack_history(messages+[old],"Напомни грунтовку",fixed_tokens=14500)
        self.assertNotIn("SUPER_SECRET_TOKEN_1234567",summary)
        self.assertIn("грунтовку",summary)
        self.assertGreaterEqual(stats["compressed_excerpts"],1)

    def test_new_task_skips_old_dialogue_and_reduces_provider_tokens(self):
        from backend.context_window import needs_older_history, explicit_history_reference

        rows = [
            line(i, "user" if i % 2 else "assistant",
                 f"Задача {i}. Завершили старый проект, нельзя менять ставки. " + "подробности " * 65)
            for i in range(180, 0, -1)
        ]
        recent, compressed, stats = pack_history(
            rows, "Сделай смету по новому PDF", fixed_tokens=15500, total_tokens=32768
        )
        self.assertEqual(compressed, "")
        self.assertFalse(stats["history_recall_enabled"])
        self.assertLessEqual(len(recent), 10)
        self.assertGreater(stats["estimated_tokens_not_sent"], 40000)
        self.assertFalse(needs_older_history("Сделай смету по новому PDF"))
        self.assertTrue(explicit_history_reference("Что мы обсуждали в прошлом чате?"))
        self.assertFalse(explicit_history_reference("Сколько стоит установка розетки?"))

    def test_followup_can_use_bounded_old_excerpt_without_resending_thread(self):
        rows = [
            line(i, "user", "Договорились использовать фирменную штукатурку. " + "заметки " * 40)
            for i in range(95, 0, -1)
        ]
        recent, older, stats = pack_history(rows, "Напомни, как договаривались",
                                             fixed_tokens=16000, total_tokens=32768)
        self.assertTrue(older)
        self.assertIn("штукатурку", older)
        self.assertLessEqual(stats["compressed_excerpts"], 5)
        self.assertLess(estimate_tokens(older), 1200)
        self.assertGreater(stats["estimated_tokens_not_sent"], 0)

    def test_openrouter_prompt_cache_is_session_scoped_and_can_be_disabled(self):
        from unittest.mock import patch
        from backend.assistant import _MODEL_SESSION, _cache_options

        self.assertEqual(_cache_options("anthropic/claude-haiku-5.5"), {})
        token = _MODEL_SESSION.set("b" * 64)
        try:
            values = _cache_options("anthropic/claude-haiku-5.5")
            self.assertEqual(values["session_id"], "b" * 64)
            self.assertEqual(values["cache_control"], {"type": "ephemeral"})
            self.assertNotIn("cache_control", _cache_options("google/gemini-2.5-flash"))
            with patch.dict("os.environ", {"SMETRA_AI_CACHE_ENABLED": "0"}):
                self.assertNotIn("cache_control", _cache_options("anthropic/claude-haiku-5.5"))
        finally:
            _MODEL_SESSION.reset(token)
        self.assertEqual(_cache_options("anthropic/claude-haiku-5.5"), {})

    def test_iterative_tool_context_compaction_keeps_protected_results(self):
        from unittest.mock import patch

        content = "Очень длинные результаты поиска. " * 600
        msgs = [
            {"role": "system", "content": "Правила важны."},
            {"role": "user", "content": "Покажи сведения о ремонте."},
        ]
        for i in range(10):
            msgs.append({"role": "assistant", "content": None, "tool_calls": [
                {"id":f"call{i}","type":"function","function":{"name":"read_file","arguments":"{}"}}
            ]})
            msgs.append({"role":"tool","tool_call_id":f"call{i}","content":content})
        before_ids = [item["tool_call_id"] for item in msgs if item["role"]=="tool"]
        with patch.dict("os.environ",{"SMETRA_ASSISTANT_CONTEXT_TOKENS":"12000"}):
            stats = enforce_round_budget(msgs,[{"type":"function","function":{"name":"read_file"}}])
        self.assertTrue(stats["compacted"])
        self.assertLess(stats["after"], stats["before"])
        self.assertEqual(before_ids,[item["tool_call_id"] for item in msgs if item["role"]=="tool"])
        self.assertEqual(msgs[-1]["content"],content)
        self.assertEqual(msgs[0]["content"],"Правила важны.")
