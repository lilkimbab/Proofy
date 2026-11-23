from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class SM2Record:
    concept: str
    repetitions: int = 0
    interval_days: int = 1
    ease_factor: float = 2.5
    next_review: str = field(default_factory=lambda: date.today().isoformat())
    is_weak: bool = False
    last_reviewed: str | None = None

    def to_dict(self) -> dict:
        return {
            "concept": self.concept,
            "repetitions": self.repetitions,
            "interval_days": self.interval_days,
            "ease_factor": self.ease_factor,
            "next_review": self.next_review,
            "is_weak": self.is_weak,
            "last_reviewed": self.last_reviewed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SM2Record:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def sm2_update(record: SM2Record, quality: int) -> SM2Record:
    """quality: 0-5 (0-2=오답, 3-5=정답)"""
    today = date.today()
    record.last_reviewed = today.isoformat()

    if quality < 3:
        record.repetitions = 0
        record.interval_days = 1
        record.ease_factor = max(1.3, record.ease_factor - 0.2)
    else:
        if record.repetitions == 0:
            record.interval_days = 1
        elif record.repetitions == 1:
            record.interval_days = 6
        else:
            record.interval_days = round(record.interval_days * record.ease_factor)
        record.ease_factor += 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        record.ease_factor = max(1.3, record.ease_factor)
        record.repetitions += 1

    record.next_review = (today + timedelta(days=record.interval_days)).isoformat()
    return record


def build_initial_records(
    concepts: list[str],
    weak_concepts: set[str],
    wrong_attempts: dict[str, int],
) -> list[SM2Record]:
    """퀴즈 이력 없는 개념은 SM-2 초기 상태로, 오답 이력이 있으면 quality로 변환해 업데이트."""
    records: list[SM2Record] = []
    for concept in concepts:
        record = SM2Record(concept=concept, is_weak=concept in weak_concepts)
        wrong_count = wrong_attempts.get(concept, 0)
        if wrong_count > 0:
            # 오답 횟수를 quality 변환: weak_concept이면 0, 아니면 1
            quality = 0 if concept in weak_concepts else 1
            for _ in range(min(wrong_count, 3)):
                record = sm2_update(record, quality)
        records.append(record)
    return records


def get_due_today(records: list[SM2Record], reference_date: date | None = None) -> list[SM2Record]:
    today = (reference_date or date.today()).isoformat()
    return [r for r in records if r.next_review <= today]
