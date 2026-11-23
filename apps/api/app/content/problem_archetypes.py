"""Problem mechanisms the generator is asked to build on, per unit.

Left to itself a model keeps reusing one or two set-ups (in our probes, 2 of
4 problems used the same "|f(x) - t| non-differentiable points" idea), and
it drifts toward problems that state f directly. Each archetype names a
mechanism that late 4-point / #22 problems actually turn on, the traps that
split strong students, and levers for making a too-easy draft harder.

These describe structures, not past exam items: the generator must write new
problems.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Archetype:
    id: str
    name: str
    mechanism: str
    traps: str
    levers: str


@dataclass(frozen=True)
class UnitBlueprint:
    unit_id: str
    course: str
    domain: str
    scope: str
    archetypes: tuple[Archetype, ...]


CALC1_DIFF = UnitBlueprint(
    unit_id="calc1-diff",
    course="미적분Ⅰ",
    domain="미분",
    scope=(
        "다항함수만 쓴다 (지수·로그·삼각함수, 몫의 미분, 합성함수 미분은 범위 밖). "
        "극한과 연속, 미분계수, 도함수, 극대·극소, 방정식과 부등식 활용, 접선까지."
    ),
    archetypes=(
        Archetype(
            id="diff-abs-kink",
            name="절댓값·구간별 함수의 미분가능성",
            mechanism=(
                "미지의 다항함수 f로 g(x)를 만든다: |f(x) - k|, (x - a)|f(x)|, x = a 기준 구간별 정의 등. "
                "'g가 실수 전체에서 미분가능' 또는 '미분가능하지 않은 점이 n개'라는 조건이 f의 중근 위치나 연결점에서의 f(a), f'(a)를 강제한다."
            ),
            traps="중근에서는 |f|가 미분가능하다는 점, 연결점에서 함숫값과 미분계수를 둘 다 맞춰야 한다는 점, 삼중근, 허근 때문에 근이 하나뿐인 경우를 빠뜨림.",
            levers="상수 k나 연결점 a도 미지수로 두기, 미분 불가능한 점의 '개수'만 주기, 다른 조건과 맞물려야 케이스가 하나로 줄게 하기.",
        ),
        Archetype(
            id="diff-root-count-function",
            name="실근 개수로 정의한 함수",
            mechanism=(
                "실수 t에 대하여 방정식 f(x) = t, f(x) = tx, f(x) = t(x - a) 같은 방정식의 서로 다른 실근 개수를 h(t)로 둔다. "
                "h의 불연속점, 특정 t에서의 값, 좌우극한 조건이 f의 극값이나 접선 기울기를 결정한다."
            ),
            traps="극값과 같은 높이에서 개수가 어느 쪽으로 바뀌는지, 원점을 지나는 접선의 기울기, 극값이 없는 삼차함수.",
            levers="h(t)의 값 대신 lim h의 합이나 불연속점 개수만 주기, 기준점 a를 미지수로 두기, 사차함수로 올리기.",
        ),
        Archetype(
            id="diff-interval-extreme",
            name="구간 최대·최소로 정의한 함수",
            mechanism=(
                "g(t)를 닫힌구간 [t, t + c]에서 f(x)의 최댓값(또는 최솟값)으로 정의한다. "
                "g의 미분가능성, g의 최솟값, g가 상수인 구간 같은 조건이 f를 결정한다."
            ),
            traps="구간 안에 극점이 들어오는 순간, 양 끝값이 같아지는 t, 최댓값이 바뀌는 지점에서 g가 꺾이는지 여부.",
            levers="구간 길이 c를 미지수로 두기, g가 미분가능하지 않은 t의 개수만 주기, f를 사차함수로 하기.",
        ),
        Archetype(
            id="diff-tangent-count",
            name="접선의 개수",
            mechanism=(
                "점 (a, b)에서 곡선 y = f(x)에 그을 수 있는 서로 다른 접선의 개수를 이용한다. "
                "a 또는 b에 따라 개수가 바뀌는 경계가 조건이 된다."
            ),
            traps="점이 곡선 위에 있을 때, 변곡점에서의 접선, 서로 다른 접점이 같은 접선을 주는 사차함수.",
            levers="접선 개수가 2가 되는 점들의 집합을 조건으로 주기, 개수를 함수로 정의해 불연속점을 묻기.",
        ),
        Archetype(
            id="diff-composite-product",
            name="곱·합성으로 만든 함수의 극값",
            mechanism=(
                "g(x) = f(x)f(x - k), f(|x|), |f(|x|) - k|, f(x)(x - a)^2 처럼 f로 새 함수를 만들고 "
                "g의 극값 개수, 극대·극소 위치, 미분 불가능한 점 개수를 조건으로 준다."
            ),
            traps="|x| 때문에 x = 0에서 생기는 꺾임, 대칭으로 극값이 겹치는 경우, 곱의 미분에서 공통인수.",
            levers="k도 미지수로 두고 조건을 만족하는 k의 개수나 합을 묻기, 정수 조건을 추가하기.",
        ),
        Archetype(
            id="diff-mean-slope",
            name="할선 기울기와 접선 기울기",
            mechanism=(
                "모든 실수 x에 대하여 성립하는 등식(예: f(x) - f(a) = (x - a)·p(x) 꼴)이나 "
                "할선 기울기 (f(x) - f(a))/(x - a)로 정의한 함수의 최솟값·극값 조건으로 f를 결정한다."
            ),
            traps="x = a에서 정의되지 않는 점의 처리(연속성으로 메우기), 할선 기울기 함수의 차수, 등호 성립 조건.",
            levers="정의되지 않는 점에서의 값을 연속 조건으로 숨기기, 최솟값이 존재한다는 사실 자체를 조건으로 쓰기.",
        ),
        Archetype(
            id="diff-integer-condition",
            name="정수 조건이 섞인 부등식",
            mechanism=(
                "f'(n), f(n)의 부호나 f(x) ≥ g(x)가 성립하는 정수 x의 개수 같은 조건으로 계수의 범위를 좁히고, "
                "다른 조건으로 하나를 고른다."
            ),
            traps="경계 정수를 넣느냐 마느냐, 부등식의 등호, 범위가 비어 버리는 경우.",
            levers="'정수 k의 개수'와 '그때 f(5)의 최댓값'처럼 두 단계로 묻기.",
        ),
    ),
)

CALC1_INTEGRAL = UnitBlueprint(
    unit_id="calc1-integral",
    course="미적분Ⅰ",
    domain="적분",
    scope="다항함수만 쓴다. 부정적분, 정적분, 정적분으로 정의된 함수, 넓이, 속도와 거리까지.",
    archetypes=(
        Archetype(
            id="int-defined-function",
            name="정적분으로 정의된 함수",
            mechanism=(
                "g(x) = ∫_a^x f(t)dt, ∫_x^(x+1) f(t)dt, ∫_0^x (x - t)f(t)dt 같은 함수의 극값·실근·최솟값 조건으로 f를 결정한다."
            ),
            traps="아래끝을 대입하면 0이 되는 점, x가 적분 기호 안에 있을 때 미분 전에 밖으로 빼야 하는 것, 극값 판정.",
            levers="g의 극값 개수만 주기, a도 미지수로 두기, g(x) = 0의 실근 개수 조건과 섞기.",
        ),
        Archetype(
            id="int-abs-area",
            name="절댓값 정적분과 넓이",
            mechanism=(
                "∫_0^t |f(x)|dx, ∫|f'(x)|dx(총 변화량), 곡선과 x축·직선이 둘러싼 두 부분의 넓이가 같다 같은 조건을 이용한다."
            ),
            traps="부호가 바뀌는 지점을 기준으로 나누기, 넓이가 같다 = 정적분이 0, 구간 밖 근.",
            levers="넓이 조건과 미분가능성 조건을 함께 걸기, 넓이를 t의 함수로 두고 그 최솟값을 묻기.",
        ),
        Archetype(
            id="int-motion",
            name="속도와 위치",
            mechanism=(
                "두 점 P, Q의 속도 함수를 주고 운동 방향이 바뀌는 횟수, 두 점이 만나는 시각, 이동 거리 조건으로 미지수를 정한다."
            ),
            traps="위치 변화량과 이동 거리 구분, 출발 위치, 속도가 0이지만 방향이 안 바뀌는 순간.",
            levers="만나는 횟수를 조건으로 주기, 미지수가 둘인 속도 함수.",
        ),
        Archetype(
            id="int-functional-equation",
            name="적분이 들어간 함수방정식",
            mechanism=(
                "x f(x) = ∫_1^x f(t)dt + (다항식), f(x) = x^2 + ∫_0^1 x f(t)dt 같은 등식으로 f의 차수와 계수를 결정한다."
            ),
            traps="차수 비교, 정적분이 상수라는 점, 양변에 특정 값 대입을 빠뜨림.",
            levers="미분가능성이나 극값 조건을 하나 더 걸어 케이스를 남기기.",
        ),
    ),
)

BLUEPRINTS: dict[str, UnitBlueprint] = {
    blueprint.unit_id: blueprint for blueprint in (CALC1_DIFF, CALC1_INTEGRAL)
}


def blueprint_for(unit_id: str) -> UnitBlueprint:
    try:
        return BLUEPRINTS[unit_id]
    except KeyError as exc:
        known = ", ".join(sorted(BLUEPRINTS))
        raise KeyError(f"no blueprint for unit {unit_id!r} (known: {known})") from exc


def archetype_for(blueprint: UnitBlueprint, archetype_id: str) -> Archetype:
    for archetype in blueprint.archetypes:
        if archetype.id == archetype_id:
            return archetype
    known = ", ".join(item.id for item in blueprint.archetypes)
    raise KeyError(f"no archetype {archetype_id!r} in {blueprint.unit_id} (known: {known})")
