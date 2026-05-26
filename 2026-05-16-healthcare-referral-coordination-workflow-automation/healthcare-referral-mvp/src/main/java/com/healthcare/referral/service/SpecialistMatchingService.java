package com.healthcare.referral.service;

import com.healthcare.referral.domain.entity.Patient;
import com.healthcare.referral.domain.entity.Provider;
import com.healthcare.referral.domain.entity.Referral;
import com.healthcare.referral.dto.response.SpecialistMatchResult;
import com.healthcare.referral.repository.ProviderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Slf4j
public class SpecialistMatchingService {

    private final ProviderRepository providerRepository;

    // Specialty code mappings for common specialties
    private static final java.util.Map<String, String> SPECIALTY_CODE_MAP = java.util.Map.ofEntries(
            java.util.Map.entry("cardiology", "CARDIO"),
            java.util.Map.entry("cardiac", "CARDIO"),
            java.util.Map.entry("heart", "CARDIO"),
            java.util.Map.entry("orthopedic", "ORTHO"),
            java.util.Map.entry("orthopedics", "ORTHO"),
            java.util.Map.entry("orthopaedic", "ORTHO"),
            java.util.Map.entry("neurology", "NEURO"),
            java.util.Map.entry("neurological", "NEURO"),
            java.util.Map.entry("gastroenterology", "GI"),
            java.util.Map.entry("gastro", "GI"),
            java.util.Map.entry("endocrinology", "ENDO"),
            java.util.Map.entry("diabetes", "ENDO"),
            java.util.Map.entry("pulmonology", "PULM"),
            java.util.Map.entry("pulmonary", "PULM"),
            java.util.Map.entry("sleep", "PULM")
    );

    public SpecialistMatchResult findMatches(Referral referral) {
        Patient patient = referral.getPatient();
        String specialtyCode = resolveSpecialtyCode(referral.getSpecialtyNeeded(), referral.getSpecialtyCode());
        String payerId = resolvePayerId(referral, patient);

        log.info("Finding specialists for referral {} - specialty: {}, payer: {}",
                referral.getReferralNumber(), specialtyCode, payerId);

        List<Provider> candidates;

        // Try exact specialty code + insurance match first
        if (specialtyCode != null && payerId != null) {
            candidates = providerRepository.findAvailableBySpecialtyAndInsurance(specialtyCode, payerId);
            log.debug("Found {} providers matching specialty code {} and payer {}",
                    candidates.size(), specialtyCode, payerId);
        } else if (specialtyCode != null) {
            candidates = providerRepository.findBySpecialtyCodeAndAcceptingNewPatientsTrue(specialtyCode);
        } else {
            // Fall back to keyword search
            candidates = providerRepository.findBySpecialtyKeywordAndInsurance(
                    referral.getSpecialtyNeeded(), payerId != null ? payerId : "ANY");
            if (candidates.isEmpty()) {
                candidates = fallbackKeywordSearch(referral.getSpecialtyNeeded());
            }
        }

        // Score and rank candidates
        List<SpecialistMatchResult.MatchedProvider> matches = candidates.stream()
                .map(provider -> scoreProvider(provider, patient, payerId))
                .sorted(Comparator.comparingDouble(SpecialistMatchResult.MatchedProvider::getMatchScore).reversed())
                .limit(5)
                .collect(Collectors.toList());

        return SpecialistMatchResult.builder()
                .matchFound(!matches.isEmpty())
                .totalCandidates(candidates.size())
                .matches(matches)
                .build();
    }

    private List<Provider> fallbackKeywordSearch(String specialtyNeeded) {
        String keyword = specialtyNeeded.toLowerCase().split("[,\\s]+")[0];
        return providerRepository.findAll().stream()
                .filter(p -> p.getAcceptingNewPatients() != null && p.getAcceptingNewPatients())
                .filter(p -> p.getSpecialty().toLowerCase().contains(keyword))
                .collect(Collectors.toList());
    }

    public String resolveSpecialtyCode(String specialtyNeeded, String existingCode) {
        if (existingCode != null && !existingCode.isBlank()) {
            return existingCode;
        }
        if (specialtyNeeded == null) return null;

        String lower = specialtyNeeded.toLowerCase();
        return SPECIALTY_CODE_MAP.entrySet().stream()
                .filter(e -> lower.contains(e.getKey()))
                .map(java.util.Map.Entry::getValue)
                .findFirst()
                .orElse(null);
    }

    private String resolvePayerId(Referral referral, Patient patient) {
        if (referral.getInsurancePayerId() != null) return referral.getInsurancePayerId();
        if (patient.getInsurancePayerId() != null) return patient.getInsurancePayerId();
        return null;
    }

    private SpecialistMatchResult.MatchedProvider scoreProvider(
            Provider provider, Patient patient, String payerId) {

        double score = 50.0; // base score

        // Check in-network status
        boolean inNetwork = isInNetwork(provider, payerId);
        if (inNetwork) score += 30.0;

        // Availability bonus
        if (provider.getAcceptingNewPatients() != null && provider.getAcceptingNewPatients()) {
            score += 10.0;
        }

        // Wait time factor (lower is better, +up to 10 points)
        if (provider.getAverageWaitDays() != null) {
            score += Math.max(0, 10.0 - provider.getAverageWaitDays() * 0.5);
        }

        // Portal bonus (faster communication)
        if (Boolean.TRUE.equals(provider.getPortalEnabled())) {
            score += 5.0;
        }

        // Distance calculation
        double distance = calculateDistance(patient, provider);
        // Reduce score for distance (up to -15 for 50+ miles)
        score -= Math.min(15.0, distance * 0.3);

        // Get insurance networks list
        List<String> networks = new ArrayList<>();
        if (provider.getInsuranceNetworks() != null) {
            networks = provider.getInsuranceNetworks().stream()
                    .filter(n -> n.isActive())
                    .map(n -> n.getPayerName())
                    .collect(Collectors.toList());
        }

        return SpecialistMatchResult.MatchedProvider.builder()
                .providerId(provider.getId())
                .npi(provider.getNpi())
                .fullName(provider.getFullName())
                .specialty(provider.getSpecialty())
                .practiceName(provider.getPracticeName())
                .city(provider.getCity())
                .stateAbbr(provider.getStateAbbr())
                .phone(provider.getPhone())
                .acceptingNewPatients(provider.getAcceptingNewPatients())
                .averageWaitDays(provider.getAverageWaitDays())
                .inNetwork(inNetwork)
                .portalEnabled(provider.getPortalEnabled())
                .matchScore(Math.min(100.0, Math.max(0.0, score)))
                .distanceMiles(distance)
                .insuranceNetworks(networks)
                .build();
    }

    private boolean isInNetwork(Provider provider, String payerId) {
        if (payerId == null || provider.getInsuranceNetworks() == null) return false;
        return provider.getInsuranceNetworks().stream()
                .anyMatch(n -> n.getPayerId().equalsIgnoreCase(payerId) && n.isActive());
    }

    private double calculateDistance(Patient patient, Provider provider) {
        if (patient.getLatitude() == null || patient.getLongitude() == null
                || provider.getLatitude() == null || provider.getLongitude() == null) {
            return 10.0; // Default assumption
        }
        return haversineDistance(
                patient.getLatitude(), patient.getLongitude(),
                provider.getLatitude(), provider.getLongitude());
    }

    /**
     * Haversine formula for distance in miles between two lat/lon points.
     */
    public static double haversineDistance(double lat1, double lon1, double lat2, double lon2) {
        final double R = 3958.8; // Earth radius in miles
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }
}