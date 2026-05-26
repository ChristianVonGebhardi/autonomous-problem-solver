package com.healthcare.referral.domain.enums;

/**
 * 12-state referral lifecycle states.
 * Mirrors the state machine transitions for the full referral workflow.
 */
public enum ReferralStatus {
    /** New referral order received from EMR */
    NEW,
    /** Referral received and being processed */
    RECEIVED,
    /** Finding appropriate specialist based on insurance/location */
    MATCHING,
    /** Specialist matched, waiting prior auth if required */
    MATCHED,
    /** Prior authorization submitted to payer */
    PRIOR_AUTH_SUBMITTED,
    /** Prior authorization approved */
    PRIOR_AUTH_APPROVED,
    /** Prior authorization denied */
    PRIOR_AUTH_DENIED,
    /** Referral packet sent to specialist office */
    SENT_TO_SPECIALIST,
    /** Patient has been notified and outreach in progress */
    PATIENT_NOTIFIED,
    /** Appointment scheduled with specialist */
    APPOINTMENT_SCHEDULED,
    /** Patient seen by specialist, awaiting consult note */
    APPOINTMENT_COMPLETED,
    /** Consult note received, referral complete */
    COMPLETED,
    /** Referral cancelled */
    CANCELLED,
    /** Referral failed/expired without completion */
    FAILED
}