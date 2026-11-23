import json
from pathlib import Path


MANIFEST_PATH = Path("evals/live_materials/current_data_material_manifest.json")


def test_current_data_material_manifest_exists_and_parses():
    assert MANIFEST_PATH.exists()
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert isinstance(payload["materials"], list)
    assert len(payload["materials"]) == 9


def test_current_data_material_manifest_contains_required_document_ids():
    materials = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["materials"]
    document_ids = {entry["document_id"] for entry in materials}

    assert document_ids == {
        "bio_gene_sequence_lecture10",
        "stats_discriminant_analysis",
        "physics_capacitance_dielectrics",
        "linguistics_discourse_genre",
        "nlp_transformers_cs224n",
        "ko_ml_sequence_rnn_cnn",
        "cv_detection_segmentation_cs231n",
        "econ_imperfect_competition_game_theory",
        "cpp_heap_destructors",
    }


def test_current_data_material_manifest_language_and_domain_coverage():
    materials = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["materials"]
    languages = {entry["language"] for entry in materials}
    domain_families = {entry["domain_family"] for entry in materials}

    assert {"en", "ko"} <= languages
    assert {
        "biology",
        "statistics",
        "physics",
        "linguistics",
        "computer_science",
        "economics",
    } <= domain_families

    assert "ko_accounting_principles_appraiser_2026" not in {
        entry["document_id"] for entry in materials
    }
    assert "accounting" not in domain_families


def test_current_data_material_manifest_entries_have_topics_and_styles():
    materials = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["materials"]

    for entry in materials:
        assert entry["topics"]
        assert entry["recommended_problem_styles"]
        assert entry["recommended_case_count"] >= 2
