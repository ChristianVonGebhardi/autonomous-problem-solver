package com.healthcare.referral.domain.entity;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;

import java.time.LocalDate;

@Entity
@Table(name = "provider_insurance_networks")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class ProviderInsuranceNetwork {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "provider_id", nullable = false)
    private Provider provider;

    @Column(name = "payer_id", nullable = false)
    private String payerId;

    @Column(name = "payer_name", nullable = false)
    private String payerName;

    @Column(name = "network_name")
    private String networkName;

    @Column(name = "effective_date")
    private LocalDate effectiveDate;

    @Column(name = "termination_date")
    private LocalDate terminationDate;

    public boolean isActive() {
        LocalDate today = LocalDate.now();
        boolean effectiveOk = effectiveDate == null || !effectiveDate.isAfter(today);
        boolean terminationOk = terminationDate == null || terminationDate.isAfter(today);
        return effectiveOk && terminationOk;
    }
}