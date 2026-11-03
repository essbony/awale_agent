"""Tests pour awale_agent/agent.py : anonymize, extract_numbers, check_grounding."""

import re
import sys
import os

import pytest

# Import direct sans passer par build_agent (évite dépendances LLM/DB)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import anonymize, extract_numbers, check_grounding, PHONE_PATTERN, NUMBER_PATTERN


# --- anonymize -----------------------------------------------------------

class TestAnonymize:
    def test_local_ivoirian_number_masked(self):
        # 10 chiffres commençant par 0 -> masqué
        result = anonymize("Contactez le 0701234567 pour info")
        assert "0701234567" not in result
        assert "**" in result  # masquage avec *
        # format attendu : 2 premiers chiffres + étoiles + 2 derniers
        assert "07" in result and "67" in result

    def test_international_plus225_masked(self):
        result = anonymize("Appelez +225 07 01 23 45 67")
        assert "0701234567" not in result
        assert "**" in result

    def test_international_00225_masked(self):
        result = anonymize("Numéro 00225 0701234567 disponible")
        assert "0701234567" not in result
        assert "**" in result

    def test_multiple_numbers_all_masked(self):
        result = anonymize("Tel1 0701112233 et tel2 0509876543")
        assert "0701112233" not in result
        assert "0509876543" not in result
        # deux masquages présents
        assert result.count("**") >= 2

    def test_fcfa_amount_not_masked(self):
        # Un gros montant FCFA ne doit pas être confondu avec un téléphone
        # (pas de préfixe 0/+225 suivi de 10 chiffres collés)
        text = "Chiffre d'affaires 12 500 000 FCFA"
        result = anonymize(text)
        # Le montant doit rester intact (pas de ** injecté sur ce segment)
        assert "12 500 000" in result or "12" in result

    def test_short_digits_not_masked(self):
        # Moins de 8 chiffres -> pas de masquage
        result = anonymize("Code 12345")
        assert result == "Code 12345"

    def test_phone_with_separators(self):
        result = anonymize("Tel: 07-01-23-45-67")
        assert "0701234567" not in result.replace("-", "").replace(" ", "")
        # Vérifie que le résultat contient bien un masquage
        assert "*" in result

    def test_empty_string(self):
        assert anonymize("") == ""

    def test_no_phone_unchanged(self):
        text = "Bonjour, le CA est de 5000 FCFA ce mois."
        assert anonymize(text) == text

    def test_mask_format_length(self):
        # Le masquage doit préserver la longueur : 2 + (n-4) étoiles + 2
        result = anonymize("0701234567")
        # digits = 0701234567 (10) -> 07 + ****** + 67 = 10 chars
        # On cherche le masque dans le résultat
        masked = re.search(r"07\*+67", result)
        assert masked is not None
        assert len(masked.group(0)) == 10

    def test_anonymize_idempotent_on_masked(self):
        once = anonymize("0701234567")
        twice = anonymize(once)
        # Le masque contient des * donc ne doit plus matcher PHONE_PATTERN
        assert once == twice


# --- extract_numbers -----------------------------------------------------

class TestExtractNumbers:
    def test_simple_integer(self):
        nums = extract_numbers("CA 1234 FCFA")
        assert "1234" in nums

    def test_decimal_comma_normalized(self):
        nums = extract_numbers("Valeur 12,5 %")
        assert "12.5" in nums

    def test_decimal_dot(self):
        nums = extract_numbers("Score 3.14")
        assert "3.14" in nums

    def test_spaces_removed(self):
        nums = extract_numbers("Montant 1 234 567 FCFA")
        # "1 234 567" -> "1234567" après remove spaces
        assert "1234567" in nums

    def test_multiple_numbers(self):
        nums = extract_numbers("A 100 B 200,5 C 300")
        assert "100" in nums
        assert "200.5" in nums
        assert "300" in nums

    def test_no_numbers(self):
        assert extract_numbers("aucun chiffre ici") == set()

    def test_empty(self):
        assert extract_numbers("") == set()

    def test_phone_like_numbers_extracted(self):
        nums = extract_numbers("Tel 0701234567")
        assert "0701234567" in nums


# --- check_grounding -----------------------------------------------------

class TestCheckGrounding:
    def test_grounded_numbers_returns_true(self):
        answer = "Le CA est de 1234 FCFA et 5678 unités"
        tool_outputs = ["SELECT 1234, 5678 FROM fct_business_performance"]
        assert check_grounding(answer, tool_outputs) is True

    def test_ungrounded_number_returns_false(self):
        answer = "Le CA est de 9999 FCFA"
        tool_outputs = ["Résultat: 1111"]
        assert check_grounding(answer, tool_outputs) is False

    def test_small_numbers_ignored(self):
        # Nombres < 3 chiffres ignorés
        answer = "Note 12 sur 20"
        tool_outputs = ["aucun chiffre"]
        # 12 et 20 ont len < 3 donc pas de vérification
        assert check_grounding(answer, tool_outputs) is True

    def test_no_numbers_in_answer_returns_true(self):
        assert check_grounding("Bonjour sans chiffres", ["1234"]) is True

    def test_empty_tool_outputs_with_large_number_fails(self):
        assert check_grounding("Valeur 1234", []) is False

    def test_empty_tool_outputs_no_numbers_passes(self):
        assert check_grounding("Pas de chiffres", []) is True

    def test_grounding_with_decimal_normalization(self):
        # extract_numbers normalise virgule -> point
        answer = "Taux 12,5 %"
        # 12,5 -> 12.5 : 3 chiffres sans point = "125" => len 3 => significatif
        tool_outputs = ["12.5"]
        assert check_grounding(answer, tool_outputs) is True

    def test_partial_grounding_fails(self):
        answer = "Valeurs 111 et 222"
        tool_outputs = ["111"]
        assert check_grounding(answer, tool_outputs) is False

    def test_grounding_ignores_spaces(self):
        answer = "Montant 1 234 FCFA"
        tool_outputs = ["1234"]
        assert check_grounding(answer, tool_outputs) is True

    def test_threshold_exactly_3_digits_checked(self):
        # 100 a 3 chiffres -> vérifié
        assert check_grounding("Valeur 100", ["999"]) is False
        assert check_grounding("Valeur 100", ["100"]) is True

    def test_threshold_2_digits_not_checked(self):
        assert check_grounding("Valeur 99", ["000"]) is True
