package com.healthcare.referral.service;

import com.healthcare.referral.domain.entity.CommunicationLog;
import com.healthcare.referral.domain.entity.Provider;
import com.healthcare.referral.domain.entity.Referral;
import com.healthcare.referral.domain.enums.CommunicationChannel;
import com.healthcare.referral.repository.CommunicationLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
@Slf4j
public class NotificationService {

    private final CommunicationLogRepository communicationLogRepository;

    @Value("${app.notifications.simulated:true}")
    private boolean simulated;

    @Async
    public void notifyPatientReferralCreated(Referral referral) {
        String message = buildPatientCreatedMessage(referral);
        sendToPatient(referral, CommunicationChannel.EMAIL,
                "Your Referral Has Been Created - " + referral.getSpecialtyNeeded(),
                message);

        if (referral.getPatient().getPhone() != null) {
            String smsMessage = String.format(
                    "Hi %s, your referral to %s has been received. Ref# %s. We will contact you shortly to schedule.",
                    referral.getPatient().getFirstName(),
                    referral.getSpecialtyNeeded(),
                    referral.getReferralNumber());
            sendToPatient(referral, CommunicationChannel.SMS, null, smsMessage);
        }
    }

    @Async
    public void notifyPatientSpecialistMatched(Referral referral) {
        if (referral.getAssignedProvider() == null) return;

        Provider specialist = referral.getAssignedProvider();
        String message = String.format(
                "Great news, %s! We've matched you with %s (%s) at %s in %s, %s. " +
                "Average wait time: %d days. We're reaching out to schedule your appointment. " +
                "Referral #: %s",
                referral.getPatient().getFirstName(),
                specialist.getFullName(),
                specialist.getSpecialty(),
                specialist.getPracticeName(),
                specialist.getCity(),
                specialist.getStateAbbr(),
                specialist.getAverageWaitDays(),
                referral.getReferralNumber());

        sendToPatient(referral, CommunicationChannel.EMAIL,
                "Your Specialist Has Been Matched - Action Required", message);

        if (referral.getPatient().getPhone() != null) {
            String sms = String.format(
                    "Hi %s, we matched you with Dr. %s %s for your %s referral. " +
                    "We'll contact you to schedule. Reply CONFIRM to accept. Ref# %s",
                    referral.getPatient().getFirstName(),
                    specialist.getFirstName(),
                    specialist.getLastName(),
                    referral.getSpecialtyNeeded(),
                    referral.getReferralNumber());
            sendToPatient(referral, CommunicationChannel.SMS, null, sms);
        }
    }

    @Async
    public void notifyPatientAppointmentScheduled(Referral referral) {
        if (referral.getAppointmentDatetime() == null) return;

        String message = String.format(
                "Your appointment with %s has been scheduled for %s at %s. " +
                "Please arrive 15 minutes early with your insurance card. " +
                "Referral #: %s",
                referral.getAssignedProvider() != null ?
                        referral.getAssignedProvider().getFullName() : "your specialist",
                referral.getAppointmentDatetime(),
                referral.getAssignedProvider() != null ?
                        referral.getAssignedProvider().getPracticeName() : "the office",
                referral.getReferralNumber());

        sendToPatient(referral, CommunicationChannel.EMAIL,
                "Appointment Scheduled - " + referral.getSpecialtyNeeded(), message);
    }

