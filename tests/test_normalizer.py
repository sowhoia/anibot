from app.services.normalizer import normalize_kodik_item


def test_normalize_dict_generates_episodes_and_alt_titles():
    raw = {
        "id": "kodik123",
        "title": "Тайтл",
        "title_orig": "Title",
        "translation": {"id": 10, "title": "Test", "type": "voice"},
        "year": 2024,
        "last_episode": 2,
        "material_data": {
            "poster_url": "https://example.com/poster.jpg",
            "description": "desc",
            "genres": ["action"],
            "other_titles": ["Alt"],
        },
        "additional_data": {"episodes_count": 2},
        "shikimori_id": 1,
        "kinopoisk_id": None,
        "imdb_id": None,
    }

    bundle = normalize_kodik_item(raw)

    assert bundle.anime["id"] == "kodik123"
    assert bundle.translation["id"] == 10
    # episodes_count fallback is used
    assert len(bundle.episodes) == 2
    assert bundle.episodes[0].id == "kodik123:10:1"
    # alt_titles de-duplicates values
    assert "Alt" in bundle.anime["alt_titles"]
