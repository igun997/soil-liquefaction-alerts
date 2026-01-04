"""
Soil data models for SPT and CPT test data.
Based on Boulanger & Idriss (2014) methodology.
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class SoilLayer(BaseModel):
    """Individual soil layer properties."""

    depth_top: float = Field(..., ge=0, description="Top depth of layer (m)")
    depth_bottom: float = Field(..., gt=0, description="Bottom depth of layer (m)")
    unit_weight: float = Field(
        default=18.0, ge=10, le=25, description="Total unit weight (kN/m³)"
    )
    fines_content: float = Field(
        default=5.0, ge=0, le=100, description="Fines content FC (%)"
    )
    plasticity_index: Optional[float] = Field(
        default=None, ge=0, le=100, description="Plasticity Index PI (%)"
    )
    soil_type: Optional[str] = Field(
        default=None, description="Soil classification (e.g., SP, SM, ML)"
    )

    @property
    def thickness(self) -> float:
        """Layer thickness in meters."""
        return self.depth_bottom - self.depth_top

    @property
    def mid_depth(self) -> float:
        """Mid-point depth of layer."""
        return (self.depth_top + self.depth_bottom) / 2


class SPTData(BaseModel):
    """Standard Penetration Test (SPT) data at a specific depth."""

    depth: float = Field(..., ge=0, description="Test depth (m)")
    n_value: int = Field(..., ge=0, le=100, description="Raw SPT N-value (blows/ft)")
    hammer_energy_ratio: float = Field(
        default=60.0,
        ge=30,
        le=100,
        description="Hammer energy ratio ER (%)",
    )
    borehole_diameter: float = Field(
        default=100.0, description="Borehole diameter (mm)"
    )
    rod_length: float = Field(default=10.0, ge=0, description="Rod length (m)")
    sampler_type: Literal["standard", "non_standard"] = Field(
        default="standard", description="Sampler type"
    )
    fines_content: float = Field(
        default=5.0, ge=0, le=100, description="Fines content FC (%)"
    )


class CPTData(BaseModel):
    """Cone Penetration Test (CPT) data at a specific depth."""

    depth: float = Field(..., ge=0, description="Test depth (m)")
    qc: float = Field(..., ge=0, description="Cone tip resistance qc (MPa)")
    fs: float = Field(default=0.0, ge=0, description="Sleeve friction fs (kPa)")
    u2: float = Field(default=0.0, description="Pore pressure u2 (kPa)")
    fines_content: Optional[float] = Field(
        default=None, ge=0, le=100, description="Fines content FC (%) if known"
    )

    @property
    def friction_ratio(self) -> float:
        """Friction ratio Rf (%)."""
        if self.qc > 0:
            return (self.fs / (self.qc * 1000)) * 100
        return 0.0

    @property
    def qt(self) -> float:
        """Corrected cone tip resistance qt (MPa)."""
        # Assuming a = 0.8 for typical cone
        a = 0.8
        return self.qc + self.u2 * (1 - a) / 1000


class SoilProfile(BaseModel):
    """Complete soil profile with layers and test data."""

    name: str = Field(default="Site Profile", description="Profile name/ID")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude")
    groundwater_depth: float = Field(
        default=2.0, ge=0, description="Groundwater table depth (m)"
    )
    layers: List[SoilLayer] = Field(default_factory=list, description="Soil layers")
    spt_data: List[SPTData] = Field(default_factory=list, description="SPT test data")
    cpt_data: List[CPTData] = Field(default_factory=list, description="CPT test data")

    @property
    def max_depth(self) -> float:
        """Maximum investigation depth."""
        depths = []
        if self.layers:
            depths.append(max(layer.depth_bottom for layer in self.layers))
        if self.spt_data:
            depths.append(max(spt.depth for spt in self.spt_data))
        if self.cpt_data:
            depths.append(max(cpt.depth for cpt in self.cpt_data))
        return max(depths) if depths else 0.0

    def get_unit_weight_at_depth(self, depth: float) -> float:
        """Get unit weight at a specific depth."""
        for layer in self.layers:
            if layer.depth_top <= depth < layer.depth_bottom:
                return layer.unit_weight
        # Default unit weight if no layer defined
        return 18.0

    def get_fines_content_at_depth(self, depth: float) -> float:
        """Get fines content at a specific depth."""
        for layer in self.layers:
            if layer.depth_top <= depth < layer.depth_bottom:
                return layer.fines_content
        return 5.0  # Default clean sand
