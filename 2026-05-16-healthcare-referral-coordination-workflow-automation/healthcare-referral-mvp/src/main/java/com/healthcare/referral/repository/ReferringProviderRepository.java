package com.healthcare.referral.repository;

import com.healthcare.referral.domain.entity.ReferringProvider;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface ReferringProviderRepository extends JpaRepository<ReferringProvider, Long> {

    Optional<ReferringProvider> findByNpi(String npi);
}