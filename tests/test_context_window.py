"""Adaptive context-window regression checks: bounded size without lost history."""
import unittest

from backend.context_window import (
    estimate_tokens, pack_history, MAX_MESSAGES_IN_PROMPT
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
