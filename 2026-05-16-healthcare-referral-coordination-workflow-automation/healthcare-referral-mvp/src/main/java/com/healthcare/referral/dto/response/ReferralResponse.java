package com.healthcare.referral.dto.response;

import com.healthcare.referral.domain.enums.ReferralPriority;
import com.healthcare.referral.domain.enums.ReferralStatus;
import lombok.Data;
import lombok.Builder;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ReferralResponse {

    private Long id;
    private String referralNumber;
    private String fhirServiceRequestId;
    private ReferralStatus status;
    private ReferralPriority priority;

    private PatientSummary patient;
    private ProviderSummary referringProvider;
    private ProviderSummary assignedProvider;

    private String specialtyNeeded;
    private String specialtyCode;
    private String reasonForReferral;
    private String clinicalNotes;
    private String diagnosisCodes;
    private String procedureCodes;

    private String insurancePayerId;
    private String insuranceMemberId;
    private Boolean priorAuthRequired;
    private String priorAuthNumber;
    private String priorAuthStatus;
    private LocalDateTime priorAuthSubmittedAt;
    private LocalDateTime priorAuthDecisionAt;

    private String appointmentId;
    private LocalDateTime appointmentDatetime;
    private String appointmentStatus;

    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    private LocalDateTime completedAt;
    private LocalDate dueDate;

    private LocalDateTime patientNotifiedAt;
    private LocalDateTime patientConfirmedAt;
    private LocalDateTime specialistSentAt;
    private LocalDateTime consultNoteReceivedAt;

    private Integer matchingAttempts;
    private Integer notificationAttempts;

    private List<StateHistoryEntry> stateHistory;
    private List<CommunicationEntry> recentCommunications;

    // Computed fields
    private Long daysOpen;
    private String statusLabel;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class PatientSummary {
        private Long id;
        private String externalId;
        private String fullName;
        private String dateOfBirth;
        private String phone;
        private String email;
        private String insurancePayerId;
        private String insurancePlanName;
        private String insuranceMemberId;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ProviderSummary {
        private Long id;
        private String npi;
        private String fullName;
        private String specialty;
        private String practiceName;
        private String phone;
        private String city;
        private String stateAbbr;
        private Integer averageWaitDays;
        private Boolean portalEnabled;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class StateHistoryEntry {
        private String fromStatus;
        private String toStatus;
        private String transitionEvent;
        private String notes;
        private String performedBy;
        private LocalDateTime performedAt;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class CommunicationEntry {
        private String channel;
        private String recipientType;
        private String subject;
        private String status;
        private LocalDateTime sentAt;
    }
}