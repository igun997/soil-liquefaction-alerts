"""
Tests for liquefaction calculation engine.

Tests based on published examples from Boulanger & Idriss (2014).
"""
import pytest
from app.services.liquefaction import LiquefactionCalculator
from app.models.soil import SoilProfile, SPTData, CPTData, SoilLayer


@pytest.fixture
def calculator():
    """Create calculator instance."""
    return LiquefactionCalculator()


@pytest.fixture
def sample_profile():
    """Create sample soil profile for testing."""
    return SoilProfile(
        name="Test Profile",
        latitude=37.5,
        longitude=-122.0,
        groundwater_depth=2.0,
        layers=[
            SoilLayer(
                depth_top=0,
                depth_bottom=20,
                unit_weight=18.0,
                fines_content=10.0,
            )
        ],
        spt_data=[
            SPTData(depth=3.0, n_value=10, fines_content=10.0),
            SPTData(depth=6.0, n_value=12, fines_content=10.0),
            SPTData(depth=9.0, n_value=15, fines_content=10.0),
            SPTData(depth=12.0, n_value=18, fines_content=10.0),
        ],
    )


class TestStressCalculations:
    """Test stress calculation methods."""

    def test_stress_above_gwt(self, calculator):
        """Test stress calculation above groundwater table."""
        profile = SoilProfile(
            latitude=0,
            longitude=0,
            groundwater_depth=5.0,
            layers=[
                SoilLayer(depth_top=0, depth_bottom=10, unit_weight=18.0)
            ],
        )

        stress = calculator.calculate_stress_state(3.0, profile)

        # At 3m depth, above GWT
        assert stress.depth == 3.0
        assert stress.sigma_v == pytest.approx(54.0, rel=0.05)  # 18 * 3
        assert stress.sigma_v_eff == pytest.approx(54.0, rel=0.05)  # Same as total
        assert stress.u == 0.0

    def test_stress_below_gwt(self, calculator):
        """Test stress calculation below groundwater table."""
        profile = SoilProfile(
            latitude=0,
            longitude=0,
            groundwater_depth=2.0,
            layers=[
                SoilLayer(depth_top=0, depth_bottom=10, unit_weight=18.0)
            ],
        )

        stress = calculator.calculate_stress_state(5.0, profile)

        # At 5m depth, 3m below GWT
        assert stress.depth == 5.0
        assert stress.sigma_v == pytest.approx(90.0, rel=0.05)  # 18 * 5
        # Effective = 18*2 + (18-9.81)*3 ≈ 36 + 24.57 = 60.57
        assert stress.sigma_v_eff == pytest.approx(60.57, rel=0.1)
        assert stress.u == pytest.approx(29.43, rel=0.05)  # 9.81 * 3


class TestRdCalculation:
    """Test stress reduction factor calculation."""

    def test_rd_shallow_depth(self, calculator):
        """Test rd at shallow depth."""
        rd = calculator.calculate_rd(3.0, 7.5)
        # rd should be close to 1.0 at shallow depths
        assert 0.9 <= rd <= 1.0

    def test_rd_deep(self, calculator):
        """Test rd at deeper depth."""
        rd = calculator.calculate_rd(15.0, 7.5)
        # rd decreases with depth
        assert 0.3 <= rd <= 0.8

    def test_rd_magnitude_effect(self, calculator):
        """Test magnitude effect on rd."""
        rd_m7 = calculator.calculate_rd(10.0, 7.0)
        rd_m8 = calculator.calculate_rd(10.0, 8.0)
        # Higher magnitude typically gives higher rd
        assert rd_m8 >= rd_m7 * 0.95


class TestCSRCalculation:
    """Test CSR calculation."""

    def test_csr_basic(self, calculator):
        """Test basic CSR calculation."""
        csr = calculator.calculate_csr(
            amax=0.2,
            sigma_v=100,
            sigma_v_eff=70,
            rd=0.95,
        )
        # CSR = 0.65 * 0.2 * (100/70) * 0.95 ≈ 0.176
        assert csr == pytest.approx(0.176, rel=0.05)

    def test_csr_zero_stress(self, calculator):
        """Test CSR with zero effective stress."""
        csr = calculator.calculate_csr(
            amax=0.2,
            sigma_v=100,
            sigma_v_eff=0,
            rd=0.95,
        )
        assert csr == 0.0


class TestMSFCalculation:
    """Test magnitude scaling factor."""

    def test_msf_reference(self, calculator):
        """Test MSF for reference magnitude 7.5."""
        msf = calculator.calculate_msf(7.5)
        # MSF should be close to 1.0 for M=7.5
        assert msf == pytest.approx(1.0, rel=0.1)

    def test_msf_smaller_magnitude(self, calculator):
        """Test MSF for smaller magnitude."""
        msf = calculator.calculate_msf(6.0)
        # MSF > 1.0 for M < 7.5
        assert msf > 1.0

    def test_msf_larger_magnitude(self, calculator):
        """Test MSF for larger magnitude."""
        msf = calculator.calculate_msf(8.0)
        # MSF < 1.0 for M > 7.5
        assert msf < 1.0


