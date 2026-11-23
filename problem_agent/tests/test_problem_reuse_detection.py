from app.services.problem_service import ProblemService


def service():
    return object.__new__(ProblemService)


def test_reuse_detects_same_calculation_template_with_changed_numbers():
    problem_service = service()
    previous = {
        "type": "short_answer",
        "difficulty": "medium",
        "bloom_level": "apply",
        "question": "힘이 10N이고 질량이 2kg일 때 F = ma를 이용해 가속도를 구하시오.",
        "answer": {"choice_id": None, "text": "a = 10 / 2 = 5m/s^2"},
        "explanation": "공식에 값을 대입해 계산한다.",
        "rubric": [{"criterion": "공식에 대입해 계산한다.", "points": 2}],
        "concepts": ["뉴턴 제2법칙"],
    }
    current = {
        "type": "short_answer",
        "difficulty": "medium",
        "bloom_level": "apply",
        "question": "힘이 18N이고 질량이 3kg일 때 F = ma를 이용해 가속도를 구하시오.",
        "answer": {"choice_id": None, "text": "a = 18 / 3 = 6m/s^2"},
        "explanation": "공식에 값을 대입해 계산한다.",
        "rubric": [{"criterion": "공식에 대입해 계산한다.", "points": 2}],
        "concepts": ["뉴턴 제2법칙"],
    }

    assert problem_service._is_reused_problem(
        problem_data=current,
        seen_fingerprints=[problem_service._problem_fingerprint(previous)],
    )


def test_reuse_detects_definition_recall_template_with_different_wording():
    problem_service = service()
    previous = {
        "type": "multiple_choice",
        "difficulty": "easy",
        "bloom_level": "remember",
        "question": "뉴턴 제2법칙은 무엇인가?",
        "choices": [{"id": "A", "text": "힘은 질량과 가속도의 곱이다."}],
        "answer": {"choice_id": "A", "text": "힘은 질량과 가속도의 곱이다."},
        "explanation": "정의를 확인하는 문제이다.",
        "concepts": ["뉴턴 제2법칙"],
    }
    current = {
        "type": "multiple_choice",
        "difficulty": "easy",
        "bloom_level": "remember",
        "question": "뉴턴 제2법칙의 의미로 가장 적절한 설명을 고르시오.",
        "choices": [{"id": "A", "text": "힘은 질량과 가속도의 곱이다."}],
        "answer": {"choice_id": "A", "text": "힘은 질량과 가속도의 곱이다."},
        "explanation": "개념의 의미를 확인하는 문제이다.",
        "concepts": ["뉴턴 제2법칙"],
    }

    assert problem_service._is_reused_problem(
        problem_data=current,
        seen_fingerprints=[problem_service._problem_fingerprint(previous)],
    )


def test_reuse_does_not_auto_reject_distinct_error_diagnosis_scenarios():
    problem_service = service()
    previous = {
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "item_model_id": "error_detection",
        "question": "Build-Max-Heap에서 마지막 내부 노드가 아니라 마지막 리프부터 시작한 오류를 찾아 수정하시오.",
        "answer": {"choice_id": None, "text": "마지막 내부 노드부터 루트 방향으로 Max-Heapify를 적용해야 한다."},
        "explanation": "리프는 이미 heap property를 만족하므로 시작점이 잘못되었다.",
        "rubric": [{"criterion": "시작 노드 오류를 진단한다.", "points": 2}],
        "concepts": ["heapsort"],
    }
    current = {
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "item_model_id": "error_detection",
        "question": "Heap-Extract-Max에서 heap size를 줄이기 전에 Max-Heapify를 호출한 잘못을 찾아 고치시오.",
        "answer": {"choice_id": None, "text": "최댓값을 제거하고 heap size를 줄인 뒤 루트에서 Max-Heapify를 수행해야 한다."},
        "explanation": "정렬된 영역을 heapify 대상에 포함하면 heap 영역 경계가 깨진다.",
        "rubric": [{"criterion": "heap 영역 경계 오류를 진단한다.", "points": 2}],
        "concepts": ["heapsort"],
    }

    assert not problem_service._is_reused_problem(
        problem_data=current,
        seen_fingerprints=[problem_service._problem_fingerprint(previous)],
    )


def test_reuse_does_not_match_same_template_without_concept_overlap():
    problem_service = service()
    previous = {
        "type": "short_answer",
        "difficulty": "easy",
        "bloom_level": "remember",
        "question": "미분의 정의는 무엇인가?",
        "answer": {"choice_id": None, "text": "순간 변화율이다."},
        "explanation": "정의를 확인한다.",
        "rubric": [{"criterion": "정의를 쓴다.", "points": 1}],
        "concepts": ["미분"],
    }
    current = {
        "type": "short_answer",
        "difficulty": "easy",
        "bloom_level": "remember",
        "question": "계약의 정의는 무엇인가?",
        "answer": {"choice_id": None, "text": "청약과 승낙으로 성립하는 법률행위이다."},
        "explanation": "정의를 확인한다.",
        "rubric": [{"criterion": "정의를 쓴다.", "points": 1}],
        "concepts": ["계약"],
    }

    assert not problem_service._is_reused_problem(
        problem_data=current,
        seen_fingerprints=[problem_service._problem_fingerprint(previous)],
    )


def test_reuse_preserves_exact_signature_duplicate_detection():
    problem_service = service()
    previous = {
        "type": "multiple_choice",
        "question": "힘과 질량의 관계를 고르시오.",
        "choices": [{"id": "A", "text": "F = ma"}],
        "answer": {"choice_id": "A", "text": "F = ma"},
        "concepts": ["뉴턴 제2법칙"],
    }

    assert problem_service._is_reused_problem(
        problem_data=dict(previous),
        seen_fingerprints=[problem_service._problem_fingerprint(previous)],
    )


def test_reuse_preserves_high_question_token_similarity_detection():
    problem_service = service()
    previous = {
        "type": "short_answer",
        "question": "뉴턴 제2법칙에서 같은 힘 조건일 때 질량과 가속도의 관계를 비교하시오.",
        "answer": {"choice_id": None, "text": "질량이 클수록 가속도는 작아진다."},
        "concepts": ["뉴턴 제2법칙"],
    }
    current = {
        "type": "short_answer",
        "question": "뉴턴 제2법칙에서 같은 힘 조건일 때 질량과 가속도의 관계를 비교하시오!",
        "answer": {"choice_id": None, "text": "질량이 클수록 가속도는 작아진다."},
        "concepts": ["뉴턴 제2법칙"],
    }

    assert problem_service._is_reused_problem(
        problem_data=current,
        seen_fingerprints=[problem_service._problem_fingerprint(previous)],
    )


def test_problem_fingerprint_includes_reasoning_template():
    problem_service = service()
    fingerprint = problem_service._problem_fingerprint(
        {
            "type": "short_answer",
            "question": "조건이 바뀔 때 결과 변화를 분석하시오.",
            "answer": {"choice_id": None, "text": "조건 변화가 결과를 바꾼다."},
            "concepts": ["조건 관계"],
        }
    )

    assert fingerprint["reasoning_template"]
