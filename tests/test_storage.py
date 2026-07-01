import tempfile
import unittest
from pathlib import Path

from storage import StateStore


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_state.db"
        self.store = StateStore(self.db_path, enabled=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_universal_memory_round_trip(self):
        self.store.save_universal_memory(["fact one", "fact two"])
        self.assertEqual(
            self.store.load_universal_memory(),
            ["fact one", "fact two"],
        )
        self.store.clear_universal_memory()
        self.assertEqual(self.store.load_universal_memory(), [])

    def test_dm_history_round_trip(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hey"},
        ]
        self.store.save_dm_history(42, messages)
        self.assertEqual(self.store.load_dm_histories(), {42: messages})
        self.store.delete_dm_history(42)
        self.assertEqual(self.store.load_dm_histories(), {})

    def test_channel_history_round_trip(self):
        messages = [{"role": "user", "content": "Name: hi"}]
        self.store.save_channel_history(99, messages)
        self.assertEqual(self.store.load_channel_histories(), {99: messages})

    def test_disabled_store_is_no_op(self):
        disabled = StateStore(self.db_path, enabled=False)
        disabled.save_universal_memory(["ignored"])
        self.assertEqual(disabled.load_universal_memory(), [])