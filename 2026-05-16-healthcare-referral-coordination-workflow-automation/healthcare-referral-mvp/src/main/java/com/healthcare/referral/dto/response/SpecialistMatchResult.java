package com.healthcare.referral.dto.response;

import lombok.Data;
import lombok.Builder;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SpecialistMatchResult {

    private boolean matchFound;
    private int totalCandidates;
    private List<MatchedProvider> matches;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class MatchedProvider {
        private Long providerId;
        private String npi;
        private String fullName;
        private String specialty;
        private String practiceName;
        private String city;
        private String stateAbbr;
        private String phone;
        private Boolean acceptingNewPatients;
        private Integer averageWaitDays;
        private Boolean inNetwork;
        private Boolean portalEnabled;
        private Double matchScore;
        private Double distanceMiles;
        private List<String> insuranceNetworks;
    }
}