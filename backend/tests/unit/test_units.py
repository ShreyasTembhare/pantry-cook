"""Tests for the units domain module — conversion, arithmetic, rounding, formatting."""

from decimal import Decimal

import pytest

from app.domain.units import (
    Dimension,
    DimensionMismatchError,
    Quantity,
    Unit,
)


class TestUnitProperties:
    def test_g_is_mass(self) -> None:
        assert Unit.G.dimension == Dimension.MASS

    def test_kg_is_mass(self) -> None:
        assert Unit.KG.dimension == Dimension.MASS

    def test_ml_is_volume(self) -> None:
        assert Unit.ML.dimension == Dimension.VOLUME

    def test_l_is_volume(self) -> None:
        assert Unit.L.dimension == Dimension.VOLUME

    def test_count_is_count(self) -> None:
        assert Unit.COUNT.dimension == Dimension.COUNT

    def test_kg_factor(self) -> None:
        assert Unit.KG.factor_to_base == Decimal("1000")

    def test_l_factor(self) -> None:
        assert Unit.L.factor_to_base == Decimal("1000")

    def test_g_base_unit(self) -> None:
        assert Unit.G.base_unit == Unit.G

    def test_kg_base_unit(self) -> None:
        assert Unit.KG.base_unit == Unit.G


class TestQuantityCreation:
    def test_from_decimal(self) -> None:
        q = Quantity(Decimal("1.5"), Unit.KG)
        assert q.amount == Decimal("1.50")
        assert q.unit == Unit.KG

    def test_from_float(self) -> None:
        q = Quantity(1.5, Unit.KG)
        assert q.amount == Decimal("1.50")

    def test_from_int(self) -> None:
        q = Quantity(3, Unit.COUNT)
        assert q.amount == Decimal("3")

    def test_from_string(self) -> None:
        q = Quantity("2.75", Unit.G)
        assert q.amount == Decimal("2.75")

    def test_count_rounded_to_integer(self) -> None:
        q = Quantity("2.7", Unit.COUNT)
        assert q.amount == Decimal("3")

    def test_mass_quantised_to_hundredths(self) -> None:
        q = Quantity("1.005", Unit.G)
        assert q.amount == Decimal("1.01")

    def test_zero_quantity(self) -> None:
        q = Quantity(0, Unit.G)
        assert q.amount == Decimal("0.00")


class TestConversion:
    def test_kg_to_g(self) -> None:
        q = Quantity("1.5", Unit.KG)
        base = q.to_base()
        assert base.unit == Unit.G
        assert base.amount == Decimal("1500.00")

    def test_g_to_kg(self) -> None:
        q = Quantity("1500", Unit.G)
        kg = q.to_unit(Unit.KG)
        assert kg.unit == Unit.KG
        assert kg.amount == Decimal("1.50")

    def test_l_to_ml(self) -> None:
        q = Quantity("2", Unit.L)
        ml = q.to_base()
        assert ml.unit == Unit.ML
        assert ml.amount == Decimal("2000.00")

    def test_ml_to_l(self) -> None:
        q = Quantity("500", Unit.ML)
        l_qty = q.to_unit(Unit.L)
        assert l_qty.amount == Decimal("0.50")

    def test_roundtrip_kg_g_kg(self) -> None:
        original = Quantity("1.23", Unit.KG)
        roundtripped = original.to_base().to_unit(Unit.KG)
        assert roundtripped.amount == original.amount

    def test_roundtrip_l_ml_l(self) -> None:
        original = Quantity("0.75", Unit.L)
        roundtripped = original.to_base().to_unit(Unit.L)
        assert roundtripped.amount == original.amount

    def test_count_to_base_is_identity(self) -> None:
        q = Quantity(5, Unit.COUNT)
        base = q.to_base()
        assert base.amount == Decimal("5")
        assert base.unit == Unit.COUNT

    def test_cross_dimension_raises(self) -> None:
        q = Quantity(100, Unit.G)
        with pytest.raises(DimensionMismatchError):
            q.to_unit(Unit.ML)


class TestArithmetic:
    def test_add_same_unit(self) -> None:
        a = Quantity("100", Unit.G)
        b = Quantity("200", Unit.G)
        result = a + b
        assert result.amount == Decimal("300.00")
        assert result.unit == Unit.G

    def test_add_different_units_same_dimension(self) -> None:
        a = Quantity("1", Unit.KG)
        b = Quantity("500", Unit.G)
        result = a + b
        assert result.amount == Decimal("1.50")
        assert result.unit == Unit.KG

    def test_sub_same_unit(self) -> None:
        a = Quantity("500", Unit.ML)
        b = Quantity("200", Unit.ML)
        result = a - b
        assert result.amount == Decimal("300.00")

    def test_sub_different_units(self) -> None:
        a = Quantity("2", Unit.L)
        b = Quantity("500", Unit.ML)
        result = a - b
        assert result.amount == Decimal("1.50")

    def test_add_cross_dimension_raises(self) -> None:
        with pytest.raises(DimensionMismatchError):
            Quantity(100, Unit.G) + Quantity(100, Unit.ML)

    def test_sub_cross_dimension_raises(self) -> None:
        with pytest.raises(DimensionMismatchError):
            Quantity(100, Unit.G) - Quantity(100, Unit.ML)


class TestComparison:
    def test_equal_same_unit(self) -> None:
        assert Quantity(100, Unit.G) == Quantity(100, Unit.G)

    def test_equal_different_units(self) -> None:
        assert Quantity(1, Unit.KG) == Quantity(1000, Unit.G)

    def test_not_equal(self) -> None:
        assert Quantity(100, Unit.G) != Quantity(200, Unit.G)

    def test_lt(self) -> None:
        assert Quantity(100, Unit.G) < Quantity(200, Unit.G)

    def test_gt(self) -> None:
        assert Quantity(200, Unit.G) > Quantity(100, Unit.G)

    def test_le(self) -> None:
        assert Quantity(100, Unit.G) <= Quantity(100, Unit.G)

    def test_ge(self) -> None:
        assert Quantity(100, Unit.G) >= Quantity(100, Unit.G)


class TestFormat:
    def test_trailing_zeros_trimmed(self) -> None:
        q = Quantity("1.50", Unit.KG)
        assert q.format() == "1.5 kg"

    def test_integer_shown_without_decimal(self) -> None:
        q = Quantity(500, Unit.G)
        assert q.format() == "500 g"

    def test_count_format(self) -> None:
        q = Quantity(6, Unit.COUNT)
        assert q.format() == "6 count"

    def test_small_value(self) -> None:
        q = Quantity("0.01", Unit.G)
        assert q.format() == "0.01 g"


class TestFromBase:
    def test_from_base_to_kg(self) -> None:
        q = Quantity.from_base(1500.0, Dimension.MASS, Unit.KG)
        assert q.amount == Decimal("1.50")
        assert q.unit == Unit.KG

    def test_from_base_to_g(self) -> None:
        q = Quantity.from_base(1500.0, Dimension.MASS, Unit.G)
        assert q.amount == Decimal("1500.00")

    def test_from_base_to_l(self) -> None:
        q = Quantity.from_base(2000.0, Dimension.VOLUME, Unit.L)
        assert q.amount == Decimal("2.00")

    def test_float_roundtrip_quantises(self) -> None:
        q = Quantity.from_base(0.1, Dimension.MASS, Unit.G)
        assert q.amount == Decimal("0.10")
