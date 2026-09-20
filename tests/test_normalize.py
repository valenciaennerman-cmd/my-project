"""Name/position/rating normalisation."""
from __future__ import annotations

import pytest

from app.services.matching.normalize import (
    compact,
    fold,
    normalize_position,
    normalize_rating,
    slug_to_name,
    surname,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Marina Martí", "marina marti"),
        ("Dinkçi", "dinkci"),
        ("Kylian Mbappé", "kylian mbappe"),
        ("Zinedine Zidane", "zinedine zidane"),
        ("Erling Håland", "erling haland"),
        ("İlkay Gündoğan", "ilkay gundogan"),
        ("Şahin Özdemir", "sahin ozdemir"),
        ("Robin Le Normand", "robin le normand"),
        ("Carlota Suárez Crespo", "carlota suarez crespo"),
        ("N'Golo Kanté", "n'golo kante"),
        ("Ødegaard", "odegaard"),
        ("  double   spaces  ", "double spaces"),
        ("", ""),
    ],
)
def test_fold_strips_accents_and_turkish_letters(raw, expected):
    assert fold(raw) == expected


def test_fold_handles_dotless_and_dotted_i():
    # Turkish 'ı' and 'İ' both have to land on plain ascii 'i'.
    assert fold("Işıl") == "isil"
    assert fold("İsmail") == "ismail"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Kika Nazareth", "kikanazareth"),
        ("Lamine Yamal", "lamineyamal"),
        ("Ko Pil Gwan", "kopilgwan"),
        ("Marina Martí", "marinamarti"),
    ],
)
def test_compact_glues_names(raw, expected):
    """OCR and card art both render names without separators."""
    assert compact(raw) == expected


def test_surname_takes_last_token():
    assert surname("Zinedine Zidane") == "zidane"
    assert surname("Kim Chang Hun") == "hun"
    assert surname("Maicon") == "maicon"
    assert surname("") == ""


def test_slug_to_name_drops_leading_id():
    assert slug_to_name("1397-zinedine-zidane") == "zinedine zidane"
    assert slug_to_name("231747-kylian-mbappe") == "kylian mbappe"
    assert slug_to_name("41-iniesta") == "iniesta"
    # A slug with no numeric prefix is still usable.
    assert slug_to_name("zinedine-zidane") == "zinedine zidane"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ST", "ST"), ("st", "ST"), (" cam ", "CAM"), ("GK", "GK"),
        ("CDM", "CDM"), ("LWB", "LWB"),
        ("Goalkeeper", "GK"), ("striker", "ST"),
        ("C AM", "CAM"),          # stray space from OCR
        ("ST+", "ST"),            # chemistry marker stripped
        ("CAM++", "CAM"),
        ("RIM", None),            # a real OCR misread must NOT become RM
        ("CIM", None),
        ("15", None),
        ("", None), (None, None),
    ],
)
def test_normalize_position(raw, expected):
    assert normalize_position(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [(94, 94), ("94", 94), (" 47 ", 47), (99, 99), (1, 1),
     (0, None), (100, None), (-5, None), ("abc", None), (None, None), ("", None)],
)
def test_normalize_rating_bounds(raw, expected):
    assert normalize_rating(raw) == expected
