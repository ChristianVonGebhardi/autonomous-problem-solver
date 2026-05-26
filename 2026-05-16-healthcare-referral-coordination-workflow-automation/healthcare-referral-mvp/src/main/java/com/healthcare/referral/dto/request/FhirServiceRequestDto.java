package com.healthcare.referral.dto.request;

import lombok.Data;

import java.util.List;

/**
 * Simplified FHIR ServiceRequest DTO for inbound EMR integration.
 * Represents a subset of the HL7 FHIR R4 ServiceRequest resource.
 */
@Data
public class FhirServiceRequestDto {

    private String resourceType = "ServiceRequest";
    private String id;
    private String status;
    private String intent;
    private String priority;

    // Subject (Patient)
    private FhirReference subject;

    // Requester (Referring Provider)
    private FhirReference requester;

    // Performer type (specialty)
    private List<FhirCodeableConcept> performerType;

    // Code (what procedure/specialty)
    private FhirCodeableConcept code;

    // Reason codes (diagnosis)
    private List<FhirCodeableConcept> reasonCode;

    // Notes
    private List<FhirAnnotation> note;

    // Order detail
    private String orderDetail;

    @Data
    public static class FhirReference {
        private String reference;
        private String display;
    }

    @Data
    public static class FhirCodeableConcept {
        private List<FhirCoding> coding;
        private String text;
    }

    @Data
    public static class FhirCoding {
        private String system;
        private String code;
        private String display;
    }

    @Data
    public static class FhirAnnotation {
        private String text;
    }
}