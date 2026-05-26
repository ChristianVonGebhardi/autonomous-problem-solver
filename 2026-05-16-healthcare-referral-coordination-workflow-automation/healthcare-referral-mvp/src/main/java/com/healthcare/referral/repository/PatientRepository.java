package com.healthcare.referral.repository;

import com.healthcare.referral.domain.entity.Patient;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface PatientRepository extends JpaRepository<Patient, Long> {

    Optional<Patient> findByExternalId(String externalId);

    Optional<Patient> findByFhirId(String fhirId);

    Optional<Patient> findByInsuranceMemberId(String insuranceMemberId);

    @Query("SELECT p FROM Patient p WHERE LOWER(p.lastName) = LOWER(:lastName) AND p.dateOfBirth = :dob")
    java.util.List<Patient> findByLastNameAndDob(String lastName, java.time.LocalDate dob);
}