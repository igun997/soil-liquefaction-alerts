"""
Liquefaction calculation engine based on Boulanger & Idriss (2014) methodology.

References:
- Boulanger, R.W. & Idriss, I.M. (2014). "CPT and SPT based liquefaction
  triggering procedures." Report No. UCD/CGM-14/01
- Idriss, I.M. & Boulanger, R.W. (2008). "Soil liquefaction during earthquakes."
  EERI Monograph MNO-12
"""
import math
from typing import List, Optional, Tuple
from dataclasses import dataclass

from app.models.soil import SoilProfile, SPTData, CPTData
from app.models.analysis import LayerResult, LiquefactionRisk, RiskLevel


@dataclass
class StressState:
    """Stress state at a given depth."""

    depth: float
    sigma_v: float  # Total vertical stress (kPa)
    sigma_v_eff: float  # Effective vertical stress (kPa)
    u: float  # Pore water pressure (kPa)


class LiquefactionCalculator:
    """
    Calculates liquefaction potential using simplified procedures.

    Supports both SPT and CPT based methods from Boulanger & Idriss (2014).
    """

    # Physical constants
    GRAVITY = 9.81  # m/s²
    WATER_UNIT_WEIGHT = 9.81  # kN/m³
    ATMOSPHERIC_PRESSURE = 101.325  # kPa

    def __init__(self):
        """Initialize calculator with default parameters."""
        pass

    def calculate_stress_state(
        self,
        depth: float,
        profile: SoilProfile,
    ) -> StressState:
        """
        Calculate total and effective vertical stress at a given depth.

        Args:
            depth: Depth below ground surface (m)
            profile: Soil profile with layer data

        Returns:
            StressState with sigma_v, sigma_v_eff, and pore pressure
        """
        gwt = profile.groundwater_depth
        sigma_v = 0.0
        sigma_v_eff = 0.0

        # Calculate stress by integrating through depth
        dz = 0.1  # Integration step (m)
        z = 0.0

        while z < depth:
            step = min(dz, depth - z)
            unit_weight = profile.get_unit_weight_at_depth(z)

            # Add to total stress
            sigma_v += unit_weight * step

            # Effective stress (subtract buoyancy below GWT)
            if z >= gwt:
                sigma_v_eff += (unit_weight - self.WATER_UNIT_WEIGHT) * step
            else:
                sigma_v_eff += unit_weight * step

            z += step

        # Pore water pressure
        if depth > gwt:
            u = self.WATER_UNIT_WEIGHT * (depth - gwt)
        else:
            u = 0.0

        return StressState(
            depth=depth,
            sigma_v=sigma_v,
            sigma_v_eff=max(sigma_v_eff, 0.1),  # Avoid zero
            u=u,
        )

    def calculate_rd(self, depth: float, magnitude: float = 7.5) -> float:
        """
        Calculate stress reduction coefficient rd.

        Based on Idriss (1999) and Idriss & Boulanger (2008).

        Args:
            depth: Depth (m)
            magnitude: Earthquake magnitude

        Returns:
            Stress reduction factor rd
        """
        # Idriss (1999) - depth-dependent with magnitude correction
        if depth <= 34:
            alpha = -1.012 - 1.126 * math.sin(depth / 11.73 + 5.133)
            beta = 0.106 + 0.118 * math.sin(depth / 11.28 + 5.142)
        else:
            alpha = -0.0014
            beta = 0.0

        rd = math.exp(alpha + beta * magnitude)

        # Limit rd to reasonable range
        return max(0.1, min(1.0, rd))

    def calculate_csr(
        self,
        amax: float,
        sigma_v: float,
        sigma_v_eff: float,
        rd: float,
    ) -> float:
        """
        Calculate Cyclic Stress Ratio (CSR).

        CSR = 0.65 * (amax/g) * (sigma_v/sigma_v_eff) * rd

        Args:
            amax: Peak ground acceleration (g)
            sigma_v: Total vertical stress (kPa)
            sigma_v_eff: Effective vertical stress (kPa)
            rd: Stress reduction factor

        Returns:
            Cyclic Stress Ratio
        """
        if sigma_v_eff <= 0:
            return 0.0

        csr = 0.65 * amax * (sigma_v / sigma_v_eff) * rd
        return csr

    def calculate_msf(self, magnitude: float) -> float:
        """
        Calculate Magnitude Scaling Factor (MSF).

        Based on Idriss (1999) for M < 7.5 and Idriss & Boulanger (2008)
        for general case.

        Args:
            magnitude: Earthquake magnitude

        Returns:
            Magnitude Scaling Factor
        """
        # Boulanger & Idriss (2014) MSF
        msf = 6.9 * math.exp(-magnitude / 4) - 0.058

        # Limit MSF to reasonable range
        return max(0.8, min(msf, 2.0))

    def calculate_k_sigma(self, sigma_v_eff: float, n1_60_cs: float = 15) -> float:
        """
        Calculate overburden correction factor K_sigma.

        Based on Boulanger & Idriss (2004).

        Args:
            sigma_v_eff: Effective vertical stress (kPa)
            n1_60_cs: Clean sand equivalent N-value (for estimating C_sigma)

        Returns:
            Overburden correction factor K_sigma
        """
        pa = self.ATMOSPHERIC_PRESSURE

        # C_sigma depends on relative density (approximated from N1_60_cs)
        # C_sigma = 1/(37.3 - 8.27*(N1)60cs^0.264) <= 0.3
        if n1_60_cs > 0:
            c_sigma = 1 / (37.3 - 8.27 * (n1_60_cs ** 0.264))
            c_sigma = min(c_sigma, 0.3)
        else:
            c_sigma = 0.3

        # K_sigma = 1 - C_sigma * ln(sigma'v/Pa) <= 1.0
        if sigma_v_eff > pa:
            k_sigma = 1 - c_sigma * math.log(sigma_v_eff / pa)
        else:
            k_sigma = 1.0

        return max(0.5, min(k_sigma, 1.1))

    # =========================================================================
    # SPT-Based Methods
    # =========================================================================

    def correct_spt_n_value(
        self,
        spt: SPTData,
        sigma_v_eff: float,
    ) -> Tuple[float, float]:
        """
        Apply SPT corrections to get (N1)60 and (N1)60cs.

        Corrections include:
        - CN: Overburden correction
        - CE: Energy ratio correction
        - CB: Borehole diameter correction
        - CR: Rod length correction
        - CS: Sampler correction
        - Fines content adjustment

        Returns:
            Tuple of (N1_60, N1_60_cs)
        """
        n = spt.n_value
        pa = self.ATMOSPHERIC_PRESSURE

        # CN - Overburden correction (Liao & Whitman, 1986 modified)
        # CN = (Pa/sigma'v)^0.5 <= 1.7
        if sigma_v_eff > 0:
            cn = min((pa / sigma_v_eff) ** 0.5, 1.7)
        else:
            cn = 1.7

        # CE - Energy ratio correction (normalize to 60%)
        ce = spt.hammer_energy_ratio / 60.0

        # CB - Borehole diameter correction
        if spt.borehole_diameter <= 115:
            cb = 1.0
        elif spt.borehole_diameter <= 150:
            cb = 1.05
        else:
            cb = 1.15

        # CR - Rod length correction
        if spt.rod_length < 3:
            cr = 0.75
        elif spt.rod_length < 4:
            cr = 0.80
        elif spt.rod_length < 6:
            cr = 0.85
        elif spt.rod_length < 10:
            cr = 0.95
        else:
            cr = 1.0

        # CS - Sampler correction
        cs = 1.0 if spt.sampler_type == "standard" else 1.1

        # Calculate (N1)60
        n1_60 = n * cn * ce * cb * cr * cs

        # Fines content correction for (N1)60cs
        fc = spt.fines_content
        if fc <= 5:
            delta_n = 0
        elif fc <= 35:
            delta_n = math.exp(1.63 + 9.7 / fc - (15.7 / fc) ** 2)
        else:
            delta_n = 5.0

        n1_60_cs = n1_60 + delta_n

        return n1_60, n1_60_cs

    def calculate_crr_spt(self, n1_60_cs: float) -> float:
        """
        Calculate CRR from SPT using Boulanger & Idriss (2014).

        CRR_7.5 = exp[(N1)60cs/14.1 + ((N1)60cs/126)^2
                      - ((N1)60cs/23.6)^3 + ((N1)60cs/25.4)^4 - 2.8]

        Args:
            n1_60_cs: Clean sand equivalent SPT N-value

        Returns:
            CRR for M=7.5 earthquake
        """
        if n1_60_cs <= 0:
            return 0.05

        # Limit N1_60_cs to avoid unrealistic values
        n = min(n1_60_cs, 37.5)

        # Boulanger & Idriss (2014) equation
        crr = math.exp(
            n / 14.1
            + (n / 126) ** 2
            - (n / 23.6) ** 3
            + (n / 25.4) ** 4
            - 2.8
        )

        return min(crr, 2.0)  # Cap at 2.0

    # =========================================================================
    # CPT-Based Methods
    # =========================================================================

    def correct_cpt_values(
        self,
        cpt: CPTData,
        sigma_v: float,
        sigma_v_eff: float,
    ) -> Tuple[float, float, float]:
        """
        Apply CPT corrections to get qc1N, Ic, and qc1Ncs.

        Returns:
            Tuple of (qc1N, Ic, qc1Ncs)
        """
        pa = self.ATMOSPHERIC_PRESSURE
        qc = cpt.qc * 1000  # Convert MPa to kPa
        fs = cpt.fs

        # Normalize cone resistance
        # Cn = (Pa/sigma'v)^m where m varies with soil type
        # Initial estimate with m = 0.5
        if sigma_v_eff > 0:
            cn = min((pa / sigma_v_eff) ** 0.5, 1.7)
        else:
            cn = 1.7

        qc1n = (qc / pa) * cn

        # Friction ratio
        if qc > 0:
            fr = (fs / qc) * 100
        else:
            fr = 0

        # Soil behavior type index Ic
        # Ic = [(3.47 - log(qc1N))^2 + (log(Fr) + 1.22)^2]^0.5
        if qc1n > 0 and fr > 0:
            ic = math.sqrt(
                (3.47 - math.log10(qc1n)) ** 2
                + (math.log10(fr) + 1.22) ** 2
            )
        else:
            ic = 2.6  # Default for clay-like soils

        # Iterate to refine Cn exponent based on Ic
        for _ in range(3):
            if ic <= 1.64:
                m = 0.5
            elif ic >= 2.6:
                m = 1.0
            else:
                m = 0.5 + (ic - 1.64) * (1.0 - 0.5) / (2.6 - 1.64)

            if sigma_v_eff > 0:
                cn = min((pa / sigma_v_eff) ** m, 1.7)
            qc1n = (qc / pa) * cn

            if qc1n > 0 and fr > 0:
                ic = math.sqrt(
                    (3.47 - math.log10(max(qc1n, 1))) ** 2
                    + (math.log10(max(fr, 0.1)) + 1.22) ** 2
                )

        # Fines content correction for qc1Ncs
        if cpt.fines_content is not None:
            fc = cpt.fines_content
        else:
            # Estimate FC from Ic (Robertson & Wride 1998)
            if ic < 1.26:
                fc = 0
            elif ic > 3.5:
                fc = 100
            else:
                fc = 1.75 * ic ** 3.25 - 3.7

        # Delta qc1N for fines content
        if fc <= 5:
            delta_qc1n = 0
        elif fc <= 35:
            delta_qc1n = 11.9 + (qc1n / 14.6) * (1.63 - 9.7 / fc + (15.7 / fc) ** 2)
        else:
            delta_qc1n = 5.0

        qc1n_cs = qc1n + delta_qc1n

        return qc1n, ic, qc1n_cs

    def calculate_crr_cpt(self, qc1n_cs: float) -> float:
        """
        Calculate CRR from CPT using Boulanger & Idriss (2014).

        CRR_7.5 = exp[qc1Ncs/540 + (qc1Ncs/67)^2
                      - (qc1Ncs/80)^3 + (qc1Ncs/114)^4 - 3]

        Args:
            qc1n_cs: Clean sand equivalent normalized CPT tip resistance

        Returns:
            CRR for M=7.5 earthquake
        """
        if qc1n_cs <= 0:
            return 0.05

        # Limit qc1Ncs
        q = min(qc1n_cs, 211)

        # Boulanger & Idriss (2014) equation
        crr = math.exp(
            q / 540
            + (q / 67) ** 2
            - (q / 80) ** 3
            + (q / 114) ** 4
            - 3
        )

        return min(crr, 2.0)

    # =========================================================================
    # Main Analysis Methods
    # =========================================================================

    def calculate_factor_of_safety(
        self,
        crr_7_5: float,
        csr: float,
        msf: float,
        k_sigma: float,
    ) -> float:
        """
        Calculate Factor of Safety against liquefaction.

        FS = (CRR_7.5 * MSF * K_sigma) / CSR

        Returns:
            Factor of Safety (FS < 1.0 indicates liquefaction likely)
        """
        if csr <= 0:
            return 10.0  # No seismic loading

        fs = (crr_7_5 * msf * k_sigma) / csr
        return min(fs, 10.0)

    def get_risk_level(self, fs: float) -> RiskLevel:
        """Determine risk level from Factor of Safety."""
        if fs < 0.5:
            return RiskLevel.VERY_HIGH
        elif fs < 1.0:
            return RiskLevel.HIGH
        elif fs < 1.5:
            return RiskLevel.MODERATE
        else:
            return RiskLevel.LOW

    def analyze_spt(
        self,
        spt: SPTData,
        profile: SoilProfile,
        amax: float,
        magnitude: float,
    ) -> LayerResult:
        """
        Perform liquefaction analysis at SPT test depth.

        Args:
            spt: SPT test data
            profile: Soil profile
            amax: Peak ground acceleration (g)
            magnitude: Earthquake magnitude

        Returns:
            LayerResult with all calculated values
        """
        # Calculate stress state
        stress = self.calculate_stress_state(spt.depth, profile)

        # Calculate CSR
        rd = self.calculate_rd(spt.depth, magnitude)
        csr = self.calculate_csr(amax, stress.sigma_v, stress.sigma_v_eff, rd)

        # Correct SPT values and calculate CRR
        n1_60, n1_60_cs = self.correct_spt_n_value(spt, stress.sigma_v_eff)
        crr = self.calculate_crr_spt(n1_60_cs)

        # Calculate correction factors
        msf = self.calculate_msf(magnitude)
        k_sigma = self.calculate_k_sigma(stress.sigma_v_eff, n1_60_cs)

        # Calculate Factor of Safety
        fs = self.calculate_factor_of_safety(crr, csr, msf, k_sigma)

        return LayerResult(
            depth=spt.depth,
            sigma_v=stress.sigma_v,
            sigma_v_eff=stress.sigma_v_eff,
            rd=rd,
            csr=csr,
            n1_60_cs=n1_60_cs,
            qc1n_cs=None,
            crr=crr,
            msf=msf,
            k_sigma=k_sigma,
            factor_of_safety=fs,
            risk_level=self.get_risk_level(fs),
            test_type="SPT",
        )

    def analyze_cpt(
        self,
        cpt: CPTData,
        profile: SoilProfile,
        amax: float,
        magnitude: float,
    ) -> Optional[LayerResult]:
        """
        Perform liquefaction analysis at CPT test depth.

        Args:
            cpt: CPT test data
            profile: Soil profile
            amax: Peak ground acceleration (g)
            magnitude: Earthquake magnitude

        Returns:
            LayerResult or None if soil is clay-like (Ic > 2.6)
        """
        # Calculate stress state
        stress = self.calculate_stress_state(cpt.depth, profile)

        # Correct CPT values
        qc1n, ic, qc1n_cs = self.correct_cpt_values(
            cpt, stress.sigma_v, stress.sigma_v_eff
        )

        # Check if soil is clay-like (not susceptible to liquefaction)
        if ic > 2.6:
            return None

        # Calculate CSR
        rd = self.calculate_rd(cpt.depth, magnitude)
        csr = self.calculate_csr(amax, stress.sigma_v, stress.sigma_v_eff, rd)

        # Calculate CRR
        crr = self.calculate_crr_cpt(qc1n_cs)

        # Calculate correction factors
        msf = self.calculate_msf(magnitude)
        k_sigma = self.calculate_k_sigma(stress.sigma_v_eff, qc1n_cs / 10)

        # Calculate Factor of Safety
        fs = self.calculate_factor_of_safety(crr, csr, msf, k_sigma)

        return LayerResult(
            depth=cpt.depth,
            sigma_v=stress.sigma_v,
            sigma_v_eff=stress.sigma_v_eff,
            rd=rd,
            csr=csr,
            n1_60_cs=None,
            qc1n_cs=qc1n_cs,
            crr=crr,
            msf=msf,
            k_sigma=k_sigma,
            factor_of_safety=fs,
            risk_level=self.get_risk_level(fs),
            test_type="CPT",
        )

    def calculate_lpi(self, layer_results: List[LayerResult]) -> float:
        """
        Calculate Liquefaction Potential Index (LPI).

        Based on Iwasaki et al. (1978, 1982).
        LPI = integral from 0 to 20m of F(z) * w(z) dz

        Where:
            F(z) = 1 - FS if FS < 1, else 0
            w(z) = 10 - 0.5*z (depth weighting)

        Returns:
            LPI value (0 = low risk, >15 = high risk)
        """
        lpi = 0.0

        for result in layer_results:
            if result.depth > 20:
                continue

            if result.factor_of_safety < 1.0:
                f_z = 1 - result.factor_of_safety
            else:
                f_z = 0

            w_z = 10 - 0.5 * result.depth
            w_z = max(w_z, 0)

            # Approximate integration with 1m intervals
            lpi += f_z * w_z * 1.0

        return lpi

    def analyze_profile(
        self,
        profile: SoilProfile,
        amax: float,
        magnitude: float,
    ) -> Tuple[List[LayerResult], LiquefactionRisk]:
        """
        Analyze complete soil profile for liquefaction potential.

        Args:
            profile: Soil profile with test data
            amax: Peak ground acceleration (g)
            magnitude: Earthquake magnitude

        Returns:
            Tuple of (layer_results, risk_assessment)
        """
        layer_results: List[LayerResult] = []

        # Analyze SPT data
        for spt in profile.spt_data:
            result = self.analyze_spt(spt, profile, amax, magnitude)
            layer_results.append(result)

        # Analyze CPT data
        for cpt in profile.cpt_data:
            result = self.analyze_cpt(cpt, profile, amax, magnitude)
            if result:  # Skip clay-like soils
                layer_results.append(result)

        # Sort by depth
        layer_results.sort(key=lambda x: x.depth)

        # Calculate overall risk
        if layer_results:
            min_fs = min(r.factor_of_safety for r in layer_results)
            critical_depth = next(
                r.depth for r in layer_results if r.factor_of_safety == min_fs
            )
            lpi = self.calculate_lpi(layer_results)
        else:
            min_fs = 10.0
            critical_depth = 0.0
            lpi = 0.0

        liquefaction_likely = min_fs < 1.0

        # Generate recommendation
        risk_level = self.get_risk_level(min_fs)
        if risk_level == RiskLevel.VERY_HIGH:
            recommendation = (
                "CRITICAL: Very high liquefaction risk. Immediate ground improvement "
                "or foundation redesign required. Consider deep foundations, "
                "ground densification, or drainage solutions."
            )
        elif risk_level == RiskLevel.HIGH:
            recommendation = (
                "WARNING: High liquefaction risk. Ground improvement measures "
                "strongly recommended. Evaluate stone columns, vibro-compaction, "
                "or jet grouting options."
            )
        elif risk_level == RiskLevel.MODERATE:
            recommendation = (
                "CAUTION: Moderate liquefaction risk. Consider site-specific "
                "analysis and potential mitigation measures. Monitor during "
                "seismic events."
            )
        else:
            recommendation = (
                "LOW RISK: Liquefaction is unlikely at this site under the "
                "analyzed conditions. Standard foundation design may proceed."
            )

        risk_assessment = LiquefactionRisk(
            overall_fs=min_fs,
            overall_risk=risk_level,
            lpi=lpi,
            critical_depth=critical_depth,
            liquefaction_likely=liquefaction_likely,
            recommendation=recommendation,
        )

        return layer_results, risk_assessment
