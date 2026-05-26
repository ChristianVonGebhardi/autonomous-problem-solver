package com.healthcare.referral.service;

import com.healthcare.referral.domain.entity.*;
import com.healthcare.referral.domain.enums.ReferralStatus;
import com.healthcare.referral.dto.request.CreateReferralRequest;
import com.healthcare.referral.dto.response.ReferralResponse;
import com.healthcare.referral.dto.response.SpecialistMatchResult;
import com.healthcare.referral.repository.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class ReferralWorkflowService {

    private final ReferralRepository referralRepository;
    private final PatientRepository patientRepository;
    private final ReferringProviderRepository referringProviderRepository;
    private final ProviderRepository providerRepository;
    private final ReferralStateHistoryRepository stateHistoryRepository;
    private final PriorAuthRequestRepository priorAuthRequestRepository;
    private final ReferralNumberGenerator referralNumberGenerator;
    private final SpecialistMatchingService matchingService;
    private final PriorAuthService priorAuthService;
    private final NotificationService notificationService;
    private final ApplicationEventPublisher eventPublisher;

    @Transactional
    public Referral createReferral(CreateReferralRequest request) {
        log.info("Creating referral for patient {} - specialty: {}",
                request.getPatientExternalId(), request.getSpecialtyNeeded());

        // Look up patient
        Patient patient = patientRepository.findByExternalId(request.getPatientExternalId())
                .orElseThrow(() -> new IllegalArgumentException(
                        "Patient not found: " + request.getPatientExternalId()));

        // Look up referring provider
        ReferringProvider referringProvider = null;
        if (request.getReferringProviderNpi() != null) {
            referringProvider = referringProviderRepository.findByNpi(request.getReferringProviderNpi())
                    .orElse(null);
        }

        // Determine insurance
        String payerId = request.getInsurancePayerId() != null ?
                request.getInsurancePayerId() : patient.getInsurancePayerId();
        String memberId = request.getInsuranceMemberId() != null ?
                request.getInsuranceMemberId() : patient.getInsuranceMemberId();

        // Resolve specialty code
        String specialtyCode = matchingService.resolveSpecialtyCode(
                request.getSpecialtyNeeded(), request.getSpecialtyCode());

        // Build referral entity
        Referral referral = Referral.builder()
                .referralNumber(referralNumberGenerator.generate())
                .fhirServiceRequestId(request.getFhirServiceRequestId())
                .status(ReferralStatus.NEW)
                .priority(request.getPriority())
                .patient(patient)
                .referringProvider(referringProvider)
                .specialtyNeeded(request.getSpecialtyNeeded())
                .specialtyCode(specialtyCode)
                .reasonForReferral(request.getReasonForReferral())
                .clinicalNotes(request.getClinicalNotes())
                .diagnosisCodes(request.getDiagnosisCodes())
                .procedureCodes(request.getProcedureCodes())
                .insurancePayerId(payerId)
                .insuranceMemberId(memberId)
                .emrOrderId(request.getEmrOrderId())
                .sourceSystem(request.getSourceSystem())
                .matchingAttempts(0)
                .notificationAttempts(0)
                .build();

        // Check if prior auth might be needed
        referral.setPriorAuthRequired(priorAuthService.requiresPriorAuth(referral));

        referral = referralRepository.save(referral);

        // Record initial state
        recordStateTransition(referral, null, ReferralStatus.NEW, "REFERRAL_CREATED", "system");

        // Trigger async workflow
        processReferralAsync(referral.getId());

        return referral;
    }

    @Async
    public void processReferralAsync(Long referralId) {
        try {
            // Brief delay to simulate async processing
            Thread.sleep(500);

            Referral referral = referralRepository.findById(referralId)
                    .orElseThrow(() -> new RuntimeException("Referral not found: " + referralId));

            // Transition to RECEIVED
            transitionStatus(referral, ReferralStatus.RECEIVED, "REFERRAL_RECEIVED", "system");

            // Notify patient
            notificationService.notifyPatientReferralCreated(referral);
            referral.setPatientNotifiedAt(LocalDateTime.now());
            referral.setNotificationAttempts(referral.getNotificationAttempts() + 1);
            referral = referralRepository.save(referral);

            // Transition to MATCHING
            transitionStatus(referral, ReferralStatus.MATCHING, "MATCHING_STARTED", "system");

            // Run specialist matching
            Thread.sleep(1000);
            performMatching(referral.getId());

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.error("Referral processing interrupted for {}", referralId);
        } catch (Exception e) {
            log.error("Error processing referral {}: {}", referralId, e.getMessage(), e);
        }
    }

    @Transactional
    public void performMatching(Long referralId) {
        Referral referral = referralRepository.findById(referralId).orElseThrow();

        referral.setMatchingAttempts(referral.getMatchingAttempts() + 1);
        referral = referralRepository.save(referral);

        SpecialistMatchResult result = matchingService.findMatches(referral);

        if (result.isMatchFound() && !result.getMatches().isEmpty()) {
            // Assign top-scoring specialist
            SpecialistMatchResult.MatchedProvider topMatch = result.getMatches().get(0);
            Provider specialist = providerRepository.findById(topMatch.getProviderId()).orElse(null);

            if (specialist != null) {
                referral.setAssignedProvider(specialist);
                transitionStatus(referral, ReferralStatus.MATCHED, "SPECIALIST_MATCHED",
                        "matching-engine");

                referral = referralRepository.findById(referralId).orElseThrow();

                // Notify patient of match
                notificationService.notifyPatientSpecialistMatched(referral);

                // Check if prior auth needed
                if (Boolean.TRUE.equals(referral.getPriorAuthRequired())) {
                    processWithPriorAuth(referral);
                } else {
                    sendToSpecialist(referral);
                }
            }
        } else {
            log.warn("No matching specialists found for referral {} - specialty: {}, payer: {}",
                    referral.getReferralNumber(), referral.getSpecialtyNeeded(),
                    referral.getInsurancePayerId());
            // Keep in MATCHING status - would retry in production
        }
    }

    @Transactional
    private void processWithPriorAuth(Referral referral) {
        log.info("Initiating prior authorization for referral {}", referral.getReferralNumber());
        transitionStatus(referral, ReferralStatus.PRIOR_AUTH_SUBMITTED, "PRIOR_AUTH_INITIATED", "system");

        PriorAuthRequest authRequest = priorAuthService.submitPriorAuth(referral);

        referral.setPriorAuthSubmittedAt(LocalDateTime.now());
        referral = referralRepository.save(referral);

        // Simulate async prior auth decision
        final Referral finalReferral = referral;
        priorAuthService.simulatePriorAuthDecision(authRequest, finalReferral, this);
    }

    @Transactional
    private void sendToSpecialist(Referral referral) {
        transitionStatus(referral, ReferralStatus.SENT_TO_SPECIALIST, "SENT_TO_SPECIALIST", "system");

        referral.setSpecialistSentAt(LocalDateTime.now());
        referral = referralRepository.save(referral);

        notificationService.notifySpecialistOfReferral(referral);

        transitionStatus(referral, ReferralStatus.PATIENT_NOTIFIED, "PATIENT_NOTIFIED", "system");
    }

    @Transactional
    public void handlePriorAuthApproved(Long referralId, String authNumber) {
        Referral referral = referralRepository.findById(referralId).orElseThrow();
        referral.setPriorAuthNumber(authNumber);
        referral.setPriorAuthStatus("APPROVED");
        referral.setPriorAuthDecisionAt(LocalDateTime.now());
        referral = referralRepository.save(referral);

        transitionStatus(referral, ReferralStatus.PRIOR_AUTH_APPROVED, "PRIOR_AUTH_APPROVED", "payer-portal");
        sendToSpecialist(referral);
    }

    @Transactional
    public void handlePriorAuthDenied(Long referralId, String reason) {
        Referral referral = referralRepository.findById(referralId).orElseThrow();
        referral.setPriorAuthStatus("DENIED");
        referral.setPriorAuthDecisionAt(LocalDateTime.now());
        referral = referralRepository.save(referral);

        transitionStatus(referral, ReferralStatus.PRIOR_AUTH_DENIED,
                "PRIOR_AUTH_DENIED", "payer-portal",
                "Denial reason: " + reason);
    }

    @Transactional
    public Referral scheduleAppointment(Long referralId, LocalDateTime appointmentTime,
                                        String performedBy) {
        Referral referral = referralRepository.findById(referralId).orElseThrow();

        String appointmentId = "APT-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        referral.setAppointmentId(appointmentId);
        referral.setAppointmentDatetime(appointmentTime);
        referral.setAppointmentStatus("SCHEDULED");
        referral = referralRepository.save(referral);

        transitionStatus(referral, ReferralStatus.APPOINTMENT_SCHEDULED,
                "APPOINTMENT_SCHEDULED", performedBy);

        notificationService.notifyPatientAppointmentScheduled(referral);

        return referral;
    }

    @Transactional
    public Referral recordConsultNote(Long referralId, String consultNoteContent, String performedBy) {
        Referral referral = referralRepository.findById(referralId).orElseThrow();

        referral.setConsultNoteReceivedAt(LocalDateTime.now());
        referral.setAppointmentStatus("COMPLETED");
        referral = referralRepository.save(referral);

        transitionStatus(referral, ReferralStatus.APPOINTMENT_COMPLETED,
                "APPOINTMENT_COMPLETED", performedBy);

        // Complete the referral
        completeReferral(referralId, performedBy);

        return referralRepository.findById(referralId).orElseThrow();
    }

    @Transactional
    public Referral completeReferral(Long referralId, String performedBy) {
        Referral referral = referralRepository.findById(referralId).orElseThrow();
        referral.setCompletedAt(LocalDateTime.now());
        referral = referralRepository.save(referral);

        transitionStatus(referral, ReferralStatus.COMPLETED, "REFERRAL_COMPLETED", performedBy);
        notificationService.notifyCareteamReferralComplete(referral);

        log.info("Referral {} completed successfully", referral.getReferralNumber());
        return referral;
    }

    @Transactional
    public Referral cancelReferral(Long referralId, String reason, String performedBy) {
        Referral referral = referralRepository.findById(referralId).orElseThrow();
        transitionStatus(referral, ReferralStatus.CANCELLED, "REFERRAL_CANCELLED", performedBy, reason);
        return referral;
    }

    @Transactional
    public Referral manualStatusUpdate(Long referralId, String newStatus,
                                       String notes, String performedBy) {
        Referral referral = referralRepository.findById(referralId).orElseThrow();
        ReferralStatus status = ReferralStatus.valueOf(newStatus.toUpperCase());
        transitionStatus(referral, status, "MANUAL_UPDATE", performedBy, notes);
        return referralRepository.findById(referralId).orElseThrow();
    }

    @Transactional
    public Referral assignSpecialist(Long referralId, Long providerId, String performedBy) {
        Referral referral = referralRepository.findById(referralId).orElseThrow();
        Provider provider = providerRepository.findById(providerId).orElseThrow();

        referral.setAssignedProvider(provider);
        referral = referralRepository.save(referral);

        transitionStatus(referral, ReferralStatus.MATCHED, "SPECIALIST_ASSIGNED_MANUAL", performedBy,
                "Manually assigned to " + provider.getFullName());

        return referral;
    }

    private void transitionStatus(Referral referral, ReferralStatus newStatus,
                                   String event, String performedBy) {
        transitionStatus(referral, newStatus, event, performedBy, null);
    }

    @Transactional
    private void transitionStatus(Referral referral, ReferralStatus newStatus,
                                   String event, String performedBy, String notes) {
        ReferralStatus oldStatus = referral.getStatus();

        referral.setStatus(newStatus);
        referral = referralRepository.save(referral);

        recordStateTransition(referral, oldStatus, newStatus, event, performedBy, notes);

        log.info("Referral {} transitioned {} -> {} (event: {})",
                referral.getReferralNumber(), oldStatus, newStatus, event);
    }

    private void recordStateTransition(Referral referral, ReferralStatus from,
                                        ReferralStatus to, String event, String performedBy) {
        recordStateTransition(referral, from, to, event, performedBy, null);
    }

    private void recordStateTransition(Referral referral, ReferralStatus from,
                                        ReferralStatus to, String event, String performedBy,
                                        String notes) {
        ReferralStateHistory history = ReferralStateHistory.builder()
                .referral(referral)
                .fromStatus(from != null ? from.name() : null)
                .toStatus(to.name())
                .transitionEvent(event)
                .notes(notes)
                .performedBy(performedBy)
                .build();
        stateHistoryRepository.save(history);
    }

    public ReferralResponse toResponse(Referral referral, boolean includeHistory) {
        ReferralResponse.ReferralResponseBuilder builder = ReferralResponse.builder()
                .id(referral.getId())
                .referralNumber(referral.getReferralNumber())
                .fhirServiceRequestId(referral.getFhirServiceRequestId())
                .status(referral.getStatus())
                .priority(referral.getPriority())
                .specialtyNeeded(referral.getSpecialtyNeeded())
                .specialtyCode(referral.getSpecialtyCode())
                .reasonForReferral(referral.getReasonForReferral())
                .clinicalNotes(referral.getClinicalNotes())
                .diagnosisCodes(referral.getDiagnosisCodes())
                .procedureCodes(referral.getProcedureCodes())
                .insurancePayerId(referral.getInsurancePayerId())
                .insuranceMemberId(referral.getInsuranceMemberId())
                .priorAuthRequired(referral.getPriorAuthRequired())
                .priorAuthNumber(referral.getPriorAuthNumber())
                .priorAuthStatus(referral.getPriorAuthStatus())
                .priorAuthSubmittedAt(referral.getPriorAuthSubmittedAt())
                .priorAuthDecisionAt(referral.getPriorAuthDecisionAt())
                .appointmentId(referral.getAppointmentId())
                .appointmentDatetime(referral.getAppointmentDatetime())
                .appointmentStatus(referral.getAppointmentStatus())
                .createdAt(referral.getCreatedAt())
                .updatedAt(referral.getUpdatedAt())
                .completedAt(referral.getCompletedAt())
                .dueDate(referral.getDueDate())
                .patientNotifiedAt(referral.getPatientNotifiedAt())
                .patientConfirmedAt(referral.getPatientConfirmedAt())
                .specialistSentAt(referral.getSpecialistSentAt())
                .consultNoteReceivedAt(referral.getConsultNoteReceivedAt())
                .matchingAttempts(referral.getMatchingAttempts())
                .notificationAttempts(referral.getNotificationAttempts());

        // Patient summary
        if (referral.getPatient() != null) {
            Patient p = referral.getPatient();
            builder.patient(ReferralResponse.PatientSummary.builder()
                    .id(p.getId())
                    .externalId(p.getExternalId())
                    .fullName(p.getFullName())
                    .dateOfBirth(p.getDateOfBirth().toString())
                    .phone(p.getPhone())
                    .email(p.getEmail())
                    .insurancePayerId(p.getInsurancePayerId())
                    .insurancePlanName(p.getInsurancePlanName())
                    .insuranceMemberId(p.getInsuranceMemberId())
                    .build());
        }

        // Referring provider summary
        if (referral.getReferringProvider() != null) {
            ReferringProvider rp = referral.getReferringProvider();
            builder.referringProvider(ReferralResponse.ProviderSummary.builder()
                    .id(rp.getId())
                    .npi(rp.getNpi())
                    .fullName(rp.getFullName())
                    .specialty(rp.getSpecialty())
                    .practiceName(rp.getPracticeName())
                    .phone(rp.getPhone())
                    .build());
        }

        // Assigned provider summary
        if (referral.getAssignedProvider() != null) {
            Provider ap = referral.getAssignedProvider();
            builder.assignedProvider(ReferralResponse.ProviderSummary.builder()
                    .id(ap.getId())
                    .npi(ap.getNpi())
                    .fullName(ap.getFullName())
                    .specialty(ap.getSpecialty())
                    .practiceName(ap.getPracticeName())
                    .phone(ap.getPhone())
                    .city(ap.getCity())
                    .stateAbbr(ap.getStateAbbr())
                    .averageWaitDays(ap.getAverageWaitDays())
                    .portalEnabled(ap.getPortalEnabled())
                    .build());
        }

        // Days open calculation
        if (referral.getCreatedAt() != null) {
            LocalDateTime endTime = referral.getCompletedAt() != null ?
                    referral.getCompletedAt() : LocalDateTime.now();
            builder.daysOpen(ChronoUnit.DAYS.between(referral.getCreatedAt(), endTime));
        }

        if (includeHistory) {
            List<ReferralStateHistory> history =
                    stateHistoryRepository.findByReferralIdOrderByPerformedAtAsc(referral.getId());
            builder.stateHistory(history.stream().map(h ->
                    ReferralResponse.StateHistoryEntry.builder()
                            .fromStatus(h.getFromStatus())
                            .toStatus(h.getToStatus())
                            .transitionEvent(h.getTransitionEvent())
                            .notes(h.getNotes())
                            .performedBy(h.getPerformedBy())
                            .performedAt(h.getPerformedAt())
                            .build()).toList());
        }

        return builder.build();
    }
}