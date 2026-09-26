import json
import tempfile
import unittest
from pathlib import Path
from evaluate import run
from pipeline import IncidentQueue
from vector import local_embedding, cosine, local_search

ROOT = Path(__file__).resolve().parent

class PipelineTests(unittest.TestCase):
    def test_vectors(self):
        a = local_embedding("payments-api 502 error")
        self.assertEqual(len(a), 256)
        self.assertAlmostEqual(cosine(a,a), 1)
        docs = json.loads((ROOT / "runbooks.json").read_text())
        self.assertEqual(local_search("inventory-db connections exhausted", docs)[0]["id"], "RB-DB")

    def test_dedup_and_outbox(self):
        with tempfile.TemporaryDirectory() as td:
            q = IncidentQueue(Path(td) / "queue.sqlite")
            item = {"id":"INC-1", "severity":"SEV1", "service":"db", "description":"db unavailable"}
            self.assertFalse(q.ingest(item)["duplicate"])
            again = {**item, "id":"INC-2"}
            self.assertTrue(q.ingest(again)["duplicate"])
            self.assertEqual(q.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 1)
            self.assertEqual(q.db.execute("SELECT sightings FROM incidents").fetchone()[0], 2)
            q.close()

    def test_eval(self):
        summary = run()
        self.assertEqual(summary["retrieval_recall_at_2"], 1.0)
        self.assertTrue(summary["citation_coverage"])
        self.assertTrue(summary["unsafe_instruction_omitted"])

if __name__ == "__main__": unittest.main()
