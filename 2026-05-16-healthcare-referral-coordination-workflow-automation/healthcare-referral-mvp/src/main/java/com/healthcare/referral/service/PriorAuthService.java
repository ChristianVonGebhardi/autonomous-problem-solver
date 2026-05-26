package com.healthcare.referral.service;

import com.healthcare.referral.domain.entity.PriorAuthRequest;
import com.healthcare.referral.domain.entity.Referral;
import com.healthcare.referral.repository.PriorAuthRequestRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@Service
@RequiredArgsConstructor
@Slf4j
public class PriorAuthService {

    private final PriorAuthRequestRepository priorAuthRequestRepository;

    // Payers that typically require prior auth for specialty referrals
    private static final Set<String> PRIOR_AUTH_REQUIRED_PAYERS = Set.of(
            "BCBS-MA", "UHC", "AETNA", "CIGNA"
    );

    // Specialties commonly requiring prior auth
    private static final Set<String> PRIOR_AUTH_REQUIRED_SPECIALTIES = Set.of(
            "CARDIO", "NEURO", "ORTHO", "GI"
    );

    public boolean requiresPriorAuth(Referral referral) {
        String payerId = referral.getInsurancePayerId();
        String specialtyCode = referral.getSpecialtyCode();

        if (payerId == null || specialtyCode == null) return false;

        return PRIOR_AUTH_REQUIRED_PAYERS.contains(payerId)
                && PRIOR_AUTH_REQUIRED_SPECIALTIES.contains(specialtyCode);
    }

    @Transactional
    public PriorAuthRequest submitPriorAuth(Referral referral) {
        log.info("Submitting prior auth for referral {} to payer {}",
                referral.getReferralNumber(), referral.getInsurancePayerId());

        String clinicalJustification = buildClinicalJustification(referral);

        PriorAuthRequest authRequest = PriorAuthRequest.builder()
                .referral(referral)
                .payerId(referral.getInsurancePayerId())
                .payerName(resolvePayerName(referral.getInsurancePayerId()))
                .procedureCodes(referral.getProcedureCodes())
                .diagnosisCodes(referral.getDiagnosisCodes())
                .clinicalJustification(clinicalJustification)
                .status("SUBMITTED")
                .submittedAt(LocalDateTime.now())
                .build();

        return priorAuthRequestRepository.save(authRequest);
    }

    @Async
    @Transactional
    public void simulatePriorAuthDecision(PriorAuthRequest authRequest, Referral referral,
                                          ReferralWorkflowService workflowService) {
        try {
            // Simulate processing delay (2-5 seconds in MVP, would be hours/days in production)
            Thread.sleep(3000 + ThreadLocalRandom.current().nextInt(3000));

            // 85% approval rate simulation
            boolean approved = ThreadLocalRandom.current().nextDouble() < 0.85;

            if (approved) {
                String authNumber = "AUTH-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
                authRequest.setStatus("APPROVED");
                authRequest.setAuthNumber(authNumber);
                authRequest.setDecisionAt(LocalDateTime.now());
                authRequest.setExpiresAt(LocalDate.now().plusMonths(3));
                priorAuthRequestRepository.save(authRequest);

                log.info("Prior auth APPROVED for referral {} - Auth#: {}",
                        referral.getReferralNumber(), authNumber);

                workflowService.handlePriorAuthApproved(referral.getId(), authNumber);
            } else {
                authRequest.setStatus("DENIED");
                authRequest.setDecisionAt(LocalDateTime.now());
                authRequest.setDenialReason("Medical necessity criteria not met per plan guidelines. Peer-to-peer review available.");
                authRequest.setAppealDeadline(LocalDate.now().plusDays(30));
                priorAuthRequestRepository.save(authRequest);

                log.warn("Prior auth DENIED for referral {}", referral.getReferralNumber());

                workflowService.handlePriorAuthDenied(referral.getId(),
                        authRequest.getDenialReason());
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.error("Prior auth simulation interrupted for referral {}", referral.getReferralNumber());
        }
    }

    private String buildClinicalJustification(Referral referral) {
        // In production, this would use LLM (GPT-4) to extract and structure clinical notes
        return String.format(
                "Patient %s (DOB: %s, Insurance ID: %s) requires %s consultation.\n\n" +
                "Clinical Indication: %s\n" +
                "Diagnosis Codes: %s\n" +
                "Procedure Codes: %s\n" +
                "Clinical Notes: %s\n\n" +
                "This referral is medically necessary as the patient's condition requires " +
                "specialist evaluation that cannot be adequately managed in a primary care setting.",
                referral.getPatient().getFullName(),
                referral.getPatient().getDateOfBirth(),
                referral.getInsuranceMemberId(),
                referral.getSpecialtyNeeded(),
                referral.getReasonForReferral(),
                referral.getDiagnosisCodes() != null ? referral.getDiagnosisCodes() : "Not specified",
                referral.getProcedureCodes() != null ? referral.getProcedureCodes() : "Not specified",
                referral.getClinicalNotes() != null ? referral.getClinicalNotes() : "See referral notes"
        );
    }

    private String resolvePayerName(String payerId) {
        if (payerId == null) return "Unknown";
        return switch (payerId) {
            case "BCBS-MA" -> "Blue Cross Blue Shield Massachusetts";
            case "UHC" -> "United Healthcare";
            case "AETNA" -> "Aetna";
            case "CIGNA" -> "Cigna";
            case "MEDICARE" -> "Medicare";
            case "MEDICAID" -> "Medicaid";
            default -> payerId;
        };
    }
}