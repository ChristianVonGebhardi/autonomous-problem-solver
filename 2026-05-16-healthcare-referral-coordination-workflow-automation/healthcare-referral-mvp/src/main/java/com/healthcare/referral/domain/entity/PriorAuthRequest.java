package com.healthcare.referral.domain.entity;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Entity
@Table(name = "prior_auth_requests")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PriorAuthRequest {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "referral_id", nullable = false)
    private Referral referral;

    @Column(name = "auth_number")
    private String authNumber;

    @Column(name = "payer_id", nullable = false)
    private String payerId;

    @Column(name = "payer_name")
    private String payerName;

    @Column(name = "procedure_codes")
    private String procedureCodes;

    @Column(name = "diagnosis_codes")
    private String diagnosisCodes;

    @Column(name = "clinical_justification", columnDefinition = "TEXT")
    private String clinicalJustification;

    @Column(nullable = false)
    private String status = "PENDING";

    @Column(name = "submitted_at")
    private LocalDateTime submittedAt;

    @Column(name = "decision_at")
    private LocalDateTime decisionAt;

    @Column(name = "denial_reason")
    private String denialReason;

    @Column(name = "appeal_deadline")
    private LocalDate appealDeadline;

    @Column(name = "expires_at")
    private LocalDate expiresAt;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }
}