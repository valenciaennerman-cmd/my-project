"""Storage behaviour: de-duplication, remembered corrections, catalog merges."""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.tables import CatalogCard


class TestScanDeduplication:
    def test_same_image_hash_is_recognised(self, repo):
        assert not repo.scan_exists("abc123")
        repo.insert_scan("abc123", r"C:\shots\a.png", "pending")
        assert repo.scan_exists("abc123")

    def test_different_hashes_are_independent(self, repo):
        repo.insert_scan("hash-a", "a.png", "matched")
        assert not repo.scan_exists("hash-b")

    def test_scan_ids_increment(self, repo):
        first = repo.insert_scan("h1", "a.png", "pending")
        second = repo.insert_scan("h2", "b.png", "pending")
        assert second > first

    def test_payload_round_trips(self, repo):
        scan_id = repo.insert_scan("h1", "a.png", "pending", source="clipboard")
        repo.update_scan(scan_id, "matched", {"card": {"ea_id": 1397}, "price": {"value": 5}})

        rows = repo.recent_scans()
        assert len(rows) == 1
        assert rows[0]["scan_id"] == scan_id
        assert rows[0]["status"] == "matched"
        assert rows[0]["card"]["ea_id"] == 1397
        assert rows[0]["source"] == "clipboard"

    def test_recent_scans_are_newest_first(self, repo):
        for i in range(5):
            repo.insert_scan(f"h{i}", f"{i}.png", "matched")
        ids = [row["scan_id"] for row in repo.recent_scans()]
        assert ids == sorted(ids, reverse=True)

    def test_recent_scans_respects_limit(self, repo):
        for i in range(10):
            repo.insert_scan(f"h{i}", f"{i}.png", "matched")
        assert len(repo.recent_scans(limit=3)) == 3

    def test_updating_a_missing_scan_is_logged_not_raised(self, repo):
        repo.update_scan(9999, "matched", {})  # must not raise


class TestCorrections:
    def test_remembering_and_recalling(self, repo):
        assert repo.correction_for("phash-1") is None
        repo.remember_correction("phash-1", 100664693)
        assert repo.correction_for("phash-1") == 100664693

    def test_a_correction_can_be_changed(self, repo):
        repo.remember_correction("phash-1", 1397)
        repo.remember_correction("phash-1", 100664693)
        assert repo.correction_for("phash-1") == 100664693

    def test_corrections_are_per_image(self, repo):
        repo.remember_correction("phash-1", 1397)
        assert repo.correction_for("phash-2") is None


