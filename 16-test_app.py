import unittest
from app import analyze, main, retrieve


class IncidentTests(unittest.TestCase):
    def test_end_to_end(self):
        payload = main([])
        self.assertEqual(payload["processed"], 3)
        self.assertEqual(payload["results"][0]["incident_id"], "INC-101")
        self.assertTrue(all(item["human_approval_required"] for item in payload["results"]))
        self.assertIn("RB-DB", [x["id"] for x in payload["results"][0]["evidence"]])

    def test_no_evidence_does_not_invent_remediation(self):
        row = analyze({"id": "X", "severity": "SEV4", "description": "unmatched"}, [])
        self.assertEqual(row["evidence"], [])
        self.assertIn("No relevant runbook", row["draft"])

    def test_invalid_severity(self):
        with self.assertRaises(ValueError):
            analyze({"id": "X", "severity": "critical", "description": "help"}, [])


if __name__ == "__main__":
    unittest.main()
