"""
SPDX License Risk Tier Classification
Based on copyleft strength and commercial use implications
"""
from typing import Dict, Tuple


# Risk tier constants
TIER_HIGH = "high"        # Strong copyleft - requires source disclosure
TIER_MEDIUM = "medium"    # Weak copyleft - limited viral effect
TIER_LOW = "low"          # Permissive - minimal restrictions
TIER_UNKNOWN = "unknown"  # Unidentified license


# SPDX identifier -> (risk_tier, description)
LICENSE_TAXONOMY: Dict[str, Tuple[str, str]] = {
    # HIGH RISK - Strong copyleft
    "GPL-1.0-only": (TIER_HIGH, "GNU GPL v1 - Strong copyleft"),
    "GPL-1.0-or-later": (TIER_HIGH, "GNU GPL v1+ - Strong copyleft"),
    "GPL-2.0-only": (TIER_HIGH, "GNU GPL v2 - Strong copyleft, must release source"),
    "GPL-2.0-or-later": (TIER_HIGH, "GNU GPL v2+ - Strong copyleft"),
    "GPL-3.0-only": (TIER_HIGH, "GNU GPL v3 - Strong copyleft + patent clauses"),
    "GPL-3.0-or-later": (TIER_HIGH, "GNU GPL v3+ - Strong copyleft"),
    "AGPL-3.0-only": (TIER_HIGH, "GNU AGPL v3 - Network use triggers source disclosure"),
    "AGPL-3.0-or-later": (TIER_HIGH, "GNU AGPL v3+ - Strongest copyleft"),
    "SSPL-1.0": (TIER_HIGH, "Server Side Public License - Service deployment triggers"),
    "BUSL-1.1": (TIER_HIGH, "Business Source License - Production use restricted"),
    "CC-BY-SA-4.0": (TIER_HIGH, "Creative Commons SA - ShareAlike applies to code"),
    "OSL-3.0": (TIER_HIGH, "Open Software License 3.0 - Strong copyleft"),
    "EUPL-1.2": (TIER_MEDIUM, "European Union Public License"),
    
    # MEDIUM RISK - Weak copyleft
    "LGPL-2.0-only": (TIER_MEDIUM, "GNU LGPL v2 - Library copyleft"),
    "LGPL-2.0-or-later": (TIER_MEDIUM, "GNU LGPL v2+"),
    "LGPL-2.1-only": (TIER_MEDIUM, "GNU LGPL v2.1 - Library copyleft"),
    "LGPL-2.1-or-later": (TIER_MEDIUM, "GNU LGPL v2.1+"),
    "LGPL-3.0-only": (TIER_MEDIUM, "GNU LGPL v3 - Library copyleft"),
    "LGPL-3.0-or-later": (TIER_MEDIUM, "GNU LGPL v3+"),
    "MPL-1.0": (TIER_MEDIUM, "Mozilla Public License 1.0 - File-level copyleft"),
    "MPL-1.1": (TIER_MEDIUM, "Mozilla Public License 1.1"),
    "MPL-2.0": (TIER_MEDIUM, "Mozilla Public License 2.0 - File-level copyleft"),
    "CDDL-1.0": (TIER_MEDIUM, "Common Development Distribution License"),
    "EPL-1.0": (TIER_MEDIUM, "Eclipse Public License 1.0 - Plugin copyleft"),
    "EPL-2.0": (TIER_MEDIUM, "Eclipse Public License 2.0"),
    "EUPL-1.1": (TIER_MEDIUM, "European Union Public License 1.1"),
    "CECILL-2.1": (TIER_MEDIUM, "CeCILL License - French GPL-compatible"),
    
    # LOW RISK - Permissive
    "MIT": (TIER_LOW, "MIT License - Highly permissive"),
    "MIT-0": (TIER_LOW, "MIT No Attribution"),
    "Apache-2.0": (TIER_LOW, "Apache License 2.0 - Permissive with patent grant"),
    "BSD-2-Clause": (TIER_LOW, "BSD 2-Clause - Permissive"),
    "BSD-3-Clause": (TIER_LOW, "BSD 3-Clause - Permissive, no endorsement"),
    "BSD-4-Clause": (TIER_LOW, "BSD 4-Clause - Advertising clause"),
    "ISC": (TIER_LOW, "ISC License - Functionally equivalent to MIT"),
    "Zlib": (TIER_LOW, "zlib License - Permissive"),
    "Unlicense": (TIER_LOW, "The Unlicense - Public domain dedication"),
    "CC0-1.0": (TIER_LOW, "CC0 1.0 Universal - Public domain"),
    "WTFPL": (TIER_LOW, "Do What The F*ck You Want"),
    "0BSD": (TIER_LOW, "BSD Zero Clause"),
    "PSF-2.0": (TIER_LOW, "Python Software Foundation License"),
    "Python-2.0": (TIER_LOW, "Python 2.0 License"),
    "Artistic-2.0": (TIER_LOW, "Artistic License 2.0"),
    "BSL-1.0": (TIER_LOW, "Boost Software License 1.0"),
    "curl": (TIER_LOW, "curl License"),
    "libtiff": (TIER_LOW, "libtiff License"),
    "MIT-Modern-Variant": (TIER_LOW, "MIT Modern Variant"),
    "PostgreSQL": (TIER_LOW, "PostgreSQL License"),
    "OFL-1.1": (TIER_LOW, "SIL Open Font License 1.1"),
}

# Aliases and common variations
LICENSE_ALIASES: Dict[str, str] = {
    "GPL-2.0": "GPL-2.0-only",
    "GPL-3.0": "GPL-3.0-only",
    "LGPL-2.1": "LGPL-2.1-only",
    "LGPL-3.0": "LGPL-3.0-only",
    "AGPL-3.0": "AGPL-3.0-only",
    "MIT License": "MIT",
    "Apache 2.0": "Apache-2.0",
    "Apache License 2.0": "Apache-2.0",
    "BSD": "BSD-3-Clause",
}

# Risk tier ordering for severity (highest first)
RISK_TIER_ORDER = [TIER_HIGH, TIER_MEDIUM, TIER_LOW, TIER_UNKNOWN]

# Recommendations per tier
TIER_RECOMMENDATIONS = {
    TIER_HIGH: "BLOCK: This code matches a strong copyleft license. Using it may require you to open-source your entire codebase. Seek legal review immediately.",
    TIER_MEDIUM: "WARN: This code matches a weak copyleft license. File-level or library-level disclosure may be required. Review with your legal team.",
    TIER_LOW: "INFO: This code matches a permissive license. Attribution may be required. Low legal risk.",
    TIER_UNKNOWN: "REVIEW: License could not be determined. Manual review required before use in production.",
    "clean": "CLEAN: No license contamination detected. Safe to use.",
}


def classify_license(spdx_id: str) -> Tuple[str, str]:
    """Returns (risk_tier, description) for a given SPDX identifier."""
    # Try direct lookup
    if spdx_id in LICENSE_TAXONOMY:
        return LICENSE_TAXONOMY[spdx_id]
    
    # Try aliases
    canonical = LICENSE_ALIASES.get(spdx_id)
    if canonical and canonical in LICENSE_TAXONOMY:
        return LICENSE_TAXONOMY[canonical]
    
    return TIER_UNKNOWN, f"Unknown license: {spdx_id}"


def get_highest_risk_tier(tiers: list) -> str:
    """Returns the highest (most severe) risk tier from a list."""
    for tier in RISK_TIER_ORDER:
        if tier in tiers:
            return tier
    return "clean"