class TestSPTCorrections:
    """Test SPT value corrections."""

    def test_n1_60_correction(self, calculator):
        """Test (N1)60 correction."""
        spt = SPTData(
            depth=5.0,
            n_value=15,
            hammer_energy_ratio=60,
            fines_content=5,
        )

        n1_60, n1_60_cs = calculator.correct_spt_n_value(spt, sigma_v_eff=50)

        # N1_60 should be corrected for overburden
        assert n1_60 > 0
        # Clean sand correction minimal for FC=5%
        assert n1_60_cs >= n1_60

    def test_fines_correction(self, calculator):
        """Test fines content correction."""
        spt_clean = SPTData(depth=5.0, n_value=15, fines_content=5)
        spt_silty = SPTData(depth=5.0, n_value=15, fines_content=25)

        _, n1_60_cs_clean = calculator.correct_spt_n_value(spt_clean, 50)
        _, n1_60_cs_silty = calculator.correct_spt_n_value(spt_silty, 50)

        # Higher fines content should give higher correction
        assert n1_60_cs_silty > n1_60_cs_clean


class TestCRRCalculation:
    """Test CRR calculation."""

    def test_crr_spt_low_n(self, calculator):
        """Test CRR for low N-value."""
        crr = calculator.calculate_crr_spt(10)
        # Low N should give low CRR
        assert 0.05 <= crr <= 0.2

    def test_crr_spt_high_n(self, calculator):
        """Test CRR for high N-value."""
        crr = calculator.calculate_crr_spt(30)
        # High N should give high CRR
        assert crr > 0.3

    def test_crr_cpt(self, calculator):
        """Test CRR from CPT."""
        crr = calculator.calculate_crr_cpt(100)
        assert crr > 0


class TestFactorOfSafety:
    """Test factor of safety calculation."""

    def test_fs_calculation(self, calculator):
        """Test FS calculation."""
        fs = calculator.calculate_factor_of_safety(
            crr_7_5=0.2,
            csr=0.15,
            msf=1.0,
            k_sigma=1.0,
        )
        # FS = 0.2 * 1.0 * 1.0 / 0.15 = 1.33
        assert fs == pytest.approx(1.33, rel=0.05)

    def test_fs_with_corrections(self, calculator):
        """Test FS with MSF and K_sigma corrections."""
        fs = calculator.calculate_factor_of_safety(
            crr_7_5=0.2,
            csr=0.2,
            msf=1.2,
            k_sigma=0.9,
        )
        # FS = 0.2 * 1.2 * 0.9 / 0.2 = 1.08
        assert fs == pytest.approx(1.08, rel=0.05)


class TestRiskLevel:
    """Test risk level classification."""

    def test_very_high_risk(self, calculator):
        """Test very high risk classification."""
        from app.models.analysis import RiskLevel

        risk = calculator.get_risk_level(0.3)
        assert risk == RiskLevel.VERY_HIGH

    def test_high_risk(self, calculator):
        """Test high risk classification."""
        from app.models.analysis import RiskLevel

        risk = calculator.get_risk_level(0.7)
        assert risk == RiskLevel.HIGH

    def test_moderate_risk(self, calculator):
        """Test moderate risk classification."""
        from app.models.analysis import RiskLevel

        risk = calculator.get_risk_level(1.2)
        assert risk == RiskLevel.MODERATE

    def test_low_risk(self, calculator):
        """Test low risk classification."""
        from app.models.analysis import RiskLevel

        risk = calculator.get_risk_level(2.0)
        assert risk == RiskLevel.LOW


class TestProfileAnalysis:
    """Test complete profile analysis."""

    def test_analyze_profile(self, calculator, sample_profile):
        """Test full profile analysis."""
        layer_results, risk = calculator.analyze_profile(
            profile=sample_profile,
            amax=0.2,
            magnitude=7.0,
        )

        # Should have results for each SPT test
        assert len(layer_results) == 4

        # Each result should have required fields
        for result in layer_results:
            assert result.depth > 0
            assert result.csr > 0
            assert result.crr > 0
            assert result.factor_of_safety > 0

        # Risk assessment should be populated
        assert risk.overall_fs > 0
        assert risk.critical_depth > 0
        assert risk.recommendation

    def test_lpi_calculation(self, calculator, sample_profile):
        """Test LPI calculation."""
        layer_results, risk = calculator.analyze_profile(
            profile=sample_profile,
            amax=0.3,  # Higher PGA
            magnitude=7.5,
        )

        # LPI should be calculated
        assert risk.lpi is not None
        assert risk.lpi >= 0


class TestCPTAnalysis:
    """Test CPT-based analysis."""

    def test_analyze_cpt(self, calculator):
        """Test CPT analysis."""
        profile = SoilProfile(
            latitude=0,
            longitude=0,
            groundwater_depth=1.5,
            layers=[
                SoilLayer(depth_top=0, depth_bottom=15, unit_weight=18.0)
            ],
            cpt_data=[
                CPTData(depth=2.0, qc=5.0, fs=50),
                CPTData(depth=5.0, qc=8.0, fs=80),
                CPTData(depth=8.0, qc=12.0, fs=100),
            ],
        )

        layer_results, risk = calculator.analyze_profile(
            profile=profile,
            amax=0.2,
            magnitude=7.0,
        )

        # Should analyze CPT data
        assert len(layer_results) >= 1

        # Results should use CPT method
        for result in layer_results:
            assert result.test_type == "CPT"
            assert result.qc1n_cs is not None
