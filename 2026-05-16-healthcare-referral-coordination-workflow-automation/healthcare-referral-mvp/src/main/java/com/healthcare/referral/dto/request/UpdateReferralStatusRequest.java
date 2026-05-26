package com.healthcare.referral.dto.request;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class UpdateReferralStatusRequest {

    @NotBlank
    private String status;

    private String notes;
    private String performedBy;
    private String appointmentId;
    private String appointmentDatetime;
    private String priorAuthNumber;
    private String consultNoteContent;
}