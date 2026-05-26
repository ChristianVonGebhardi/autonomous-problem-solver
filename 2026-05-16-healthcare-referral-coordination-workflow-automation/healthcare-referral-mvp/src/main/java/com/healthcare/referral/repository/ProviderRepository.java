package com.healthcare.referral.repository;

import com.healthcare.referral.domain.entity.Provider;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface ProviderRepository extends JpaRepository<Provider, Long> {

    Optional<Provider> findByNpi(String npi);

    List<Provider> findBySpecialtyCodeAndAcceptingNewPatientsTrue(String specialtyCode);

    @Query("""
            SELECT DISTINCT p FROM Provider p
            JOIN p.insuranceNetworks net
            WHERE p.specialtyCode = :specialtyCode
              AND p.acceptingNewPatients = true
              AND net.payerId = :payerId
              AND (net.terminationDate IS NULL OR net.terminationDate > CURRENT_DATE)
            """)
    List<Provider> findAvailableBySpecialtyAndInsurance(
            @Param("specialtyCode") String specialtyCode,
            @Param("payerId") String payerId);

    @Query("""
            SELECT DISTINCT p FROM Provider p
            JOIN p.insuranceNetworks net
            WHERE UPPER(p.specialty) LIKE UPPER(CONCAT('%', :specialtyKeyword, '%'))
              AND p.acceptingNewPatients = true
              AND net.payerId = :payerId
              AND (net.terminationDate IS NULL OR net.terminationDate > CURRENT_DATE)
            """)
    List<Provider> findBySpecialtyKeywordAndInsurance(
            @Param("specialtyKeyword") String specialtyKeyword,
            @Param("payerId") String payerId);

    List<Provider> findBySpecialtyCodeAndStateAbbrAndAcceptingNewPatientsTrue(
            String specialtyCode, String stateAbbr);
}