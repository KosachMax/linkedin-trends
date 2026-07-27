"""Contract checks for the shared article fixture.

The tests deliberately use only Python's standard library so this layer can run
before the new pipeline dependencies are introduced.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "articles.json"
REQUIRED_FIELDS = {
    "id",
    "source_id",
    "source_name",
    "url",
    "title",
    "excerpt",
    "published_at",
    "language",
    "topic_hints",
}


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class ArticleFixtureContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture()
        cls.articles = cls.fixture["articles"]

    def test_fixture_contains_exactly_ten_articles(self) -> None:
        self.assertEqual(len(self.articles), 10)

    def test_every_article_has_a_different_source(self) -> None:
        source_ids = [article["source_id"] for article in self.articles]
        self.assertEqual(len(source_ids), len(set(source_ids)))

    def test_article_ids_are_unique(self) -> None:
        article_ids = [article["id"] for article in self.articles]
        self.assertEqual(len(article_ids), len(set(article_ids)))

    def test_required_fields_are_present_and_non_empty(self) -> None:
        for article in self.articles:
            with self.subTest(article_id=article.get("id")):
                self.assertTrue(REQUIRED_FIELDS <= article.keys())
                for field in REQUIRED_FIELDS - {"topic_hints"}:
                    self.assertTrue(article[field])
                self.assertTrue(article["topic_hints"])

    def test_urls_are_absolute_http_urls(self) -> None:
        for article in self.articles:
            with self.subTest(article_id=article["id"]):
                parsed = urlparse(article["url"])
                self.assertIn(parsed.scheme, {"http", "https"})
                self.assertTrue(parsed.netloc)

    def test_dates_are_timezone_aware_iso_8601(self) -> None:
        for article in self.articles:
            with self.subTest(article_id=article["id"]):
                value = article["published_at"].replace("Z", "+00:00")
                parsed = datetime.fromisoformat(value)
                self.assertIsNotNone(parsed.tzinfo)

    def test_expected_groups_only_reference_known_articles(self) -> None:
        known_ids = {article["id"] for article in self.articles}
        for group in self.fixture["expected_event_groups"]:
            with self.subTest(event_key=group["event_key"]):
                self.assertGreaterEqual(len(group["article_ids"]), 2)
                self.assertTrue(set(group["article_ids"]) <= known_ids)

    def test_digest_membership_covers_every_article_once(self) -> None:
        membership = self.fixture["expected_digest_membership"]
        assigned_ids = [article_id for ids in membership.values() for article_id in ids]
        known_ids = {article["id"] for article in self.articles}
        self.assertEqual(set(assigned_ids), known_ids)
        self.assertEqual(len(assigned_ids), len(set(assigned_ids)))


if __name__ == "__main__":
    unittest.main()

