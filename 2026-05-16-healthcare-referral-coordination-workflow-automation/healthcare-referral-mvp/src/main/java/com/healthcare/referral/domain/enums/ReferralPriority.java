package com.healthcare.referral.domain.enums;

public enum ReferralPriority {
    STAT,      // Same day / emergency
    URGENT,    // Within 24-48 hours
    ROUTINE,   // Standard 2-4 weeks
    ELECTIVE   // Patient convenience scheduling
}