package com.healthcare.referral.domain.entity;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;

import java.time.LocalDateTime;

@Entity
@Table(name = "referring_providers")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ReferringProvider {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(unique = true, nullable = false)
    private String npi;

    @Column(name = "first_name", nullable = false)
    private String firstName;

    @Column(name = "last_name", nullable = false)
    private String lastName;

    private String specialty;

    @Column(name = "practice_name")
    private String practiceName;

    private String phone;
    private String fax;
    private String email;

    @Column(name = "health_system_id")
    private String healthSystemId;

    @Column(name = "emr_system")
    private String emrSystem;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    public String getFullName() {
        return "Dr. " + firstName + " " + lastName;
    }
}