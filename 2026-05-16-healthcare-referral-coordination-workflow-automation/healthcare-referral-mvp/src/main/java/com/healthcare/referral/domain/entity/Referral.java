package com.healthcare.referral.domain.entity;

import com.healthcare.referral.domain.enums.ReferralPriority;
import com.healthcare.referral.domain.enums.ReferralStatus;
import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

@Entity
@Table(name = "referrals")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Referral {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "referral_number", unique = true, nullable = false)
    private String referralNumber;

    @Column(name = "fhir_service_request_id")
    private String fhirServiceRequestId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ReferralStatus status = ReferralStatus.NEW;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ReferralPriority priority = ReferralPriority.ROUTINE;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "patient_id", nullable = false)
    private Patient patient;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "referring_provider_id")
    private ReferringProvider referringProvider;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "assigned_provider_id")
    private Provider assignedProvider;

    @Column(name = "specialty_needed", nullable = false)
    private String specialtyNeeded;

    @Column(name = "specialty_code")
    private String specialtyCode;

    @Column(name = "reason_for_referral", nullable = false, columnDefinition = "TEXT")
    private String reasonForReferral;

    @Column(name = "clinical_notes", columnDefinition = "TEXT")
    private String clinicalNotes;

    @Column(name = "diagnosis_codes")
    private String diagnosisCodes;

    @Column(name = "procedure_codes")
    private String procedureCodes;

    @Column(name = "insurance_payer_id")
    private String insurancePayerId;

    @Column(name = "insurance_member_id")
    private String insuranceMemberId;

    @Column(name = "prior_auth_required")
    private Boolean priorAuthRequired = false;

    @Column(name = "prior_auth_number")
    private String priorAuthNumber;

    @Column(name = "prior_auth_status")
    private String priorAuthStatus;

    @Column(name = "prior_auth_submitted_at")
    private LocalDateTime priorAuthSubmittedAt;

    @Column(name = "prior_auth_decision_at")
    private LocalDateTime priorAuthDecisionAt;

    @Column(name = "appointment_id")
    private String appointmentId;

    @Column(name = "appointment_datetime")
    private LocalDateTime appointmentDatetime;

    @Column(name = "appointment_status")
    private String appointmentStatus;

    @Column(name = "emr_order_id")
    private String emrOrderId;

    @Column(name = "source_system")
    private String sourceSystem;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @Column(name = "completed_at")
    private LocalDateTime completedAt;

    @Column(name = "due_date")
    private LocalDate dueDate;

    @Column(name = "patient_notified_at")
    private LocalDateTime patientNotifiedAt;

    @Column(name = "patient_confirmed_at")
    private LocalDateTime patientConfirmedAt;

    @Column(name = "specialist_sent_at")
    private LocalDateTime specialistSentAt;

    @Column(name = "consult_note_received_at")
    private LocalDateTime consultNoteReceivedAt;

    @Column(name = "matching_attempts")
    private Integer matchingAttempts = 0;

    @Column(name = "notification_attempts")
    private Integer notificationAttempts = 0;

    @OneToMany(mappedBy = "referral", fetch = FetchType.LAZY, cascade = CascadeType.ALL)
    private List<ReferralStateHistory> stateHistory;

    @OneToMany(mappedBy = "referral", fetch = FetchType.LAZY, cascade = CascadeType.ALL)
    private List<CommunicationLog> communicationLogs;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}