    @Async
    public void notifySpecialistOfReferral(Referral referral) {
        if (referral.getAssignedProvider() == null) return;

        Provider specialist = referral.getAssignedProvider();
        String recipientEmail = specialist.getEmail();
        if (recipientEmail == null) return;

        String message = String.format(
                "New referral received for patient %s (DOB: %s)\n" +
                "Specialty: %s | Priority: %s\n" +
                "Reason: %s\n" +
                "Referring Provider: %s\n" +
                "Insurance: %s (Member ID: %s)\n" +
                "Referral #: %s\n\n" +
                "Please log into the Specialist Portal to accept and schedule.",
                referral.getPatient().getFullName(),
                referral.getPatient().getDateOfBirth(),
                referral.getSpecialtyNeeded(),
                referral.getPriority(),
                referral.getReasonForReferral(),
                referral.getReferringProvider() != null ?
                        referral.getReferringProvider().getFullName() : "Unknown",
                referral.getInsurancePayerId(),
                referral.getInsuranceMemberId(),
                referral.getReferralNumber());

        log.info("[NOTIFICATION] Sending referral to specialist {} at {}",
                specialist.getFullName(), recipientEmail);

        CommunicationLog log2 = CommunicationLog.builder()
                .referral(referral)
                .channel(CommunicationChannel.EMAIL)
                .recipientType("SPECIALIST")
                .recipientAddress(recipientEmail)
                .subject("New Referral - " + referral.getPatient().getFullName())
                .messageBody(message)
                .status(simulated ? "SIMULATED" : "SENT")
                .sentAt(LocalDateTime.now())
                .build();
        communicationLogRepository.save(log2);
    }

    @Async
    public void notifyCareteamReferralComplete(Referral referral) {
        if (referral.getReferringProvider() == null ||
                referral.getReferringProvider().getEmail() == null) return;

        String message = String.format(
                "Referral #%s for %s has been completed.\n" +
                "Specialist: %s\n" +
                "Appointment: %s\n" +
                "Consult note received: %s",
                referral.getReferralNumber(),
                referral.getPatient().getFullName(),
                referral.getAssignedProvider() != null ?
                        referral.getAssignedProvider().getFullName() : "N/A",
                referral.getAppointmentDatetime(),
                referral.getConsultNoteReceivedAt());

        CommunicationLog commLog = CommunicationLog.builder()
                .referral(referral)
                .channel(CommunicationChannel.EMAIL)
                .recipientType("REFERRING_PROVIDER")
                .recipientAddress(referral.getReferringProvider().getEmail())
                .subject("Referral Complete - " + referral.getPatient().getFullName())
                .messageBody(message)
                .status(simulated ? "SIMULATED" : "SENT")
                .sentAt(LocalDateTime.now())
                .build();
        communicationLogRepository.save(commLog);

        log.info("[NOTIFICATION] Notified referring provider {} of completion for referral {}",
                referral.getReferringProvider().getFullName(), referral.getReferralNumber());
    }

    private void sendToPatient(Referral referral, CommunicationChannel channel,
                               String subject, String message) {
        String address = (channel == CommunicationChannel.SMS)
                ? referral.getPatient().getPhone()
                : referral.getPatient().getEmail();

        if (address == null || address.isBlank()) {
            log.warn("No {} address for patient {} - skipping notification",
                    channel, referral.getPatient().getExternalId());
            return;
        }

        String status = simulated ? "SIMULATED" : "SENT";
        log.info("[NOTIFICATION] {} to patient {} ({}): {}",
                channel, referral.getPatient().getFullName(), address,
                subject != null ? subject : message.substring(0, Math.min(50, message.length())));

        CommunicationLog commLog = CommunicationLog.builder()
                .referral(referral)
                .channel(channel)
                .recipientType("PATIENT")
                .recipientAddress(address)
                .subject(subject)
                .messageBody(message)
                .status(status)
                .sentAt(LocalDateTime.now())
                .build();
        communicationLogRepository.save(commLog);
    }

    private String buildPatientCreatedMessage(Referral referral) {
        return String.format(
                "Dear %s,\n\n" +
                "Your healthcare provider has submitted a referral for you to see a %s specialist.\n\n" +
                "Referral Number: %s\n" +
                "Priority: %s\n" +
                "Reason: %s\n\n" +
                "Our team is currently finding the best in-network specialist for you. " +
                "You will receive a follow-up message once a match is found.\n\n" +
                "If you have questions, please contact your care coordinator.\n\n" +
                "Thank you,\nHealthcare Referral Coordination Team",
                referral.getPatient().getFullName(),
                referral.getSpecialtyNeeded(),
                referral.getReferralNumber(),
                referral.getPriority(),
                referral.getReasonForReferral());
    }
}