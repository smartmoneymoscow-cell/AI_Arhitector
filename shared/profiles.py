"""
shared/profiles.py — L11: Pipeline profile validation.

Validates that pipeline_profile is one of the known values.
Returns 400 error instead of silently falling back to default.
"""

from fastapi import HTTPException

VALID_PROFILES = {
    "quick",
    "standard",
    "full",
    "premium",
    "interior",
    "presentation",
    "electrical",
    "bathhouse",
    "landscape",
    "mep_documentation",
    "interior_full",
}

VALID_QUALITIES = {
    "preview",
    "standard",
    "high",
    "ultra",
    "16k",
}


def validate_pipeline_profile(profile: str) -> str:
    """L11: Validate pipeline profile. Returns profile or raises 400."""
    if profile not in VALID_PROFILES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_pipeline_profile",
                "message": f"Unknown profile: '{profile}'",
                "valid_profiles": sorted(VALID_PROFILES),
                "received": profile,
            },
        )
    return profile


def validate_quality(quality: str) -> str:
    """Validate quality setting. Returns quality or raises 400."""
    if quality not in VALID_QUALITIES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_quality",
                "message": f"Unknown quality: '{quality}'",
                "valid_qualities": sorted(VALID_QUALITIES),
                "received": quality,
            },
        )
    return quality
