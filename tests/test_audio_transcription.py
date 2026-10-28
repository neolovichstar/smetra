"""Audio attachment validation, workspace isolation and transcript preview."""

import base64
import io
import unittest
import wave

import test_business
from backend.audio_transcription import validate_audio
from backend.business import DomainError


def short_wav():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(b"\\x00\\x00" * 800)
    return stream.getvalue()


class AudioValidationTests(unittest.TestCase):
    def test_wav_and_aac_signature_validation(self):
        self.assertEqual(validate_audio("room.wav", short_wav())[1], "wav")
        self.assertEqual(
            validate_audio("room.aac", bytes.fromhex("fff15080001ffc") + b"abc")[1],
            "aac",
        )
        for name, payload in (
            ("recording.wav", b"RIFF" + b"x" * 60),
            ("recording.aac", b"<html>not audio</html>"),
            ("recording.mp3", b"MZ" + b"\\x00" * 100),
            ("recording.wav", b""),
            ("recording.exe", short_wav()),
        ):
            with self.subTest(name=name, payload=payload[:12]):
                with self.assertRaises(DomainError):
                    validate_audio(name, payload)


class AudioTranscriptRouteTests(unittest.TestCase):
    setUpClass = classmethod(test_business.BusinessFlows.setUpClass.__func__)
    tearDownClass = classmethod(test_business.BusinessFlows.tearDownClass.__func__)
    setUp = test_business.BusinessFlows.setUp
    call = test_business.BusinessFlows.call
    account = test_business.BusinessFlows.account

    def test_transcript_is_private_and_requires_matching_file_hash(self):
        owner, _ = self.account("audio-route-owner")
        stranger, _ = self.account("audio-route-stranger")
        status, result = self.call(
            "/files", "POST",
            {"assistant_upload": True, "name": "room.wav",
             "content": base64.b64encode(short_wav()).decode()},
            owner,
        )
        self.assertEqual(status, 201, result)
        file_id = result["file"]["id"]
        self.assertEqual(self.call("/files/" + file_id + "/transcript", token=owner)[0], 409)
        self.assertEqual(self.call("/files/" + file_id + "/transcript", token=stranger)[0], 404)
        self.assertEqual(self.call("/files/" + file_id + "/transcript", "POST", {}, owner)[0], 405)
        with self.mod.db() as con:
            row = con.execute("SELECT workspace_id,sha256 FROM files WHERE id=?", (file_id,)).fetchone()
            con.execute(
                "INSERT INTO file_text_chunks(file_id,workspace_id,page,text,source_sha256) VALUES(?,?,?,?,?)",
                (file_id, row["workspace_id"], 1, "Площадь комнаты двадцать метров.", row["sha256"]),
            )
            con.execute(
                "UPDATE files SET index_status='ready',index_method='transcription',index_hash=sha256 "
                "WHERE id=?", (file_id,),
            )
        status, result = self.call("/files/" + file_id + "/transcript", token=owner)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["text"], "Площадь комнаты двадцать метров.")
        self.assertFalse(result["truncated"])
        self.assertEqual(self.call("/files/" + file_id + "/transcript", token=stranger)[0], 404)
        with self.mod.db() as con:
            con.execute("UPDATE files SET index_hash='stale' WHERE id=?", (file_id,))
        self.assertEqual(self.call("/files/" + file_id + "/transcript", token=owner)[0], 409)
