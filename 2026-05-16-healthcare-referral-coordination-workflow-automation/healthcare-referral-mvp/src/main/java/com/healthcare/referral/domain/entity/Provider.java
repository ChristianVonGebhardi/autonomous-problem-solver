package com.healthcare.referral.domain.entity;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;

import java.time.LocalDateTime;
import java.util.List;

@Entity
@Table(name = "providers")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Provider {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(unique = true, nullable = false)
    private String npi;

    @Column(name = "first_name", nullable = false)
    private String firstName;

    @Column(name = "last_name", nullable = false)
    private String lastName;

    private String credentials;

    @Column(nullable = false)
    private String specialty;

    @Column(name = "specialty_code")
    private String specialtyCode;

    @Column(name = "practice_name")
    private String practiceName;

    private String phone;
    private String fax;
    private String email;

    @Column(name = "address_line1")
    private String addressLine1;

    private String city;

    @Column(name = "state_abbr")
    private String stateAbbr;

    @Column(name = "zip_code")
    private String zipCode;

    private Double latitude;
    private Double longitude;

    @Column(name = "accepting_new_patients")
    private Boolean acceptingNewPatients = true;

    @Column(name = "average_wait_days")
    private Integer averageWaitDays = 14;

    @Column(name = "portal_enabled")
    private Boolean portalEnabled = false;

    @OneToMany(mappedBy = "provider", fetch = FetchType.LAZY, cascade = CascadeType.ALL)
    private List<ProviderInsuranceNetwork> insuranceNetworks;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public String getFullName() {
        return firstName + " " + lastName + (credentials != null ? ", " + credentials : "");
    }
}