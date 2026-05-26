package com.healthcare.referral.dto.request;

import com.healthcare.referral.domain.enums.ReferralPriority;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class CreateReferralRequest {

    @NotBlank(message = "Patient external ID is required")
    private String patientExternalId;

    private String referringProviderNpi;

    @NotBlank(message = "Specialty needed is required")
    private String specialtyNeeded;

    private String specialtyCode;

    @NotBlank(message = "Reason for referral is required")
    private String reasonForReferral;

    private String clinicalNotes;
    private String diagnosisCodes;
    private String procedureCodes;

    @NotNull(message = "Priority is required")
    private ReferralPriority priority = ReferralPriority.ROUTINE;

    private String emrOrderId;
    private String sourceSystem;
    private String fhirServiceRequestId;

    // Override insurance (defaults to patient's insurance)
    private String insurancePayerId;
    private String insuranceMemberId;
}