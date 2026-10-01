"""Summary and source analytics computations for ThermalIntel Phase 4.

Provides mathematical aggregations, KPI calculations, and source distribution
analytics compliant with frozen SummaryResponse and SourcesResponse schemas.
"""

from typing import List, Dict, Optional, Tuple
from services.api.schemas.common import RiskLevel, SourceType, DataMode
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.summary import SourceBreakdown

# Standard labels and drivers matching frozen specification
SOURCE_METADATA: Dict[SourceType, Tuple[str, str]] = {
    SourceType.WILDFIRE: (
        "Wildfire / Forest Fire",
        "Vegetative dry fuel & wind propagation",
    ),
    SourceType.INDUSTRIAL: (
        "Industrial Facility / Flare Stack",
        "Petrochemical, refining, & gas processing",
    ),
    SourceType.AGRICULTURAL: (
        "Agricultural Residue Burn",
        "Seasonal crop clearing & stubble combustion",
    ),
    SourceType.PRESCRIBED_BURN: (
        "Controlled / Prescribed Burn",
        "Managed land conservation fuel reduction",
    ),
    SourceType.URBAN: (
        "Urban Structural / Heat Anomaly",
        "High thermal mass, roofing, or localized structural fire",
    ),
    SourceType.VOLCANIC: (
        "Volcanic / Geothermal Activity",
        "Magmatic effusion & geothermal vents",
    ),
    SourceType.UNKNOWN: (
        "Unclassified Thermal Signature",
        "Undergoing multi-spectral model verification",
    ),
}


class SummaryAnalytics:
    """Performs deterministic KPI calculations and distribution metrics."""

    @staticmethod
    def classify_risk_tier(hotspot: Hotspot) -> RiskLevel:
        """Deterministically assign a hotspot to exactly one of the four severity tiers."""
        # Risk level enum takes precedence if valid; fallback to numerical score
        if hotspot.risk_level == RiskLevel.CRITICAL or hotspot.risk_score >= 75.0:
            return RiskLevel.CRITICAL
        elif hotspot.risk_level == RiskLevel.HIGH or hotspot.risk_score >= 50.0:
            return RiskLevel.HIGH
        elif hotspot.risk_level == RiskLevel.MEDIUM or hotspot.risk_score >= 25.0:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    @classmethod
    def compute_kpis(
        cls,
        hotspots: List[Hotspot],
        active_alerts_count: int = 0,
    ) -> Dict[str, object]:
        """Compute high-level summary KPIs.
        
        Guarantees internal consistency:
            total_active_hotspots == critical + high + medium + low
        """
        total = len(hotspots)
        if total == 0:
            return {
                "total_active_hotspots": 0,
                "critical_risk_count": 0,
                "high_risk_count": 0,
                "medium_risk_count": 0,
                "low_risk_count": 0,
                "active_alerts_count": active_alerts_count,
                "average_frp": 0.0,
                "max_frp": 0.0,
                "average_risk_score": 0.0,
                "dominant_source": SourceType.UNKNOWN,
                "source_counts": {},
                "recent_critical_hotspots": [],
            }

        critical_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0

        total_frp = 0.0
        max_frp = 0.0
        total_risk = 0.0
        source_counts: Dict[str, int] = {}

        for h in hotspots:
            tier = cls.classify_risk_tier(h)
            if tier == RiskLevel.CRITICAL:
                critical_count += 1
            elif tier == RiskLevel.HIGH:
                high_count += 1
            elif tier == RiskLevel.MEDIUM:
                medium_count += 1
            else:
                low_count += 1

            total_frp += h.frp
            if h.frp > max_frp:
                max_frp = h.frp
            total_risk += h.risk_score

            st_val = h.source_type.value
            source_counts[st_val] = source_counts.get(st_val, 0) + 1

        avg_frp = round(total_frp / total, 2)
        avg_risk = round(total_risk / total, 1)
        max_frp = round(max_frp, 2)

        # Dominant source calculation
        dominant_source_str = max(source_counts.items(), key=lambda x: (x[1], x[0]))[0]
        try:
            dominant_source = SourceType(dominant_source_str)
        except ValueError:
            dominant_source = SourceType.UNKNOWN

        # Top critical and high risk hotspots
        high_crit_hotspots = [
            h for h in hotspots if cls.classify_risk_tier(h) in (RiskLevel.CRITICAL, RiskLevel.HIGH)
        ]
        high_crit_hotspots.sort(key=lambda h: (-h.risk_score, -h.frp, h.id))
        recent_critical = high_crit_hotspots[:5]

        return {
            "total_active_hotspots": total,
            "critical_risk_count": critical_count,
            "high_risk_count": high_count,
            "medium_risk_count": medium_count,
            "low_risk_count": low_count,
            "active_alerts_count": active_alerts_count,
            "average_frp": avg_frp,
            "max_frp": max_frp,
            "average_risk_score": avg_risk,
            "dominant_source": dominant_source,
            "source_counts": source_counts,
            "recent_critical_hotspots": recent_critical,
        }

    @classmethod
    def compute_source_breakdown(
        cls, hotspots: List[Hotspot]
    ) -> Tuple[List[SourceBreakdown], int, SourceType]:
        """Compute source distribution breakdowns and dominant source."""
        total = len(hotspots)
        if total == 0:
            return [], 0, SourceType.UNKNOWN

        grouped: Dict[SourceType, List[Hotspot]] = {}
        for h in hotspots:
            grouped.setdefault(h.source_type, []).append(h)

        breakdowns: List[SourceBreakdown] = []
        for source_type, items in grouped.items():
            count = len(items)
            pct = round((count / total) * 100.0, 1)
            avg_frp = round(sum(h.frp for h in items) / count, 2)
            avg_risk = round(sum(h.risk_score for h in items) / count, 1)

            display_name, driver = SOURCE_METADATA.get(
                source_type, (source_type.value.title(), "Thermal radiance signature")
            )

            breakdowns.append(
                SourceBreakdown(
                    source_type=source_type,
                    display_name=display_name,
                    count=count,
                    percentage=pct,
                    average_frp=avg_frp,
                    average_risk=avg_risk,
                    primary_driver=driver,
                )
            )

        # Sort breakdowns deterministically: highest count first, then highest average_risk
        breakdowns.sort(key=lambda b: (-b.count, -b.average_risk, b.source_type.value))

        dominant = breakdowns[0].source_type if breakdowns else SourceType.UNKNOWN
        return breakdowns, total, dominant
