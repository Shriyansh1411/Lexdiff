"""Lendwise's own regression tests. Lexdiff locks these: they must stay green on the fix."""
import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.getcwd())


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["LENDWISE_DATA_DIR"] = self.tmp.name
        from app.main import create_app
        from app.security import current_totp
        self.client = create_app().test_client()
        self.mfa = {"X-MFA-Code": current_totp()}

    def tearDown(self):
        self.tmp.cleanup()

    def test_health_is_public(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_create_application_roundtrip(self):
        body = {"name": "A B", "email": "a@b.test", "ssn": "900-00-1111", "account_number": "42", "amount": 100}
        resp = self.client.post("/applications", json=body, headers=self.mfa)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["status"], "received")

    def test_export_job_writes_csv(self):
        body = {"name": "A B", "email": "a@b.test", "ssn": "900-00-1111", "account_number": "42", "amount": 100}
        self.client.post("/applications", json=body, headers=self.mfa)
        from jobs import export_underwriting
        path = export_underwriting.run()
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertIn("application_id", rows[0])
        self.assertEqual(rows[0]["applicant"], "A B")

    def test_login_with_valid_credentials(self):
        resp = self.client.post("/login", json={"username": "canary", "password": "canary-pass"}, headers=self.mfa)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.get_json())


if __name__ == "__main__":
    unittest.main()
