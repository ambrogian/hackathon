"""Inspection rules. Every threshold is a named constant; edit here.

NETA MTS Table 100.18 delta-T tiers (similar components) as reported by secondary sources
(ITC study guide, Fluke table copy, Eaton). Action wording differs between sources and the
standard itself was not read: verify against the current edition before any real-world use.
"""
TIERS = [  # (min delta-T in deg C, key, action); order = severity, highest first
    (15.0, "critical", "Major discrepancy: repair immediately"),
    (4.0, "probable", "Probable deficiency: repair as time permits"),
    (1.0, "possible", "Possible deficiency: investigate, recheck next quarter"),
]
SEVERITY = ["none", "possible", "probable", "critical"]
FAULT_MIN_DT = 4.0     # deg C: probable tier and above counts as a thermal fault
MIN_LOAD_PCT = 40.0    # assumption from a secondary source: thermal criteria invalid below this load
COH_DETECT = 0.04      # coherent-power fraction: acoustic source present (set from noise-only runs)
KURT_IMPULSIVE = 6.0   # beamformed kurtosis above this: crackle, not hiss
COLOC_DEG = 10.0       # acoustic peak within this angle of the hottest lug: same defect


def tier(dt):
    for lo, key, action in TIERS:
        if dt >= lo:
            return key, action
    return "none", "Normal"
