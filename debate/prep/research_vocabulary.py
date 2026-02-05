"""Research vocabulary for combinatorial task expansion.

These terms are used to create variants of base research tasks,
giving SearchAgent multiple angles to explore for each argument.
"""

# Impact scenarios that commonly appear in debate evidence
IMPACT_TRIGGERS_NEGATIVE = [
    "nuclear escalation",
    "economic recession",
    "terrorism",
    "cyberattacks",
    "unemployment",
    "food insecurity",
    "supply chain collapse",
    "financial crisis",
    "refugee crisis",
    "pandemic outbreak",
]

IMPACT_TRIGGERS_POSITIVE = [
    "job creation",
    "technological innovation",
    "poverty reduction",
    "healthcare access",
    "educational opportunity",
    "environmental restoration",
    "diplomatic cooperation",
    "trade expansion",
    "energy independence",
    "infrastructure development",
]

# Core debate concepts
CORE_CONCEPTS = [
    "national security",
    "privacy rights",
    "economic growth",
    "democracy",
    "free speech",
    "human rights",
    "public health",
    "social equity",
    "civil liberties",
    "consumer protection",
]

# Geographic regions to narrow research scope
REGIONS = [
    "Sub-Saharan Africa",
    "Middle East",
    "Latin America",
    "East Asia",
    "South Asia",
    "Eastern Europe",
    "Southeast Asia",
    "Central America",
    "Pacific Islands",
    "North Africa",
]

# Evidence sources (mix of specific and general)
SOURCES_SPECIFIC = [
    "Harvard study",
    "Brookings Institution",
    "World Bank data",
    "IMF analysis",
    "RAND Corporation",
]

SOURCES_GENERAL = [
    "expert analysis",
    "economic data",
    "case studies",
    "empirical evidence",
    "government reports",
]

# Combined vocabulary for random selection
ALL_TERMS = (
    IMPACT_TRIGGERS_NEGATIVE + IMPACT_TRIGGERS_POSITIVE + CORE_CONCEPTS + REGIONS + SOURCES_SPECIFIC + SOURCES_GENERAL
)
