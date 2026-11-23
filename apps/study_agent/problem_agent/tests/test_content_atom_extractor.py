from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import ContentAtomType
from app.schemas.problems import ProblemStyle
from app.services.content_atom_extractor import ContentAtomExtractor


def chunk(text: str, *, chunk_id: str = "chunk_1", concepts: list[str] | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc_1",
        content=text,
        concepts=concepts or [],
    )


def atom_types(text: str, concepts: list[str] | None = None) -> set[ContentAtomType]:
    atoms = ContentAtomExtractor().extract(
        chunks=[chunk(text, concepts=concepts)],
        concepts=concepts or [],
        problem_style=ProblemStyle.auto,
    )
    return {atom.atom_type for atom in atoms}


def atoms_for(text: str, concepts: list[str] | None = None):
    return ContentAtomExtractor().extract(
        chunks=[chunk(text, concepts=concepts)],
        concepts=concepts or [],
        problem_style=ProblemStyle.auto,
    )


def test_korean_rule_chunk_produces_rule_and_procedure_atoms():
    types = atom_types(
        "실험 조건을 기록한다. 1) 전압을 기록한다. 2) 결과를 비교한다.",
        ["실험", "조건", "전압"],
    )

    assert ContentAtomType.rule in types
    assert ContentAtomType.procedure in types


def test_korean_formula_chunk_produces_formula_atom():
    types = atom_types("등가저항 = R1 + R2 이고 전체 전류 = 전압 / 등가저항이다.", ["등가저항"])

    assert ContentAtomType.formula in types


def test_nlp_attention_chunk_produces_rule_or_procedure_atoms():
    types = atom_types(
        "Self-attention is a sequence process: step 1 compute scores, step 2 weight values.",
        ["self-attention", "sequence"],
    )

    assert ContentAtomType.procedure in types
    assert ContentAtomType.rule in types or ContentAtomType.definition in types


def test_physics_capacitance_formula_chunk_produces_formula_atom():
    types = atom_types("For a parallel-plate capacitor, C = epsilon A / d.", ["capacitance"])

    assert ContentAtomType.formula in types


def test_law_like_rule_exception_chunk_produces_rule_and_condition_exception_atoms():
    types = atom_types("A valid offer requires definite terms unless the statute provides an exception.", ["offer"])

    assert ContentAtomType.rule in types
    assert ContentAtomType.condition_exception in types


def test_literature_evidence_chunk_produces_evidence_claim_atom():
    types = atom_types("The repeated image of winter supports the claim that the speaker feels isolated.", ["claim"])

    assert ContentAtomType.evidence_claim in types


def test_sequence_model_concepts_without_explicit_vs_produce_comparison_atom():
    atoms = atoms_for(
        "RNN keeps hidden state across a sequence and CNN applies convolutional filters over local windows.",
        ["RNN", "CNN"],
    )

    comparison_atoms = [atom for atom in atoms if atom.atom_type == ContentAtomType.comparison]
    assert comparison_atoms
    assert comparison_atoms[0].confidence >= 0.55


def test_discourse_genre_context_feature_interpretation_produces_evidence_claim_atom():
    types = atom_types(
        "Discourse and genre analysis links textual features to context, and this interpretation shows how register shapes meaning.",
        ["discourse", "genre", "context"],
    )

    assert ContentAtomType.evidence_claim in types


def test_paired_concepts_with_relation_do_not_force_comparison_atom():
    atoms = atoms_for(
        "광합성은 빛 에너지를 이용해 이산화탄소와 물로 포도당을 만드는 과정이다.",
        ["광합성", "빛 에너지"],
    )
    types = {atom.atom_type for atom in atoms}

    assert ContentAtomType.evidence_claim in types
    assert ContentAtomType.comparison not in types
