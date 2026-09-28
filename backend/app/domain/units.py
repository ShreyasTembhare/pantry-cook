from __future__ import annotations

import enum
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


class Dimension(enum.StrEnum):
    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"


class Unit(enum.StrEnum):
    G = "g"
    KG = "kg"
    ML = "ml"
    L = "L"
    COUNT = "count"

    @property
    def dimension(self) -> Dimension:
        return _UNIT_META[self].dimension

    @property
    def factor_to_base(self) -> Decimal:
        return _UNIT_META[self].factor_to_base

    @property
    def base_unit(self) -> Unit:
        return _DIMENSION_BASE[self.dimension]


class _UnitMeta:
    __slots__ = ("dimension", "factor_to_base")

    def __init__(self, dimension: Dimension, factor_to_base: Decimal) -> None:
        self.dimension = dimension
        self.factor_to_base = factor_to_base


_UNIT_META: dict[Unit, _UnitMeta] = {
    Unit.G: _UnitMeta(Dimension.MASS, Decimal("1")),
    Unit.KG: _UnitMeta(Dimension.MASS, Decimal("1000")),
    Unit.ML: _UnitMeta(Dimension.VOLUME, Decimal("1")),
    Unit.L: _UnitMeta(Dimension.VOLUME, Decimal("1000")),
    Unit.COUNT: _UnitMeta(Dimension.COUNT, Decimal("1")),
}

_DIMENSION_BASE: dict[Dimension, Unit] = {
    Dimension.MASS: Unit.G,
    Dimension.VOLUME: Unit.ML,
    Dimension.COUNT: Unit.COUNT,
}


class DimensionMismatchError(Exception):
    def __init__(self, left: Dimension, right: Dimension) -> None:
        self.left = left
        self.right = right
        super().__init__(f"Cannot operate between {left.value} and {right.value}")


_MASS_VOLUME_QUANT = Decimal("0.01")
_COUNT_QUANT = Decimal("1")

MAX_BASE_QUANTITY = Decimal("1000000")
MIN_POSITIVE_QUANTITY = Decimal("0.01")


def _quantise(amount: Decimal, dimension: Dimension) -> Decimal:
    if dimension == Dimension.COUNT:
        return amount.quantize(_COUNT_QUANT, rounding=ROUND_HALF_UP)
    return amount.quantize(_MASS_VOLUME_QUANT, rounding=ROUND_HALF_UP)


def parse_decimal(value: str | float | int | Decimal) -> Decimal:
    """Parse a value into Decimal, going through str for float to avoid float artifacts."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"Invalid decimal value: {value}") from e


class Quantity:
    """Immutable quantity value object with unit-aware arithmetic."""

    __slots__ = ("_amount", "_unit")

    def __init__(self, amount: Decimal | str | float | int, unit: Unit) -> None:
        parsed = parse_decimal(amount)
        self._amount = _quantise(parsed, unit.dimension)
        self._unit = unit

    @property
    def amount(self) -> Decimal:
        return self._amount

    @property
    def unit(self) -> Unit:
        return self._unit

    @property
    def dimension(self) -> Dimension:
        return self._unit.dimension

    def to_base(self) -> Quantity:
        """Convert to the base unit of the same dimension."""
        base_amount = self._amount * self._unit.factor_to_base
        base_unit = self._unit.base_unit
        return Quantity(base_amount, base_unit)

    def to_unit(self, target: Unit) -> Quantity:
        """Convert to a different unit within the same dimension."""
        if target.dimension != self._unit.dimension:
            raise DimensionMismatchError(self._unit.dimension, target.dimension)
        base_amount = self._amount * self._unit.factor_to_base
        converted = base_amount / target.factor_to_base
        return Quantity(converted, target)

    def __add__(self, other: Quantity) -> Quantity:
        if self._unit.dimension != other._unit.dimension:
            raise DimensionMismatchError(self._unit.dimension, other._unit.dimension)
        base_self = self._amount * self._unit.factor_to_base
        base_other = other._amount * other._unit.factor_to_base
        total_base = base_self + base_other
        result = total_base / self._unit.factor_to_base
        return Quantity(result, self._unit)

    def __sub__(self, other: Quantity) -> Quantity:
        if self._unit.dimension != other._unit.dimension:
            raise DimensionMismatchError(self._unit.dimension, other._unit.dimension)
        base_self = self._amount * self._unit.factor_to_base
        base_other = other._amount * other._unit.factor_to_base
        total_base = base_self - base_other
        result = total_base / self._unit.factor_to_base
        return Quantity(result, self._unit)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        if self._unit.dimension != other._unit.dimension:
            return False
        return (self._amount * self._unit.factor_to_base) == (
            other._amount * other._unit.factor_to_base
        )

    def __lt__(self, other: Quantity) -> bool:
        if self._unit.dimension != other._unit.dimension:
            raise DimensionMismatchError(self._unit.dimension, other._unit.dimension)
        return (self._amount * self._unit.factor_to_base) < (
            other._amount * other._unit.factor_to_base
        )

    def __le__(self, other: Quantity) -> bool:
        return self == other or self < other

    def __gt__(self, other: Quantity) -> bool:
        return not self <= other

    def __ge__(self, other: Quantity) -> bool:
        return not self < other

    def __repr__(self) -> str:
        return f"Quantity({self._amount}, {self._unit.value})"

    def format(self) -> str:
        """Human-readable display: trims trailing zeros, e.g. '1.5 kg'."""
        display = self._amount.normalize()
        if display == display.to_integral_value():
            display = display.quantize(Decimal("1"))
        return f"{display} {self._unit.value}"

    @classmethod
    def from_base(
        cls, base_amount: float | Decimal, dimension: Dimension, display_unit: Unit
    ) -> Quantity:
        """Create a Quantity from a base-unit amount, converting to the display unit."""
        parsed = parse_decimal(base_amount)
        base_unit = _DIMENSION_BASE[dimension]
        base_qty = cls(parsed, base_unit)
        return base_qty.to_unit(display_unit)