class TestCatalog:
    def test_stub_insert_then_detail_merge(self, repo):
        repo.upsert_players([(1397, "1397-zinedine-zidane", "zinedine zidane")])
        added = repo.upsert_card_stubs(
            [(1397, 1397, "zidane", "1397-zinedine-zidane", "https://x/27-1397/")]
        )
        assert added == 1

        stub = repo.card(1397)
        assert stub is not None and stub.rating is None
        assert repo.cards_missing_details([1397]) == [1397]

        repo.upsert_card(
            CatalogCard(
                ea_id=1397, base_player_ea_id=1397, name="Zinedine Zidane",
                slug="1397-zinedine-zidane", url="https://x/27-1397/",
                rating=94, position="CAM", alt_positions=["CM"],
                rarity_name="Base Icon", version_label="Base Icon",
                image_url="https://img/1397.webp",
            )
        )

        full = repo.card(1397)
        assert full.rating == 94
        assert full.alt_positions == ["CM"]
        assert full.display_version == "Base Icon"
        assert repo.cards_missing_details([1397]) == []

    def test_stub_insert_is_idempotent(self, repo):
        repo.upsert_players([(1397, "s", "zinedine zidane")])
        rows = [(1397, 1397, "zidane", "s", "u")]
        assert repo.upsert_card_stubs(rows) == 1
        assert repo.upsert_card_stubs(rows) == 0

    def test_merge_never_erases_a_known_field(self, repo):
        repo.upsert_players([(1397, "s", "zinedine zidane")])
        repo.upsert_card(
            CatalogCard(ea_id=1397, base_player_ea_id=1397, name="Zidane", slug="s",
                        url="u", rating=94, position="CAM", version_label="Base Icon")
        )
        # A later partial read (siblings carry less detail) must not blank it.
        repo.upsert_card(
            CatalogCard(ea_id=1397, base_player_ea_id=1397, name="Zidane", slug="s",
                        url="u", rating=None, position=None, version_label=None)
        )
        card = repo.card(1397)
        assert (card.rating, card.position, card.version_label) == (94, "CAM", "Base Icon")

    def test_the_zidane_pair_coexists(self, repo):
        """Two cards, same player, same rating and position, different ids."""
        repo.upsert_players([(1397, "1397-zinedine-zidane", "zinedine zidane")])
        for ea_id, version in (
            (1397, "Base Icon"),
            (100664693, "Base Icon Pristine Holographic"),
        ):
            repo.upsert_card(
                CatalogCard(
                    ea_id=ea_id, base_player_ea_id=1397, name="Zinedine Zidane",
                    slug="1397-zinedine-zidane", url=f"https://x/27-{ea_id}/",
                    rating=94, position="CAM", rarity_name="Base Icon",
                    version_label=version,
                )
            )

        cards = repo.cards_for_player(1397)
        assert len(cards) == 2
        assert {c.version_label for c in cards} == {
            "Base Icon", "Base Icon Pristine Holographic"
        }

    def test_player_index_is_keyed_on_folded_names(self, repo):
        repo.upsert_players(
            [(1397, "1397-zinedine-zidane", "zinedine zidane"),
             (19617, "19617-marina-marti-serna", "marina marti serna")]
        )
        index = repo.player_index()
        assert index["zinedine zidane"] == (1397, "1397-zinedine-zidane")
        assert "marina marti serna" in index

    def test_counts(self, repo):
        assert repo.player_count() == 0 and repo.card_count() == 0
        repo.upsert_players([(1, "a", "a"), (2, "b", "b")])
        repo.upsert_card_stubs([(10, 1, "a", "a", "u"), (20, 2, "b", "b", "u")])
        assert repo.player_count() == 2
        assert repo.card_count() == 2

    def test_missing_details_on_empty_input(self, repo):
        assert repo.cards_missing_details([]) == []


class TestFutwizBridge:
    def test_mapping_round_trip(self, repo):
        assert repo.futwiz_id(100664693) is None
        repo.set_futwiz_id(100664693, 111560, "zinedine-zidane")
        assert repo.futwiz_id(100664693) == (111560, "zinedine-zidane")

    def test_mapping_can_be_corrected(self, repo):
        repo.set_futwiz_id(100664693, 1, "x")
        repo.set_futwiz_id(100664693, 111560, "zinedine-zidane")
        assert repo.futwiz_id(100664693) == (111560, "zinedine-zidane")


class TestPriceCache:
    def test_round_trip_and_platform_separation(self, repo):
        now = datetime.now(timezone.utc)
        repo.store_price(1397, "pc", "futwiz", 2_850_000, False, "PC", "u", now)
        repo.store_price(1397, "console", "futgg", 1_370_000, False, "console", "u", now)

        assert repo.cached_price(1397, "pc").price == 2_850_000
        assert repo.cached_price(1397, "console").price == 1_370_000

    def test_overwrite_updates_in_place(self, repo):
        now = datetime.now(timezone.utc)
        repo.store_price(1397, "pc", "futwiz", 1, False, None, None, now)
        repo.store_price(1397, "pc", "futwiz", 2, False, None, None, now)
        assert repo.cached_price(1397, "pc").price == 2

    def test_timestamps_come_back_timezone_aware(self, repo):
        """A naive datetime would make every age calculation wrong."""
        repo.store_price(1397, "pc", "futwiz", 1, False, None, None,
                         datetime.now(timezone.utc))
        assert repo.cached_price(1397, "pc").fetched_at.tzinfo is not None

    def test_missing_entry(self, repo):
        assert repo.cached_price(999, "pc") is None


class TestMeta:
    def test_round_trip(self, repo):
        assert repo.get_meta("catalog_synced_at") is None
        repo.set_meta("catalog_synced_at", "2026-09-20")
        assert repo.get_meta("catalog_synced_at") == "2026-09-20"
        repo.set_meta("catalog_synced_at", "2026-09-21")
        assert repo.get_meta("catalog_synced_at") == "2026-09-21"
