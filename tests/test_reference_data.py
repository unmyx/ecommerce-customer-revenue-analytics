from __future__ import annotations

from novacart.synthetic import reference


def test_reference_probability_tables_are_consistent() -> None:
    reference.validate_reference_data()


def test_country_codes_are_two_letters_and_unique() -> None:
    for code, profile in reference.COUNTRIES.items():
        assert len(code) == 2 and code.isupper()
        assert code == profile.code
        assert 0.0 < profile.vat_rate < 0.30
        assert profile.cities


def test_category_names_match_their_keys() -> None:
    for name, category in reference.CATEGORIES.items():
        assert name == category.name
        assert category.product_nouns
        assert category.subcategories

